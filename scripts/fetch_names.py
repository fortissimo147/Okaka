"""
東証の上場銘柄一覧から正式日本語社名を取得する。
"""
import json
import requests
import pandas as pd
from pathlib import Path
from io import BytesIO

NAMES_PATH = Path(__file__).parent.parent / "data" / "company_names.json"
TSE_URL = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"


def fetch_tse_names() -> dict:
    """東証の上場銘柄一覧CSVから {証券コード: 日本語社名} を返す。"""
    print("東証から上場銘柄一覧を取得中...")
    resp = requests.get(TSE_URL, timeout=30)
    resp.raise_for_status()

    df = pd.read_excel(BytesIO(resp.content))
    print("列名:", df.columns.tolist())

    code_col = [c for c in df.columns if "コード" in str(c)][0]
    name_col = [c for c in df.columns if "銘柄名" in str(c)][0]

    tse_names = {}
    for _, row in df.iterrows():
        code = str(row[code_col]).strip().zfill(4)
        name = str(row[name_col]).strip()
        if code and name and name != "nan":
            tse_names[code] = name

    print(f"{len(tse_names)}社取得")
    return tse_names


def update_names_cache(tse_names: dict) -> int:
    """既存キャッシュに東証データをマージして保存。更新件数を返す。"""
    existing = {}
    if NAMES_PATH.exists():
        existing = json.loads(NAMES_PATH.read_text(encoding="utf-8"))

    updated = 0
    for code, name in tse_names.items():
        if code in existing and existing[code] != name:
            print(f"  更新: {code} {existing[code]} → {name}")
            updated += 1
        existing[code] = name

    NAMES_PATH.parent.mkdir(parents=True, exist_ok=True)
    NAMES_PATH.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"保存完了（{updated}件更新）: {NAMES_PATH}")
    return updated


def main():
    tse_names = fetch_tse_names()
    update_names_cache(tse_names)


if __name__ == "__main__":
    main()
