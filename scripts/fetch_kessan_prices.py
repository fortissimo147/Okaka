"""
かぶたん (kabutan.jp) の日足株価ページから
決算日±1の株価を取得して data/kessan_prices.csv に保存する。

URL例: https://kabutan.jp/stock/kabuka?code=6965&ashi=day&page=1

使い方:
  uv run python -m scripts.fetch_kessan_prices
"""

import csv
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

KESSAN_CSV = Path(__file__).parent.parent / "data" / "kessan.csv"
OUTPUT_CSV = Path(__file__).parent.parent / "data" / "kessan_prices.csv"
START_DATE = "2022-01-01"
INTERVAL_SEC = 0.8
MAX_RETRIES = 2
MAX_PAGES = 40  # 1ページ約30日分 → 最大40ページで約4年分

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


def load_kessan() -> dict[str, list[str]]:
    """code → sorted([kessan_date, ...]) のマップ（START_DATE以降）。"""
    result: dict[str, list[str]] = {}
    with open(KESSAN_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            code, date = row["code"], row["date"]
            if date >= START_DATE and code.isdigit() and len(code) == 4:
                result.setdefault(code, []).append(date)
    for code in result:
        result[code] = sorted(set(result[code]))
    return result


def needed_dates(kessan_dates: list[str]) -> set[str]:
    """決算日±2日（営業日前後のバッファ込み）を返す。"""
    result = set()
    for d in kessan_dates:
        dt = datetime.strptime(d, "%Y-%m-%d")
        for delta in range(-3, 4):  # ±3日のバッファ（祝日対応）
            result.add((dt + timedelta(days=delta)).strftime("%Y-%m-%d"))
    return result


def parse_page(html: str) -> list[dict]:
    """かぶたん日足テーブルをパースして行リストを返す。"""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="stock_kabuka_dwm")
    if table is None:
        # フォールバック: 株価テーブルを探す
        for t in soup.find_all("table"):
            hdrs = [th.get_text(strip=True) for th in t.find_all("th")]
            if "始値" in hdrs and "終値" in hdrs:
                table = t
                break
    if table is None:
        return []

    rows = table.find_all("tr")
    if not rows:
        return []

    # ヘッダー行でインデックスを特定
    headers = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])]
    def idx(name):
        return headers.index(name) if name in headers else -1

    date_i    = idx("日付")
    open_i    = idx("始値")
    high_i    = idx("高値")
    low_i     = idx("安値")
    close_i   = idx("終値")
    change_i  = idx("前日比")
    changep_i = next((i for i, h in enumerate(headers) if "%" in h), -1)

    if date_i < 0 or close_i < 0:
        return []

    records = []
    for row in rows[1:]:
        cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
        if not cells or date_i >= len(cells):
            continue
        raw_date = cells[date_i]
        # "25/04/30" や "2025/04/30" 形式を YYYY-MM-DD に変換
        m = re.match(r"^(\d{2,4})[/\-](\d{2})[/\-](\d{2})$", raw_date)
        if not m:
            continue
        y, mo, d = m.groups()
        if len(y) == 2:
            y = "20" + y
        date_str = f"{y}-{mo}-{d}"

        def to_float(s):
            if not s or s in ("--", "---", "－"):
                return None
            try:
                return float(s.replace(",", "").replace("＋", "+").replace("△", "-").replace("▲", "-"))
            except ValueError:
                return None

        records.append({
            "date":       date_str,
            "open":       to_float(cells[open_i])   if open_i  >= 0 and open_i  < len(cells) else None,
            "high":       to_float(cells[high_i])   if high_i  >= 0 and high_i  < len(cells) else None,
            "low":        to_float(cells[low_i])    if low_i   >= 0 and low_i   < len(cells) else None,
            "close":      to_float(cells[close_i])  if close_i >= 0 and close_i < len(cells) else None,
            "change":     to_float(cells[change_i]) if change_i >= 0 and change_i < len(cells) else None,
            "change_pct": to_float(cells[changep_i]) if changep_i >= 0 and changep_i < len(cells) else None,
        })
    return records


def fetch_prices_for_code(
    session: requests.Session,
    code: str,
    target_dates: set[str],
    earliest_needed: str,
) -> dict[str, dict]:
    """
    かぶたんから日足データをページ送りして取得し、
    target_dates に含まれる行のみ {date: row} で返す。
    """
    collected: dict[str, dict] = {}

    for page in range(1, MAX_PAGES + 1):
        url = f"https://kabutan.jp/stock/kabuka?code={code}&ashi=day&page={page}"
        html = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = session.get(url, headers=HEADERS, timeout=20)
                if resp.status_code == 404:
                    return collected
                if resp.status_code == 403:
                    print(f"  [{code}] p{page}: 403 blocked", file=sys.stderr)
                    return collected
                resp.raise_for_status()
                resp.encoding = resp.apparent_encoding or "utf-8"
                html = resp.text
                break
            except requests.RequestException as e:
                if attempt == MAX_RETRIES:
                    print(f"  [{code}] p{page}: エラー {e}", file=sys.stderr)
                    return collected
                time.sleep(2)

        rows = parse_page(html)
        if not rows:
            break  # データなし＝ページ終端

        for row in rows:
            d = row["date"]
            if d in target_dates:
                collected[d] = row

        # 最も古い日付がSTART_DATEより前になったら終了
        oldest = min(r["date"] for r in rows)
        if oldest < earliest_needed:
            break

        time.sleep(INTERVAL_SEC)

    return collected


def assign_offsets(
    price_by_date: dict[str, dict],
    kessan_dates: list[str],
) -> list[dict]:
    """
    決算日±1に対応する株価行を特定してoffsetを付与する。
    price_by_date のキーは実際に取得できた日付のみ。
    """
    sorted_avail = sorted(price_by_date.keys())
    records = []

    for kd in kessan_dates:
        kd_dt = datetime.strptime(kd, "%Y-%m-%d")

        for offset in [-1, 0, 1]:
            # offset=0: 決算日当日またはその最近傍
            # offset=-1: 決算日の1つ前の取引日
            # offset=+1: 決算日の1つ後の取引日
            if offset == 0:
                target = kd
                candidates = [d for d in sorted_avail if abs((datetime.strptime(d, "%Y-%m-%d") - kd_dt).days) <= 3]
                if not candidates:
                    continue
                chosen = min(candidates, key=lambda d: abs((datetime.strptime(d, "%Y-%m-%d") - kd_dt).days))
            else:
                # offset != 0: 基準日（offset=0で選んだ日）の前後の取引日
                base_candidates = [d for d in sorted_avail if abs((datetime.strptime(d, "%Y-%m-%d") - kd_dt).days) <= 3]
                if not base_candidates:
                    continue
                base = min(base_candidates, key=lambda d: abs((datetime.strptime(d, "%Y-%m-%d") - kd_dt).days))
                bi = sorted_avail.index(base)
                ni = bi + offset
                if ni < 0 or ni >= len(sorted_avail):
                    continue
                chosen = sorted_avail[ni]

            row = price_by_date[chosen]
            if row["close"] is None:
                continue
            records.append({
                "code":        "",   # 呼び出し元で設定
                "kessan_date": kd,
                "offset":      offset,
                "date":        chosen,
                "open":        row["open"],
                "high":        row["high"],
                "low":         row["low"],
                "close":       row["close"],
                "change_pct":  row["change_pct"],
            })

    return records


def main():
    print("決算データを読み込み中...")
    kessan = load_kessan()
    all_codes = sorted(kessan.keys())
    total_events = sum(len(v) for v in kessan.values())
    print(f"  {len(all_codes)} 銘柄 / {total_events} 決算イベント（{START_DATE}以降）")

    session = requests.Session()
    all_records = []
    blocked = 0

    for i, code in enumerate(all_codes, 1):
        dates = kessan[code]
        target = needed_dates(dates)
        earliest = min(
            (datetime.strptime(d, "%Y-%m-%d") - timedelta(days=5)).strftime("%Y-%m-%d")
            for d in dates
        )

        print(f"[{i}/{len(all_codes)}] {code} ({len(dates)}決算)", end=" ", flush=True)
        price_by_date = fetch_prices_for_code(session, code, target, earliest)

        if not price_by_date:
            blocked += 1
            print("→ データなし")
            if blocked > 10:
                print("ブロックが続いています。処理を中断します。", file=sys.stderr)
                sys.exit(1)
            time.sleep(INTERVAL_SEC)
            continue

        blocked = 0
        rows = assign_offsets(price_by_date, dates)
        for r in rows:
            r["code"] = code
        all_records.extend(rows)
        print(f"→ {len(rows)} 件")
        time.sleep(INTERVAL_SEC)

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["code", "kessan_date", "offset", "date", "open", "high", "low", "close", "change_pct"]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_records)

    print(f"\n完了: {len(all_records)} 件 → {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
