"""
SBI証券の決算カレンダーから発表日・銘柄コード・銘柄名を取得してCSVに保存。
Playwright（ヘッドレスブラウザ）を使用。

使い方:
  pip install playwright beautifulsoup4
  playwright install chromium
  python scripts/scrape_kessan_sbi.py
  python scripts/scrape_kessan_sbi.py --from 2025-10-01 --to 2026-05-07 --out data/kessan.csv
"""

import argparse
import csv
import sys
import time
from datetime import datetime, date, timedelta
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

DEFAULT_FROM = "2025-10-01"
DEFAULT_OUT  = "data/kessan.csv"
PAGE_WAIT_MS = 3000   # ページ読み込み待機（ms）
INTERVAL_SEC = 1.5    # リクエスト間隔（秒）

URL_TEMPLATE = (
    "https://www.sbisec.co.jp/ETGate/"
    "?_ControlID=WPLETmgR001Control"
    "&_PageID=WPLETmgR001Mdtl20"
    "&_DataStoreID=DSWPLETmgR001Control"
    "&_ActionID=DefaultAID"
    "&burl=iris_economicCalendar"
    "&cat1=market"
    "&cat2=economicCalender"
    "&dir=tl1-cal%7Ctl2-schedule%7Ctl3-stock%7Ctl4-calsel%7Ctl9-{ym}%7Ctl10-{ymd}"
    "&file=index.html"
    "&getFlg=on"
)


def build_url(d: date) -> str:
    return URL_TEMPLATE.format(ym=d.strftime("%Y%m"), ymd=d.strftime("%Y%m%d"))


def parse_page(html: str, d: date) -> list[dict]:
    records = []
    date_str = d.strftime("%Y-%m-%d")
    soup = BeautifulSoup(html, "html.parser")

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        headers = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])]

        col_code = col_name = col_ann = -1
        for i, h in enumerate(headers):
            if h in ("コード", "銘柄コード", "証券コード"):
                col_code = i
            elif h in ("銘柄", "銘柄名"):
                col_name = i
            elif "発表" in h or "決算" in h:
                col_ann = i

        if col_code < 0 and col_name < 0:
            continue

        for row in rows[1:]:
            cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
            if len(cells) < 2:
                continue

            code = cells[col_code] if col_code >= 0 and col_code < len(cells) else ""
            name = cells[col_name] if col_name >= 0 and col_name < len(cells) else ""
            ann  = cells[col_ann]  if col_ann  >= 0 and col_ann  < len(cells) else date_str

            if not code and not name:
                continue
            # 4桁数字以外のコードは除外
            if code and not (code.isdigit() and len(code) == 4):
                code = ""

            records.append({"date": ann or date_str, "code": code, "name": name})

    return records


def scrape(from_str: str, to_str: str, out_path: str):
    start = datetime.strptime(from_str, "%Y-%m-%d").date()
    end   = datetime.strptime(to_str,   "%Y-%m-%d").date()
    print(f"取得期間: {start} 〜 {end}（{(end-start).days+1} 日間）", file=sys.stderr)

    all_records: list[dict] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            locale="ja-JP",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = ctx.new_page()

        d = start
        while d <= end:
            url = build_url(d)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(PAGE_WAIT_MS)
                html = page.content()
            except PlaywrightTimeout:
                print(f"  {d}: タイムアウト", file=sys.stderr)
                d += timedelta(days=1)
                time.sleep(INTERVAL_SEC)
                continue
            except Exception as e:
                print(f"  {d}: エラー — {e}", file=sys.stderr)
                d += timedelta(days=1)
                time.sleep(INTERVAL_SEC)
                continue

            records = parse_page(html, d)
            if records:
                all_records.extend(records)
                print(f"  {d}: {len(records)} 件（累計 {len(all_records)} 件）", file=sys.stderr)
            else:
                print(f"  {d}: 0 件（休場日・データなし）", file=sys.stderr)

            d += timedelta(days=1)
            time.sleep(INTERVAL_SEC)

        browser.close()

    if not all_records:
        print("データが取得できませんでした。", file=sys.stderr)
        sys.exit(1)

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "code", "name"])
        writer.writeheader()
        writer.writerows(all_records)

    print(f"\n完了: {len(all_records)} 件 -> {out}", file=sys.stderr)


def main():
    today = date.today().strftime("%Y-%m-%d")
    parser = argparse.ArgumentParser(description="SBI証券 決算カレンダーデータ取得")
    parser.add_argument("--from", dest="from_date", default=DEFAULT_FROM)
    parser.add_argument("--to",   dest="to_date",   default=today)
    parser.add_argument("--out",  default=DEFAULT_OUT)
    args = parser.parse_args()
    scrape(args.from_date, args.to_date, args.out)


if __name__ == "__main__":
    main()
