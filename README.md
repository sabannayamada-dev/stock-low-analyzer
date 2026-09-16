# 上場後の史上最安値タイミング分析

銘柄ごとに、上場日以降の株価履歴から次を計算してCSVに出力します。

- 史上最安値（各取引日の `Low` の最小値）とその日付
- 上場日から最安値までの経過月数
- 最安値 ÷ 公開価格
- 全銘柄における経過月数・価格比率の平均値と中央値

日本株は Yahoo Finance のティッカー末尾に `.T`（例: `7203.T`）を付けます。米国株なども
Yahoo Finance が扱うティッカーなら同じ形式で分析できます。

## 1. 準備

Python 3.10以上を推奨します。

```powershell
python -m pip install -r requirements.txt
```

`securities_sample.csv` をコピーして対象銘柄を入力します。

```csv
ticker,name,market,currency,listing_date,offer_price
7203.T,トヨタ自動車,TSE,JPY,1949-05-16,
9984.T,ソフトバンクグループ,TSE,JPY,1994-07-22,4200
AAPL,Apple,NASDAQ,USD,1980-12-12,22
```

- `ticker` と `listing_date` は必須です。
- `offer_price` が空の場合、最安値と公開価格の比率には含めません。
- 公開価格は株式分割などをどう調整した値か、銘柄間で基準を統一してください。

## 2. 株価を取得して分析

```powershell
python stock_low_analyzer.py `
  --securities securities.csv `
  --price-dir prices `
  --output results.csv `
  --summary-output summary.csv `
  --failures-output failures.csv `
  --download
```

2回目以降、保存済み株価だけで再分析する場合は `--download` を外します。

## 出力

### results.csv

銘柄別の結果です。主な列:

- `lowest_date`, `lowest_price`: 最安値の日付と価格
- `months_to_low`: 経過日数 ÷ 30.436875 の小数月
- `calendar_month_to_low`: 上場月を0とした暦月番号
- `low_offer_ratio`: 最安値 ÷ 公開価格（0.5なら公開価格の50%）
- `first_price_date`, `last_price_date`: 実際に分析できた期間

### summary.csv

`months_to_low` と `low_offer_ratio` の件数、平均値、中央値です。

### failures.csv

取得・分析できなかった銘柄と理由です。一部の銘柄が失敗しても残りは処理を続けます。

## 手元の株価CSVを使う

Yahoo Financeを使わず、`prices/<ticker>.csv` に `Date` と `Low` 列を持つCSVを置いても分析できます。
ティッカーにファイル名で使えない文字がある場合は `_` に置換されます。

## データ上の重要な注意

Yahoo Financeだけで「全上場銘柄の上場初日から現在まで」を完全には保証できません。
古い銘柄では上場日より後からしか履歴がないことがあります。必ず `first_price_date` を確認してください。

また、上場廃止銘柄を含まない現在の銘柄一覧だけで集計すると、生存者バイアスが生じます。
厳密な全市場研究には、以下が別途必要です。

1. 上場廃止銘柄を含む銘柄マスター
2. 正確な上場日と公開価格
3. 上場初日からの分割・併合を一貫して調整したOHLCデータ
4. 通貨別または市場別の集計方針

このプログラムでは銘柄マスターを外部CSVにしたため、有料データベースや取引所データへ差し替え可能です。
