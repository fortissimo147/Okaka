#!/bin/bash
# 毎週金曜日: SBI約定履歴CSVをupload/に追加してからこのスクリプトを実行する
set -e
cd "$(dirname "$0")"

echo "=== CSVをマージ中 ==="
uv run python -m scripts.merge_csv

echo ""
echo "=== Gitにコミット&プッシュ ==="
git add upload/merged.csv
git add upload/*.csv 2>/dev/null || true
git commit -m "weekly trade data update ($(date +%Y-%m-%d))"
git push -u origin "$(git branch --show-current)"

echo ""
echo "完了。trading.html に反映されます。"
