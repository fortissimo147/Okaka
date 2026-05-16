"""
かぶたん (kabutan.jp) の決算ページから発表日を取得してCSVに保存。
横持ち形式: 1行=1社、日付は date_01, date_02, ... 列に追加。

使い方:
  pip install requests beautifulsoup4
  python scripts/scrape_kessan_kabutan.py
  python scripts/scrape_kessan_kabutan.py --codes data/company_names.json --out data/kessan.csv
"""

import argparse
import csv
import json
import sys
import time
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup

DEFAULT_CODES = "data/company_names.json"
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


def load_companies(json_path: str) -> list[dict]:
    """company_names.json からコード・銘柄名リストを返す（4桁数字コードのみ）。"""
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    return [
        {"code": code, "name": name}
        for code, name in data.items()
        if code.isdigit() and len(code) == 4
    ]


def parse_yy_date(s: str) -> str | None:
    """'24/07/25' → '2024-07-25'、変換できなければNone。"""
    s = s.strip()
    m = re.match(r"^(\d{2})/(\d{2})/(\d{2})$", s)
    if not m:
        return None
    yy, mm, dd = m.groups()
    return f"{2000 + int(yy)}-{mm}-{dd}"


def fetch_ann_dates(session: requests.Session, code: str) -> list[str] | None:
    """かぶたんから指定コードの発表日リストを返す。"""
    url = f"https://kabutan.jp/stock/finance?code={code}"
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = session.get(url, headers=HEADERS, timeout=20)
            if resp.status_code == 404:
                return []
            if resp.status_code == 403:
                print(f"    [{code}] 403 blocked", file=sys.stderr)
                return None
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


def load_existing(out_path: str) -> dict[str, dict]:
    """既存の横持ちCSVを {code: {name, dates: set}} で返す。"""
    p = Path(out_path)
    if not p.exists():
        return {}
    result = {}
    with open(p, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            code = row["code"]
            dates = {v for k, v in row.items() if k.startswith("date_") and v}
            result[code] = {"name": row["name"], "dates": dates}
    return result


def write_wide(companies: dict[str, dict], out_path: str):
    """横持ち形式でCSVに書き出す。"""
    max_dates = max((len(d["dates"]) for d in companies.values()), default=0)
    fieldnames = ["code", "name"] + [f"date_{i+1:02d}" for i in range(max_dates)]

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for code in sorted(companies.keys()):
            d = companies[code]
            row = {"code": code, "name": d["name"]}
            for i, date in enumerate(sorted(d["dates"])):
                row[f"date_{i+1:02d}"] = date
            writer.writerow(row)


def scrape(codes_path: str, out_path: str):
    companies_list = load_companies(codes_path)
    print(f"対象企業数: {len(companies_list)}", file=sys.stderr)

    existing = load_existing(out_path)
    print(f"既存レコード数: {len(existing)} 社", file=sys.stderr)

    session = requests.Session()
    added_total = 0
    blocked = 0

    for i, co in enumerate(companies_list):
        code = co["code"]
        name = co["name"]

        dates = fetch_ann_dates(session, code)
        if dates is None:
            blocked += 1
        elif dates:
            entry = existing.setdefault(code, {"name": name, "dates": set()})
            entry["name"] = name
            before = len(entry["dates"])
            entry["dates"].update(dates)
            added = len(entry["dates"]) - before
            added_total += added
            if added:
                print(f"  [{i+1}/{len(companies_list)}] {code} {name}: +{added} 件", file=sys.stderr)

        if blocked > 10:
            print("ブロックが続いています。処理を中断します。", file=sys.stderr)
            sys.exit(1)

        time.sleep(INTERVAL_SEC)

    print(f"\n新規取得: {added_total} 件", file=sys.stderr)

    if added_total == 0:
        print("新しいデータはありませんでした。", file=sys.stderr)
        return

    write_wide(existing, out_path)
    print(f"完了: {len(existing)} 社 -> {out_path}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="かぶたん 決算発表日データ取得（横持ち・増分追加）")
    parser.add_argument("--codes", default=DEFAULT_CODES, help="企業一覧JSON")
    parser.add_argument("--out",   default=DEFAULT_OUT,   help="出力CSVパス")
    args = parser.parse_args()
    scrape(args.codes, args.out)


if __name__ == "__main__":
    main()
