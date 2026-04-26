import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "db" / "etf.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS holdings (
                date     TEXT NOT NULL,
                ticker   TEXT NOT NULL,
                name     TEXT NOT NULL,
                shares   REAL,
                price    REAL,
                value    REAL,
                ratio    REAL,
                PRIMARY KEY (date, ticker)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_holdings_date ON holdings(date)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_holdings_ticker ON holdings(ticker)
        """)
