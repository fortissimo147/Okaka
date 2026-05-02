"""
SQLiteからデータを取得してapp/data/dashboard.jsonを生成する。
"""
import json
from pathlib import Path
from datetime import datetime

from scripts.db import get_conn, init_db

APP_DATA = Path(__file__).parent.parent / "app" / "data"
TOP_N = 20  # 時系列グラフに表示する上位銘柄数


def build():
    init_db()
    APP_DATA.mkdir(parents=True, exist_ok=True)

    with get_conn() as conn:
        dates = [
            row[0] for row in conn.execute(
                "SELECT DISTINCT date FROM holdings ORDER BY date"
            ).fetchall()
        ]

        if not dates:
            out = {"dates": [], "changes": [], "timeseries": [], "latest": []}
            (APP_DATA / "dashboard.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))
            return

        # 全データ取得
        rows = conn.execute(
            "SELECT date, ticker, name, shares, price, value, ratio FROM holdings ORDER BY date, ratio DESC"
        ).fetchall()

    # date → {ticker: row} のマップを構築
    by_date: dict[str, dict] = {}
    for row in rows:
        d = row["date"]
        by_date.setdefault(d, {})[row["ticker"]] = dict(row)

    # 銘柄変動の計算（日付ごとに前日比を算出）
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

    # 最新日の上位N銘柄を時系列で追う
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
                })
            else:
                series.append({"date": d, "ratio": None, "shares": None})
        name = by_date[latest_date][ticker]["name"]
        timeseries.append({"ticker": ticker, "name": name, "series": series})

    # 最新日のスナップショット（全銘柄）
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
            "delta": delta,
            "is_new": prev_date is not None and ticker not in by_date.get(prev_date, {}),
        })

    # 過去10営業日 累積買い増し銘柄（保有金額2000万円以上 かつ 累積買い増し比率70%以上）
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

    out = {
        "generated_at": datetime.now().isoformat(),
        "dates": dates,
        "latest_date": latest_date,
        "changes": changes,
        "timeseries": timeseries,
        "latest": latest_snapshot,
        "strong_buys": strong_buys,
        "strong_buys_base_date": base_date,
    }

    (APP_DATA / "dashboard.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"dashboard.json を生成しました ({len(dates)} 日分, {len(timeseries)} 銘柄の時系列)")

    _build_standalone(out)


def _build_standalone(data: dict):
    import urllib.request

    app_dir = Path(__file__).parent.parent / "app"
    css = (app_dir / "index.html").read_text(encoding="utf-8")
    # CSSをindex.htmlから抽出
    import re
    style_match = re.search(r"<style>(.*?)</style>", css, re.DOTALL)
    style = style_match.group(1) if style_match else ""

    js = (app_dir / "app.js").read_text(encoding="utf-8")
    # fetchを使わずデータをインライン化
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

    # Chart.js をCDNから取得してインライン化（失敗時はCDNリンクにフォールバック）
    chartjs_tag = '<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>'
    try:
        with urllib.request.urlopen("https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js", timeout=10) as r:
            chartjs_inline = f"<script>{r.read().decode('utf-8')}</script>"
        print("  Chart.js をインライン化しました")
    except Exception:
        chartjs_inline = chartjs_tag
        print("  Chart.js のダウンロード失敗。CDNリンクを使用します（オンライン環境が必要）")

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>2083 ETF モニタリング</title>
  {chartjs_inline}
  <style>{style}</style>
</head>
<body>
  <header>
    <h1>2083 NEXT FUNDS Japan Growth Equity Active ETF</h1>
    <span class="meta" id="generated-at"></span>
  </header>
  <main id="app">
    <div id="no-data">データを読み込み中...</div>
  </main>
  <script>{js_inline}</script>
</body>
</html>"""

    out_path = Path(__file__).parent.parent / "etf_dashboard.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"スタンドアロンHTML を生成しました → {out_path}")

    # GitHub Pages用にdocs/index.htmlにもコピー
    docs_path = Path(__file__).parent.parent / "docs" / "index.html"
    docs_path.parent.mkdir(parents=True, exist_ok=True)
    docs_path.write_text(html, encoding="utf-8")
    print(f"GitHub Pages用HTML を生成しました → {docs_path}")


def main():
    build()


if __name__ == "__main__":
    main()
