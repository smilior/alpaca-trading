# テクニカル指標 リファレンス

## 主要テクニカル指標一覧

### 1. 移動平均線（Moving Average）

#### 単純移動平均（SMA）
```
SMA(n) = (P1 + P2 + ... + Pn) / n
```

#### 指数移動平均（EMA）
```
EMA(t) = α × P(t) + (1 - α) × EMA(t-1)
α = 2 / (n + 1)
```

| 期間 | 用途 |
|------|------|
| 5-10日 | 短期トレンド |
| 20-50日 | 中期トレンド |
| 100-200日 | 長期トレンド |

**使い方**:
- ゴールデンクロス: 短期MA > 長期MA → 買いシグナル
- デッドクロス: 短期MA < 長期MA → 売りシグナル
- 価格とMAの位置関係でトレンド判定

**長所**: シンプル、トレンド判定に有効
**短所**: 遅行指標（トレンド転換を遅れて検出）、レンジ相場でダマシが多い

```python
import pandas as pd

def sma(series, period):
    return series.rolling(window=period).mean()

def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()
```

### 2. RSI（Relative Strength Index）

```
RS = (n日間の平均上昇幅) / (n日間の平均下落幅)
RSI = 100 - (100 / (1 + RS))
```

通常n=14を使用。

| RSI値 | 解釈 |
|-------|------|
| > 70 | 買われすぎ |
| 30-70 | 中立 |
| < 30 | 売られすぎ |

**長所**: 0-100の範囲で正規化されているため比較しやすい
**短所**: 強いトレンド中は長期間70以上/30以下にとどまる

```python
def rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))
```

### 3. MACD（Moving Average Convergence Divergence）

```
MACD Line = EMA(12) - EMA(26)
Signal Line = EMA(9) of MACD Line
Histogram = MACD Line - Signal Line
```

**使い方**:
- MACD > Signal → 買いシグナル
- MACD < Signal → 売りシグナル
- ヒストグラムの変化でモメンタムの強弱を判定

**長所**: トレンドとモメンタムの両方を捉える
**短所**: レンジ相場でダマシが多い、パラメータ3つでやや複雑

```python
def macd(series, fast=12, slow=26, signal=9):
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram
```

### 4. ボリンジャーバンド（Bollinger Bands）

```
Middle Band = SMA(20)
Upper Band = SMA(20) + 2 × σ(20)
Lower Band = SMA(20) - 2 × σ(20)
```

**使い方**:
- バンド幅が狭まる → ボラティリティ収縮（ブレイクアウト前兆）
- 上バンドタッチ → 買われすぎの可能性
- 下バンドタッチ → 売られすぎの可能性
- %Bインジケーター: (Price - Lower) / (Upper - Lower)

**長所**: ボラティリティに自動適応
**短所**: トレンド相場ではバンドウォーク（上/下バンドに沿って動き続ける）が発生

```python
def bollinger_bands(series, period=20, num_std=2):
    middle = sma(series, period)
    std = series.rolling(window=period).std()
    upper = middle + num_std * std
    lower = middle - num_std * std
    return upper, middle, lower
```

### 5. ATR（Average True Range）

```
True Range = max(
    High - Low,
    |High - Previous Close|,
    |Low - Previous Close|
)
ATR = SMA(True Range, n)  ※通常n=14
```

**用途**: ボラティリティの測定、ストップロスの距離設定

```python
def atr(high, low, close, period=14):
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()
```

### 6. 出来高指標

#### OBV（On-Balance Volume）
```
OBV(t) = OBV(t-1) + Volume  (if Close > Previous Close)
OBV(t) = OBV(t-1) - Volume  (if Close < Previous Close)
```

#### VWAP（Volume Weighted Average Price）
```
VWAP = Σ(Price × Volume) / Σ(Volume)
```

## 指標の組み合わせパターン

### パターン1: トレンド + モメンタム
```
MA（トレンド方向）+ RSI（エントリータイミング）
例: 50MA上向き + RSI<40 → 買い（押し目買い）
```

### パターン2: トレンド + ボラティリティ
```
MA（トレンド方向）+ ATR（ポジションサイズ）
例: トレンド方向にエントリー、ATRでストップ幅を調整
```

### パターン3: モメンタム + 出来高
```
MACD（モメンタム）+ OBV（出来高確認）
例: MACDクロス + OBV上昇 → 買い（出来高で裏付け）
```

## 各指標の長所・短所まとめ

| 指標 | 種類 | 長所 | 短所 | 最適市場環境 |
|------|------|------|------|-------------|
| SMA/EMA | トレンド | シンプル、ロバスト | 遅行、レンジでダマシ | トレンド相場 |
| RSI | モメンタム | 正規化、比較容易 | トレンドで無効 | レンジ相場 |
| MACD | トレンド+モメンタム | 複合情報 | パラメータ多い | トレンド転換点 |
| BB | ボラティリティ | 自動適応 | バンドウォーク | レンジ相場 |
| ATR | ボラティリティ | リスク管理に必須 | 方向性なし | 全市場環境 |
