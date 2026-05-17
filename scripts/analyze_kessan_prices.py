"""
決算日±1株価データを集計してHTMLレポートを生成する。

入力: data/kessan_prices.csv
出力: docs/kessan_analysis.html

使い方:
  uv run python -m scripts.analyze_kessan_prices
"""

import csv
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path

INPUT_CSV = Path(__file__).parent.parent / "data" / "kessan_prices.csv"
OUTPUT_HTML = Path(__file__).parent.parent / "docs" / "kessan_analysis.html"


def quarter_label(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    q = (dt.month - 1) // 3 + 1
    return f"{dt.year}Q{q}"


def load_events():
    """(code, kessan_date) ごとに offset→change_pct を集める。"""
    events: dict[tuple[str, str], dict[int, float]] = defaultdict(dict)
    with open(INPUT_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            cp = row["change_pct"]
            if not cp:
                continue
            try:
                offset = int(row["offset"])
            except ValueError:
                continue
            events[(row["code"], row["kessan_date"])][offset] = float(cp)
    return events


def summarize(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "mean": None, "median": None, "up": 0, "down": 0, "flat": 0}
    up = sum(1 for v in values if v > 0)
    down = sum(1 for v in values if v < 0)
    flat = sum(1 for v in values if v == 0)
    return {
        "n": len(values),
        "mean": round(statistics.mean(values), 2),
        "median": round(statistics.median(values), 2),
        "up": up,
        "down": down,
        "flat": flat,
    }


def aggregate(events):
    """quarter → {offset: [change_pct, ...]} に集約。"""
    buckets: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    for (_code, kdate), offsets in events.items():
        q = quarter_label(kdate)
        for off, pct in offsets.items():
            if off in (0, 1):
                buckets[q][off].append(pct)
    return buckets


def render_html(buckets) -> str:
    quarters = sorted(buckets.keys())

    def row_cells(stats):
        if stats["n"] == 0:
            return "<td colspan='6' class='empty'>-</td>"
        return (
            f"<td>{stats['n']:,}</td>"
            f"<td class='{'pos' if stats['mean'] > 0 else 'neg' if stats['mean'] < 0 else ''}'>"
            f"{stats['mean']:+.2f}%</td>"
            f"<td class='{'pos' if stats['median'] > 0 else 'neg' if stats['median'] < 0 else ''}'>"
            f"{stats['median']:+.2f}%</td>"
            f"<td class='pos'>{stats['up']:,}</td>"
            f"<td class='neg'>{stats['down']:,}</td>"
            f"<td>{stats['flat']:,}</td>"
        )

    rows = []
    for q in quarters:
        d0 = summarize(buckets[q].get(0, []))
        d1 = summarize(buckets[q].get(1, []))
        rows.append(
            f"<tr><th>{q}</th>{row_cells(d0)}{row_cells(d1)}</tr>"
        )

    # 全期間合計
    all0 = [v for q in quarters for v in buckets[q].get(0, [])]
    all1 = [v for q in quarters for v in buckets[q].get(1, [])]
    t0 = summarize(all0)
    t1 = summarize(all1)
    rows.append(
        f"<tr class='total'><th>全期間</th>{row_cells(t0)}{row_cells(t1)}</tr>"
    )

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>決算日±1 株価変動分析</title>
<style>
  body {{ font-family: -apple-system, "Hiragino Sans", sans-serif; margin: 2em; color: #222; }}
  h1 {{ font-size: 1.5em; }}
  .desc {{ color: #666; margin-bottom: 1.5em; font-size: 0.9em; }}
  table {{ border-collapse: collapse; margin-top: 1em; }}
  th, td {{ border: 1px solid #ddd; padding: 0.5em 0.8em; text-align: right; font-variant-numeric: tabular-nums; }}
  thead th {{ background: #f3f3f3; text-align: center; }}
  tbody th {{ background: #fafafa; text-align: left; }}
  .pos {{ color: #c00; }}
  .neg {{ color: #06c; }}
  .empty {{ color: #aaa; text-align: center; }}
  .total {{ background: #fffbe6; font-weight: bold; }}
  .group {{ border-left: 2px solid #999; }}
</style>
</head>
<body>
<h1>決算日±1 株価変動分析</h1>
<p class="desc">
  対象: data/kessan_prices.csv<br>
  集計単位: 年×四半期（決算発表日ベース）<br>
  offset=0: 決算発表日終値 vs 前日終値の変化率<br>
  offset=1: 翌営業日終値 vs 決算発表日終値の変化率
</p>
<table>
<thead>
<tr>
  <th rowspan="2">四半期</th>
  <th colspan="6">offset=0（決算日）</th>
  <th colspan="6" class="group">offset=+1（翌日）</th>
</tr>
<tr>
  <th>件数</th><th>平均</th><th>中央値</th><th>上昇</th><th>下落</th><th>変わらず</th>
  <th class="group">件数</th><th>平均</th><th>中央値</th><th>上昇</th><th>下落</th><th>変わらず</th>
</tr>
</thead>
<tbody>
{chr(10).join(rows)}
</tbody>
</table>
</body>
</html>
"""


def main():
    print("読み込み中...")
    events = load_events()
    print(f"  決算イベント数: {len(events):,}")

    buckets = aggregate(events)
    OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_HTML.write_text(render_html(buckets), encoding="utf-8")
    print(f"完了 -> {OUTPUT_HTML}")


if __name__ == "__main__":
    main()
