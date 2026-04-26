#!/bin/bash
set -e
cd "$(dirname "$0")"
uv run python -m scripts.fetch
echo ""
echo "etf_dashboard.html を更新しました。code-server から Download してください。"
