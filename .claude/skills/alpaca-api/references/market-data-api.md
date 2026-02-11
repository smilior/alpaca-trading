# Market Data API リファレンス

## 概要

Alpaca Market Data APIは株価、出来高、quote、ニュースデータを提供する。

## ヒストリカルデータ（Bars）

```python
from alpaca.data import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from datetime import datetime

data_client = StockHistoricalDataClient(api_key, secret_key)

# 日足データ取得
request = StockBarsRequest(
    symbol_or_symbols=["AAPL"],
    timeframe=TimeFrame.Day,
    start=datetime(2024, 1, 1),
    end=datetime(2024, 12, 31)
)
bars = data_client.get_stock_bars(request)

# DataFrameに変換
df = bars.df
print(df.head())
# columns: open, high, low, close, volume, trade_count, vwap
```

### タイムフレーム

| TimeFrame | 説明 | 用途 |
|-----------|------|------|
| `TimeFrame.Minute` | 1分足 | デイトレード分析 |
| `TimeFrame(5, TimeFrameUnit.Minute)` | 5分足 | 短期分析 |
| `TimeFrame(15, TimeFrameUnit.Minute)` | 15分足 | イントラデイ |
| `TimeFrame.Hour` | 1時間足 | スイングトレード |
| `TimeFrame.Day` | 日足 | 中長期分析 |
| `TimeFrame.Week` | 週足 | 長期分析 |
| `TimeFrame.Month` | 月足 | 超長期分析 |

### 複数銘柄の一括取得

```python
request = StockBarsRequest(
    symbol_or_symbols=["AAPL", "MSFT", "GOOG", "AMZN"],
    timeframe=TimeFrame.Day,
    start=datetime(2024, 1, 1),
    end=datetime(2024, 12, 31)
)
bars = data_client.get_stock_bars(request)
df = bars.df

# マルチインデックス（symbol, timestamp）
# 特定銘柄のデータ抽出
aapl = df.loc["AAPL"]
```

### ページネーション

大量のデータを取得する場合、APIは自動的にページネーションを処理する。alpaca-py SDKが内部で処理するため、通常は意識する必要がない。

ただし、長期間×短い時間足の組み合わせはデータ量が大きいため注意：

```python
# 注意: 1分足×1年 = 約100,000バー
# リクエストが遅くなる可能性がある
# 必要な期間だけ取得すること
```

## リアルタイムデータ

### 最新のQuote

```python
from alpaca.data.requests import StockLatestQuoteRequest

request = StockLatestQuoteRequest(symbol_or_symbols=["AAPL"])
quote = data_client.get_stock_latest_quote(request)

aapl_quote = quote["AAPL"]
print(f"Bid: ${aapl_quote.bid_price} x {aapl_quote.bid_size}")
print(f"Ask: ${aapl_quote.ask_price} x {aapl_quote.ask_size}")
print(f"Spread: ${aapl_quote.ask_price - aapl_quote.bid_price:.4f}")
```

### 最新のTrade

```python
from alpaca.data.requests import StockLatestTradeRequest

request = StockLatestTradeRequest(symbol_or_symbols=["AAPL"])
trade = data_client.get_stock_latest_trade(request)

aapl_trade = trade["AAPL"]
print(f"Price: ${aapl_trade.price}")
print(f"Size: {aapl_trade.size}")
```

### スナップショット

```python
from alpaca.data.requests import StockSnapshotRequest

request = StockSnapshotRequest(symbol_or_symbols=["AAPL"])
snapshot = data_client.get_stock_snapshot(request)

aapl = snapshot["AAPL"]
print(f"Latest Trade: ${aapl.latest_trade.price}")
print(f"Latest Quote: ${aapl.latest_quote.bid_price}/{aapl.latest_quote.ask_price}")
print(f"Daily Bar: O={aapl.daily_bar.open} H={aapl.daily_bar.high} "
      f"L={aapl.daily_bar.low} C={aapl.daily_bar.close}")
print(f"Previous Daily Bar Close: ${aapl.previous_daily_bar.close}")
```

## WebSocket ストリーミング

```python
from alpaca.data.live import StockDataStream

stream = StockDataStream(api_key, secret_key)

async def on_bar(bar):
    print(f"{bar.symbol}: Close=${bar.close}, Volume={bar.volume}")

async def on_trade(trade):
    print(f"{trade.symbol}: ${trade.price} x {trade.size}")

async def on_quote(quote):
    print(f"{quote.symbol}: Bid=${quote.bid_price} Ask=${quote.ask_price}")

# サブスクライブ
stream.subscribe_bars(on_bar, "AAPL", "MSFT")
stream.subscribe_trades(on_trade, "AAPL")
stream.subscribe_quotes(on_quote, "AAPL")

# ストリーム開始
stream.run()
```

## ニュースAPI

```python
from alpaca.data.requests import NewsRequest

request = NewsRequest(
    symbols=["AAPL"],
    start=datetime(2024, 1, 1),
    limit=10
)
news = data_client.get_news(request)

for article in news.news:
    print(f"[{article.created_at}] {article.headline}")
    print(f"  Source: {article.source}")
    print(f"  Symbols: {article.symbols}")
    print(f"  URL: {article.url}")
    print()
```

## 無料プラン（IEX）の制限

| 項目 | 無料（IEX） | 有料（SIP） |
|------|------------|------------|
| データソース | IEXのみ | 全取引所 |
| リアルタイムquote | 15分遅延 | リアルタイム |
| ヒストリカルデータ | IEX取引のみ | 全取引所統合 |
| 出来高の正確性 | IEX分のみ | 市場全体 |

**注意**: IEXデータはIEX取引所の取引のみを含むため、出来高が実際の市場全体より少なく表示される。バックテストの出来高フィルターに影響する可能性がある。

## データ取得のベストプラクティス

```python
import time

def fetch_historical_data(client, symbols, timeframe, start, end, delay=0.3):
    """レート制限を考慮したデータ取得"""
    all_data = {}

    for symbol in symbols:
        try:
            request = StockBarsRequest(
                symbol_or_symbols=[symbol],
                timeframe=timeframe,
                start=start,
                end=end
            )
            bars = client.get_stock_bars(request)
            all_data[symbol] = bars.df.loc[symbol] if symbol in bars.df.index.get_level_values(0) else None
            time.sleep(delay)  # レート制限対策
        except Exception as e:
            print(f"Error fetching {symbol}: {e}")
            all_data[symbol] = None

    return all_data
```
