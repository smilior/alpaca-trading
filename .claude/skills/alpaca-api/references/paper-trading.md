# ペーパートレーディング リファレンス

## 概要

Alpacaのペーパートレーディングは仮想資金で実際の市場データに基づいて取引をシミュレーションする環境。

## ペーパートレーディングのエンドポイント

```
Paper: https://paper-api.alpaca.markets
Live:  https://api.alpaca.markets
```

alpaca-py SDKでは `paper=True` パラメータで切り替え：

```python
from alpaca.trading.client import TradingClient

# ペーパー
paper_client = TradingClient(api_key, secret_key, paper=True)

# リアル
# live_client = TradingClient(api_key, secret_key, paper=False)
```

## リアルとの挙動差異

### 1. スリッページ

| 項目 | ペーパー | リアル |
|------|---------|--------|
| 成行注文の約定価格 | 直近の取引価格付近 | 市場の状態による |
| スリッページ | ほぼなし | あり（特に低流動性銘柄） |
| 市場インパクト | なし | あり（大量注文時） |

**注意**: ペーパーの成績はリアルより良くなる傾向がある。ペーパーでギリギリ利益の戦略は、リアルでは損失になる可能性が高い。

### 2. 約定速度

| 項目 | ペーパー | リアル |
|------|---------|--------|
| 成行注文 | ほぼ即時 | 市場の状態による |
| 指値注文 | 価格到達で即約定 | 順番待ち（FIFO） |
| 部分約定 | 発生しにくい | 発生する |

**注意**: リアルでは指値注文が価格に到達しても約定しないことがある（先に注文していた人が優先される）。

### 3. その他の差異

| 項目 | ペーパー | リアル |
|------|---------|--------|
| 配当 | 反映されない場合がある | 反映される |
| 株式分割 | 反映に遅れがある場合 | 即時反映 |
| ハードトゥボロー（空売り制限） | 制限なし | 在庫による制限あり |
| PTDルール | 適用 | 適用 |

## 初期資金の設定

ペーパーアカウントの初期資金はデフォルトで$100,000。

### リセット方法

ペーパーアカウントはAlpacaダッシュボードからリセット可能：
1. https://app.alpaca.markets にログイン
2. Paper Trading を選択
3. Settings → Reset Account

**注意**: リセットすると全ポジション・注文・取引履歴が削除される。バックアップを取ること。

## テスト用の推奨パターン

### パターン1: 基本的な接続テスト

```python
def test_connection(client):
    """API接続テスト"""
    try:
        account = client.get_account()
        print(f"✅ 接続成功")
        print(f"  口座ステータス: {account.status}")
        print(f"  残高: ${float(account.cash):,.2f}")
        return True
    except Exception as e:
        print(f"❌ 接続失敗: {e}")
        return False
```

### パターン2: 小口注文テスト

```python
def test_small_order(client, symbol="AAPL"):
    """小口注文テスト（1株の買い→売り）"""
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
    import time

    # 買い注文
    buy_request = MarketOrderRequest(
        symbol=symbol,
        qty=1,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY
    )
    buy_order = client.submit_order(buy_request)
    print(f"✅ 買い注文送信: {buy_order.id}")

    # 約定待ち
    time.sleep(2)

    # 注文状態確認
    order = client.get_order_by_id(buy_order.id)
    print(f"  ステータス: {order.status}")
    print(f"  約定価格: {order.filled_avg_price}")

    # ポジション確認
    position = client.get_open_position(symbol)
    print(f"  ポジション: {position.qty}株")

    # 売り注文（クローズ）
    client.close_position(symbol)
    print(f"✅ ポジションクローズ完了")
```

### パターン3: ストップロスのテスト

```python
def test_bracket_order(client, symbol="AAPL"):
    """ブラケット注文テスト"""
    from alpaca.trading.requests import (
        MarketOrderRequest, StopLossRequest, TakeProfitRequest
    )

    # 現在の価格を取得
    from alpaca.data import StockHistoricalDataClient
    from alpaca.data.requests import StockLatestTradeRequest

    data_client = StockHistoricalDataClient(api_key, secret_key)
    trade = data_client.get_stock_latest_trade(
        StockLatestTradeRequest(symbol_or_symbols=[symbol])
    )
    current_price = float(trade[symbol].price)

    # ブラケット注文
    request = MarketOrderRequest(
        symbol=symbol,
        qty=1,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.GTC,
        order_class="bracket",
        stop_loss=StopLossRequest(
            stop_price=round(current_price * 0.95, 2)  # -5%
        ),
        take_profit=TakeProfitRequest(
            limit_price=round(current_price * 1.05, 2)  # +5%
        )
    )
    order = client.submit_order(request)
    print(f"✅ ブラケット注文送信: {order.id}")
    print(f"  ストップ: ${round(current_price * 0.95, 2)}")
    print(f"  利確: ${round(current_price * 1.05, 2)}")
```

## ペーパーからリアルへの移行時の注意

1. **コードの変更は最小限**: `paper=True` → `paper=False` のみ
2. **環境変数でAPIキーを分離**: ペーパーとリアルで別のAPIキーを使用
3. **初回はポジションサイズを最小に**: リアルでの挙動確認のため
4. **スリッページの実測**: ペーパーとの差を記録
5. **段階的に資金を増やす**: 1週間ごとにサイズを2倍にする等
