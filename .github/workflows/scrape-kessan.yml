"""
かぶたん (kabutan.jp) の決算ページから発表日を取得してCSVに保存。

使い方:
  pip install requests beautifulsoup4
  python scripts/scrape_kessan_kabutan.py
  python scripts/scrape_kessan_kabutan.py --codes data/companies.csv --out data/kessan.csv
"""

import argparse
import csv
import sys
import time
import re
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

DEFAULT_CODES = "data/companies.csv"
DEFAULT_OUT   = "data/kessan.csv"
INTERVAL_SEC  = 0.8
MAX_RETRIES   = 2

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": "https://kabutan.jp/",
}


def load_companies(csv_path: str) -> list[dict]:
    """companies.csv からコード・銘柄名リストを返す（ETF等を除く）。"""
    companies = []
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = row.get("コード", "").strip()
            name = row.get("銘柄名", "").strip()
            market = row.get("市場・商品区分", "").strip()
            # 4桁数字コードのみ対象
            if not (code.isdigit() and len(code) == 4):
                continue
            companies.append({"code": code, "name": name, "market": market})
    return companies


def parse_yy_date(s: str) -> str | None:
    """'24/07/25' → '2024-07-25'、変換できなければNone。"""
    s = s.strip()
    m = re.match(r"^(\d{2})/(\d{2})/(\d{2})$", s)
    if not m:
        return None
    yy, mm, dd = m.groups()
    year = 2000 + int(yy)
    return f"{year}-{mm}-{dd}"


def fetch_ann_dates(session: requests.Session, code: str) -> list[str]:
    """かぶたんから指定コードの発表日リストを返す。"""
    url = f"https://kabutan.jp/stock/finance?code={code}"
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = session.get(url, headers=HEADERS, timeout=20)
            if resp.status_code == 404:
                return []
            if resp.status_code == 403:
                print(f"    [{code}] 403 blocked", file=sys.stderr)
                return []
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            break
        except requests.RequestException as e:
            if attempt == MAX_RETRIES:
                print(f"    [{code}] エラー: {e}", file=sys.stderr)
                return []
            time.sleep(2)

    soup = BeautifulSoup(resp.text, "html.parser")
    dates = []

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        headers = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])]
        if "発表日" not in headers:
            continue
        ann_idx = headers.index("発表日")
        for row in rows[1:]:
            cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
            if ann_idx < len(cells):
                d = parse_yy_date(cells[ann_idx])
                if d and d not in dates:
                    dates.append(d)

    return dates


def scrape(codes_path: str, out_path: str):
    companies = load_companies(codes_path)
    print(f"対象企業数: {len(companies)}", file=sys.stderr)

    session = requests.Session()
    all_records: list[dict] = []
    blocked = 0

    for i, co in enumerate(companies):
        code = co["code"]
        name = co["name"]

        dates = fetch_ann_dates(session, code)
        if dates:
            for d in dates:
                all_records.append({"date": d, "code": code, "name": name})
            print(f"  [{i+1}/{len(companies)}] {code} {name}: {len(dates)} 件", file=sys.stderr)
        else:
            # ETF等は発表日なしが正常
            pass

        if blocked > 10:
            print("ブロックが続いています。処理を中断します。", file=sys.stderr)
            sys.exit(1)

        time.sleep(INTERVAL_SEC)

    if not all_records:
        print("データが取得できませんでした。", file=sys.stderr)
        sys.exit(1)

    # 日付昇順でソート
    all_records.sort(key=lambda r: (r["date"], r["code"]))

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "code", "name"])
        writer.writeheader()
        writer.writerows(all_records)

    print(f"\n完了: {len(all_records)} 件 -> {out}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="かぶたん 決算発表日データ取得")
    parser.add_argument("--codes", default=DEFAULT_CODES, help="企業一覧CSV（companies.csv）")
    parser.add_argument("--out",   default=DEFAULT_OUT,   help="出力CSVパス")
    args = parser.parse_args()
    scrape(args.codes, args.out)


if __name__ == "__main__":
    main()
