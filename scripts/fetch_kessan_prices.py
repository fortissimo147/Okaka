"""
kessan.csvに含まれる全銘柄の決算日±1の株価をyfinanceから取得する。

出力: data/kessan_prices.csv
列: code, kessan_date, offset, date, open, high, low, close, change_pct

使い方:
  uv run python -m scripts.fetch_kessan_prices
"""

import csv
import sys
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

KESSAN_CSV  = Path(__file__).parent.parent / "data" / "kessan.csv"
OUTPUT_CSV  = Path(__file__).parent.parent / "data" / "kessan_prices.csv"
START_DATE  = "2022-01-01"
BATCH_SIZE  = 50
SLEEP_SEC   = 2.0


def load_kessan() -> dict[str, list[str]]:
    """code → [kessan_date, ...] のマップを返す（START_DATE以降のみ）。"""
    result: dict[str, list[str]] = {}
    with open(KESSAN_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            code, date = row["code"], row["date"]
            if date >= START_DATE and code.isdigit() and len(code) == 4:
                result.setdefault(code, []).append(date)
    return result


def fetch_batch(codes: list[str]) -> dict[str, pd.DataFrame]:
    """複数銘柄を一括取得して {code: df} を返す。"""
    tickers = [f"{c}.T" for c in codes]
    try:
        raw = yf.download(
            tickers,
            start=START_DATE,
            auto_adjust=True,
            progress=False,
            group_by="ticker",
        )
    except Exception as e:
        print(f"  バッチ取得エラー: {e}", file=sys.stderr)
        return {}

    result = {}
    for code, ticker in zip(codes, tickers):
        try:
            if len(codes) == 1:
                df = raw.copy()
            else:
                df = raw[ticker].copy() if ticker in raw.columns.get_level_values(0) else pd.DataFrame()
            if df.empty or df["Close"].isna().all():
                continue
            df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
            df = df[~df.index.duplicated(keep="last")]
            df["change_pct"] = df["Close"].pct_change() * 100
            result[code] = df
        except Exception:
            continue
    return result


def find_price_row(df: pd.DataFrame, target_date: str, offset: int) -> dict | None:
    """target_dateのoffset営業日目の株価行を返す。"""
    dt = pd.Timestamp(target_date)
    pos = df.index.get_indexer([dt], method="nearest")[0]
    if pos < 0:
        return None
    idx = pos + offset
    if idx < 0 or idx >= len(df):
        return None
    row = df.iloc[idx]
    actual_date = df.index[idx]
    # 対象日から10日以上離れている場合はスキップ
    if abs((actual_date - dt).days) > 10:
        return None
    return {
        "date":       actual_date.strftime("%Y-%m-%d"),
        "open":       round(float(row["Open"]),  1),
        "high":       round(float(row["High"]),  1),
        "low":        round(float(row["Low"]),   1),
        "close":      round(float(row["Close"]), 1),
        "change_pct": round(float(row["change_pct"]), 2) if pd.notna(row["change_pct"]) else None,
    }


def main():
    print("決算データを読み込み中...")
    kessan = load_kessan()
    all_codes = sorted(kessan.keys())
    total_events = sum(len(v) for v in kessan.values())
    print(f"  {len(all_codes)} 銘柄 / {total_events} 決算イベント（{START_DATE}以降）")

    records = []
    batches = [all_codes[i:i + BATCH_SIZE] for i in range(0, len(all_codes), BATCH_SIZE)]

    for bi, batch in enumerate(batches, 1):
        print(f"バッチ [{bi}/{len(batches)}] {batch[0]}〜{batch[-1]} ({len(batch)}銘柄)")
        price_data = fetch_batch(batch)
        print(f"  取得成功: {len(price_data)}/{len(batch)} 銘柄")

        for code in batch:
            df = price_data.get(code)
            if df is None:
                continue
            for kessan_date in sorted(kessan[code]):
                for offset in [-1, 0, 1]:
                    price = find_price_row(df, kessan_date, offset)
                    if price is None:
                        continue
                    records.append({
                        "code":        code,
                        "kessan_date": kessan_date,
                        "offset":      offset,
                        **price,
                    })

        time.sleep(SLEEP_SEC)

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["code", "kessan_date", "offset", "date", "open", "high", "low", "close", "change_pct"]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    print(f"\n完了: {len(records)} 件 → {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
