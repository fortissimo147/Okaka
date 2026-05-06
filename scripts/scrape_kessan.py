"""
irbank.net /td/決算 から各企業の決算日データを取得し CSV に保存するスクリプト。
デフォルトのカットオフ日: 2025-10-01

使い方:
  pip install requests beautifulsoup4
  python scripts/scrape_kessan.py
  python scripts/scrape_kessan.py --cutoff 2025-10-01 --out data/kessan.csv
"""

import argparse
import csv
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://irbank.net/td/%E6%B1%BA%E7%AE%97"
DEFAULT_CUTOFF = "2025-10-01"
DEFAULT_OUT = "data/kessan.csv"
REQUEST_INTERVAL = 1.5  # 秒（サーバー負荷軽減）

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


def fetch_page(session: requests.Session, page: int) -> BeautifulSoup:
    params = {"page": page} if page > 1 else {}
    resp = session.get(BASE_URL, headers=HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def detect_columns(header_cells: list[str]) -> dict:
    """ヘッダー行からカラムインデックスを検出する。"""
    mapping = {}
    for i, cell in enumerate(header_cells):
        text = cell.strip()
        if text in ("コード", "証券コード", "銘柄コード"):
            mapping["code"] = i
        elif text in ("銘柄", "銘柄名", "企業名", "会社名"):
            mapping["name"] = i
        elif "決算" in text and ("日" in text or "月" in text or text == "決算"):
            mapping["date"] = i
        elif text in ("市場", "上場市場"):
            mapping["market"] = i
        elif text in ("業種", "セクター"):
            mapping["sector"] = i
    return mapping


def parse_date(raw: str) -> datetime | None:
    """日付文字列を datetime に変換する（複数フォーマット対応）。"""
    raw = raw.strip().replace("年", "-").replace("月", "-").replace("日", "")
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%m-%d", "%m/%d"):
        try:
            dt = datetime.strptime(raw, fmt)
            if dt.year == 1900:
                dt = dt.replace(year=2025)
            return dt
        except ValueError:
            continue
    return None


def parse_table(soup: BeautifulSoup, col_map: dict | None, cutoff: datetime):
    table = soup.find("table")
    if not table:
        return [], col_map, False

    records = []
    thead = table.find("thead")
    tbody = table.find("tbody") or table

    if col_map is None:
        if thead:
            header_cells = [th.get_text() for th in thead.find_all(["th", "td"])]
        else:
            first_row = tbody.find("tr")
            header_cells = [td.get_text() for td in first_row.find_all(["th", "td"])] if first_row else []
        col_map = detect_columns(header_cells)
        print(f"  検出カラム: {col_map}", file=sys.stderr)

    rows = tbody.find_all("tr")
    for row in rows:
        cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
        if len(cells) < 2:
            continue
        if cells[0].strip() in ("コード", "証券コード", "銘柄コード"):
            continue

        code = cells[col_map["code"]].strip() if "code" in col_map and col_map["code"] < len(cells) else ""
        name = cells[col_map["name"]].strip() if "name" in col_map and col_map["name"] < len(cells) else ""
        date_raw = cells[col_map["date"]].strip() if "date" in col_map and col_map["date"] < len(cells) else ""
        market = cells[col_map.get("market", -1)].strip() if col_map.get("market") is not None and col_map["market"] < len(cells) else ""
        sector = cells[col_map.get("sector", -1)].strip() if col_map.get("sector") is not None and col_map["sector"] < len(cells) else ""

        if not code and not name:
            continue

        dt = parse_date(date_raw)
        if dt is not None and dt > cutoff:
            continue

        records.append({
            "code": code,
            "name": name,
            "kessan_date": date_raw,
            "market": market,
            "sector": sector,
        })

    has_next = False
    for a in soup.find_all("a"):
        text = a.get_text(strip=True)
        href = a.get("href", "")
        if "page=" in href or text in ("次へ", "次", ">", "»", "Next"):
            has_next = True
            break

    return records, col_map, has_next


def scrape(cutoff_str: str, out_path: str):
    cutoff = datetime.strptime(cutoff_str, "%Y-%m-%d")
    print(f"カットオフ日: {cutoff.date()}", file=sys.stderr)

    session = requests.Session()
    all_records = []
    col_map = None
    page = 1

    while True:
        print(f"  ページ {page} 取得中...", file=sys.stderr)
        try:
            soup = fetch_page(session, page)
        except requests.HTTPError as e:
            print(f"  HTTPエラー: {e}", file=sys.stderr)
            break
        except requests.RequestException as e:
            print(f"  接続エラー: {e}", file=sys.stderr)
            break

        records, col_map, has_next = parse_table(soup, col_map, cutoff)

        if not col_map:
            print("  テーブルが見つからないか、カラムマッピングに失敗しました。", file=sys.stderr)
            print(soup.prettify()[:2000], file=sys.stderr)
            break

        all_records.extend(records)
        print(f"    -> {len(records)} 件取得（累計 {len(all_records)} 件）", file=sys.stderr)

        if not has_next:
            break

        page += 1
        time.sleep(REQUEST_INTERVAL)

    if not all_records:
        print("データが取得できませんでした。", file=sys.stderr)
        sys.exit(1)

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["code", "name", "kessan_date", "market", "sector"]
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_records)

    print(f"\n完了: {len(all_records)} 件 -> {out}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="irbank.net 決算日データ取得")
    parser.add_argument("--cutoff", default=DEFAULT_CUTOFF, help="この日付以前のデータのみ取得 (YYYY-MM-DD)")
    parser.add_argument("--out", default=DEFAULT_OUT, help="出力CSVパス")
    args = parser.parse_args()
    scrape(args.cutoff, args.out)


if __name__ == "__main__":
    main()
