"""
data/raw/ 内の全CSVを走査してSQLiteに一括取り込む（初回のみ）。
すでに同じ日付のデータがあればスキップ。
"""
from pathlib import Path
from scripts.db import get_conn, init_db
from scripts.parse import parse_csv


RAW_DIR = Path(__file__).parent.parent / "data" / "raw"


def import_file(filepath: Path):
    try:
        fund_date, df = parse_csv(filepath)
    except Exception as e:
        print(f"  SKIP (parse error): {filepath.name} — {e}")
        return

    with get_conn() as conn:
        existing = conn.execute(
            "SELECT COUNT(*) FROM holdings WHERE date = ?", (fund_date,)
        ).fetchone()[0]
        if existing > 0:
            print(f"  SKIP (already exists): {filepath.name} → {fund_date}")
            return

        rows = [
            (fund_date, row.ticker, row.name, row.shares, row.price, row.value, row.ratio)
            for row in df.itertuples(index=False)
        ]
        conn.executemany(
            "INSERT INTO holdings (date, ticker, name, shares, price, value, ratio) VALUES (?,?,?,?,?,?,?)",
            rows,
        )
        print(f"  OK: {filepath.name} → {fund_date} ({len(rows)} 銘柄)")


def main():
    init_db()
    csv_files = sorted(RAW_DIR.glob("*.csv"))
    if not csv_files:
        print(f"CSVファイルが見つかりません: {RAW_DIR}")
        return

    print(f"{len(csv_files)} ファイルを処理します...")
    for f in csv_files:
        import_file(f)
    print("完了")


if __name__ == "__main__":
    main()
