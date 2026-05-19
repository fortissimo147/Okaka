"""
j-market.info から決算短信の発表日を取得して kessan.csv に追加。

使い方:
  python scripts/scrape_jmarket.py
  python scripts/scrape_jmarket.py --from 2026-05-16 --to 2026-05-19
  python scripts/scrape_jmarket.py --debug  # 最初の1日だけ取得してHTMLを確認
"""

import argparse
import csv
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_URL     = "https://j-market.info/disclosures/{date}"
INTERVAL_SEC = 1.0
DEFAULT_OUT  = "data/kessan.csv"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Referer": "https://j-market.info/",
}


# ─── CSV 読み書き ───────────────────────────────────────────────

def load_existing(out_path: str) -> dict[str, dict]:
    """横持ちCSV → {code: {name, dates: set}}"""
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
    """横持ち形式で書き出す。"""
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
            for i, dt in enumerate(sorted(d["dates"])):
                row[f"date_{i+1:02d}"] = dt
            writer.writerow(row)


# ─── スクレイピング ────────────────────────────────────────────

def latest_date_in_csv(out_path: str) -> date | None:
    """CSVの最新日付を返す。"""
    p = Path(out_path)
    if not p.exists():
        return None
    latest = None
    with open(p, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            for k, v in row.items():
                if k.startswith("date_") and v:
                    try:
                        d = date.fromisoformat(v)
                        if latest is None or d > latest:
                            latest = d
                    except ValueError:
                        pass
    return latest


def fetch_page(session: requests.Session, target_date: str) -> str | None:
    """指定日のページHTMLを返す。取得失敗時はNone。"""
    url = BASE_URL.format(date=target_date)
    try:
        resp = session.get(url, headers=HEADERS, timeout=20)
        print(f"HTTP {resp.status_code}", file=sys.stderr, end=" ")
        if resp.status_code == 404:
            return ""  # その日はデータなし
        if resp.status_code != 200:
            print(f"(先頭100字: {resp.text[:100]})", file=sys.stderr)
            return None
        resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text
    except requests.RequestException as e:
        print(f"エラー: {e}", file=sys.stderr)
        return None


def parse_disclosures(html: str, target_date: str, debug: bool = False) -> list[dict]:
    """
    HTMLから短信の行を抽出して [{code, name}] を返す。
    列構造（スクリーンショット確認済み）:
      時刻 | 会社名 | PDF | 決算期 | 四半期 | 売上高 | 営業利益 | 経常利益 | 純利益 | EPS | コード
       0       1      2      3        4        5        6          7          8       9    10
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []

    tables = soup.find_all("table")
    if not tables:
        if debug:
            print(f"[DEBUG] テーブルが見つかりません。最初の1000文字:\n{html[:1000]}", file=sys.stderr)
        return results

    for table in tables:
        rows = table.find_all("tr")
        if not rows:
            continue

        header_row = rows[0]
        headers = [th.get_text(strip=True) for th in header_row.find_all(["th", "td"])]

        if debug:
            print(f"[DEBUG] テーブルヘッダー: {headers}", file=sys.stderr)

        # 列インデックスを動的に特定（ヘッダー名で決定）
        code_idx = name_idx = pdf_idx = None
        for i, h in enumerate(headers):
            if "コード" in h:
                code_idx = i
            if "会社名" in h or "銘柄" in h or "企業名" in h:
                name_idx = i
            if h.upper() == "PDF" or h == "種別" or h == "書類":
                pdf_idx = i

        # フォールバック: ヘッダーがなければスクリーンショットの位置で固定
        if code_idx is None and len(headers) >= 11:
            code_idx, name_idx, pdf_idx = 10, 1, 2

        if debug:
            print(f"[DEBUG] code_idx={code_idx}, name_idx={name_idx}, pdf_idx={pdf_idx}", file=sys.stderr)

        if code_idx is None:
            continue

        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if not cells:
                continue
            texts = [c.get_text(strip=True) for c in cells]

            if debug and len(results) < 5:
                print(f"[DEBUG] 行データ: {texts}", file=sys.stderr)

            if len(texts) <= code_idx:
                continue

            # コード取得（4桁数字）
            code_raw = re.sub(r"\s+", "", texts[code_idx])
            if not re.fullmatch(r"\d{4}", code_raw):
                a = cells[code_idx].find("a")
                code_raw = re.sub(r"\s+", "", a.get_text()) if a else ""
                if not re.fullmatch(r"\d{4}", code_raw):
                    continue

            # 短信フィルタ
            if pdf_idx is not None and pdf_idx < len(texts):
                pdf_cell = cells[pdf_idx]
                pdf_text = pdf_cell.get_text(strip=True)
                if "短信" not in pdf_text:
                    continue
            else:
                if "短信" not in " ".join(texts):
                    continue

            # 銘柄名取得
            name = ""
            if name_idx is not None and name_idx < len(texts):
                name = texts[name_idx]

            results.append({"code": code_raw, "name": name})

    return results


# ─── メイン ───────────────────────────────────────────────────

def run(from_date: date, to_date: date, out_path: str, debug: bool):
    existing = load_existing(out_path)
    print(f"既存レコード: {len(existing)} 社", file=sys.stderr)

    session = requests.Session()
    added_total = 0
    current = from_date

    while current <= to_date:
        ds = current.isoformat()
        print(f"取得中: {ds} ...", file=sys.stderr, end=" ")

        html = fetch_page(session, ds)
        if html is None:
            print("スキップ", file=sys.stderr)
            current += timedelta(days=1)
            time.sleep(INTERVAL_SEC)
            continue
        if html == "":
            print("データなし", file=sys.stderr)
            current += timedelta(days=1)
            time.sleep(INTERVAL_SEC)
            continue

        disclosures = parse_disclosures(html, ds, debug=debug)
        added_today = 0
        for d in disclosures:
            code, name = d["code"], d["name"]
            entry = existing.setdefault(code, {"name": name or code, "dates": set()})
            if name:
                entry["name"] = name
            if ds not in entry["dates"]:
                entry["dates"].add(ds)
                added_today += 1
                added_total += 1

        print(f"{len(disclosures)} 件（短信）、新規 {added_today} 件", file=sys.stderr)

        if debug:
            break  # デバッグ時は1日だけ

        current += timedelta(days=1)
        time.sleep(INTERVAL_SEC)

    print(f"\n合計新規追加: {added_total} 件", file=sys.stderr)

    if added_total > 0:
        write_wide(existing, out_path)
        print(f"保存完了: {out_path}", file=sys.stderr)
    else:
        print("新しいデータはありませんでした。", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="j-market.info から決算短信日を取得")
    parser.add_argument("--from", dest="from_date", help="開始日 YYYY-MM-DD（省略時: CSVの最新日+1）")
    parser.add_argument("--to",   dest="to_date",   help="終了日 YYYY-MM-DD（省略時: 今日）")
    parser.add_argument("--out",  default=DEFAULT_OUT, help="出力CSVパス")
    parser.add_argument("--debug", action="store_true", help="1日だけ取得してHTMLを確認")
    args = parser.parse_args()

    # 終了日
    to_date = date.fromisoformat(args.to_date) if args.to_date else date.today()

    # 開始日（省略時は最新日+1）
    if args.from_date:
        from_date = date.fromisoformat(args.from_date)
    else:
        latest = latest_date_in_csv(args.out)
        if latest:
            from_date = latest + timedelta(days=1)
            print(f"CSVの最新日: {latest} → {from_date} から取得", file=sys.stderr)
        else:
            print("CSVが存在しません。--from で開始日を指定してください。", file=sys.stderr)
            sys.exit(1)

    if from_date > to_date:
        print(f"取得対象なし（{from_date} > {to_date}）", file=sys.stderr)
        sys.exit(0)

    print(f"取得期間: {from_date} 〜 {to_date}", file=sys.stderr)
    run(from_date, to_date, args.out, args.debug)


if __name__ == "__main__":
    main()
