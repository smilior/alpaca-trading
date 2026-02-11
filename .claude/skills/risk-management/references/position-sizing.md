# ポジションサイズ リファレンス

## ポジションサイズが重要な理由

同じ戦略でも、ポジションサイズの決め方で結果が天と地ほど変わる。

```
例: 勝率60%、平均利益2%、平均損失1.5%の戦略

資金の10%でトレード:
→ 100回後の期待成長率: 安定的に増加

資金の50%でトレード:
→ 100回後: 数回の連続損失で破産する可能性大

資金の90%でトレード:
→ 最初の2-3回の損失で回復不能
```

## ポジションサイズ手法一覧

### 1. 固定金額法

```
ルール: 毎回同じ金額を投資する
例: 毎回$10,000投資

メリット: 最もシンプル
デメリット: 資金が増えてもポジションが同じ（複利効果なし）
         資金が減ってもポジションが同じ（リスク増大）
推奨度: ★★☆☆☆（初心者の練習用のみ）
```

### 2. 固定比率法

```
ルール: 総資金の一定比率を投資する
例: 毎回、総資金の20%を投資

メリット: 資金に応じてポジションが自動調整
デメリット: ストップロスの距離を考慮していない
推奨度: ★★★☆☆
```

### 3. 最大リスク比率法（推奨）

```
ルール: 1トレードの最大損失を総資金の一定比率に制限
例: 1トレードの最大損失 = 総資金の2%

計算式:
ポジションサイズ = (総資金 × リスク比率) / (エントリー価格 - ストップ価格)
```

```python
def max_risk_position_size(
    capital: float,
    risk_pct: float,        # 例: 0.02 (2%)
    entry_price: float,
    stop_price: float
) -> int:
    risk_per_share = abs(entry_price - stop_price)
    if risk_per_share == 0:
        return 0
    max_risk = capital * risk_pct
    shares = int(max_risk / risk_per_share)
    return shares

# 例
# 資金: $100,000
# リスク: 2%
# エントリー: $150
# ストップ: $145（ATR 1.5倍下）
shares = max_risk_position_size(100000, 0.02, 150, 145)
# = int(2000 / 5) = 400株
```

**メリット**: ストップロスの距離に応じてサイズが自動調整される
**推奨度**: ★★★★★

### 4. ケリー基準（Kelly Criterion）

```
Kelly % = W - (1 - W) / R

W = 勝率
R = ペイオフレシオ（平均利益 / 平均損失）

例:
勝率55%、平均利益$200、平均損失$150
R = 200 / 150 = 1.33
Kelly = 0.55 - (1 - 0.55) / 1.33 = 0.55 - 0.338 = 0.212

→ 各トレードで資金の21.2%をリスクにさらすべき
```

**重大な注意点**:
- ケリー基準は「勝率とペイオフレシオが正確にわかっている」前提
- 実際にはこれらは推定値であり、過大評価されがち
- **フルケリーは危険**。実際の値が推定より悪いと急速に破産する

### 5. ハーフケリー（推奨）

```
ハーフケリー % = Kelly % / 2

上記の例:
ハーフケリー = 0.212 / 2 = 0.106 → 約10.6%
```

**メリット**: ケリーの約75%のリターンを維持しつつ、ドローダウンを大幅に削減
**推奨度**: ★★★★☆

### 手法比較

| 手法 | シンプルさ | リスク管理 | 複利効果 | 推奨 |
|------|-----------|-----------|----------|------|
| 固定金額 | ★★★★★ | ★☆☆☆☆ | ☆☆☆☆☆ | 練習用のみ |
| 固定比率 | ★★★★☆ | ★★★☆☆ | ★★★☆☆ | 初心者 |
| 最大リスク比率 | ★★★☆☆ | ★★★★★ | ★★★★☆ | **メイン推奨** |
| ケリー基準 | ★★☆☆☆ | ★★☆☆☆ | ★★★★★ | 使用注意 |
| ハーフケリー | ★★☆☆☆ | ★★★★☆ | ★★★★☆ | 上級者推奨 |

## 実践的なガイドライン

### 初期段階（ペーパートレーディング〜リアル初期）

```
- 1トレードの最大リスク: 1%
- 最大同時ポジション: 3
- 最大ポートフォリオリスク: 3%
```

### 安定運用段階（3ヶ月以上の実績あり）

```
- 1トレードの最大リスク: 2%
- 最大同時ポジション: 5-8
- 最大ポートフォリオリスク: 8%
```

### ポジションサイズ算出の総合コード

```python
def calculate_full_position(
    capital: float,
    risk_pct: float,
    entry_price: float,
    stop_price: float,
    max_position_pct: float = 0.25,  # 最大ポジション比率
    max_positions: int = 5
) -> dict:
    """総合的なポジションサイズ計算"""

    # リスクベースのサイズ
    risk_per_share = abs(entry_price - stop_price)
    if risk_per_share == 0:
        return {'shares': 0, 'reason': 'ストップロス距離がゼロ'}

    max_risk = capital * risk_pct
    shares_by_risk = int(max_risk / risk_per_share)

    # 最大ポジション比率による制限
    max_position_value = capital * max_position_pct
    shares_by_position = int(max_position_value / entry_price)

    # 最大同時ポジション数による制限
    per_position_capital = capital / max_positions
    shares_by_count = int(per_position_capital / entry_price)

    # 最も保守的なサイズを採用
    final_shares = min(shares_by_risk, shares_by_position, shares_by_count)

    return {
        'shares': final_shares,
        'position_value': final_shares * entry_price,
        'max_loss': final_shares * risk_per_share,
        'risk_pct_actual': (final_shares * risk_per_share) / capital,
        'position_pct': (final_shares * entry_price) / capital,
        'limiting_factor': 'risk' if final_shares == shares_by_risk
                          else 'position_pct' if final_shares == shares_by_position
                          else 'max_positions'
    }
```
