"""
irbank.net /td/決算 から決算開示データを取得し CSV に保存するスクリプト。
カーソルベースのページネーション（?y=...&pg=true&f=...）に対応。

使い方:
  pip install requests beautifulsoup4
  python scripts/scrape_kessan.py
  python scripts/scrape_kessan.py --cutoff 2025-10-01 --out data/kessan.csv
"""

import argparse
import csv
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://irbank.net/td/%E6%B1%BA%E7%AE%97"
DEFAULT_CUTOFF = "2025-10-01"
DEFAULT_OUT = "data/kessan.csv"
REQUEST_INTERVAL = 1.5  # 秒（サーバー負荷軽減）
JST = timezone(timedelta(hours=9))

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


def fetch(session: requests.Session, url: str, params: dict | None = None) -> BeautifulSoup:
    resp = session.get(url, headers=HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def extract_date_from_page(soup: BeautifulSoup) -> str | None:
    """ページタイトルや見出しから日付を抽出する。"""
    for tag in soup.find_all(["h1", "h2", "h3", "title", "p"]):
        text = tag.get_text(strip=True)
        m = re.search(r"(\d{4})[年/\-](\d{1,2})[月/\-](\d{1,2})", text)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return None


def parse_rows(soup: BeautifulSoup, current_date: str | None) -> tuple[list[dict], str | None, dict | None]:
    """
    テーブル行をパースして返す。
    戻り値: (records, last_seen_date, next_params)
      next_params: {"y": ..., "pg": "true", "f": ...} または None
    """
    records = []
    last_date = current_date

    # --- 日付見出しとテーブル行を順に処理 ---
    # irbank は日付ヘッダー → 開示リスト の繰り返し構造
    for elem in soup.find_all(["h2", "h3", "h4", "tr", "li", "div"]):
        text = elem.get_text(strip=True)

        # 日付見出しを検出
        m = re.search(r"(\d{4})[年/\-](\d{1,2})[月/\-](\d{1,2})", text)
        if m and len(text) < 30:
            last_date = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
            continue

        # テーブル行
        if elem.name == "tr":
            cells = [td.get_text(strip=True) for td in elem.find_all(["td", "th"])]
            if len(cells) < 3:
                continue
            # ヘッダー行スキップ
            if cells[0] in ("時刻", "時間", "コード"):
                continue

            # セル構造: [時刻, コード, 企業名, タイトル] or [コード, 企業名, タイトル]
            if re.match(r"^\d{1,2}:\d{2}$", cells[0]):
                time_str, code, name, title = cells[0], cells[1] if len(cells) > 1 else "", cells[2] if len(cells) > 2 else "", cells[3] if len(cells) > 3 else ""
            else:
                time_str, code, name, title = "", cells[0], cells[1] if len(cells) > 1 else "", cells[2] if len(cells) > 2 else ""

            if not code or not name:
                continue

            records.append({
                "date": last_date or "",
                "time": time_str,
                "code": code,
                "name": name,
                "title": title,
            })

    # --- 「More」ボタン / リンクから次ページパラメータを抽出 ---
    next_params = None
    for a in soup.find_all("a"):
        href = a.get("href", "")
        if "pg=true" in href and "f=" in href:
            parsed = urlparse(href)
            qs = parse_qs(parsed.query)
            next_params = {
                "y":  qs.get("y", [""])[0],
                "pg": "true",
                "f":  qs.get("f", [""])[0],
            }
            break

    # ボタン要素（onclick / data 属性）でも探す
    if not next_params:
        for btn in soup.find_all(["button", "a", "span"]):
            onclick = btn.get("onclick", "") or btn.get("data-url", "") or btn.get("data-href", "")
            if "pg=true" in onclick and "f=" in onclick:
                m = re.search(r"[?&]y=(\d+).*?[?&]f=(\w+)", onclick)
                if m:
                    next_params = {"y": m.group(1), "pg": "true", "f": m.group(2)}
                    break

    return records, last_date, next_params


def scrape(cutoff_str: str, out_path: str):
    cutoff = datetime.strptime(cutoff_str, "%Y-%m-%d").date()
    print(f"カットオフ日: {cutoff}", file=sys.stderr)

    session = requests.Session()
    all_records = []
    current_date = None
    next_params = None
    page = 1

    while True:
        print(f"  ページ {page} 取得中... params={next_params}", file=sys.stderr)
        try:
            soup = fetch(session, BASE_URL, params=next_params)
        except requests.HTTPError as e:
            print(f"  HTTPエラー: {e}", file=sys.stderr)
            break
        except requests.RequestException as e:
            print(f"  接続エラー: {e}", file=sys.stderr)
            break

        records, current_date, next_params = parse_rows(soup, current_date)

        # カットオフ日チェック
        filtered = []
        stop = False
        for r in records:
            if r["date"]:
                try:
                    row_date = datetime.strptime(r["date"], "%Y-%m-%d").date()
                    if row_date <= cutoff:
                        filtered.append(r)
                    # カットオフより古いデータが出てきたら終了
                    if row_date < cutoff:
                        stop = True
                except ValueError:
                    filtered.append(r)
            else:
                filtered.append(r)

        all_records.extend(filtered)
        print(f"    -> {len(filtered)} 件取得（累計 {len(all_records)} 件）最終日={current_date}", file=sys.stderr)

        if stop or not next_params:
            break

        page += 1
        time.sleep(REQUEST_INTERVAL)

    if not all_records:
        print("データが取得できませんでした。HTMLを確認します...", file=sys.stderr)
        # デバッグ: 最初のページのHTMLを表示
        try:
            soup = fetch(session, BASE_URL)
            print(soup.prettify()[:3000], file=sys.stderr)
        except Exception:
            pass
        sys.exit(1)

    # CSV 出力
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["date", "time", "code", "name", "title"]
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_records)

    print(f"\n完了: {len(all_records)} 件 -> {out}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="irbank.net 決算開示データ取得")
    parser.add_argument("--cutoff", default=DEFAULT_CUTOFF, help="この日付以前のデータのみ取得 (YYYY-MM-DD)")
    parser.add_argument("--out", default=DEFAULT_OUT, help="出力CSVパス")
    args = parser.parse_args()
    scrape(args.cutoff, args.out)


if __name__ == "__main__":
    main()
