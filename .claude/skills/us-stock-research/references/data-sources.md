# データソース リファレンス

## 1. Alpaca Market Data API

### 概要
メインのデータソース。株価（OHLCV）、quote、trade、ニュースを取得可能。

### エンドポイント一覧

```python
from alpaca.data import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame
from datetime import datetime, timedelta

client = StockHistoricalDataClient(api_key, secret_key)

# ヒストリカルバー（OHLCV）
request = StockBarsRequest(
    symbol_or_symbols=["AAPL", "MSFT"],
    timeframe=TimeFrame.Day,
    start=datetime(2024, 1, 1),
    end=datetime(2024, 12, 31)
)
bars = client.get_stock_bars(request)

# 最新のquote
request = StockLatestQuoteRequest(symbol_or_symbols=["AAPL"])
quote = client.get_stock_latest_quote(request)

# ニュース
from alpaca.data.requests import NewsRequest
news_request = NewsRequest(symbols=["AAPL"], limit=10)
news = client.get_news(news_request)
```

### レート制限
- 無料プラン: 200リクエスト/分
- 対策: リクエスト間に0.3秒のスリープを入れる。バッチリクエストを活用

### データの種類と制限

| データ | 無料（IEX） | Basic | Pro | Ultra |
|--------|------------|-------|-----|-------|
| ヒストリカルバー | ✅ IEXのみ | ✅ | ✅ 全取引所 | ✅ 全取引所 |
| リアルタイムquote | 15分遅延 | 15分遅延 | ✅ リアルタイム | ✅ リアルタイム |
| ニュース | ✅ | ✅ | ✅ | ✅ |

## 2. Yahoo Finance（yfinance）

### 概要
非公式だが広く使われているデータソース。財務データの取得に有用。

### 使い方

```python
import yfinance as yf

# 株価データ
ticker = yf.Ticker("AAPL")
hist = ticker.history(period="1y")

# 財務データ
financials = ticker.financials        # 損益計算書
balance_sheet = ticker.balance_sheet  # 貸借対照表
cashflow = ticker.cashflow            # キャッシュフロー計算書

# 基本情報
info = ticker.info
pe_ratio = info.get('trailingPE')
market_cap = info.get('marketCap')
sector = info.get('sector')

# アナリスト予想
recommendations = ticker.recommendations
```

### 注意点
- 非公式APIのため、仕様変更で突然動かなくなる可能性がある
- 大量リクエストはIPブロックのリスク
- 主要データソースとしてではなく、補助的に使用すること

## 3. FRED API（Federal Reserve Economic Data）

### 概要
連邦準備銀行が提供するマクロ経済データ。無料でAPIキー取得可能。

### 主要系列

| 系列ID | 指標名 | 用途 |
|--------|--------|------|
| FEDFUNDS | FF金利 | 金融政策の方向性 |
| T10Y2Y | 10年-2年スプレッド | イールドカーブ（逆転でリセッション警戒） |
| VIXCLS | VIX | 市場の恐怖指数 |
| CPIAUCSL | 消費者物価指数 | インフレ率 |
| UNRATE | 失業率 | 雇用環境 |
| GDP | 実質GDP | 景気動向 |
| DTWEXBGS | ドル指数 | ドルの強さ |

### 使い方

```python
from fredapi import Fred

fred = Fred(api_key='YOUR_FRED_API_KEY')

# FF金利
fed_funds = fred.get_series('FEDFUNDS')

# イールドカーブ
yield_spread = fred.get_series('T10Y2Y')

# VIX
vix = fred.get_series('VIXCLS')
```

### APIキー取得
https://fred.stlouisfed.org/docs/api/api_key.html で無料登録。
レート制限: 120リクエスト/分。

## 4. SEC EDGAR

### 概要
米国証券取引委員会の公式データベース。決算書（10-K, 10-Q）、インサイダー取引、機関投資家保有情報（13F）を取得可能。

### 使い方

```python
import requests

# SEC EDGAR API（User-Agent必須）
headers = {
    'User-Agent': 'YourName your@email.com'
}

# 企業のfilingを検索
cik = '0000320193'  # Apple
url = f'https://data.sec.gov/submissions/CIK{cik}.json'
response = requests.get(url, headers=headers)

# XBRL財務データ
url = f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json'
response = requests.get(url, headers=headers)
```

### 注意点
- レート制限: 10リクエスト/秒
- User-Agentヘッダーが必須（名前とメールアドレス）
- データ形式がやや複雑（XBRLの理解が必要）

## 5. データソースの使い分け戦略

### 日次の市場チェック
```
Alpaca Market Data → 株価・出来高の確認
FRED → マクロ指標の変化チェック
```

### 銘柄スクリーニング
```
Alpaca Market Data → 流動性・ボラティリティ
yfinance → 時価総額・財務指標
```

### 決算分析
```
SEC EDGAR → 公式決算書（10-K, 10-Q）
Alpaca News → 決算関連ニュース
yfinance → アナリスト予想との比較
```

### バックテスト用データ
```
Alpaca Market Data → 主要なOHLCVデータ
yfinance → 長期ヒストリカルデータ（補完用）
FRED → マクロ指標（マクロ要因を戦略に組み込む場合）
```
