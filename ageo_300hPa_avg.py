#!/usr/bin/env python
# coding: utf-8
# 安井壯一郎さんのコードでwarningが出たので少し修正　20250805上原政博
# 引数対応（初期時刻・開始予報日・平均日数）20260408上原政博

# 使い方:
#   python ageo_300hPa_avg.py 2020032400 0000 2
#     → 初期時刻2020-03-24 00UTC, FT=0hから2個（FT=0,12h）平均
#
#   python ageo_300hPa_avg.py 2020032400 0812 4
#     → FT=204hから4個（FT=204,216,228,240h）平均
#        ※FD00-08とFD0812-1100をまたぐ場合も自動判別
#
#   引数:
#     init_time  : 初期時刻YYYYMMDDHH（例: 2020032400, 2020032412）
#     start_ddhh : 平均開始の予報日時（DDHH形式）
#                  DD=00〜11（日）, HH=00または12（時）
#                  例: 0000=FT0h, 0012=FT12h, 0800=FT192h, 0812=FT204h
#     n_steps    : 平均するデータ個数（12h間隔で何個か）
#
# ファイル種別と予報時間:
#   FD00-08    : FT=0〜192h（12h間隔、17時刻）
#   FD0812-1100: FT=204〜264h（12h間隔、6時刻）

import argparse
import os
import sys

# pyprojのPROJデータパスをimport前に設定
os.environ.setdefault("PROJ_LIB", "/opt/anaconda3/envs/met_env_310/share/proj")

from pyproj import datadir, CRS
datadir.set_data_dir(os.environ["PROJ_LIB"])

import requests
import pygrib
import numpy as np
import xarray as xr
import metpy.calc as mpcalc
from metpy.units import units
import matplotlib.pyplot as plt
import cartopy.crs as ccrs

# --- ダウンロード設定 ---
BASE_URL = "http://database.rish.kyoto-u.ac.jp/arch/jmadata/data/gpv/original"
DL_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; EPSW-Downloader/1.0)"}


def ensure_file(file_path: str, filename: str, date_str: str) -> bool:
    """
    ファイルが存在しない場合に京都大学RISHサーバーからダウンロードする。
    date_str: YYYYMMDD形式
    """
    if os.path.exists(file_path):
        return True

    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    url = f"{BASE_URL}/{date_str[:4]}/{date_str[4:6]}/{date_str[6:8]}/{filename}"
    print(f"  ファイルが存在しないためダウンロードします: {filename}")
    print(f"  URL: {url}")
    try:
        with requests.get(url, headers=DL_HEADERS, stream=True, timeout=300) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            downloaded = 0
            with open(file_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = downloaded / total * 100
                        print(f"\r    {pct:.1f}% ({downloaded / 1024 / 1024:.1f} MB)", end="", flush=True)
        print(f"\r  完了: {filename} ({downloaded / 1024 / 1024:.1f} MB)        ")
        return True
    except requests.RequestException as e:
        print(f"\n  ダウンロード失敗: {e}", file=sys.stderr)
        if os.path.exists(file_path):
            os.remove(file_path)
        return False


# --- 引数解析 ---
parser = argparse.ArgumentParser(
    description="EPSW GRIB2から300hPa非地衡風・発散場を描画する",
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog="""
使用例:
  python ageo_300hPa_avg.py 2020032400 0000 2
    → FT=0,12h（2個）平均
  python ageo_300hPa_avg.py 2020032400 0000 10
    → FT=0,12,...,108h（10個）平均
  python ageo_300hPa_avg.py 2020032400 0812 4
    → FT=204,216,228,240h（4個）平均（FD0812-1100）
  python ageo_300hPa_avg.py 2020032400 0800 6
    → FT=192,204,...,252h（6個）平均（両ファイルをまたぐ）
    """,
)
parser.add_argument("init_time",  help="初期時刻（YYYYMMDDHH形式、例: 2020032400）")
parser.add_argument("start_ddhh", help="平均開始予報日時（DDHH形式、例: 0000=FT0h, 0812=FT204h）")
parser.add_argument("n_steps",    type=int, help="平均するデータ個数（12h間隔で何個か）")
args = parser.parse_args()

# 引数の検証
if len(args.init_time) != 10 or not args.init_time.isdigit():
    print("エラー: init_time は YYYYMMDDHH 形式（10桁）で指定してください（例: 2020032400）", file=sys.stderr)
    sys.exit(1)
if args.init_time[8:10] not in ("00", "12"):
    print("エラー: init_time の時刻部分は 00 または 12 のみ対応しています", file=sys.stderr)
    sys.exit(1)
if len(args.start_ddhh) != 4 or not args.start_ddhh.isdigit():
    print("エラー: start_ddhh は DDHH 形式（4桁数字）で指定してください（例: 0000, 0812）", file=sys.stderr)
    sys.exit(1)
start_dd = int(args.start_ddhh[:2])
start_hh = int(args.start_ddhh[2:])
if not (0 <= start_dd <= 11):
    print("エラー: DD は 00〜11 の範囲で指定してください", file=sys.stderr)
    sys.exit(1)
if start_hh not in (0, 12):
    print("エラー: HH は 00 または 12 を指定してください", file=sys.stderr)
    sys.exit(1)
if args.n_steps < 1:
    print("エラー: n_steps は 1 以上を指定してください", file=sys.stderr)
    sys.exit(1)


# --- 予報時間リスト生成 ---
def get_ft_list(start_ft: int, n_steps: int) -> list:
    """平均に使う予報時間リスト（12h間隔）を生成する。"""
    return [start_ft + i * 12 for i in range(n_steps)]

# FD種別とGRIBインデックスへの変換
FD_RANGES = {
    "FD00-08":     (0,   192, 12),
    "FD0812-1100": (204, 264, 12),
}

def ft_to_fd_and_index(ft: int):
    for fd_type, (ft_min, ft_max, step) in FD_RANGES.items():
        if ft_min <= ft <= ft_max and (ft - ft_min) % step == 0:
            return fd_type, (ft - ft_min) // step
    raise ValueError(f"対応するファイルがない予報時間: FT={ft}h")


# --- 設定 ---
tagHp = 300
latS, latN = -20, 80
lonW, lonE = 70, 240

start_ft  = start_dd * 24 + start_hh
ft_list   = get_ft_list(start_ft, args.n_steps)

# FT範囲チェック（最大264h）
over = [ft for ft in ft_list if ft > 264]
if over:
    print(f"エラー: FT264h を超える予報時間が含まれています: {over}", file=sys.stderr)
    sys.exit(1)

ft_start  = ft_list[0]
ft_end    = ft_list[-1]
avg_label = f"FT{ft_start:03d}-{ft_end:03d}h_{args.n_steps}steps_avg"

print(f"初期時刻  : {args.init_time}")
print(f"平均範囲  : FT={ft_start}〜{ft_end}h（{args.n_steps}個, 12h間隔）")
print(f"予報時間  : {ft_list}")


# --- GRIB2ファイル読み込みと平均 ---
data_dir = os.path.join(os.path.dirname(__file__) or ".", "data", "epsw")

# ファイル別にFTをグループ化
fd_requests = {}
for ft in ft_list:
    fd_type, idx = ft_to_fd_and_index(ft)
    fd_requests.setdefault(fd_type, []).append((ft, idx))

valHt_all, valWu_all, valWv_all = [], [], []
latHt = lonHt = None

for fd_type in ["FD00-08", "FD0812-1100"]:
    if fd_type not in fd_requests:
        continue

    fname     = f"Z__C_RJTD_{args.init_time}0000_EPSW_GPV_Rgl_{fd_type}_grib2.bin"
    file_path = os.path.join(data_dir, fname)
    print(f"ファイル : {fname}")

    if not ensure_file(file_path, fname, args.init_time[:8]):
        print(f"エラー: ファイルの取得に失敗しました: {fname}", file=sys.stderr)
        sys.exit(1)

    grbs   = pygrib.open(file_path)
    gh_all = grbs.select(shortName="gh", typeOfLevel="isobaricInhPa", level=tagHp)
    u_all  = grbs.select(shortName="u",  typeOfLevel="isobaricInhPa", level=tagHp)
    v_all  = grbs.select(shortName="v",  typeOfLevel="isobaricInhPa", level=tagHp)
    grbs.close()

    for ft, idx in sorted(fd_requests[fd_type]):
        valHt, lat2d, lon2d = gh_all[idx].data(lat1=latS, lat2=latN, lon1=lonW, lon2=lonE)
        valWu, _, _          = u_all[idx].data( lat1=latS, lat2=latN, lon1=lonW, lon2=lonE)
        valWv, _, _          = v_all[idx].data( lat1=latS, lat2=latN, lon1=lonW, lon2=lonE)
        valHt_all.append(valHt)
        valWu_all.append(valWu)
        valWv_all.append(valWv)
        if latHt is None:
            latHt, lonHt = lat2d, lon2d

valHt_avg = np.mean(valHt_all, axis=0)
valWu_avg = np.mean(valWu_all, axis=0)
valWv_avg = np.mean(valWv_all, axis=0)


# --- データセット作成 & MetPy解析 ---
ds = xr.Dataset(
    {
        "Geopotential_height": (["lat", "lon"], valHt_avg),
        "u_wind":              (["lat", "lon"], valWu_avg),
        "v_wind":              (["lat", "lon"], valWv_avg),
    },
    coords={
        "lat": latHt[:, 0],
        "lon": lonHt[0, :],
    },
)
ds["Geopotential_height"].attrs["units"] = "m"
ds["u_wind"].attrs["units"] = "m/s"
ds["v_wind"].attrs["units"] = "m/s"

dsp = ds.metpy.parse_cf()
dsp["wind_speed"] = mpcalc.wind_speed(dsp["u_wind"], dsp["v_wind"])
dsp["uag"], dsp["vag"] = mpcalc.ageostrophic_wind(
    dsp["Geopotential_height"], dsp["u_wind"], dsp["v_wind"]
)
dsp["divergence"] = mpcalc.divergence(dsp["u_wind"], dsp["v_wind"])


# --- 作図 ---
fig = plt.figure(figsize=(10, 8))
proj = ccrs.Stereographic(central_latitude=60, central_longitude=140)
ax = fig.add_subplot(1, 1, 1, projection=proj)
latlon_proj = ccrs.PlateCarree()

ax.set_extent([115, 151, 20, 50], crs=latlon_proj)
ax.coastlines(resolution="50m")
ax.gridlines(draw_labels=False)

# 発散（カラーマップ）
div = dsp["divergence"].values * 1e5
cn_div = ax.contourf(
    dsp["lon"].values, dsp["lat"].values, div,
    levels=[-0.6, -0.4, -0.3, 0.3, 0.4, 0.6], cmap="bwr", extend="both",
    transform=latlon_proj, alpha=0.6,
)
cb = plt.colorbar(cn_div, orientation="horizontal", pad=0.05)
cb.set_label("Divergence (*1e-5 1/s)")

# 等高度線（60m間隔）
hgt = dsp["Geopotential_height"].values
levels_hgt = np.arange(
    np.floor(np.min(hgt) / 60) * 60,
    np.ceil(np.max(hgt) / 60) * 60 + 1,
    60,
)
cn_hgt = ax.contour(
    dsp["lon"], dsp["lat"], hgt,
    levels=levels_hgt, colors="black", transform=latlon_proj,
)
ax.clabel(cn_hgt, fmt="%.0f", fontsize=10)

# 等風速線（20kt間隔）
ws = dsp["wind_speed"].values
cn_ws = ax.contour(
    dsp["lon"], dsp["lat"], ws,
    levels=np.arange(40, 140, 20), colors="blue", transform=latlon_proj,
)
ax.clabel(cn_ws, fmt="%.0f", fontsize=10, colors="blue")

# 非地衡風バーブ（NaN/Inf を0に置換して安全化）
stride = 1
uag_safe = np.nan_to_num(dsp["uag"].values, nan=0.0, posinf=0.0, neginf=0.0)
vag_safe = np.nan_to_num(dsp["vag"].values, nan=0.0, posinf=0.0, neginf=0.0)
ax.barbs(
    dsp["lon"].values[::stride],
    dsp["lat"].values[::stride],
    uag_safe[::stride, ::stride],
    vag_safe[::stride, ::stride],
    length=5.5, pivot="middle", color="black",
    transform=latlon_proj,
)

# タイトル
title_main = (
    f"300 hPa: Height, Wind Speed, Divergence, Ageostrophic Wind\n"
    f"Init: {args.init_time[:8]} {args.init_time[8:]}UTC  |  "
    f"FT={ft_start}-{ft_end}h avg  ({args.n_steps} fcst steps)"
)
plt.title(title_main, fontsize=12)

# 画像保存
output_dir = os.path.join(os.path.dirname(__file__) or ".", "output")
os.makedirs(output_dir, exist_ok=True)
output_fname = f"{args.init_time}_{avg_label}.png"  # 例: 2020032400_FT192-264h_7steps_avg.png
output_path  = os.path.join(output_dir, output_fname)
plt.savefig(output_path, dpi=150, bbox_inches="tight")
print(f"保存: {output_path}")

plt.show()
