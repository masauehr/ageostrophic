# EPSW 非地衡風天気図 自動生成パイプライン

京都大学RISHサーバーからEPSW（週間アンサンブル数値予報）GRIB2データを自動ダウンロードし、
300hPa 非地衡風・発散場の天気図をPythonで生成するパイプライン。

---

## 機能概要

| スクリプト | 役割 |
|---|---|
| `download_epsw.py` | 京都大学RISHサーバーからGRIB2データをダウンロード |
| `ageo_300hPa_avg.py` | 任意の予報時間範囲を指定して天気図を生成（データがなければ自動ダウンロード） |
| `plot_ageostrophic.py` | 同上（バッチ処理向け） |
| `run_pipeline.sh` | ダウンロード→作図の一括実行 |

---

## セットアップ

```bash
conda activate met_env_310
```

必要ライブラリ（`met_env_310` 環境に含まれる）:

| ライブラリ | 用途 |
|---|---|
| `pygrib` | GRIB2ファイル読み込み |
| `xarray` | データセット操作 |
| `metpy` | 気象計算（非地衡風・発散） |
| `matplotlib` / `cartopy` | 描画・地図投影 |
| `requests` / `beautifulsoup4` | サーバーからのダウンロード |

---

## データについて

| 項目 | 内容 |
|---|---|
| 提供元 | 京都大学 生存圏研究所（RISH）|
| ベースURL | `http://database.rish.kyoto-u.ac.jp/arch/jmadata/data/gpv/original/` |
| アーカイブ期間 | ～2020年3月24日（以降廃止） |

### ファイル種別と予報時間

| ファイル種別 | 予報時間 | 間隔 | 時刻数 |
|---|---|---|---|
| `*_EPSW_GPV_Rgl_FD00-08_grib2.bin` | FT=0〜192h | 12h | 17 |
| `*_EPSW_GPV_Rgl_FD0812-1100_grib2.bin` | FT=204〜264h | 12h | 6 |

- 初期時刻: 00UTC・12UTC の1日2回
- ファイルサイズ: FD00-08 約145MB、FD0812-1100 約52MB

---

## 使い方

### 1. データのみダウンロード（`download_epsw.py`）

```bash
# 最新データを自動検索してダウンロード
python download_epsw.py

# 日付を指定
python download_epsw.py --date 20200324

# 期間を指定
python download_epsw.py --start 20200320 --end 20200324
```

### 2. 天気図生成（`ageo_300hPa_avg.py`）

データが存在しない場合は**自動的にダウンロード**してから作図します。

```bash
python ageo_300hPa_avg.py <初期時刻> <開始予報日時> <データ個数>
```

| 引数 | 形式 | 説明 |
|---|---|---|
| `初期時刻` | `YYYYMMDDHH` | 予報モデルの初期時刻（HHは00または12） |
| `開始予報日時` | `DDHH` | 平均開始の予報日時（DD=00〜11日、HH=00または12時間） |
| `データ個数` | 正整数 | 12h間隔で何個のデータを平均するか |

#### 引数の変換例

| `DDHH` 指定 | 対応するFT |
|---|---|
| `0000` | FT=0h（初期値） |
| `0012` | FT=12h |
| `0100` | FT=24h（1日後） |
| `0800` | FT=192h（8日後） |
| `0812` | FT=204h（8日12時間後） |
| `1100` | FT=264h（11日後・最終） |

#### 実行例

```bash
# 初期時刻2020-03-24 00UTC、FT=0hから2個（FT=0,12h）平均
python ageo_300hPa_avg.py 2020032400 0000 2

# FT=0hから10個（FT=0,12,...,108h）平均
python ageo_300hPa_avg.py 2020032400 0000 10

# FT=204hから4個（FT=204,216,228,240h）平均
python ageo_300hPa_avg.py 2020032400 0812 4

# FT=192hから7個（FT=192〜264h）→ FD00-08とFD0812-1100をまたぐ
python ageo_300hPa_avg.py 2020032400 0800 7
```

### 3. 一括実行（ダウンロード→作図）

```bash
bash run_pipeline.sh
```

---

## 描画内容（300hPa面）

| 要素 | 表現 |
|---|---|
| ジオポテンシャル高度 | 黒実線（60m間隔） |
| 風速 | 青実線（20kt間隔） |
| 収束・発散 | カラーフィル（赤=発散・青=収束、単位: ×10⁻⁵ s⁻¹） |
| 非地衡風 | バーブ（矢羽根） |

- 図法: 極射影（Stereographic、中心: 60°N / 140°E）
- 表示領域: 115–151°E, 20–50°N

---

## ディレクトリ構成

```
ageostrophic/
├── download_epsw.py            # EPSWデータダウンロード
├── ageo_300hPa_avg.py          # 天気図生成（引数で予報時間・個数を指定）
├── plot_ageostrophic.py        # 天気図生成（バッチ処理向け）
├── run_pipeline.sh             # ダウンロード→作図 一括実行
├── data/
│   └── epsw/                  # GRIB2ファイル置き場（Git管理外）
└── output/                    # 生成PNG置き場（Git管理外）
```

---

## 注意事項

- `data/epsw/` の大容量ファイルはGit管理外（`.gitignore` で除外）
- `output/` の画像もGit管理外
- `pygrib` は `met_env_310` 環境にのみインストール済み
- EPSWアーカイブは2020年3月24日が最終日（それ以降のデータは存在しない）
