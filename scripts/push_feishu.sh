#!/usr/bin/env bash
# 手动触发飞书日报推送
# 用法：
#   ./scripts/push_feishu.sh              # 推送 assets/data/latest.json
#   ./scripts/push_feishu.sh --alert      # 发送告警测试卡片
#   ./scripts/push_feishu.sh --dry-run    # 只打印卡片内容，不发送
#   ./scripts/push_feishu.sh --data assets/data/latest_full.json

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PYTHON="${PROJECT_ROOT}/.venv/bin/python"
if [[ ! -x "${PYTHON}" ]]; then
    echo "错误：未找到 ${PYTHON}，请先运行 uv sync 创建虚拟环境"
    exit 1
fi

export PYTHONPATH="${PROJECT_ROOT}/src"

exec "${PYTHON}" -m src.tools.feishu_pusher "$@"
