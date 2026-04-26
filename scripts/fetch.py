"""
毎朝8時にcronから実行する。
https://inav.ice.com/pcf-download/listOfZips で利用可能な最新ZIPの日付を確認し、
当日の日付と一致していればZIPをダウンロードして2083のCSVを取り出しSQLiteに格納、
ダッシュボードを再生成する。

使い方:
  uv run python -m scripts.fetch

cron例 (毎朝8時):
  0 8 * * * cd /path/to/projects/kimura && uv run python -m scripts.fetch >> logs/fetch.log 2>&1
"""
import io
import re
import sys
import zipfile
from datetime import date, datetime
from pathlib import Path

import requests

from scripts.db import get_conn, init_db
from scripts.parse import parse_csv
from scripts.build_dashboard import build

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"
LIST_URL = "https://inav.ice.com/pcf-download/listOfZips"
ZIP_URL_TEMPLATE = "https://inav.ice.com/pcf-download/all/all_pcf_{date}.zip"
ETF_CODE = "2083"


def get_latest_available_date() -> date | None:
    """listOfZips から最新の利用可能日付を返す。"""
    resp = requests.get(LIST_URL, timeout=15)
    resp.raise_for_status()
    dates = re.findall(r"all_pcf_(\d{8})\.zip", resp.text)
    if not dates:
        return None
    latest = max(dates)
    return date(int(latest[:4]), int(latest[4:6]), int(latest[6:]))


def fetch_csv(target_date: date) -> Path:
    """ZIPをダウンロードして2083のCSVをdata/raw/に保存し、パスを返す。"""
    url = ZIP_URL_TEMPLATE.format(date=target_date.strftime("%Y%m%d"))
    print(f"  ダウンロード: {url}")
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        matched = [f for f in z.namelist() if f.startswith(ETF_CODE)]
        if not matched:
            raise FileNotFoundError(f"ZIP内に {ETF_CODE} のファイルが見つかりません")
        csv_name = matched[0]
        csv_bytes = z.read(csv_name)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    dest = RAW_DIR / f"{ETF_CODE}_{target_date.strftime('%Y%m%d')}.csv"
    dest.write_bytes(csv_bytes)
    print(f"  保存: {dest.name} (元ファイル名: {csv_name})")
    return dest


def main():
    today = date.today()
    print(f"[{datetime.now().isoformat()}] fetch 開始 — {today}")

    print(f"  利用可能な最新日付を確認中...")
    try:
        latest = get_latest_available_date()
    except Exception as e:
        print(f"  ERROR: listOfZips 取得失敗 — {e}")
        sys.exit(1)

    print(f"  最新利用可能日: {latest}")
    if latest != today:
        print(f"  {today} のデータはまだ公開されていないためスキップ")
        sys.exit(0)

    try:
        filepath = fetch_csv(today)
    except Exception as e:
        print(f"  ERROR: ダウンロード失敗 — {e}")
        sys.exit(1)

    try:
        fund_date, df = parse_csv(filepath)
    except Exception as e:
        print(f"  ERROR: パース失敗 — {e}")
        sys.exit(1)

    init_db()
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT COUNT(*) FROM holdings WHERE date = ?", (fund_date,)
        ).fetchone()[0]
        if existing > 0:
            print(f"  SKIP: {fund_date} のデータはすでに存在します")
        else:
            rows = [
                (fund_date, row.ticker, row.name, row.shares, row.price, row.value, row.ratio)
                for row in df.itertuples(index=False)
            ]
            conn.executemany(
                "INSERT INTO holdings (date, ticker, name, shares, price, value, ratio) VALUES (?,?,?,?,?,?,?)",
                rows,
            )
            print(f"  INSERT: {fund_date} — {len(rows)} 銘柄")

    print("  ダッシュボード再生成...")
    build()
    print("  完了")


if __name__ == "__main__":
    main()
