# CLAUDE.md — ageostrophic プロジェクト

## プロジェクト概要

京都大学RISHサーバーからEPSW（週間アンサンブル数値予報）GRIB2データを自動ダウンロードし、
Pythonで気象図（天気図）を自動生成するパイプライン。

---

## ディレクトリ構成

```
ageostrophic/
├── CLAUDE.md               # このファイル
├── README.md               # プロジェクト説明
├── download_epsw.py        # EPSWデータ自動ダウンロードスクリプト
├── plot_ageostrophic.py    # 非地衡風・高度場・発散の図を生成
├── run_pipeline.sh         # ダウンロード→作図 一括実行スクリプト
├── data/
│   └── epsw/              # ダウンロードしたGRIB2ファイル置き場
├── output/                 # 生成した画像の出力先（PNG）
├── ageostrophic_300hPa_avg_00-08h.ipynb   # 開発用ノートブック
└── ageostrophic_300hPa_avg_00-08h.py      # ノートブックから変換したスクリプト
```

---

## データソース

| 項目 | 内容 |
|------|------|
| サーバー | 京都大学 生存圏研究所（RISH）|
| ベースURL | `http://database.rish.kyoto-u.ac.jp/arch/jmadata/data/gpv/original/` |
| パス形式 | `YYYY/MM/DD/` |
| 対象ファイル | `Z__C_RJTD_YYYYMMDD{HH}0000_EPSW_GPV_Rgl_FD00-08_grib2.bin` |
| 初期時刻 | 00UTC・12UTC の2回/日 |
| **注意** | EPSWデータのアーカイブは **2020年3月24日が最新**（それ以降は廃止） |
| ファイルサイズ | 約145MB/ファイル |

### EPSWファイルの種類（1日あたり8ファイル）

| ファイル名パターン | 内容 |
|---|---|
| `*_EPSW_GPV_Rgl_FD00-08_grib2.bin` | 全球域 FT00-08h |
| `*_EPSW_GPV_Rgl_FD0812-1100_grib2.bin` | 全球域 FT08-11d |
| `*_EPSW_GPV_Rjp_FD00-08_grib2.bin` | 日本域 FT00-08h |
| `*_EPSW_GPV_Rjp_FD0806-1100_grib2.bin` | 日本域 FT08-11d |

---

## 主要スクリプトの役割

### `download_epsw.py`
- 京都大学RISHサーバーのディレクトリを走査してEPSWファイルを検索
- 指定日付（または最新日付）のファイルを `data/epsw/` にダウンロード
- 既存ファイルはスキップ（再ダウンロード不要）
- `requests` ライブラリを使用（conda: `met_env_310`）

### `plot_ageostrophic.py`
- `data/epsw/` 内のGRIB2ファイルを読み込み
- 300hPa 高度場・風速・収束発散・非地衡風を描画
- `output/` にPNG形式で保存
- 使用ライブラリ: `pygrib`, `xarray`, `metpy`, `matplotlib`, `cartopy`

### `run_pipeline.sh`
- `download_epsw.py` → `plot_ageostrophic.py` を順に実行
- cron等での定期実行を想定

---

## 実行環境

```bash
conda activate met_env_310
python download_epsw.py
python plot_ageostrophic.py
```

または一括実行:

```bash
bash run_pipeline.sh
```

---

## 描画内容（300hPa面）

| 要素 | 表現方法 |
|------|---------|
| ジオポテンシャル高度 | 黒実線（等高度線、60m間隔） |
| 風速 | 青実線（等風速線、20kt間隔） |
| 収束・発散 | カラーフィル（bwr、赤=発散・青=収束） |
| 非地衡風 | バーブ（矢羽根） |

- 図法: 極射影（Stereographic、中心: 60°N / 140°E）
- 対象領域: 日本付近（115–151°E, 20–50°N）
- 平均化: 初期値～08時間後（8時刻平均）

---

## 注意事項

- `pygrib` は `met_env_310` または `met_env` 環境にのみインストール済み
- 生成画像は `output/` に保存し、Git管理から除外すること（`.gitignore` 推奨）
- `data/epsw/` の大容量ファイルもGit管理から除外すること
- HTTP接続時は `User-Agent` ヘッダーの付与が必要（接続リセット対策）

---

## 開発履歴

- 2020年3月24日データを `requests` + `pygrib` で処理することを確認済み
- ノートブック (`ageostrophic_300hPa_avg_00-08h.ipynb`) を `.py` に変換済み
