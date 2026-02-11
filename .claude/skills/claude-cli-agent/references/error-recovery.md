# エラー回復 リファレンス

## エラーの種類と対応方針

### 基本方針

```
エラー発生時のデフォルト動作:
1. 最も安全な行動をとる（「何もしない」が最も安全なことが多い）
2. ログに記録する
3. アラートを送信する
4. 次回の実行で回復を試みる
```

## Claude CLI実行エラー

### タイムアウト

```bash
# タイムアウト設定（2分）
timeout 120 claude -p "$PROMPT" || {
    echo "$(date): Claude CLI timeout" >> "$LOG_FILE"
    # タイムアウト時は何もしない（安全策）
    exit 0
}
```

### API認証エラー

```bash
# Claude CLI実行
RESULT=$(claude -p "$PROMPT" 2>&1)
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    if echo "$RESULT" | grep -q "authentication"; then
        echo "$(date): CRITICAL - Claude API認証エラー" >> "$LOG_FILE"
        send_alert "Claude API認証エラー: APIキーを確認してください"
    elif echo "$RESULT" | grep -q "rate_limit"; then
        echo "$(date): レート制限。5分後にリトライ" >> "$LOG_FILE"
        sleep 300
        RESULT=$(claude -p "$PROMPT" 2>&1) || exit 0
    else
        echo "$(date): Claude CLIエラー: $RESULT" >> "$LOG_FILE"
    fi
fi
```

### 不正な出力（JSONパースエラー）

```python
import json

def parse_claude_output(output, max_retries=2):
    """Claude CLIの出力をパース（リトライ付き）"""
    for attempt in range(max_retries + 1):
        try:
            # JSON部分を抽出（前後のテキストを除去）
            json_start = output.find('{')
            json_end = output.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = output[json_start:json_end]
                return json.loads(json_str)
        except json.JSONDecodeError:
            if attempt < max_retries:
                # リトライ（プロンプトに「JSONのみ出力せよ」を強調）
                output = retry_claude_with_strict_json()
            else:
                logger.error(f"JSONパース失敗（{max_retries}回リトライ後）")
                return None
    return None
```

## Alpaca API障害時のフォールバック

### 障害レベルと対応

```
Level 1: 一時的なエラー（5xx、タイムアウト）
→ リトライ（指数バックオフ、最大3回）
→ 成功しなければ「何もしない」

Level 2: 認証エラー（401, 403）
→ APIキーの確認
→ アラート送信
→ 全実行停止

Level 3: 長時間の障害（30分以上応答なし）
→ 全ポジションにストップロスが設定されていることを確認
→ Alpacaダッシュボードでの手動操作を促すアラート
```

### 実装パターン

```python
import time

class AlpacaFallbackHandler:
    """Alpaca API障害時のフォールバック"""

    def __init__(self, client, logger):
        self.client = client
        self.logger = logger
        self.consecutive_failures = 0
        self.max_failures = 3

    def execute_with_fallback(self, func, *args, **kwargs):
        """フォールバック付き実行"""
        for attempt in range(self.max_failures):
            try:
                result = func(*args, **kwargs)
                self.consecutive_failures = 0
                return result
            except Exception as e:
                self.consecutive_failures += 1
                self.logger.warning(
                    f"API呼び出し失敗 ({attempt+1}/{self.max_failures}): {e}"
                )

                if attempt < self.max_failures - 1:
                    delay = 2 ** attempt * 5  # 5, 10, 20秒
                    time.sleep(delay)

        # 全リトライ失敗
        self.logger.error("API呼び出し全リトライ失敗")
        self._on_total_failure()
        return None

    def _on_total_failure(self):
        """全リトライ失敗時の処理"""
        self.logger.critical("Alpaca API障害: フォールバック実行")

        # ポジションが存在するかの最終確認
        try:
            positions = self.client.get_all_positions()
            if positions:
                self.logger.critical(
                    f"未クローズのポジション: {len(positions)}件"
                )
                send_alert(
                    f"⚠️ Alpaca API障害中。"
                    f"未クローズのポジション: {len(positions)}件。"
                    f"手動確認が必要。"
                )
        except Exception:
            send_alert(
                "🚨 Alpaca API完全停止。"
                "ポジション確認不能。"
                "手動でダッシュボードを確認してください。"
            )
```

## ログ管理

### ログレベルの使い分け

| レベル | 用途 | 例 |
|--------|------|-----|
| DEBUG | 詳細なデバッグ情報 | API応答の全文 |
| INFO | 通常の動作記録 | 注文送信、分析結果 |
| WARNING | 想定内の問題 | レート制限、リトライ |
| ERROR | 想定外の問題 | パースエラー、API障害 |
| CRITICAL | 緊急対応必要 | 認証エラー、ポジション不整合 |

### ログローテーション

```python
import logging
from logging.handlers import RotatingFileHandler

def setup_logger(log_dir="logs"):
    logger = logging.getLogger("trading_agent")
    logger.setLevel(logging.DEBUG)

    # 10MB × 5ファイルでローテーション
    handler = RotatingFileHandler(
        f"{log_dir}/agent.log",
        maxBytes=10*1024*1024,
        backupCount=5
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s"
    ))
    logger.addHandler(handler)
    return logger
```

## アラート通知

### Slack通知

```python
import requests

def send_slack_alert(webhook_url, message, level="warning"):
    """Slackにアラートを送信"""
    emoji = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}
    payload = {
        "text": f"{emoji.get(level, '📢')} Trading Bot Alert\n{message}"
    }
    try:
        requests.post(webhook_url, json=payload, timeout=10)
    except Exception as e:
        # アラート送信自体が失敗した場合はログに記録
        logging.error(f"Slack通知失敗: {e}")
```

### メール通知

```python
import smtplib
from email.mime.text import MIMEText

def send_email_alert(to_email, subject, body):
    """メールアラートを送信"""
    msg = MIMEText(body)
    msg['Subject'] = f"[Trading Bot] {subject}"
    msg['From'] = "bot@example.com"
    msg['To'] = to_email

    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login("bot@example.com", os.environ['EMAIL_PASSWORD'])
            server.send_message(msg)
    except Exception as e:
        logging.error(f"メール送信失敗: {e}")
```

## 回復チェックリスト

障害発生後、運用再開前に以下を確認せよ：

- [ ] Alpaca APIが正常に応答するか
- [ ] ポジションの状態がAlpaca側と一致しているか
- [ ] 未約定の注文がないか（あれば意図したものか確認）
- [ ] ログに未処理のエラーがないか
- [ ] 日次/月次の損失制限に達していないか
- [ ] cron設定が正しく動作しているか
