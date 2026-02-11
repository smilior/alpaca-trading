# スクリーニング基準 リファレンス

## アルゴリズムトレーディングに適した銘柄の条件

アルゴ取引では「どの銘柄を取引するか」が戦略の成否に直結する。以下の条件で銘柄をスクリーニングせよ。

## 基本スクリーニング条件

### 1. 流動性（最重要）

**なぜ重要か**: 流動性が低いと、注文が想定価格で約定しない（スリッページ）。バックテストで利益が出ても、リアルではスリッページで利益が消える。

| 条件 | 最低基準 | 推奨基準 |
|------|----------|----------|
| 日次平均出来高 | 50万株以上 | 100万株以上 |
| 日次平均売買代金 | $1,000万以上 | $5,000万以上 |

```
❌ 悪い例: 日次出来高5万株の小型株でアルゴ取引
→ 1,000株の注文でも株価を動かしてしまう

✅ 良い例: 日次出来高500万株のAAPLでアルゴ取引
→ 10,000株の注文でも市場インパクトが極小
```

### 2. スプレッド（ビッドアスクスプレッド）

**なぜ重要か**: スプレッドは「取引するだけで払うコスト」。スプレッドが広いと、エントリーした瞬間に含み損を抱える。

| 条件 | 最低基準 | 推奨基準 |
|------|----------|----------|
| スプレッド比率 | 0.10%以下 | 0.05%以下 |
| 絶対スプレッド | $0.05以下 | $0.02以下 |

```
スプレッド比率の計算:
spread_pct = (ask - bid) / ((ask + bid) / 2) * 100
```

### 3. 時価総額

| 条件 | 最低基準 | 推奨基準 |
|------|----------|----------|
| 時価総額 | $1B（10億ドル）以上 | $10B以上 |

**理由**: 小型株はニュースや大口注文で急激に動き、予測が困難。

### 4. ボラティリティ

戦略によって適正なボラティリティは異なる。

| 戦略タイプ | 推奨ATR% | 理由 |
|-----------|----------|------|
| トレンドフォロー | 1.5-3.0% | 一定の値動きが必要 |
| ミーンリバーション | 1.0-2.0% | 極端なボラは逆張りリスク大 |
| ペアトレード | 低相関の2銘柄 | 相関の崩れが収益源 |

```python
# ATR%の計算
import pandas as pd

def calc_atr_pct(bars_df, period=14):
    high = bars_df['high']
    low = bars_df['low']
    close = bars_df['close'].shift(1)

    tr = pd.concat([
        high - low,
        (high - close).abs(),
        (low - close).abs()
    ], axis=1).max(axis=1)

    atr = tr.rolling(period).mean()
    atr_pct = atr / bars_df['close'] * 100
    return atr_pct
```

### 5. 価格帯

| 条件 | 基準 | 理由 |
|------|------|------|
| 最低株価 | $5以上 | ペニーストック除外（規制・流動性リスク） |
| 推奨価格帯 | $10-$500 | 適切な流動性と発注しやすさ |

## 戦略別スクリーニングテンプレート

### テンプレート1: デイトレード/スイングトレード用

```python
screening_criteria = {
    'min_avg_volume': 1_000_000,      # 日次出来高100万株以上
    'min_market_cap': 10_000_000_000, # 時価総額$10B以上
    'max_spread_pct': 0.05,           # スプレッド0.05%以下
    'min_price': 10,                  # $10以上
    'max_price': 500,                 # $500以下
    'min_atr_pct': 1.0,               # ATR% 1%以上
    'max_atr_pct': 5.0,               # ATR% 5%以下
}
```

### テンプレート2: 中長期（週次リバランス）用

```python
screening_criteria = {
    'min_avg_volume': 500_000,        # 日次出来高50万株以上
    'min_market_cap': 5_000_000_000,  # 時価総額$5B以上
    'max_spread_pct': 0.10,           # スプレッド0.10%以下
    'min_price': 5,                   # $5以上
    'sectors': ['Technology', 'Health Care', 'Financials'],  # セクター絞り込み
}
```

### テンプレート3: ニュースベース戦略用

```python
screening_criteria = {
    'min_avg_volume': 2_000_000,      # 出来高が多い（ニュースで動く銘柄）
    'min_market_cap': 10_000_000_000, # 大型株（ニュースカバレッジが多い）
    'index_member': ['S&P500'],       # S&P500構成銘柄
    'has_options': True,              # オプション市場あり（センチメント指標として）
}
```

## スクリーニングの実施手順

```
Step 1: ユニバース定義
  → S&P500 or Russell 1000 or 全米国株 から開始

Step 2: 基本フィルター適用
  → 流動性、時価総額、価格帯でフィルタリング

Step 3: 戦略固有フィルター適用
  → ボラティリティ、セクター等の条件追加

Step 4: 銘柄リスト確定
  → 20-50銘柄程度に絞り込み

Step 5: 定期的な見直し
  → 月次でスクリーニングを再実行
  → 条件を満たさなくなった銘柄を除外
```

## スクリーニング実装例（Alpaca + yfinance）

```python
from alpaca.data import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

def screen_stocks(symbols, criteria, alpaca_client):
    """銘柄スクリーニングを実行する"""
    results = []

    for symbol in symbols:
        try:
            # yfinanceで基本情報取得
            ticker = yf.Ticker(symbol)
            info = ticker.info

            market_cap = info.get('marketCap', 0)
            avg_volume = info.get('averageVolume', 0)
            price = info.get('currentPrice', 0)

            # 基本フィルター
            if market_cap < criteria['min_market_cap']:
                continue
            if avg_volume < criteria['min_avg_volume']:
                continue
            if price < criteria.get('min_price', 0):
                continue
            if price > criteria.get('max_price', float('inf')):
                continue

            results.append({
                'symbol': symbol,
                'market_cap': market_cap,
                'avg_volume': avg_volume,
                'price': price,
                'sector': info.get('sector', 'N/A')
            })

        except Exception as e:
            continue

    return pd.DataFrame(results)
```
