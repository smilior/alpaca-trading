---
name: alpaca-api
description: |
  Alpaca APIを正しく・安全に使うためのスキル。
  以下のキーワードでトリガーする：「Alpaca」「アルパカ」「ペーパートレーディング」
  「株の売買API」「注文API」「ブローカーAPI」「alpaca-py」「注文執行」
  「マーケットデータ取得」「ポジション取得」「口座情報」「Alpaca SDK」。
  Alpaca関連のコードを書く際、Alpaca APIを呼び出すコードをレビューする際に必ず使用すること。
  ペーパーとリアルの混同事故は絶対に防がなければならない。
---

# Alpaca APIスキル

## このスキルの目的

Alpaca APIを正しく、安全に使え。特にペーパートレーディングとリアルの混同を防ぐことが最優先。

## Alpaca APIの全体像

```
Alpaca API
├── Trading API（注文・ポジション・口座管理）
│   ├── Paper Trading: https://paper-api.alpaca.markets
│   └── Live Trading:  https://api.alpaca.markets
├── Market Data API（株価・出来高・ニュース）
│   ├── Historical: https://data.alpaca.markets
│   └── Real-time:  wss://stream.data.alpaca.markets
└── Broker API（マルチアカウント管理）※個人では通常不使用
```

## 認証方法

```python
# 環境変数から読み込む（ハードコードは絶対禁止）
import os

ALPACA_API_KEY = os.environ['ALPACA_API_KEY']
ALPACA_SECRET_KEY = os.environ['ALPACA_SECRET_KEY']
# ペーパーかリアルかを明示的に指定
ALPACA_PAPER = os.environ.get('ALPACA_PAPER', 'true').lower() == 'true'
```

## 最重要: ペーパーとリアルを間違えないための安全策

### 環境変数の命名規則

```bash
# .env ファイル（gitignoreに必ず追加すること）

# ペーパートレーディング用
ALPACA_API_KEY=PKXXXXXXXXXXXXXXXXXX
ALPACA_SECRET_KEY=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
ALPACA_PAPER=true

# リアル用（別の環境変数名を使う）
# ALPACA_LIVE_API_KEY=AKXXXXXXXXXXXXXXXXXX
# ALPACA_LIVE_SECRET_KEY=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
# ALPACA_PAPER=false
```

**ルール**:
1. デフォルトは常にペーパートレーディング
2. リアルに切り替えるには明示的な操作が必要
3. 環境変数 `ALPACA_PAPER` がない場合はペーパーとして動作

### 起動時の確認ログ出力

```python
def initialize_alpaca():
    """Alpacaクライアントを初期化（安全策付き）"""
    api_key = os.environ.get('ALPACA_API_KEY')
    secret_key = os.environ.get('ALPACA_SECRET_KEY')
    is_paper = os.environ.get('ALPACA_PAPER', 'true').lower() == 'true'

    if not api_key or not secret_key:
        raise ValueError("ALPACA_API_KEY / ALPACA_SECRET_KEY が未設定")

    # 起動時に大きく表示
    mode = "📝 PAPER TRADING" if is_paper else "💰 LIVE TRADING"
    print("=" * 50)
    print(f"  Alpaca Mode: {mode}")
    print(f"  API Key: {api_key[:4]}...{api_key[-4:]}")
    print("=" * 50)

    # リアルの場合は追加確認
    if not is_paper:
        print("⚠️  WARNING: LIVE TRADING MODE")
        print("⚠️  実際のお金で取引されます！")
        # 自動実行（cron）の場合はここで確認ダイアログは出せないが、
        # ログに明示的に記録する

    from alpaca.trading.client import TradingClient
    client = TradingClient(api_key, secret_key, paper=is_paper)

    # 口座情報で接続確認
    account = client.get_account()
    print(f"  口座残高: ${float(account.cash):,.2f}")
    print(f"  ポートフォリオ: ${float(account.portfolio_value):,.2f}")
    print("=" * 50)

    return client
```

### alpaca-py SDKの基本的な使い方

```python
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest, LimitOrderRequest,
    StopLossRequest, TakeProfitRequest
)
from alpaca.trading.enums import OrderSide, TimeInForce

# クライアント初期化
client = TradingClient(api_key, secret_key, paper=True)
```

## レート制限と対策

| API | 制限 | 対策 |
|-----|------|------|
| Trading API | 200リクエスト/分 | リクエスト間に0.3秒sleep |
| Market Data API | 200リクエスト/分 | バッチリクエスト活用 |
| WebSocket | 接続数制限あり | 1接続で複数銘柄をsubscribe |

```python
import time

def rate_limited_request(func, *args, delay=0.3, **kwargs):
    """レート制限対応のリクエストラッパー"""
    result = func(*args, **kwargs)
    time.sleep(delay)
    return result
```

## エンドポイント詳細

以下のリファレンスを参照せよ：
- **注文の種類と操作**: [references/trading-api.md](references/trading-api.md)
- **マーケットデータ取得**: [references/market-data-api.md](references/market-data-api.md)
- **ペーパートレーディング固有の注意点**: [references/paper-trading.md](references/paper-trading.md)
- **エラーハンドリング**: [references/error-handling.md](references/error-handling.md)

## .envとgitignoreの設定

```bash
# .gitignore に必ず以下を追加
.env
.env.local
.env.production
*.pem
*.key
```

## チェックリスト

コードを書く前に必ず確認せよ：

- [ ] APIキーはハードコードされていないか（環境変数を使用しているか）
- [ ] .envが.gitignoreに含まれているか
- [ ] ペーパー/リアルの切り替えが明示的か
- [ ] 起動時にモード（PAPER/LIVE）がログに出力されるか
- [ ] レート制限への対策があるか
- [ ] エラーハンドリングが実装されているか
- [ ] マーケット時間外の注文処理を考慮しているか
