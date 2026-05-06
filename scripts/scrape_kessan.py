"""
irbank.net /market/kessan?y=YYYY-MM-DD から日付ごとの決算企業データを取得し CSV に保存。

使い方:
  pip install requests beautifulsoup4
  python scripts/scrape_kessan.py
  python scripts/scrape_kessan.py --from 2025-10-01 --to 2026-05-06 --out data/kessan.csv
"""

import argparse
import csv
import sys
import time
from datetime import datetime, date, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://irbank.net/market/kessan"
DEFAULT_FROM = "2025-10-01"
DEFAULT_OUT  = "data/kessan.csv"
REQUEST_INTERVAL = 1.0  # 秒

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Referer": "https://irbank.net/",
}


def fetch_day(session: requests.Session, d: date) -> BeautifulSoup | None:
    try:
        resp = session.get(
            BASE_URL,
            headers=HEADERS,
            params={"y": d.strftime("%Y-%m-%d")},
            timeout=30,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        return BeautifulSoup(resp.text, "html.parser")
    except requests.RequestException as e:
        print(f"    エラー ({d}): {e}", file=sys.stderr)
        return None


def parse_day(soup: BeautifulSoup, d: date) -> list[dict]:
    records = []
    date_str = d.strftime("%Y-%m-%d")

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue

        # ヘッダー行からカラムを検出
        header_cells = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])]
        col = {}
        for i, h in enumerate(header_cells):
            if h in ("コード", "証券コード", "銘柄コード"):
                col["code"] = i
            elif h in ("銘柄", "銘柄名", "企業名", "会社名"):
                col["name"] = i
            elif "市場" in h:
                col["market"] = i
            elif "業種" in h:
                col["sector"] = i
            elif "決算" in h:
                col["kessan"] = i

        # カラムが検出できなければ位置推定（コード=0, 銘柄名=1 が多い）
        if "code" not in col and len(header_cells) >= 2:
            col.setdefault("code", 0)
            col.setdefault("name", 1)

        for row in rows[1:]:
            cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
            if len(cells) < 2:
                continue

            code   = cells[col["code"]]  if "code"   in col and col["code"]   < len(cells) else ""
            name   = cells[col["name"]]  if "name"   in col and col["name"]   < len(cells) else ""
            market = cells[col["market"]]if "market" in col and col["market"] < len(cells) else ""
            sector = cells[col["sector"]]if "sector" in col and col["sector"] < len(cells) else ""
            kessan = cells[col["kessan"]]if "kessan" in col and col["kessan"] < len(cells) else ""

            if not code and not name:
                continue

            records.append({
                "date":   date_str,
                "code":   code,
                "name":   name,
                "market": market,
                "sector": sector,
                "kessan": kessan,
            })

    return records


def scrape(from_str: str, to_str: str, out_path: str):
    start = datetime.strptime(from_str, "%Y-%m-%d").date()
    end   = datetime.strptime(to_str,   "%Y-%m-%d").date()
    total_days = (end - start).days + 1
    print(f"取得期間: {start} 〜 {end}（{total_days} 日間）", file=sys.stderr)

    session = requests.Session()
    all_records: list[dict] = []
    empty_days = 0

    d = start
    while d <= end:
        soup = fetch_day(session, d)
        if soup is None:
            d += timedelta(days=1)
            time.sleep(REQUEST_INTERVAL)
            continue

        records = parse_day(soup, d)
        if records:
            all_records.extend(records)
            print(f"  {d}: {len(records)} 件（累計 {len(all_records)} 件）", file=sys.stderr)
            empty_days = 0
        else:
            empty_days += 1
            if empty_days <= 3:
                print(f"  {d}: 0 件（休場日・データなし）", file=sys.stderr)

        d += timedelta(days=1)
        time.sleep(REQUEST_INTERVAL)

    if not all_records:
        print("データが取得できませんでした。", file=sys.stderr)
        sys.exit(1)

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["date", "code", "name", "market", "sector", "kessan"]
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_records)

    print(f"\n完了: {len(all_records)} 件 -> {out}", file=sys.stderr)


def main():
    today = date.today().strftime("%Y-%m-%d")
    parser = argparse.ArgumentParser(description="irbank.net 決算企業データ取得")
    parser.add_argument("--from", dest="from_date", default=DEFAULT_FROM,
                        help="取得開始日 (YYYY-MM-DD, デフォルト: 2025-10-01)")
    parser.add_argument("--to",   dest="to_date",   default=today,
                        help=f"取得終了日 (YYYY-MM-DD, デフォルト: 本日 {today})")
    parser.add_argument("--out",  default=DEFAULT_OUT, help="出力CSVパス")
    args = parser.parse_args()
    scrape(args.from_date, args.to_date, args.out)


if __name__ == "__main__":
    main()
