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
    """(code, kessan_date) ごとに offset → {change_pct, open, close} を集める。"""
    rows_by_event: dict[tuple[str, str], dict[int, dict]] = defaultdict(dict)
    with open(INPUT_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                offset = int(row["offset"])
            except ValueError:
                continue
            key = (row["code"], row["kessan_date"])
            entry = {"change_pct": None, "open": None, "close": None}
            if row["change_pct"]:
                entry["change_pct"] = float(row["change_pct"])
            if row["open"]:
                entry["open"] = float(row["open"])
            if row["close"]:
                entry["close"] = float(row["close"])
            rows_by_event[key][offset] = entry
    return rows_by_event


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


def aggregate(rows_by_event):
    """quarter → {metric_key: [values]} に集約。
    metric_key:
      "day_close"   : offset=0 の前日終値→当日終値変化率 (change_pct)
      "day_intraday": offset=0 の始値→終値変化率
      "next_close"  : offset=+1 の当日終値→翌日終値変化率 (change_pct)
      "span"        : offset=-1 終値 → offset=+1 終値 の変化率
    """
    buckets: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    for (_code, kdate), offsets in rows_by_event.items():
        q = quarter_label(kdate)

        d0 = offsets.get(0)
        d1 = offsets.get(1)
        dm1 = offsets.get(-1)

        # 前日終値→当日終値
        if d0 and d0["change_pct"] is not None:
            buckets[q]["day_close"].append(d0["change_pct"])

        # 当日始値→終値（イントラデイ）
        if d0 and d0["open"] and d0["close"]:
            intra = (d0["close"] / d0["open"] - 1) * 100
            buckets[q]["day_intraday"].append(round(intra, 2))

        # 当日終値→翌日終値
        if d1 and d1["change_pct"] is not None:
            buckets[q]["next_close"].append(d1["change_pct"])

        # 前日終値→翌日終値（3日跨ぎ）
        if dm1 and d1 and dm1["close"] and d1["close"]:
            span = (d1["close"] / dm1["close"] - 1) * 100
            buckets[q]["span"].append(round(span, 2))

    return buckets


def render_html(buckets) -> str:
    quarters = sorted(buckets.keys())

    METRICS = [
        ("day_close",    "前日終値→当日終値"),
        ("day_intraday", "当日始値→終値"),
        ("next_close",   "当日終値→翌日終値"),
        ("span",         "前日終値→翌日終値"),
    ]

    def row_cells(stats, is_group=False):
        grp = ' class="group"' if is_group else ""
        if stats["n"] == 0:
            return f"<td{grp} colspan='6' style='color:#aaa;text-align:center'>-</td>"
        mean_color = "pos" if stats["mean"] > 0 else "neg" if stats["mean"] < 0 else ""
        med_color  = "pos" if stats["median"] > 0 else "neg" if stats["median"] < 0 else ""
        mc = f' class="group {mean_color}"' if is_group and mean_color else (f' class="group"' if is_group else f' class="{mean_color}"' if mean_color else "")
        medc = f' class="{med_color}"' if med_color else ""
        return (
            f"<td{grp}>{stats['n']:,}</td>"
            f"<td{mc}>{stats['mean']:+.2f}%</td>"
            f"<td{medc}>{stats['median']:+.2f}%</td>"
            f"<td class='pos'>{stats['up']:,}</td>"
            f"<td class='neg'>{stats['down']:,}</td>"
            f"<td>{stats['flat']:,}</td>"
        )

    # ヘッダー行
    header1 = "<tr><th rowspan='2'>四半期</th>"
    header2 = "<tr>"
    for i, (key, label) in enumerate(METRICS):
        grp = ' class="group"' if i > 0 else ""
        header1 += f"<th colspan='6'{grp}>{label}</th>"
        n_grp = ' class="group"' if i > 0 else ""
        header2 += f"<th{n_grp}>件数</th><th>平均</th><th>中央値</th><th>上昇</th><th>下落</th><th>変わらず</th>"
    header1 += "</tr>"
    header2 += "</tr>"

    rows = []
    for q in quarters:
        row = f"<tr><th>{q}</th>"
        for i, (key, _) in enumerate(METRICS):
            stats = summarize(buckets[q].get(key, []))
            row += row_cells(stats, is_group=(i > 0))
        row += "</tr>"
        rows.append(row)

    # 全期間合計
    total_row = "<tr class='total'><th>全期間</th>"
    for i, (key, _) in enumerate(METRICS):
        all_vals = [v for q in quarters for v in buckets[q].get(key, [])]
        stats = summarize(all_vals)
        total_row += row_cells(stats, is_group=(i > 0))
    total_row += "</tr>"
    rows.append(total_row)

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>決算日±1 株価変動分析</title>
<style>
  body {{ font-family: -apple-system, "Hiragino Sans", sans-serif; margin: 2em; color: #222; font-size: 14px; }}
  h1 {{ font-size: 1.4em; }}
  .desc {{ color: #666; margin-bottom: 1.5em; font-size: 0.88em; line-height: 1.6; }}
  table {{ border-collapse: collapse; margin-top: 1em; white-space: nowrap; }}
  th, td {{ border: 1px solid #ddd; padding: 0.4em 0.7em; text-align: right; font-variant-numeric: tabular-nums; }}
  thead th {{ background: #f3f3f3; text-align: center; }}
  tbody th {{ background: #fafafa; text-align: left; }}
  .pos {{ color: #c00; }}
  .neg {{ color: #06c; }}
  .total {{ background: #fffbe6; font-weight: bold; }}
  .group {{ border-left: 3px solid #aaa; }}
</style>
</head>
<body>
<h1>決算日±1 株価変動分析</h1>
<p class="desc">
  対象: data/kessan_prices.csv　｜　集計単位: 年×四半期（決算発表日ベース）<br>
  <b>前日終値→当日終値</b>: 決算発表日の前日終値に対する当日終値の変化率<br>
  <b>当日始値→終値</b>: 決算発表日のイントラデイ変化率（始値→終値）<br>
  <b>当日終値→翌日終値</b>: 決算発表日終値に対する翌営業日終値の変化率<br>
  <b>前日終値→翌日終値</b>: 前日終値から翌日終値までの3日跨ぎ変化率
</p>
<table>
<thead>
{header1}
{header2}
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
    rows_by_event = load_events()
    print(f"  決算イベント数: {len(rows_by_event):,}")

    buckets = aggregate(rows_by_event)
    OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_HTML.write_text(render_html(buckets), encoding="utf-8")
    print(f"完了 -> {OUTPUT_HTML}")


if __name__ == "__main__":
    main()
