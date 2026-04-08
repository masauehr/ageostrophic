#!/usr/bin/env python
# coding: utf-8
"""
京都大学RISHサーバーからEPSW（週間アンサンブル数値予報）GRIB2データをダウンロードする。

使い方:
    python download_epsw.py                     # 最新の利用可能な日付を自動検索
    python download_epsw.py --date 20200324     # 日付を指定
    python download_epsw.py --start 20200320 --end 20200324  # 期間指定
"""

import argparse
import os
import re
import sys
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

# --- 設定 ---
BASE_URL = "http://database.rish.kyoto-u.ac.jp/arch/jmadata/data/gpv/original"
SAVE_DIR = os.path.join(os.path.dirname(__file__), "data", "epsw")
# EPSWアーカイブの既知の最終日付（2020-03-24 以降は廃止）
EPSW_LAST_DATE = datetime(2020, 3, 24)
EPSW_FIRST_DATE = datetime(2019, 1, 1)  # アーカイブ開始の目安
TARGET_PATTERN = re.compile(r"Z__C_RJTD_\d{14}_EPSW_GPV_Rgl_FD(?:00-08|0812-1100)_grib2\.bin")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; EPSW-Downloader/1.0)"}


def list_epsw_files(date: datetime) -> list[str]:
    """指定日のディレクトリにあるEPSW FD00-08ファイル名一覧を返す。"""
    url = f"{BASE_URL}/{date.strftime('%Y/%m/%d')}/"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  ディレクトリ取得失敗 ({url}): {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    files = []
    for link in soup.find_all("a", href=True):
        name = link["href"].strip("/")
        if TARGET_PATTERN.match(name):
            files.append(name)
    return sorted(files)


def download_file(filename: str, date: datetime) -> bool:
    """1ファイルをダウンロードし、data/epsw/ に保存する。既存ならスキップ。"""
    os.makedirs(SAVE_DIR, exist_ok=True)
    dest = os.path.join(SAVE_DIR, filename)

    if os.path.exists(dest):
        size = os.path.getsize(dest)
        print(f"  スキップ（既存）: {filename} ({size / 1024 / 1024:.1f} MB)")
        return True

    url = f"{BASE_URL}/{date.strftime('%Y/%m/%d')}/{filename}"
    print(f"  ダウンロード中: {filename}")
    try:
        with requests.get(url, headers=HEADERS, stream=True, timeout=120) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            downloaded = 0
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = downloaded / total * 100
                        print(f"\r    {pct:.1f}% ({downloaded / 1024 / 1024:.1f} MB)", end="", flush=True)
        print(f"\r  完了: {filename} ({downloaded / 1024 / 1024:.1f} MB)        ")
        return True
    except requests.RequestException as e:
        print(f"\n  ダウンロード失敗: {e}")
        if os.path.exists(dest):
            os.remove(dest)
        return False


def find_latest_date() -> datetime | None:
    """EPSWが存在する最新日付をEPSW_LAST_DATEから遡って探す。"""
    print("最新のEPSW日付を検索中...")
    date = EPSW_LAST_DATE
    for _ in range(30):  # 最大30日遡る
        files = list_epsw_files(date)
        if files:
            print(f"  最新日付: {date.strftime('%Y-%m-%d')} ({len(files)} ファイル)")
            return date
        date -= timedelta(days=1)
    print("  EPSWファイルが見つかりませんでした。")
    return None


def download_date(date: datetime) -> int:
    """指定日のEPSWファイルをすべてダウンロード。ダウンロード数を返す。"""
    print(f"\n--- {date.strftime('%Y-%m-%d')} ---")
    files = list_epsw_files(date)
    if not files:
        print("  EPSWファイルなし")
        return 0
    count = 0
    for f in files:
        if download_file(f, date):
            count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description="京都大学RISHサーバーからEPSWデータをダウンロード")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--date", metavar="YYYYMMDD", help="ダウンロードする日付")
    group.add_argument("--start", metavar="YYYYMMDD", help="開始日（--end と併用）")
    parser.add_argument("--end", metavar="YYYYMMDD", help="終了日（--start と併用）")
    args = parser.parse_args()

    if args.date:
        date = datetime.strptime(args.date, "%Y%m%d")
        download_date(date)

    elif args.start:
        start = datetime.strptime(args.start, "%Y%m%d")
        end = datetime.strptime(args.end, "%Y%m%d") if args.end else EPSW_LAST_DATE
        date = start
        total = 0
        while date <= end:
            total += download_date(date)
            date += timedelta(days=1)
        print(f"\n合計 {total} ファイルをダウンロードしました。")

    else:
        # デフォルト: 最新日付を自動検索してダウンロード
        date = find_latest_date()
        if date:
            download_date(date)


if __name__ == "__main__":
    main()
