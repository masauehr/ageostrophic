#!/usr/bin/env python
# coding: utf-8
"""
EPSW GRIB2ファイルから300hPa非地衡風・発散場の天気図を生成してPNGで保存する。

使い方:
    python plot_ageostrophic.py <初期時刻> <平均開始予報日> <平均日数>

    <初期時刻>       : YYYYMMDDHH形式（例: 2020032400, 2020032412）
    <平均開始予報日> : 0〜11（FD00〜FD11に対応、FD0=FT0h, FD1=FT24h, ..., FD11=FT264h）
    <平均日数>       : 正整数（1日=FT2本×12h間隔, 最大FT264hでクリップ）

例:
    python plot_ageostrophic.py 2020032400 0 5
        → FD0〜FD4: FT=0,12,24,...,108h（10時刻）を平均

    python plot_ageostrophic.py 2020032412 3 4
        → FD3〜FD6: FT=72,84,...,156h（8時刻）を平均

    python plot_ageostrophic.py 2020032400 8 3
        → FD8〜FD10: FT=192,204,...,252h（6時刻）を平均（FD00-08とFD0812-1100をまたぐ）

ファイル種別と予報時間:
    FD00-08    : FT=0〜192h（12h間隔、17時刻）
    FD0812-1100: FT=204〜264h（12h間隔、6時刻）
"""

import argparse
import os
import sys
import warnings

warnings.filterwarnings("ignore")

# pyprojのPROJデータパスをimport前に設定（met_env_310環境向け）
os.environ.setdefault("PROJ_LIB", "/opt/anaconda3/envs/met_env_310/share/proj")

import numpy as np

try:
    from pyproj import datadir
    datadir.set_data_dir(os.environ["PROJ_LIB"])
except Exception:
    pass

import matplotlib
matplotlib.use("Agg")  # GUI不要（ファイル保存のみ）
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import pygrib
import xarray as xr
import metpy.calc as mpcalc

# --- 設定 ---
DATA_DIR   = os.path.join(os.path.dirname(__file__), "data", "epsw")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
TAG_HP     = 300        # 対象気圧面 (hPa)
LAT_S, LAT_N = -20, 80
LON_W, LON_E = 70, 240

# 各ファイル種別の予報時間範囲（FTはh単位、12h間隔）
FD_RANGES = {
    "FD00-08":     (0,   192, 12),   # FT=0,12,...,192h（17時刻）
    "FD0812-1100": (204, 264, 12),   # FT=204,216,...,264h（6時刻）
}


def get_ft_list(start_day: int, avg_days: int) -> list[int]:
    """
    平均に使う予報時間リスト（12h間隔）を生成する。
    start_day: 開始予報日（0〜11）、1日あたりFT2本（00h・12h）
    avg_days : 平均する日数
    最大FT264h（FD11）でクリップする。
    """
    all_fts = list(range(start_day * 24, (start_day + avg_days) * 24, 12))
    return [ft for ft in all_fts if ft <= 264]


def ft_to_fd_and_index(ft: int) -> tuple[str, int]:
    """予報時間(h)からファイル種別とGRIBメッセージインデックス(0始まり)を返す。"""
    for fd_type, (ft_min, ft_max, step) in FD_RANGES.items():
        if ft_min <= ft <= ft_max and (ft - ft_min) % step == 0:
            return fd_type, (ft - ft_min) // step
    raise ValueError(
        f"対応するファイルが存在しない予報時間です: FT={ft}h\n"
        f"  FD00-08: 0〜192h（12h間隔）\n"
        f"  FD0812-1100: 204〜264h（12h間隔）"
    )


def build_filepath(init_time: str, fd_type: str) -> str:
    """init_time（YYYYMMDDHH）とファイル種別からフルパスを構築する。"""
    fname = f"Z__C_RJTD_{init_time}0000_EPSW_GPV_Rgl_{fd_type}_grib2.bin"
    return os.path.join(DATA_DIR, fname)


def load_averaged_data(init_time: str, ft_list: list[int]) -> dict:
    """
    指定した予報時間リストのGRIBデータを読み込んで平均する。
    FD00-08とFD0812-1100にまたがる場合は両ファイルから読み込む。
    """
    # FT → (ファイル種別, インデックス) に変換し、ファイル別に整理
    fd_requests: dict[str, list[tuple[int, int]]] = {}  # {fd_type: [(ft, idx), ...]}
    for ft in ft_list:
        fd_type, idx = ft_to_fd_and_index(ft)
        fd_requests.setdefault(fd_type, []).append((ft, idx))

    valHt_all, valWu_all, valWv_all = [], [], []
    lat = lon = None

    for fd_type in ["FD00-08", "FD0812-1100"]:  # 時系列順に処理
        if fd_type not in fd_requests:
            continue

        fpath = build_filepath(init_time, fd_type)
        if not os.path.exists(fpath):
            raise FileNotFoundError(f"GRIBファイルが見つかりません: {fpath}")

        grbs   = pygrib.open(fpath)
        gh_all = grbs.select(shortName="gh", typeOfLevel="isobaricInhPa", level=TAG_HP)
        u_all  = grbs.select(shortName="u",  typeOfLevel="isobaricInhPa", level=TAG_HP)
        v_all  = grbs.select(shortName="v",  typeOfLevel="isobaricInhPa", level=TAG_HP)
        grbs.close()

        for ft, idx in sorted(fd_requests[fd_type]):  # FT昇順に処理
            gh, u, v = gh_all[idx], u_all[idx], v_all[idx]
            valHt, latHt, lonHt = gh.data(lat1=LAT_S, lat2=LAT_N, lon1=LON_W, lon2=LON_E)
            valWu, _, _          = u.data( lat1=LAT_S, lat2=LAT_N, lon1=LON_W, lon2=LON_E)
            valWv, _, _          = v.data( lat1=LAT_S, lat2=LAT_N, lon1=LON_W, lon2=LON_E)
            valHt_all.append(valHt)
            valWu_all.append(valWu)
            valWv_all.append(valWv)
            if lat is None:
                lat, lon = latHt[:, 0], lonHt[0, :]
            print(f"    読込: {os.path.basename(build_filepath(init_time, fd_type))} [{fd_type} idx={idx}, FT={ft}h]")

    if not valHt_all:
        raise RuntimeError("読み込めたデータが0件です。")

    return {
        "hgt": np.mean(valHt_all, axis=0),
        "u":   np.mean(valWu_all, axis=0),
        "v":   np.mean(valWv_all, axis=0),
        "lat": lat,
        "lon": lon,
    }


def calc_fields(data: dict) -> "xr.Dataset":
    """MetPyで非地衡風・発散・風速を計算する。"""
    ds = xr.Dataset(
        {
            "Geopotential_height": (["lat", "lon"], data["hgt"]),
            "u_wind":              (["lat", "lon"], data["u"]),
            "v_wind":              (["lat", "lon"], data["v"]),
        },
        coords={"lat": data["lat"], "lon": data["lon"]},
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
    return dsp


def plot_and_save(dsp: "xr.Dataset", output_path: str, title_sub: str):
    """天気図を描画してPNGに保存する。"""
    proj       = ccrs.Stereographic(central_latitude=60, central_longitude=140)
    latlon_proj = ccrs.PlateCarree()

    fig = plt.figure(figsize=(10, 8))
    plt.subplots_adjust(left=0.02, right=0.98, bottom=0.10, top=0.92)
    ax = fig.add_subplot(1, 1, 1, projection=proj)
    ax.set_extent([115, 151, 20, 50], crs=latlon_proj)
    ax.coastlines(resolution="50m")
    ax.gridlines(draw_labels=False)

    # 発散・収束（カラーフィル）
    div    = dsp["divergence"].values * 1e5
    cn_div = ax.contourf(
        dsp["lon"].values, dsp["lat"].values, div,
        levels=[-0.6, -0.4, -0.3, 0.3, 0.4, 0.6],
        cmap="bwr", extend="both",
        transform=latlon_proj, alpha=0.6,
    )
    cb = plt.colorbar(cn_div, orientation="horizontal", pad=0.05)
    cb.set_label("Divergence (*1e-5 1/s)")

    # 等高度線（60m間隔）
    hgt       = dsp["Geopotential_height"].values
    levels_hgt = np.arange(
        np.floor(np.min(hgt) / 60) * 60,
        np.ceil(np.max(hgt) / 60) * 60 + 1,
        60,
    )
    cn_hgt = ax.contour(
        dsp["lon"], dsp["lat"], hgt,
        levels=levels_hgt, colors="black", transform=latlon_proj,
    )
    ax.clabel(cn_hgt, fmt="%.0f", fontsize=9)

    # 等風速線（20kt間隔）
    ws    = dsp["wind_speed"].values
    cn_ws = ax.contour(
        dsp["lon"], dsp["lat"], ws,
        levels=np.arange(40, 140, 20), colors="blue", transform=latlon_proj,
    )
    ax.clabel(cn_ws, fmt="%.0f", fontsize=9, colors="blue")

    # 非地衡風バーブ（NaN/Inf を0に置換して安全化）
    stride = 1
    uag = np.nan_to_num(dsp["uag"].values, nan=0.0, posinf=0.0, neginf=0.0)
    vag = np.nan_to_num(dsp["vag"].values, nan=0.0, posinf=0.0, neginf=0.0)
    ax.barbs(
        dsp["lon"].values[::stride],
        dsp["lat"].values[::stride],
        uag[::stride, ::stride],
        vag[::stride, ::stride],
        length=5.5, pivot="middle", color="black",
        transform=latlon_proj,
    )

    plt.title(
        f"300 hPa: Height, Wind Speed, Divergence, Ageostrophic Wind\n{title_sub}",
        fontsize=12,
    )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  保存: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="EPSW GRIB2から300hPa天気図を生成",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "例:\n"
            "  python plot_ageostrophic.py 2020032400 0 5\n"
            "    → FD0〜FD4: FT=0,12,...,108h（10時刻）を平均\n"
            "  python plot_ageostrophic.py 2020032400 8 3\n"
            "    → FD8〜FD10: FT=192,204,...,252h（6時刻）を平均"
        ),
    )
    parser.add_argument(
        "init_time",
        help="初期時刻（YYYYMMDDHH形式、例: 2020032400）",
    )
    parser.add_argument(
        "start_day",
        type=int,
        metavar="start_day",
        help="平均開始予報日（0〜11、FD00〜FD11に対応）",
    )
    parser.add_argument(
        "avg_days",
        type=int,
        help="平均する日数（正整数、1日=FT2本×12h間隔）",
    )
    args = parser.parse_args()

    # 引数バリデーション
    if len(args.init_time) != 10 or not args.init_time.isdigit():
        parser.error("init_time はYYYYMMDDHH形式（10桁数字）で指定してください。")
    if args.init_time[8:10] not in ("00", "12"):
        parser.error("init_time の時刻部分は 00 または 12 のみ対応しています。")
    if not (0 <= args.start_day <= 11):
        parser.error("start_day は 0〜11 の整数で指定してください。")
    if args.avg_days < 1:
        parser.error("avg_days は1以上の整数を指定してください。")

    ft_list = get_ft_list(args.start_day, args.avg_days)
    if not ft_list:
        print("エラー: 有効な予報時間がありません（start_dayが範囲外の可能性）。", file=sys.stderr)
        sys.exit(1)

    ft_start = ft_list[0]
    ft_end   = ft_list[-1]
    end_day  = args.start_day + args.avg_days - 1

    # 予報時間が有効範囲に収まるか確認
    for ft in ft_list:
        try:
            ft_to_fd_and_index(ft)
        except ValueError as e:
            print(f"エラー: {e}", file=sys.stderr)
            sys.exit(1)

    # 出力ファイル名・タイトル
    output_fname = (
        f"{args.init_time}_FD{args.start_day:02d}-{end_day:02d}"
        f"_avg{args.avg_days}d_{len(ft_list)}steps.png"
    )
    output_path = os.path.join(OUTPUT_DIR, output_fname)
    title_sub = (
        f"Init: {args.init_time[:8]} {args.init_time[8:]}UTC  |  "
        f"FD{args.start_day:02d}–{end_day:02d} (FT={ft_start}–{ft_end}h) avg  "
        f"({len(ft_list)} fcst steps)"
    )

    print(f"初期時刻  : {args.init_time}")
    print(f"平均範囲  : FD{args.start_day:02d}〜FD{end_day:02d}（FT={ft_start}〜{ft_end}h, {len(ft_list)}時刻）")
    print(f"予報時間  : {ft_list}")

    try:
        data = load_averaged_data(args.init_time, ft_list)
        dsp  = calc_fields(data)
        plot_and_save(dsp, output_path, title_sub)
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
