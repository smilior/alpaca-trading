# シグナル設計 リファレンス

## シグナル設計の基本

### エントリーシグナルとエグジットシグナル

| 種類 | 定義 | 設計のポイント |
|------|------|---------------|
| エントリー | ポジションを取る条件 | 偽シグナルを減らしつつ、機会を逃さない |
| エグジット（利確） | 利益を確定する条件 | 利益を伸ばしつつ、反転リスクを抑える |
| エグジット（損切り） | 損失を確定する条件 | 損失を限定しつつ、ノイズで切らない |
| エグジット（時間） | 一定時間後にクローズ | デッドマネーを防ぐ |

## エントリーシグナルの設計パターン

### パターン1: クロスオーバー

```python
# 短期MAが長期MAを上抜け → 買い
def crossover_signal(short_ma, long_ma):
    prev_short = short_ma.shift(1)
    prev_long = long_ma.shift(1)
    buy = (prev_short <= prev_long) & (short_ma > long_ma)
    sell = (prev_short >= prev_long) & (short_ma < long_ma)
    return buy, sell
```

**長所**: シンプル、理解しやすい
**短所**: 遅い、レンジでダマシが多い

### パターン2: 閾値ブレイク

```python
# RSIが閾値を超えたら売買
def threshold_signal(rsi, buy_threshold=30, sell_threshold=70):
    buy = (rsi.shift(1) >= buy_threshold) & (rsi < buy_threshold)
    sell = (rsi.shift(1) <= sell_threshold) & (rsi > sell_threshold)
    return buy, sell
```

**長所**: タイミングが明確
**短所**: 閾値の設定が恣意的になりがち

### パターン3: ブレイクアウト

```python
# n日間の高値/安値をブレイク
def breakout_signal(close, high, low, period=20):
    upper = high.rolling(period).max()
    lower = low.rolling(period).min()
    buy = close > upper.shift(1)
    sell = close < lower.shift(1)
    return buy, sell
```

**長所**: トレンドの初動を捉えられる
**短所**: レンジ相場でダマシ、エントリーが遅い場合がある

## 複合シグナルの組み方

### AND条件（すべて満たす）

```python
# 複数条件をANDで結合
def composite_and(close, volume):
    ma_trend = close > sma(close, 50)     # トレンド上向き
    rsi_ok = rsi(close) < 40              # RSIが低い（押し目）
    vol_ok = volume > sma(volume, 20)     # 出来高増加
    buy = ma_trend & rsi_ok & vol_ok
    return buy
```

**特徴**: 偽シグナルが減るが、取引機会も減る

### OR条件（いずれか満たす）

```python
# 複数条件をORで結合
def composite_or(close):
    signal_a = rsi(close) < 25            # 極端な売られすぎ
    signal_b = (close < bollinger_lower)  # BBの下バンド以下
    buy = signal_a | signal_b
    return buy
```

**特徴**: 取引機会が増えるが、偽シグナルも増える

### 加重スコア方式（推奨）

```python
def weighted_score_signal(close, volume, high, low):
    """各指標にスコアを付与し、合計で判断"""
    score = pd.Series(0.0, index=close.index)

    # トレンド（重み: 0.3）
    if_trend_up = (close > sma(close, 50)).astype(float)
    score += if_trend_up * 0.3

    # RSI（重み: 0.25）
    rsi_val = rsi(close)
    rsi_score = ((50 - rsi_val) / 50).clip(0, 1)  # RSI低いほど高スコア
    score += rsi_score * 0.25

    # MACD（重み: 0.25）
    macd_line, signal_line, _ = macd(close)
    macd_bull = (macd_line > signal_line).astype(float)
    score += macd_bull * 0.25

    # 出来高（重み: 0.2）
    vol_above_avg = (volume > sma(volume, 20)).astype(float)
    score += vol_above_avg * 0.2

    # スコア > 0.7 で買い
    buy = score > 0.7
    return buy, score
```

**長所**:
- 各指標の重要度を柔軟に調整できる
- 「ほぼ条件を満たしている」ケースも捉えられる
- スコアの値でポジションサイズを調整できる

**短所**:
- 重みの設定がパラメータになる（過学習リスク）
- 重みの数を最小限に保つこと

## エグジット設計

### 利確（Take Profit）

| 方式 | 設計 | メリット | デメリット |
|------|------|----------|-----------|
| 固定比率 | +3%で利確 | シンプル | トレンドを逃す |
| ATRベース | +2×ATRで利確 | ボラティリティ適応 | ATR変動に影響される |
| トレーリング | 高値から1×ATR下落で利確 | 利益を伸ばせる | 急落時に利益を削る |
| シグナル反転 | 買いシグナルの逆が出たら | 論理的一貫性 | 遅い場合がある |

### 損切り（Stop Loss）

**詳細は risk-management スキルの references/stop-loss-strategies.md を参照。**

### 時間ベースエグジット

```python
def time_exit(entry_date, current_date, max_holding_days=10):
    """保有日数が上限を超えたらエグジット"""
    holding_days = (current_date - entry_date).days
    return holding_days >= max_holding_days
```

**用途**: デッドマネー（利益も損失も出ない膠着状態）を回避

## シグナルの品質テスト

### テスト1: 予測力の確認

```python
# シグナル発生後n日のリターン分布を確認
def signal_forward_returns(signals, returns, forward_days=5):
    """シグナル発生後のリターンを集計"""
    forward_ret = returns.shift(-forward_days)
    signal_returns = forward_ret[signals]
    no_signal_returns = forward_ret[~signals]

    print(f"シグナルあり: 平均 {signal_returns.mean():.4f}")
    print(f"シグナルなし: 平均 {no_signal_returns.mean():.4f}")
    print(f"差分: {signal_returns.mean() - no_signal_returns.mean():.4f}")
```

### テスト2: シグナルの安定性

パラメータを±20%変化させても結果が大きく変わらないことを確認する。
変わる場合はオーバーフィッティングの可能性が高い。

### テスト3: 市場環境別のパフォーマンス

```
ブル相場（2019-2021）での成績: ?
ベア相場（2022前半）での成績: ?
レンジ相場（2023前半）での成績: ?

→ 3つすべてでプラスまたは、特定環境だけ強いが他では大損しないこと
```
