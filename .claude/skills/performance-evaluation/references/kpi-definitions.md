# KPI定義と計算式 リファレンス

## 1. シャープレシオ（Sharpe Ratio）

### 定義
リスク（標準偏差）1単位あたりの超過リターン。リスク調整後のリターンを測る最も一般的な指標。

### 計算式

```
Sharpe Ratio = (Rp - Rf) / σp

Rp = ポートフォリオのリターン（年率）
Rf = リスクフリーレート（年率）
σp = ポートフォリオのリターンの標準偏差（年率）
```

### 年率化の方法

```
日次リターンから年率化:
年率リターン = 日次平均リターン × 252
年率標準偏差 = 日次標準偏差 × √252

Sharpe = (日次平均リターン × 252 - Rf) / (日次標準偏差 × √252)
       = (日次平均リターン - Rf/252) / 日次標準偏差 × √252
```

### Pythonコード

```python
import numpy as np

def sharpe_ratio(returns, risk_free_rate=0.04, periods_per_year=252):
    """シャープレシオを計算（年率化）"""
    excess_returns = returns - risk_free_rate / periods_per_year
    if excess_returns.std() == 0:
        return 0.0
    return np.sqrt(periods_per_year) * excess_returns.mean() / excess_returns.std()

# 使用例
# daily_returns = pd.Series([0.001, -0.002, 0.003, ...])
# sr = sharpe_ratio(daily_returns)
```

### 判断基準

| シャープレシオ | 評価 |
|---------------|------|
| < 0 | 損失。戦略に問題あり |
| 0 - 0.5 | 不十分。改善が必要 |
| 0.5 - 1.0 | 許容範囲。ベンチマークと比較 |
| 1.0 - 2.0 | 良好 |
| 2.0 - 3.0 | 非常に良好 |
| > 3.0 | 疑わしい（過学習の可能性） |

## 2. ソルティノレシオ（Sortino Ratio）

### 定義
下方偏差（下振れリスク）のみを分母に使うシャープレシオの改良版。上方の変動（利益が大きい）をペナルティとしない。

### 計算式

```
Sortino Ratio = (Rp - Rf) / σd

σd = 下方偏差（Downside Deviation）
   = √(Σ min(Ri - Rf, 0)² / n)
```

### Pythonコード

```python
def sortino_ratio(returns, risk_free_rate=0.04, periods_per_year=252):
    """ソルティノレシオを計算"""
    excess_returns = returns - risk_free_rate / periods_per_year
    downside_returns = excess_returns[excess_returns < 0]
    if len(downside_returns) == 0 or downside_returns.std() == 0:
        return float('inf') if excess_returns.mean() > 0 else 0.0
    downside_std = np.sqrt((downside_returns ** 2).mean())
    return np.sqrt(periods_per_year) * excess_returns.mean() / downside_std
```

## 3. 最大ドローダウン（Maximum Drawdown, MDD）

### 定義
ピークから最大下落するまでの割合。「最悪のケースでどのくらい損するか」を示す。

### 計算式

```
Drawdown(t) = (Peak(t) - Value(t)) / Peak(t)
MDD = max(Drawdown(t))  for all t
```

### Pythonコード

```python
def max_drawdown(equity_curve):
    """最大ドローダウンを計算"""
    peak = equity_curve.cummax()
    drawdown = (equity_curve - peak) / peak
    return drawdown.min()  # 負の値（例: -0.15 = 15%のドローダウン）

def max_drawdown_duration(equity_curve):
    """最大ドローダウンの期間（回復までの日数）"""
    peak = equity_curve.cummax()
    drawdown = equity_curve < peak

    durations = []
    current_duration = 0
    for is_dd in drawdown:
        if is_dd:
            current_duration += 1
        else:
            if current_duration > 0:
                durations.append(current_duration)
            current_duration = 0

    return max(durations) if durations else 0
```

## 4. プロフィットファクター（Profit Factor）

### 定義
総利益を総損失で割ったもの。1以上で利益、1未満で損失。

### 計算式

```
Profit Factor = Σ(勝ちトレードの利益) / |Σ(負けトレードの損失)|
```

### Pythonコード

```python
def profit_factor(trade_pnls):
    """プロフィットファクターを計算"""
    gross_profit = trade_pnls[trade_pnls > 0].sum()
    gross_loss = abs(trade_pnls[trade_pnls < 0].sum())
    if gross_loss == 0:
        return float('inf') if gross_profit > 0 else 0.0
    return gross_profit / gross_loss
```

| プロフィットファクター | 評価 |
|----------------------|------|
| < 1.0 | 損失（総損失 > 総利益） |
| 1.0 - 1.5 | ギリギリ利益 |
| 1.5 - 2.0 | 良好 |
| 2.0 - 3.0 | 非常に良好 |
| > 3.0 | 優秀（ただし取引回数が少ない可能性） |

## 5. 勝率とペイオフレシオ

```python
def win_rate(trade_pnls):
    """勝率を計算"""
    wins = (trade_pnls > 0).sum()
    total = len(trade_pnls)
    return wins / total if total > 0 else 0.0

def payoff_ratio(trade_pnls):
    """ペイオフレシオ（平均利益 / 平均損失）"""
    avg_win = trade_pnls[trade_pnls > 0].mean() if (trade_pnls > 0).any() else 0
    avg_loss = abs(trade_pnls[trade_pnls < 0].mean()) if (trade_pnls < 0).any() else 0
    if avg_loss == 0:
        return float('inf') if avg_win > 0 else 0.0
    return avg_win / avg_loss
```

### 勝率とペイオフレシオの関係

```
期待値 = 勝率 × 平均利益 - (1 - 勝率) × 平均損失

勝率とペイオフレシオの損益分岐点:
勝率30% → ペイオフレシオ 2.33以上で期待値プラス
勝率40% → ペイオフレシオ 1.50以上
勝率50% → ペイオフレシオ 1.00以上
勝率60% → ペイオフレシオ 0.67以上
勝率70% → ペイオフレシオ 0.43以上
```

## 6. 期待値（Expectancy）

```python
def expectancy(trade_pnls):
    """1トレードあたりの期待値"""
    return trade_pnls.mean()

def expectancy_per_dollar(trade_pnls, position_sizes):
    """投資$1あたりの期待値"""
    returns = trade_pnls / position_sizes
    return returns.mean()
```

## 7. CAGR（Compound Annual Growth Rate）

```python
def cagr(start_value, end_value, years):
    """年率複利成長率"""
    return (end_value / start_value) ** (1 / years) - 1

# 使用例
# start = 100000, end = 120000, years = 0.5 (6ヶ月)
# cagr(100000, 120000, 0.5) = 0.44 = 44% 年率
```

## 8. カルマーレシオ（Calmar Ratio）

```python
def calmar_ratio(returns, periods_per_year=252):
    """CAGRを最大ドローダウンで割ったもの"""
    annual_return = returns.mean() * periods_per_year
    mdd = abs(max_drawdown(
        (1 + returns).cumprod()
    ))
    if mdd == 0:
        return float('inf') if annual_return > 0 else 0.0
    return annual_return / mdd
```

## 総合パフォーマンスレポート関数

```python
def full_performance_report(daily_returns, trade_pnls, benchmark_returns=None):
    """総合パフォーマンスレポートを生成"""
    equity = (1 + daily_returns).cumprod()

    report = {
        'total_return': equity.iloc[-1] - 1,
        'cagr': cagr(1, equity.iloc[-1], len(daily_returns) / 252),
        'sharpe_ratio': sharpe_ratio(daily_returns),
        'sortino_ratio': sortino_ratio(daily_returns),
        'max_drawdown': max_drawdown(equity),
        'calmar_ratio': calmar_ratio(daily_returns),
        'profit_factor': profit_factor(trade_pnls),
        'win_rate': win_rate(trade_pnls),
        'payoff_ratio': payoff_ratio(trade_pnls),
        'expectancy': expectancy(trade_pnls),
        'total_trades': len(trade_pnls),
        'avg_daily_return': daily_returns.mean(),
        'daily_volatility': daily_returns.std(),
        'best_day': daily_returns.max(),
        'worst_day': daily_returns.min(),
    }

    if benchmark_returns is not None:
        bench_equity = (1 + benchmark_returns).cumprod()
        report['benchmark_return'] = bench_equity.iloc[-1] - 1
        report['alpha'] = report['total_return'] - report['benchmark_return']
        report['benchmark_sharpe'] = sharpe_ratio(benchmark_returns)

    return report
```
