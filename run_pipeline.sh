#!/bin/bash
# ============================================================
# EPSW 自動ダウンロード & 天気図生成パイプライン
#
# 使い方:
#   bash run_pipeline.sh                      # 最新データを自動取得して作図
#   bash run_pipeline.sh --date 20200324      # 日付指定
#   bash run_pipeline.sh --start 20200320 --end 20200324  # 期間指定
# ============================================================

set -e  # エラー時に即終了

# スクリプトのディレクトリに移動
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# conda 環境名
CONDA_ENV="met_env_310"

# --- conda の初期化 ---
if [ -f "/opt/anaconda3/etc/profile.d/conda.sh" ]; then
    source /opt/anaconda3/etc/profile.d/conda.sh
elif [ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]; then
    source "$HOME/anaconda3/etc/profile.d/conda.sh"
elif [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
else
    echo "[ERROR] conda が見つかりません。パスを確認してください。"
    exit 1
fi

conda activate "$CONDA_ENV"
echo "[INFO] 環境: $(conda info --envs | grep '*' | awk '{print $1}')"
echo "[INFO] Python: $(python --version)"
echo ""

# --- ステップ1: ダウンロード ---
echo "=========================================="
echo " ステップ1: EPSWデータのダウンロード"
echo "=========================================="
python download_epsw.py "$@"

# --- ステップ2: 作図 ---
echo ""
echo "=========================================="
echo " ステップ2: 天気図の生成"
echo "=========================================="
python plot_ageostrophic.py

echo ""
echo "=========================================="
echo " パイプライン完了"
echo " 出力先: $SCRIPT_DIR/output/"
echo "=========================================="
