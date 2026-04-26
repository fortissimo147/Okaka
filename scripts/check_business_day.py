"""営業日判定ユーティリティ"""
from datetime import date
from pathlib import Path
import csv

BUSINESS_DAYS_CSV = Path(__file__).parent.parent / "data" / "business_days.csv"


def load_business_days() -> set[str]:
    if not BUSINESS_DAYS_CSV.exists():
        return set()
    with open(BUSINESS_DAYS_CSV) as f:
        reader = csv.DictReader(f)
        return {row["date"].strip() for row in reader}


def is_business_day(target: date | None = None) -> bool:
    if target is None:
        target = date.today()
    return target.isoformat() in load_business_days()
