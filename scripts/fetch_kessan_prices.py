"""
ETFに組み入れ実績のある銘柄について、決算日±1の株価をyfinanceから取得する。

出力: data/kessan_prices.csv
列: code, kessan_date, offset, date, open, high, low, close, change_pct

使い方:
  uv run python -m scripts.fetch_kessan_prices
"""

import csv
import sys
import time
from pathlib import Path
from datetime import datetime

import pandas as pd
import yfinance as yf

from scripts.db import get_conn

KESSAN_CSV  = Path(__file__).parent.parent / "data" / "kessan.csv"
OUTPUT_CSV  = Path(__file__).parent.parent / "data" / "kessan_prices.csv"
START_DATE  = "2022-01-01"
INTERVAL_SEC = 1.0


def load_held_codes() -> set[str]:
    with get_conn() as conn:
        return set(r[0] for r in conn.execute("SELECT DISTINCT ticker FROM holdings").fetchall())


def load_kessan(codes: set[str]) -> dict[str, list[str]]:
    """code → [kessan_date, ...] のマップを返す（START_DATE以降のみ）。"""
    result: dict[str, list[str]] = {}
    with open(KESSAN_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            code, date = row["code"], row["date"]
            if code in codes and date >= START_DATE:
                result.setdefault(code, []).append(date)
    return result


def fetch_history(code: str) -> pd.DataFrame | None:
    """yfinanceで全期間の日足を取得してDataFrameを返す。"""
    ticker = f"{code}.T"
    try:
        df = yf.download(ticker, start=START_DATE, auto_adjust=True, progress=False)
        if df.empty:
            print(f"  [{code}] データなし", file=sys.stderr)
            return None
        df.index = pd.to_datetime(df.index).tz_localize(None)
        df.index = df.index.normalize()
        # 前日比% 列を追加
        df["change_pct"] = df["Close"].pct_change() * 100
        return df
    except Exception as e:
        print(f"  [{code}] 取得エラー: {e}", file=sys.stderr)
        return None


def find_price_row(df: pd.DataFrame, target_date: str, offset: int) -> dict | None:
    """target_dateのoffset営業日目の株価行を返す。"""
    dt = pd.Timestamp(target_date)
    try:
        pos = df.index.get_indexer([dt], method="nearest")[0]
    except Exception:
        return None
    idx = pos + offset
    if idx < 0 or idx >= len(df):
        return None
    row = df.iloc[idx]
    actual_date = df.index[idx]
    # 対象日から離れすぎている場合はスキップ（±5営業日超）
    if abs((actual_date - dt).days) > 10:
        return None
    return {
        "date": actual_date.strftime("%Y-%m-%d"),
        "open":  round(float(row["Open"]),  1),
        "high":  round(float(row["High"]),  1),
        "low":   round(float(row["Low"]),   1),
        "close": round(float(row["Close"]), 1),
        "change_pct": round(float(row["change_pct"]), 2) if pd.notna(row["change_pct"]) else None,
    }


def main():
    print("組み入れ実績銘柄を読み込み中...")
    codes = load_held_codes()
    print(f"  {len(codes)} 銘柄")

    kessan = load_kessan(codes)
    total_events = sum(len(v) for v in kessan.values())
    print(f"  {len(kessan)} 銘柄 / {total_events} 決算イベント（{START_DATE}以降）")

    records = []
    for i, (code, dates) in enumerate(sorted(kessan.items()), 1):
        print(f"[{i}/{len(kessan)}] {code} ({len(dates)}件の決算)")
        df = fetch_history(code)
        if df is None:
            time.sleep(INTERVAL_SEC)
            continue

        for kessan_date in sorted(dates):
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

        time.sleep(INTERVAL_SEC)

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["code", "kessan_date", "offset", "date", "open", "high", "low", "close", "change_pct"]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    print(f"\n完了: {len(records)} 件 → {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
