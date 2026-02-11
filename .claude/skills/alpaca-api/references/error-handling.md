# エラーハンドリング リファレンス

## よくあるエラーコードと対処法

### HTTP 403: Forbidden

```
原因: APIキーが無効、または権限不足
対処:
1. APIキーが正しく設定されているか確認
2. ペーパー用キーでリアルAPI、またはその逆にアクセスしていないか確認
3. Alpacaダッシュボードでキーが有効か確認
```

### HTTP 422: Unprocessable Entity

```
原因: リクエストのパラメータが不正
よくあるケース:
- qty が0以下
- limit_price が不正（負の値等）
- symbol が存在しない
- time_in_force が注文タイプと互換性がない

対処: リクエストパラメータを検証してから送信
```

### HTTP 429: Too Many Requests

```
原因: レート制限超過
対処:
1. リクエスト間にsleepを入れる（0.3-1.0秒）
2. バッチリクエストを活用する
3. 指数バックオフでリトライ
```

```python
import time

def retry_with_backoff(func, max_retries=3, base_delay=1.0):
    """指数バックオフ付きリトライ"""
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if '429' in str(e) and attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(f"レート制限。{delay}秒後にリトライ...")
                time.sleep(delay)
            else:
                raise
```

### Insufficient Buying Power（購買力不足）

```
原因: 注文に必要な資金が不足
対処:
1. account.buying_power を確認
2. 未約定の注文が購買力を消費していないか確認
3. ポジションサイズを調整

確認コード:
```

```python
def check_buying_power(client, required_amount):
    """購買力チェック"""
    account = client.get_account()
    buying_power = float(account.buying_power)

    if buying_power < required_amount:
        print(f"⚠️ 購買力不足: 必要=${required_amount:,.2f}, "
              f"利用可能=${buying_power:,.2f}")
        return False
    return True
```

### Market Closed（市場クローズ中）

```
原因: 市場時間外に成行注文を出した
対処:
1. 市場時間を確認してから注文
2. 時間外取引が可能な注文タイプを使用
3. 翌営業日にスケジュール
```

```python
from alpaca.trading.client import TradingClient

def is_market_open(client):
    """市場が開いているか確認"""
    clock = client.get_clock()
    return clock.is_open

def get_next_open(client):
    """次の市場オープン時間を取得"""
    clock = client.get_clock()
    return clock.next_open

# 使用例
if not is_market_open(client):
    next_open = get_next_open(client)
    print(f"市場クローズ中。次のオープン: {next_open}")
    # 成行注文は出さない
    # 指値/逆指値注文はGTCで出せる
```

## 包括的なエラーハンドリングパターン

```python
from alpaca.common.exceptions import APIError
import logging

logger = logging.getLogger(__name__)

class AlpacaOrderManager:
    """安全な注文管理クラス"""

    def __init__(self, client):
        self.client = client

    def submit_order_safe(self, request):
        """安全な注文送信"""
        try:
            # 事前チェック
            if not self._pre_order_check(request):
                return None

            # 注文送信
            order = self.client.submit_order(request)
            logger.info(f"注文送信成功: {order.id} "
                       f"{request.symbol} {request.side} {request.qty}")
            return order

        except APIError as e:
            logger.error(f"API Error: {e.status_code} - {e.message}")
            self._handle_api_error(e)
            return None

        except Exception as e:
            logger.error(f"予期しないエラー: {e}")
            return None

    def _pre_order_check(self, request):
        """注文前のチェック"""
        # 市場時間チェック（成行注文の場合）
        if request.__class__.__name__ == 'MarketOrderRequest':
            if not is_market_open(self.client):
                logger.warning("市場クローズ中。成行注文は送信しない")
                return False

        # 購買力チェック
        # (指値注文の場合はlimit_price、成行の場合は概算)
        return True

    def _handle_api_error(self, error):
        """APIエラーの処理"""
        if error.status_code == 403:
            logger.critical("認証エラー。APIキーを確認")
        elif error.status_code == 422:
            logger.error(f"パラメータエラー: {error.message}")
        elif error.status_code == 429:
            logger.warning("レート制限。リクエスト頻度を下げる")
        else:
            logger.error(f"未知のエラー: {error.status_code}")
```

## APIダウン時のフォールバック

```python
def emergency_fallback(client):
    """API障害時の緊急対応"""
    try:
        # まず全ポジションの強制クローズを試みる
        client.close_all_positions(cancel_orders=True)
        logger.critical("緊急: 全ポジションクローズ実行")
    except Exception:
        logger.critical(
            "緊急: API応答なし。ポジションクローズ不能。"
            "手動でAlpacaダッシュボードから操作が必要"
        )
        # アラート送信
        send_alert("Alpaca API障害: 手動対応が必要")

def send_alert(message):
    """アラート送信（Slack/メール等）"""
    # 実装は環境に応じて
    print(f"🚨 ALERT: {message}")
```

## ログ管理のベストプラクティス

```python
import logging
from datetime import datetime

def setup_trading_logger(log_dir="logs"):
    """トレーディング用ロガーのセットアップ"""
    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger("trading")
    logger.setLevel(logging.DEBUG)

    # ファイルハンドラー（日次ローテーション）
    date_str = datetime.now().strftime("%Y-%m-%d")
    fh = logging.FileHandler(f"{log_dir}/trading_{date_str}.log")
    fh.setLevel(logging.DEBUG)

    # コンソールハンドラー
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)

    # フォーマット
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s"
    )
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)

    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger
```
