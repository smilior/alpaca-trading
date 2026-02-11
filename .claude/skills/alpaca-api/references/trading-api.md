# Trading API リファレンス

## 注文の種類

### 1. Market Order（成行注文）

```python
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

request = MarketOrderRequest(
    symbol="AAPL",
    qty=100,                        # 株数
    side=OrderSide.BUY,
    time_in_force=TimeInForce.DAY   # 当日有効
)
order = client.submit_order(request)
```

**注意**: 成行注文は約定価格が保証されない。スリッページが発生する可能性がある。

### 2. Limit Order（指値注文）

```python
from alpaca.trading.requests import LimitOrderRequest

request = LimitOrderRequest(
    symbol="AAPL",
    qty=100,
    side=OrderSide.BUY,
    time_in_force=TimeInForce.GTC,  # キャンセルまで有効
    limit_price=150.00
)
order = client.submit_order(request)
```

### 3. Stop Order（逆指値注文）

```python
from alpaca.trading.requests import StopOrderRequest

request = StopOrderRequest(
    symbol="AAPL",
    qty=100,
    side=OrderSide.SELL,
    time_in_force=TimeInForce.GTC,
    stop_price=145.00               # この価格以下で成行売り
)
order = client.submit_order(request)
```

### 4. Stop Limit Order（逆指値指値注文）

```python
from alpaca.trading.requests import StopLimitOrderRequest

request = StopLimitOrderRequest(
    symbol="AAPL",
    qty=100,
    side=OrderSide.SELL,
    time_in_force=TimeInForce.GTC,
    stop_price=145.00,              # トリガー価格
    limit_price=144.50              # 指値（最低この価格で売り）
)
order = client.submit_order(request)
```

### 5. Trailing Stop Order（トレーリングストップ）

```python
from alpaca.trading.requests import TrailingStopOrderRequest

request = TrailingStopOrderRequest(
    symbol="AAPL",
    qty=100,
    side=OrderSide.SELL,
    time_in_force=TimeInForce.GTC,
    trail_percent=2.0               # 高値から2%下落でトリガー
    # または trail_price=3.00      # 高値から$3下落でトリガー
)
order = client.submit_order(request)
```

## Time in Force（注文の有効期限）

| 値 | 意味 | 用途 |
|----|------|------|
| `DAY` | 当日のみ有効 | 日中取引 |
| `GTC` | キャンセルまで有効 | ストップロス注文 |
| `IOC` | 即時約定or即キャンセル | 大量注文の部分約定 |
| `FOK` | 全数量約定orキャンセル | 全数量が必要な場合 |

## 注文ステータスのライフサイクル

```
new → accepted → filled（約定）
new → accepted → partially_filled → filled
new → accepted → canceled
new → accepted → expired
new → rejected（口座残高不足等）
new → pending_new（市場クローズ中）
```

```python
# 注文ステータスの確認
order = client.get_order_by_id(order_id)
print(f"Status: {order.status}")
print(f"Filled Qty: {order.filled_qty}")
print(f"Filled Avg Price: {order.filled_avg_price}")
```

## ポジション管理

```python
# 全ポジション取得
positions = client.get_all_positions()
for position in positions:
    print(f"{position.symbol}: {position.qty}株 "
          f"@ ${float(position.avg_entry_price):.2f} "
          f"PnL: ${float(position.unrealized_pl):.2f}")

# 特定銘柄のポジション
position = client.get_open_position("AAPL")

# ポジションクローズ（全数量）
client.close_position("AAPL")

# ポジション部分クローズ
from alpaca.trading.requests import ClosePositionRequest
close_request = ClosePositionRequest(qty=50)
client.close_position("AAPL", close_position_request=close_request)

# 全ポジションクローズ（緊急時）
client.close_all_positions(cancel_orders=True)
```

## 口座情報

```python
account = client.get_account()

print(f"口座ステータス: {account.status}")
print(f"現金残高: ${float(account.cash):,.2f}")
print(f"ポートフォリオ価値: ${float(account.portfolio_value):,.2f}")
print(f"購買力: ${float(account.buying_power):,.2f}")
print(f"日次損益: ${float(account.equity) - float(account.last_equity):,.2f}")
print(f"PDTフラグ: {account.pattern_day_trader}")
```

## 注文のキャンセル

```python
# 特定の注文をキャンセル
client.cancel_order_by_id(order_id)

# 全注文キャンセル
client.cancel_orders()
```

## Bracket Order（OCO注文）

エントリーと同時にストップロスと利確を設定する。

```python
from alpaca.trading.requests import (
    MarketOrderRequest, StopLossRequest, TakeProfitRequest
)

request = MarketOrderRequest(
    symbol="AAPL",
    qty=100,
    side=OrderSide.BUY,
    time_in_force=TimeInForce.GTC,
    order_class="bracket",
    stop_loss=StopLossRequest(stop_price=145.00),
    take_profit=TakeProfitRequest(limit_price=160.00)
)
order = client.submit_order(request)
```

**推奨**: 全てのエントリーにブラケット注文を使用し、ストップロスを必ず設定せよ。

## 注文の実用パターン

### パターン: 安全なエントリー

```python
def safe_entry(client, symbol, side, qty, stop_price, take_profit_price=None):
    """安全なエントリー（必ずストップロス付き）"""

    # ストップロスなしのエントリーは拒否
    if stop_price is None:
        raise ValueError("ストップロスなしのエントリーは許可されていません")

    if take_profit_price:
        # ブラケット注文
        request = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=side,
            time_in_force=TimeInForce.GTC,
            order_class="bracket",
            stop_loss=StopLossRequest(stop_price=stop_price),
            take_profit=TakeProfitRequest(limit_price=take_profit_price)
        )
    else:
        # OTO注文（エントリー + ストップロス）
        request = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=side,
            time_in_force=TimeInForce.GTC,
            order_class="oto",
            stop_loss=StopLossRequest(stop_price=stop_price)
        )

    return client.submit_order(request)
```
