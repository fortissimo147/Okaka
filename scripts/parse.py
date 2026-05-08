import pandas as pd
from pathlib import Path


def parse_csv(filepath: Path) -> tuple[str, float, pd.DataFrame]:
    """
    CSVをパースして (fund_date, cash_component, holdings_df) を返す。
    fund_date は "YYYY-MM-DD" 形式。
    """
    meta = pd.read_csv(filepath, nrows=1)
    raw_date = str(int(meta["Fund Date"].iloc[0]))  # 例: "20260224"
    fund_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
    cash_component = float(meta["Fund Cash Component"].iloc[0])

    df = pd.read_csv(filepath, skiprows=3)
    df = df.rename(columns={
        "Code": "ticker",
        "Name": "name",
        "Shares Amount": "shares",
        "Stock Price": "price",
    })
    df = df[["ticker", "name", "shares", "price"]].copy()
    df["ticker"] = df["ticker"].astype(str).str.strip()
    df["shares"] = pd.to_numeric(df["shares"], errors="coerce")
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df["value"] = df["shares"] * df["price"]

    total_value = df["value"].sum()
    df["ratio"] = (df["value"] / total_value * 100).round(4) if total_value > 0 else 0.0

    return fund_date, cash_component, df
