"""
SQLiteからデータを取得してapp/data/dashboard.jsonを生成する。
"""
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

from scripts.db import get_conn, init_db

APP_DATA = Path(__file__).parent.parent / "app" / "data"
NAMES_FILE = Path(__file__).parent.parent / "data" / "company_names.json"
TOP_N = 20
JST = timezone(timedelta(hours=9))


def load_company_names() -> dict:
    if NAMES_FILE.exists():
        return json.loads(NAMES_FILE.read_text(encoding="utf-8"))
    return {}


def save_company_names(names: dict):
    NAMES_FILE.parent.mkdir(parents=True, exist_ok=True)
    NAMES_FILE.write_text(json.dumps(names, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_missing_names(tickers: list[str], existing: dict) -> dict:
    import yfinance as yf
    result = {}
    for ticker in tickers:
        if ticker in existing:
            continue
        try:
            info = yf.Ticker(f"{ticker}.T").info
            name = info.get("longName") or info.get("shortName") or ""
            result[ticker] = name if name else None
            print(f"  {ticker}: {result[ticker]}")
        except Exception as e:
            print(f"  {ticker}: 取得失敗 ({e})")
            result[ticker] = None
    return result


def _maybe_refresh_names():
    import time
    from scripts.fetch_names import fetch_tse_names, update_names_cache
    if NAMES_FILE.exists():
        age_days = (time.time() - NAMES_FILE.stat().st_mtime) / 86400
        if age_days < 7:
            return
        print(f"company_names.json が {age_days:.0f}日前のため東証CSVを再取得します...")
    else:
        print("company_names.json が存在しないため東証CSVを取得します...")
    try:
        tse_names = fetch_tse_names()
        update_names_cache(tse_names)
    except Exception as e:
        print(f"  東証CSV取得失敗（スキップ）: {e}")


BASELINE_DATE = "2026-03-27"


def _calc_unrealized_gains(by_date: dict, dates: list, latest_date: str) -> dict:
    """
    推測含み益を計算する。
    - 加重平均取得原価: 保有株数が増えた日の価格で更新、減った日は平均単価を維持
    - BASELINE_DATE より保有株数が少ない銘柄は除外
    """
    baseline = by_date.get(BASELINE_DATE, {})

    items = []
    for ticker, latest_row in by_date[latest_date].items():
        current_shares = latest_row["shares"] or 0
        latest_price = latest_row["price"]
        if not latest_price or current_shares <= 0:
            continue

        # 03/27時点より株数が減っている銘柄は除外
        baseline_shares = (baseline.get(ticker) or {}).get("shares", 0) or 0
        if current_shares < baseline_shares:
            continue

        # 加重平均取得原価の計算
        avg_cost = 0.0
        tracked_shares = 0.0
        for d in dates:
            row = by_date[d].get(ticker)
            if not row or not row["price"]:
                continue
            day_shares = row["shares"] or 0
            day_price = row["price"]
            if tracked_shares == 0:
                avg_cost = day_price
                tracked_shares = day_shares
            else:
                added = day_shares - tracked_shares
                if added > 0:
                    avg_cost = (avg_cost * tracked_shares + day_price * added) / day_shares
                tracked_shares = day_shares

        if avg_cost <= 0:
            continue

        unrealized = (latest_price - avg_cost) * current_shares
        items.append({
            "ticker": ticker,
            "name": latest_row["name"],
            "shares": current_shares,
            "avg_cost": round(avg_cost, 2),
            "latest_price": latest_price,
            "unrealized": round(unrealized),
            "unrealized_pct": round((latest_price / avg_cost - 1) * 100, 2),
        })

    items.sort(key=lambda x: -x["unrealized"])
    total = sum(r["unrealized"] for r in items)
    return {"baseline_date": BASELINE_DATE, "total": round(total), "items": items}


def build():
    init_db()
    APP_DATA.mkdir(parents=True, exist_ok=True)
    _maybe_refresh_names()

    with get_conn() as conn:
        dates = [
            row[0] for row in conn.execute(
                "SELECT DISTINCT date FROM holdings ORDER BY date"
            ).fetchall()
        ]
        dates = [d for d in dates if d != "2026-02-24"]

        if not dates:
            out = {"dates": [], "changes": [], "timeseries": [], "latest": []}
            (APP_DATA / "dashboard.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
            return

        rows = conn.execute(
            "SELECT date, ticker, name, shares, price, value, ratio FROM holdings ORDER BY date, ratio DESC"
        ).fetchall()

        fund_stats_rows = conn.execute(
            "SELECT date, cash_component FROM fund_stats ORDER BY date"
        ).fetchall()
    cash_by_date = {r["date"]: r["cash_component"] for r in fund_stats_rows}

    by_date: dict[str, dict] = {}
    for row in rows:
        d = row["date"]
        by_date.setdefault(d, {})[row["ticker"]] = dict(row)

    all_tickers = sorted({ticker for d_data in by_date.values() for ticker in d_data})
    company_names = load_company_names()
    new_names = fetch_missing_names(all_tickers, company_names)
    if new_names:
        company_names.update(new_names)
        save_company_names(company_names)
    for d_data in by_date.values():
        for ticker, row in d_data.items():
            jp_name = company_names.get(ticker)
            if jp_name:
                row["name"] = jp_name

    changes = []
    for i, d in enumerate(dates):
        if i == 0:
            continue
        prev_d = dates[i - 1]
        curr = by_date[d]
        prev = by_date[prev_d]

        curr_tickers = set(curr.keys())
        prev_tickers = set(prev.keys())

        new_tickers = sorted(curr_tickers - prev_tickers)
        removed_tickers = sorted(prev_tickers - curr_tickers)

        increased = []
        decreased = []
        for ticker in curr_tickers & prev_tickers:
            curr_shares = curr[ticker]["shares"] or 0
            prev_shares = prev[ticker]["shares"] or 0
            if prev_shares == 0:
                continue
            shares_change_pct = (curr_shares - prev_shares) / prev_shares * 100
            if shares_change_pct > 0:
                increased.append({
                    "ticker": ticker,
                    "name": curr[ticker]["name"],
                    "delta": round(shares_change_pct, 2),
                    "shares": curr_shares,
                    "ratio": round(curr[ticker]["ratio"], 4),
                })
            elif shares_change_pct < 0:
                decreased.append({
                    "ticker": ticker,
                    "name": curr[ticker]["name"],
                    "delta": round(shares_change_pct, 2),
                    "shares": curr_shares,
                    "ratio": round(curr[ticker]["ratio"], 4),
                })

        increased.sort(key=lambda x: -x["delta"])
        decreased.sort(key=lambda x: x["delta"])

        changes.append({
            "date": d,
            "new": [{"ticker": t, "name": curr[t]["name"], "ratio": round(curr[t]["ratio"], 4)} for t in new_tickers],
            "removed": [{"ticker": t, "name": prev[t]["name"]} for t in removed_tickers],
            "increased": increased,
            "decreased": decreased,
        })

    latest_date = dates[-1]
    top_tickers = [
        ticker for ticker, _ in sorted(
            by_date[latest_date].items(),
            key=lambda x: -x[1]["ratio"]
        )[:TOP_N]
    ]

    timeseries = []
    for ticker in top_tickers:
        series = []
        for d in dates:
            if ticker in by_date[d]:
                series.append({
                    "date": d,
                    "ratio": round(by_date[d][ticker]["ratio"], 4),
                    "shares": by_date[d][ticker]["shares"],
                    "price": by_date[d][ticker]["price"],
                })
            else:
                series.append({"date": d, "ratio": None, "shares": None, "price": None})
        name = by_date[latest_date][ticker]["name"]
        timeseries.append({"ticker": ticker, "name": name, "series": series})

    latest_snapshot = []
    prev_date = dates[-2] if len(dates) >= 2 else None
    for ticker, row in sorted(by_date[latest_date].items(), key=lambda x: -x[1]["ratio"]):
        prev_ratio = by_date[prev_date][ticker]["ratio"] if prev_date and ticker in by_date[prev_date] else None
        delta = round(row["ratio"] - prev_ratio, 4) if prev_ratio is not None else None
        latest_snapshot.append({
            "ticker": ticker,
            "name": row["name"],
            "ratio": round(row["ratio"], 4),
            "shares": row["shares"],
            "value": round(row["value"]) if row["value"] is not None else None,
            "delta": delta,
            "is_new": prev_date is not None and ticker not in by_date.get(prev_date, {}),
        })

    base_date = dates[-11] if len(dates) >= 11 else dates[0]
    strong_buys = []
    for ticker, row in by_date[latest_date].items():
        value = row["value"] or 0
        if value < 20_000_000:
            continue
        if ticker not in by_date[base_date]:
            continue
        base_shares = by_date[base_date][ticker]["shares"] or 0
        if base_shares == 0:
            continue
        cumulative_pct = (row["shares"] - base_shares) / base_shares * 100
        if cumulative_pct >= 70:
            strong_buys.append({
                "ticker": ticker,
                "name": row["name"],
                "cumulative_pct": round(cumulative_pct, 1),
                "value": round(value),
                "shares": row["shares"],
                "base_shares": base_shares,
                "base_date": base_date,
            })
    strong_buys.sort(key=lambda x: -x["cumulative_pct"])

    recent_dates = dates[-20:] if len(dates) >= 20 else dates
    buyup_pnl = []
    for ticker in by_date[latest_date]:
        entries = []
        for i in range(1, len(recent_dates)):
            d = recent_dates[i]
            prev_d = recent_dates[i - 1]
            if ticker not in by_date[d] or ticker not in by_date[prev_d]:
                continue
            curr_shares = by_date[d][ticker]["shares"] or 0
            prev_shares = by_date[prev_d][ticker]["shares"] or 0
            added = curr_shares - prev_shares
            if added > 0:
                entries.append({
                    "date": d,
                    "added_shares": added,
                    "entry_price": by_date[d][ticker]["price"],
                })
        if not entries:
            continue
        total_added = sum(e["added_shares"] for e in entries)
        avg_entry = sum(e["added_shares"] * e["entry_price"] for e in entries) / total_added
        latest_price = by_date[latest_date][ticker]["price"]
        latest_row = by_date[latest_date][ticker]
        pnl_pct = latest_price / avg_entry - 1
        buyup_pnl.append({
            "ticker": ticker,
            "name": latest_row["name"],
            "total_added_shares": total_added,
            "latest_shares": latest_row["shares"],
            "latest_price": latest_price,
            "avg_entry_price": round(avg_entry, 2),
            "entries": entries,
            "pnl_pct": round(pnl_pct, 6),
            "latest_ratio": round(latest_row["ratio"], 4),
        })
    buyup_pnl.sort(key=lambda x: -x["pnl_pct"])

    trading_analysis = []
    for ticker in by_date[latest_date]:
        if ticker not in by_date[recent_dates[0]]:
            continue
        base_row = by_date[recent_dates[0]][ticker]
        base_price = base_row["price"]
        if not base_price:
            continue
        buy_entries = []
        sell_entries = []
        for i in range(1, len(recent_dates)):
            d = recent_dates[i]
            prev_d = recent_dates[i - 1]
            if ticker not in by_date[d] or ticker not in by_date[prev_d]:
                continue
            curr_shares = by_date[d][ticker]["shares"] or 0
            prev_shares = by_date[prev_d][ticker]["shares"] or 0
            diff = curr_shares - prev_shares
            if diff > 0:
                buy_entries.append({
                    "date": d,
                    "added_shares": diff,
                    "entry_price": by_date[d][ticker]["price"],
                })
            elif diff < 0:
                sell_entries.append({
                    "date": d,
                    "sold_shares": -diff,
                    "sell_price": by_date[d][ticker]["price"],
                })
        if not buy_entries and not sell_entries:
            continue
        latest_price = by_date[latest_date][ticker]["price"]
        latest_row = by_date[latest_date][ticker]
        benchmark_pnl_pct = latest_price / base_price - 1
        total_buy_shares = sum(e["added_shares"] for e in buy_entries)
        total_sell_shares = sum(e["sold_shares"] for e in sell_entries)
        total_traded = total_buy_shares + total_sell_shares
        buy_pnl_sum = sum(e["added_shares"] * (latest_price / e["entry_price"] - 1) for e in buy_entries) if buy_entries else 0
        sell_pnl_sum = sum(e["sold_shares"] * (latest_price / e["sell_price"] - 1) for e in sell_entries) if sell_entries else 0
        actual_pnl_pct = (buy_pnl_sum + sell_pnl_sum) / total_traded
        evaluation_pct = actual_pnl_pct - benchmark_pnl_pct
        trading_analysis.append({
            "ticker": ticker,
            "name": latest_row["name"],
            "base_date": recent_dates[0],
            "base_price": base_price,
            "latest_price": latest_price,
            "benchmark_pnl_pct": round(benchmark_pnl_pct, 6),
            "actual_pnl_pct": round(actual_pnl_pct, 6),
            "evaluation_pct": round(evaluation_pct, 6),
            "buy_entries": buy_entries,
            "sell_entries": sell_entries,
            "latest_ratio": round(latest_row["ratio"], 4),
        })
    trading_analysis.sort(key=lambda x: -x["evaluation_pct"])

    price_data = {}
    for ticker in by_date[latest_date].keys():
        prices = []
        for d in dates:
            if ticker in by_date[d] and by_date[d][ticker]["price"] is not None:
                prices.append({"date": d, "close": by_date[d][ticker]["price"]})
        if prices:
            price_data[ticker] = prices

    all_series = []
    for ticker in by_date[latest_date].keys():
        series = []
        for d in dates:
            if ticker in by_date[d]:
                row = by_date[d][ticker]
                series.append({
                    "date": d,
                    "ratio": round(row["ratio"], 4),
                    "shares": row["shares"],
                    "price": row["price"],
                })
            else:
                series.append({"date": d, "ratio": None, "shares": None, "price": None})
        name = by_date[latest_date][ticker]["name"]
        all_series.append({"ticker": ticker, "name": name, "series": series})

    fund_cash_series = []
    for d in dates:
        stock_total = sum(v["value"] for v in by_date[d].values() if v["value"] is not None)
        cash = cash_by_date.get(d)
        nav = (stock_total + cash) if cash is not None else None
        cash_ratio = (cash / nav * 100) if (cash is not None and nav) else None
        fund_cash_series.append({
            "date": d,
            "cash": round(cash) if cash is not None else None,
            "nav": round(nav) if nav is not None else None,
            "cash_ratio": round(cash_ratio, 2) if cash_ratio is not None else None,
        })

    unrealized_gains = _calc_unrealized_gains(by_date, dates, latest_date)

    out = {
        "generated_at": datetime.now(JST).isoformat(),
        "dates": dates,
        "latest_date": latest_date,
        "changes": changes,
        "timeseries": timeseries,
        "latest": latest_snapshot,
        "strong_buys": strong_buys,
        "strong_buys_base_date": base_date,
        "buyup_pnl": buyup_pnl,
        "trading_analysis": trading_analysis,
        "all_series": all_series,
        "price_data": price_data,
        "fund_cash_series": fund_cash_series,
        "unrealized_gains": unrealized_gains,
    }

    (APP_DATA / "dashboard.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"dashboard.json を生成しました ({len(dates)} 日分, {len(timeseries)} 銘柄の時系列)")

    _build_standalone(out)


def _build_standalone(data: dict):
    import urllib.request

    app_dir = Path(__file__).parent.parent / "app"

    html = (app_dir / "index.html").read_text(encoding="utf-8")

    js = (app_dir / "app.js").read_text(encoding="utf-8")
    js_inline = js.replace(
        """async function load() {
  try {
    const res = await fetch("data/dashboard.json");
    if (!res.ok) throw new Error(res.statusText);
    DATA = await res.json();
    render();
  } catch (e) {
    document.getElementById("no-data").textContent = "データの読み込みに失敗しました: " + e.message;
  }
}""",
        f"""function load() {{
  DATA = {json.dumps(data, ensure_ascii=False)};
  render();
}}"""
    )
    html = html.replace('<script src="app.js"></script>', f"<script>{js_inline}</script>")

    chartjs_tag = '<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>'
    try:
        with urllib.request.urlopen("https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js", timeout=10) as r:
            html = html.replace(chartjs_tag, f"<script>{r.read().decode('utf-8')}</script>")
        print("  Chart.js をインライン化しました")
    except Exception:
        print("  Chart.js のダウンロード失敗。CDNリンクを使用します（オンライン環境が必要）")

    docs_path = Path(__file__).parent.parent / "docs" / "index.html"
    docs_path.parent.mkdir(parents=True, exist_ok=True)
    docs_path.write_text(html, encoding="utf-8")
    print(f"GitHub Pages用HTML を生成しました → {docs_path}")


def main():
    build()


if __name__ == "__main__":
    main()
