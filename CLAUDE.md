# Okaka プロジェクト — CLAUDE.md

このファイルはプロジェクトの構造・仕様・過去に発生した問題と解決策をまとめたナレッジベースです。

---

## プロジェクト概要

| 目的 | 株式トレードの記録・分析、決算発表前後の株価変動分析、銘柄の期待増益率計算 |
|---|---|
| 公開URL | `https://fortissimo147.github.io/Okaka/` |
| GitHub Pages | `docs/` ディレクトリをそのまま配信 |

---

## ディレクトリ構成

```
Okaka/
├── data/
│   ├── beta_refer.csv          # ベータ値参照ファイル（UTF-8 with BOM, 4126社）
│   ├── company_names.json      # 銘柄コード→銘柄名マップ（法人・ETF・ETN・投信は除外済み）
│   ├── kessan.csv              # 決算発表日（横持ち形式: 1行=1社, date_01, date_02, ...）
│   └── kessan_prices.csv       # 決算前後の株価データ
├── docs/
│   ├── index.html              # 2083モニタリング（GitHub Actions が自動生成・上書き）
│   ├── trading.html            # トレード分析メインページ
│   ├── kessan_analysis.html    # 決算発表日の株価変動分析（Pythonスクリプトで生成）
│   └── expected_growth.html    # 期待増益率計算ツール
├── scripts/
│   ├── scrape_kessan_kabutan.py  # 決算発表日スクレイピング（増分モード）
│   ├── fetch_kessan_prices.py    # 決算前後の株価取得
│   └── analyze_kessan_prices.py  # kessan_analysis.html 生成
├── upload/
│   └── merged.csv              # 約定履歴（Shift-JIS, 約定履歴照会フォーマット）
└── .github/workflows/          # GitHub Actions
```

---

## データフォーマット

### `data/kessan.csv` — 横持ち形式

```
code,name,date_01,date_02,date_03,...
1234,銘柄名,2024-05-10,2024-11-08,...
```

- 1行 = 1社、日付は `date_01, date_02, ...` で右に追加していく
- 縦持ち（1行=1決算）ではない
- `parseKessan()` in `trading.html` はこの形式を読む

### `upload/merged.csv` — 約定履歴

- **エンコーディング**: Shift-JIS
- **フォーマット**: 約定履歴照会（松井証券）
- 列: `約定日,銘柄コード,銘柄名,売買区分,数量,約定単価,約定代金,...`
- 「新規買」「新規売」「決済買」「決済売」で区別
- 新しい履歴を追加するときは `scripts/merge_csv.py` を使う

### `data/beta_refer.csv` — ベータ値参照

- **エンコーディング**: UTF-8 with BOM
- 列: `コード,銘柄名,市場,現在値,前日比(%),ベータ(対TOPIX)`
- `expected_growth.html` がGitHub raw URLから直接フェッチして使用

---

## GitHub Actions パターン

### 非 fast-forward エラーの回避

複数のジョブが同一ブランチにpushするときは以下のパターンを使う:

```yaml
- name: Push
  run: |
    git config user.name "github-actions[bot]"
    git config user.email "github-actions[bot]@users.noreply.github.com"
    git add data/kessan.csv
    git commit -m "update kessan" || echo "no changes"
    git pull --rebase origin main
    git push origin HEAD:main
```

`git pull --rebase` を push 直前に入れることで競合を防ぐ。

### `docs/index.html` の注意

- `index.html` は `.github/workflows/update.yml` が自動生成・上書きする
- 手動でナビを追加しても上書きされる
- index.html を編集したいときは `update.yml` のテンプレートを編集すること

---

## kabutan.jp スクレイピング

### 株価取得（`fetch_kessan_prices.py`）

- URL: `https://kabutan.jp/stock/kabuka?code={CODE}&ashi=day&page={PAGE}`
- テーブル: `stock_kabuka_dwm`
- **制限**: 直近約1年分しか取得できない（仕様）
- スクレイピング間隔: `INTERVAL_SEC = 0.3`（0.3秒 × 4000社 ≈ 5時間、6時間制限以内）

### 決算発表日取得（`scrape_kessan_kabutan.py`）

- URL: `https://kabutan.jp/stock/finance?code={CODE}`
- 増分モード: `data/kessan.csv` に既存データがあればスキップ、なければ追加
- 1件あたり約0.3秒

---

## HTMLページ仕様

### `docs/trading.html`

#### 定数・設定

```javascript
const INITIAL_BALANCE = 4000000;  // 初期残高（円）
const CASHFLOW = [
  { date: '2025/11/14', amount:  500000 },
  { date: '2025/11/18', amount:  319000 },
  { date: '2026/01/07', amount: -100719 },
  { date: '2026/01/30', amount: -500000 },
  { date: '2026/02/03', amount:   45000 },
  { date: '2026/02/17', amount:   11000 },
  { date: '2026/03/04', amount: -1000000 },
  { date: '2026/03/12', amount:   35000 },
  { date: '2026/03/23', amount:   40000 },
  { date: '2026/04/01', amount:   30000 },
  { date: '2026/04/09', amount:   45000 },
  { date: '2026/04/17', amount:  -10000 },
  { date: '2026/05/04', amount:  -10000 },
];
```

#### 建玉クラスシステム

- 建玉サイズ（`costBasis`）を50万円刻みのクラスに変換する
- クラスインデックス: `Math.max(2, Math.round(costBasis / 500000))`
- クラス名: `${classIdx * 50}万円クラス`（例: 2→100万円クラス, 3→150万円クラス）
- 半月カードで、期間内の中央値クラスより **上に2クラス以上** 離れたトレードを赤表示

#### `parseKessan()` の形式

横持ち形式（`date_01, date_02, ...`）を読んで `{code: [dates]}` のマップを返す。

### `docs/expected_growth.html`

#### 計算式

1. **CAPM**: `Ke = Rf + β × (Rm - Rf)`
   - Rf: 無リスク金利（デフォルト1.5%）
   - Rm - Rf: 市場リスクプレミアム（デフォルト6.0%）
   - β: 対TOPIXベータ（beta_refer.csvから自動入力）
2. **FCFイールド**: `FCF per share ÷ 株価`
3. **期待増益率**: `Ke - FCFイールド`

#### β入力の自動補完

- 4桁コード入力 → 銘柄名・βを自動入力
- 銘柄名入力（部分一致）→ ドロップダウンで候補表示 → 選択するとコード・βも入力

### `docs/kessan_analysis.html`

- `scripts/analyze_kessan_prices.py` が生成する（手動編集不可・上書きされる）
- 高化け値: 前日終値→翌日終値の変化率 ≥ +20%
- 安化け値: 前日終値→翌日終値の変化率 ≤ -20%

---

## ナビゲーション（全ページ共通）

右上に以下のリンクを配置:

```
2083モニタリング | 損益分析 | 決算分析 | 期待増益率
```

対応URL:
- 2083モニタリング: `https://fortissimo147.github.io/Okaka/`
- 損益分析: `./trading.html`（または絶対URL）
- 決算分析: `./kessan_analysis.html`
- 期待増益率: `./expected_growth.html`

---

## よくあるエラーと解決策

### `NameError: name 'START_DATE' is not defined`

`fetch_kessan_prices.py` の `main()` でf-string内に `START_DATE` の参照が残っていた。  
→ その文字列を削除。

### f-string内のバックスラッシュ（Python 3.11以前）

```python
# NG
f"{'\\n'.join(items)}"
# OK
sep = '\n'
f"{sep.join(items)}"
```

### `Unexpected token 'function'`（JavaScript）

Edit ツールの適用ミスで関数定義が二重になった。  
→ 重複している `return rows; }` や関数定義ブロックを削除。

### GitHub Pages 404（`/Okaka/` が404）

`docs/index.html` が削除されると発生。  
→ `git show <commit>:docs/index.html > docs/index.html` で復元してpush。  
→ または `update.yml` を手動トリガーして再生成。

### git push 非 fast-forward

→ 「GitHub Actions パターン」の節を参照。`git pull --rebase origin main` を push 直前に追加。

---

## `company_names.json` の管理ルール

以下の会社は除外する:
- 社名に「法人」を含む（例: 投資法人、商事法人）
- 「ETF」「ETN」「投信」を含む

フィルタリングは `scripts/fetch_names.py` または手動で行う。

---

## 新しい約定履歴の追加方法

1. 松井証券から「約定履歴照会」CSVをダウンロード（Shift-JIS）
2. `upload/` に配置
3. `python scripts/merge_csv.py` を実行 → `upload/merged.csv` に追記
4. `docs/trading.html` は `upload/merged.csv` をGitHub raw URLから直接フェッチして表示

---

## テスト用ワークフロー

`.github/workflows/test-kessan-3.yml` — 3社のみで動作確認するためのワークフロー。  
本番を動かす前にここで検証する。
