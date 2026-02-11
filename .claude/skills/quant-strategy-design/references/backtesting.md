# バックテスト リファレンス

## バックテストとは

過去の市場データに対してトレーディング戦略を適用し、仮にその戦略で取引していたらどうなったかをシミュレーションすること。

**バックテストの目的**: 戦略の有効性を検証すること。ただし「過去に有効だった＝未来も有効」ではないことを常に意識せよ。

## Pythonでのバックテスト実装

### 方法1: vectorbt（ベクトル化バックテスト）

```python
import vectorbt as vbt
import pandas as pd

# データ取得
price = vbt.YFData.download("AAPL", start="2020-01-01").get("Close")

# 移動平均クロスオーバー戦略
fast_ma = vbt.MA.run(price, window=10)
slow_ma = vbt.MA.run(price, window=50)

entries = fast_ma.ma_crossed_above(slow_ma)
exits = fast_ma.ma_crossed_below(slow_ma)

# バックテスト実行
portfolio = vbt.Portfolio.from_signals(
    price, entries, exits,
    init_cash=100000,
    fees=0.001,        # 手数料0.1%
    slippage=0.001     # スリッページ0.1%
)

# 結果
print(portfolio.stats())
```

**長所**: 高速（ベクトル演算）、パラメータ最適化が容易
**短所**: 複雑なロジック（条件分岐等）が書きにくい

### 方法2: backtesting.py

```python
from backtesting import Backtest, Strategy
from backtesting.lib import crossover
import pandas as pd

class MACrossStrategy(Strategy):
    fast_period = 10
    slow_period = 50

    def init(self):
        self.fast_ma = self.I(
            lambda x: pd.Series(x).rolling(self.fast_period).mean(),
            self.data.Close
        )
        self.slow_ma = self.I(
            lambda x: pd.Series(x).rolling(self.slow_period).mean(),
            self.data.Close
        )

    def next(self):
        if crossover(self.fast_ma, self.slow_ma):
            self.buy()
        elif crossover(self.slow_ma, self.fast_ma):
            self.sell()

bt = Backtest(
    data,
    MACrossStrategy,
    cash=100000,
    commission=0.001
)
stats = bt.run()
print(stats)
```

**長所**: 直感的なAPI、イベントドリブンで複雑なロジックが書ける
**短所**: vectorbtより遅い

## バックテストの落とし穴

### 落とし穴1: ルックアヘッドバイアス（先読みバイアス）

**定義**: 実際の取引時点では入手不可能な未来の情報を使ってしまうこと。

```
❌ ルックアヘッドバイアスの例:
- 当日の終値を使って当日の売買を判断する
  → 終値は市場クローズ後にしか確定しない
- 企業の四半期決算を発表日より前に使う
- 翌日の出来高でフィルタリングする

✅ 正しい実装:
- シグナルは前日のデータまでで計算
- 約定は翌日の始値（またはそれ以降）で実行
```

```python
# ❌ 悪い例（ルックアヘッド）
signal = close > sma(close, 20)  # 当日の終値でシグナル
buy_price = close                 # 当日の終値で約定

# ✅ 良い例
signal = close.shift(1) > sma(close.shift(1), 20)  # 前日までのデータ
buy_price = open_price  # 翌日の始値で約定
```

### 落とし穴2: サバイバーシップバイアス

**定義**: 現在も存在する（上場廃止されていない）銘柄だけでテストすること。

```
❌ 悪い例:
「現在のS&P500銘柄で2010年からバックテスト」
→ 2010年にはS&P500に入っていなかった銘柄や、
  その後上場廃止された銘柄が考慮されていない

✅ 良い例:
「当時の構成銘柄リストを使ってバックテスト」
または「サバイバーシップバイアスを考慮して、
結果を保守的に解釈する（実際はもう少し悪い）」
```

### 落とし穴3: スリッページの無視

```
❌ 悪い例:
手数料0、スリッページ0でバックテスト
→ バックテストの利益の大半がスリッページで消える可能性

✅ 良い例:
- 手数料: Alpacaは$0だが、スプレッドは考慮
- スリッページ: 最低0.05-0.1%を想定
- 市場インパクト: 大きな注文の場合はさらに上乗せ
```

### 落とし穴4: データマイニングバイアス

```
❌ 悪い例:
100個のパラメータ組み合わせを試して、
最も良い結果のものを「戦略が有効」と主張
→ 100回試せば、偶然良い結果が出る組み合わせがある

✅ 良い例:
仮説に基づいてパラメータ範囲を事前に決め、
結果を見る前に「成功基準」を定義しておく
```

## インサンプル / アウトサンプル分割

```
全データ期間: 2018-2024

❌ 悪い方法:
2018-2024の全期間でパラメータ最適化 → 全期間で検証
→ 同じデータで訓練と評価をしている（テスト漏れ）

✅ 良い方法:
インサンプル: 2018-2022（パラメータ最適化に使用）
アウトサンプル: 2023-2024（一切触らずに最終検証）
→ アウトサンプルは1回だけ使う（何度も使うと意味がなくなる）
```

## ウォークフォワード検証

最も信頼性の高いバックテスト手法。

```
期間: 2018-2024

Window 1: 訓練 2018-2020 → テスト 2021
Window 2: 訓練 2019-2021 → テスト 2022
Window 3: 訓練 2020-2022 → テスト 2023
Window 4: 訓練 2021-2023 → テスト 2024

各テスト期間の結果を統合して、全体の成績を評価
```

**メリット**: 異なる市場環境で戦略のロバストネスを検証できる
**デメリット**: データが多く必要、計算時間がかかる

## 統計的に有意な結果の判断

### 最低取引回数

```
統計的に意味のある結論を出すための最低取引回数:
- 最低: 30回（大まかな傾向は見える）
- 推奨: 100回以上（信頼区間が狭まる）
- 理想: 300回以上（安定した統計量）
```

### シャープレシオのt検定

```python
import numpy as np
from scipy import stats

def sharpe_significance(returns, risk_free_rate=0.0):
    """シャープレシオが統計的に有意かテスト"""
    excess_returns = returns - risk_free_rate / 252
    sharpe = np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(252)

    # t値の計算
    n = len(returns)
    t_stat = sharpe * np.sqrt(n) / np.sqrt(1 + 0.5 * sharpe**2)
    p_value = 1 - stats.t.cdf(t_stat, df=n-1)

    return {
        'sharpe_ratio': sharpe,
        't_statistic': t_stat,
        'p_value': p_value,
        'significant': p_value < 0.05
    }
```

### 判断基準

| 指標 | 基準 | 解釈 |
|------|------|------|
| p値 | < 0.05 | 統計的に有意 |
| シャープレシオ | > 0.5 | 最低ライン |
| シャープレシオ | > 1.0 | 良好 |
| シャープレシオ | > 2.0 | 非常に良好（過学習を疑え） |
| シャープレシオ | > 3.0 | ほぼ確実に過学習 |
