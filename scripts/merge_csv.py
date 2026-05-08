"""
upload/ フォルダ内のSBI証券約定履歴CSVを全て読み込み、
約定日順に連結して upload/merged.csv に出力する。

使い方:
  uv run python -m scripts.merge_csv
"""

import csv
import glob
import io
import os
import sys

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "upload")
OUTPUT_FILE = os.path.join(UPLOAD_DIR, "merged.csv")
ENCODING = "cp932"
HEADER_START = "約定日"

EXPECTED_COLS = [
    "約定日", "銘柄", "銘柄コード", "市場", "取引", "期限",
    "預り", "課税", "約定数量", "約定単価", "手数料/諸経費等",
    "税額", "受渡日", "受渡金額/決済損益",
]


def parse_file(path: str) -> list[list[str]]:
    with open(path, "rb") as f:
        raw = f.read()
    text = raw.decode(ENCODING)
    lines = text.splitlines()

    header_idx = None
    for i, line in enumerate(lines):
        if line.startswith(HEADER_START):
            header_idx = i
            break

    if header_idx is None:
        print(f"  [skip] ヘッダー行が見つかりません: {path}", file=sys.stderr)
        return []

    reader = csv.reader(io.StringIO("\n".join(lines[header_idx:])))
    rows = list(reader)
    if not rows:
        return []

    if rows[0] != EXPECTED_COLS:
        print(f"  [warn] 列が想定外: {path}", file=sys.stderr)

    data_rows = [
        row for row in rows[1:]
        if row and row[0].strip() and len(row) > 4 and "信用" in row[4]
    ]
    return data_rows


def merge():
    pattern = os.path.join(UPLOAD_DIR, "*.csv")
    files = sorted(
        f for f in glob.glob(pattern)
        if os.path.basename(f) != "merged.csv"
    )

    if not files:
        print("upload/ にCSVファイルが見つかりません。")
        sys.exit(1)

    print(f"{len(files)} ファイルを処理中...")
    all_rows = []

    for path in files:
        rows = parse_file(path)
        if all_rows:
            last_date = all_rows[-1][0]
            before = len(rows)
            rows = [r for r in rows if r[0] != last_date]
            skipped = before - len(rows)
            skip_note = f"  ※ {last_date} の {skipped} 件をスキップ" if skipped else ""
        else:
            skip_note = ""
        print(f"  読み込み: {os.path.basename(path)}  ({len(rows)} 件){skip_note}")
        all_rows.extend(rows)

    all_rows.sort(key=lambda r: r[0])

    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(EXPECTED_COLS)
    writer.writerows(all_rows)

    with open(OUTPUT_FILE, "wb") as f:
        f.write(output.getvalue().encode(ENCODING))

    print(f"\n完了: {len(all_rows)} 件 → {OUTPUT_FILE}")


if __name__ == "__main__":
    merge()
