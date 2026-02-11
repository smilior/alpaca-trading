# ストップロス戦略 リファレンス

## ストップロスの原則

**ストップロスは「保険」である。保険なしで運転しない。ストップなしでトレードしない。**

## ストップロスの種類

### 1. 固定ストップ（Fixed Stop）

```
ルール: エントリー価格から固定%で設定
例: エントリー$100 → ストップ$97（-3%）

メリット: シンプル
デメリット: ボラティリティを考慮していない
           低ボラ銘柄では遠すぎ、高ボラ銘柄では近すぎる
```

```
❌ 悪い例:
全銘柄一律で-5%のストップ
→ ATR 0.5%の低ボラ銘柄ではストップに到達しない（無意味に遠い）
→ ATR 3%の高ボラ銘柄ではノイズで切られる（近すぎる）

✅ 良い例:
ボラティリティに応じてストップ距離を調整（→ ATRベース推奨）
```

### 2. ATRベースストップ（推奨）

```
ルール: エントリー価格からATRの倍数で設定
例: エントリー$100、ATR=$3 → ストップ$100 - 2×$3 = $94

一般的な設定:
- 短期（デイトレ〜数日）: 1.5-2.0 × ATR
- 中期（数週間）: 2.0-3.0 × ATR
- 長期（数ヶ月）: 3.0-4.0 × ATR
```

```python
def atr_stop_loss(entry_price, atr_value, multiplier=2.0, direction='long'):
    """ATRベースのストップロスを計算"""
    stop_distance = atr_value * multiplier
    if direction == 'long':
        return entry_price - stop_distance
    else:  # short
        return entry_price + stop_distance

# 例
# entry=$150, ATR(14)=$4.50, multiplier=2.0
stop = atr_stop_loss(150, 4.50, 2.0, 'long')
# = 150 - 9.0 = $141.0
```

**メリット**: ボラティリティに自動適応、ノイズで切られにくい
**推奨度**: ★★★★★

### 3. トレーリングストップ

```
ルール: 価格が有利な方向に動くたびにストップを引き上げ（引き下げ）る
例: ロングの場合、高値から2×ATR下にストップを追従

高値$100 → ストップ$94
高値$105 → ストップ$99（引き上げ）
高値$103 → ストップ$99（引き下げない）
高値$110 → ストップ$104（引き上げ）
→ $104で利確（利益$4）
```

```python
def trailing_stop(highs, atr_values, multiplier=2.0):
    """トレーリングストップを計算"""
    stops = []
    current_stop = highs.iloc[0] - atr_values.iloc[0] * multiplier

    for i in range(len(highs)):
        new_stop = highs.iloc[i] - atr_values.iloc[i] * multiplier
        current_stop = max(current_stop, new_stop)  # ロングの場合
        stops.append(current_stop)

    return pd.Series(stops, index=highs.index)
```

**メリット**: 利益を伸ばしつつ、一定以上の反落でエグジット
**デメリット**: 急落時に大きなギャップで想定以上の損失（ギャップリスク）

### 4. 時間ベースストップ

```
ルール: 一定期間内に期待した方向に動かなければエグジット
例: エントリー後5日間で+1%に達しなければクローズ

用途: デッドマネー（利益も損失も出ない膠着状態）の回避
```

```python
def time_stop(entry_date, entry_price, current_date, current_price,
              max_days=5, min_profit_pct=0.01):
    """時間ベースのストップ"""
    days_held = (current_date - entry_date).days
    profit_pct = (current_price - entry_price) / entry_price

    if days_held >= max_days and profit_pct < min_profit_pct:
        return True  # エグジット
    return False
```

### 5. テクニカルストップ（サポートライン下）

```
ルール: 直近のサポートライン（安値）の少し下にストップを設定
例: 直近安値$98 → ストップ$97.50（$0.50のバッファー）

メリット: テクニカル的に意味のある位置にストップ
デメリット: サポートの特定が主観的
```

## ストップロスの設計ガイド

### 良いストップと悪いストップ

```
❌ 悪いストップの例:

1. ストップなし
→ 「いつか戻るだろう」は希望であり戦略ではない

2. エントリー直下のストップ（$100エントリー → $99.80ストップ）
→ ノイズで即座に切られる。ATRの0.5倍以下は近すぎる

3. エントリーから10%以上離れたストップ
→ 損失が大きすぎる。ポジションサイズを適切に設定すべき

4. 心理的なキリのいい数字のストップ（$100.00ちょうど）
→ 多くのストップが集中する価格帯。ストップ狩りに遭いやすい
```

```
✅ 良いストップの例:

1. ATR 2倍のストップ
→ ボラティリティに適応し、ノイズで切られにくい

2. 直近サポート下 + ATRバッファー
→ テクニカル的に意味のある位置

3. リスクリワード比1:2以上を確保するストップ距離
→ 勝率40%でも利益が出る設計

4. キリのいい数字を少し外す（$99.73等）
→ ストップ狩りの回避
```

## ストップロスの組み合わせ

複数のストップを組み合わせて使うことを推奨する。

```python
def combined_stop_loss(
    entry_price, current_price, highest_since_entry,
    atr_value, entry_date, current_date,
    atr_multiplier=2.0, max_holding_days=10,
    max_loss_pct=0.05
):
    """複合ストップロス"""
    stops = {}

    # 1. ATRベースストップ（初期）
    stops['atr_initial'] = entry_price - atr_value * atr_multiplier

    # 2. トレーリングストップ
    stops['trailing'] = highest_since_entry - atr_value * atr_multiplier

    # 3. 最大損失ストップ
    stops['max_loss'] = entry_price * (1 - max_loss_pct)

    # 最も近い（保守的な）ストップを採用
    active_stop = max(stops.values())

    # 4. 時間ベースストップ（別途チェック）
    days_held = (current_date - entry_date).days
    time_exit = days_held >= max_holding_days

    should_exit = (current_price <= active_stop) or time_exit

    return {
        'should_exit': should_exit,
        'active_stop': active_stop,
        'stops': stops,
        'time_exit': time_exit
    }
```

## ギャップリスクへの対策

ストップロスは「株価がストップ価格に到達したら約定する」が、ギャップダウン（翌日の始値が大きく下落して始まる）の場合、ストップ価格より大幅に不利な価格で約定する。

```
ストップ: $95
翌日始値: $85（ギャップダウン）
→ $85で約定。想定の2倍の損失。

対策:
1. ポジションサイズでカバー: ギャップを想定したサイズに
2. 分散: 1銘柄に集中しない
3. 決算発表前のポジション縮小
4. 週末持ち越し時のサイズ縮小
```
