# システム設計書 v3

> [v3変更] 本文書は、v2をベースに STRAT/QUANT/RISK/ARCH/DEVIL の5名によるv3レビューを統合したものである。変更箇所には `[v3追加]` `[v3改訂]` タグを付与。DEVILの複雑性警告を踏まえ、各機能に **MVP**（Phase 1必須）/ **追加**（Phase 3以降）/ **将来**（リアル移行時以降）の優先度を明記する。

---

## 1. アーキテクチャ図

### 全Python化アーキテクチャ

> v2で確立した全Python化アーキテクチャを維持。v3では型安全なモジュール間インターフェース（ARCH）と構造化ロギング（ARCH）を追加。

```
                          ┌─────────────────────────────────────┐
                          │     launchd スケジューラ              │
                          │  (09:30, 10:30, 13:00, 15:30 ET)    │
                          │  ※ macOSではcronではなくlaunchdを使用 │
                          └──────────┬──────────────────────────┘
                                     │
                                     ▼
                          ┌──────────────────────┐
                          │  trading_agent.py     │
                          │  (メインオーケストラ)  │
                          │  [v3改訂] 型安全I/F   │
                          └──────────┬───────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    ▼                ▼                ▼
         ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐
         │ Step 0:      │  │ Step 1:      │  │ Step 2:          │
         │ 冪等性チェック│  │ Reconcile    │  │ ヘルスチェック    │
         │ ロック+実行ID │  │ Alpaca↔DB照合│  │ [v3改訂]         │
         │              │  │ [v3改訂]     │  │ 二重API確認      │
         └──────┬───────┘  └──────┬───────┘  └──────┬───────────┘
                │                 │                  │
                ▼                 ▼                  ▼
         ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
         │ Step 3:      │  │ Step 4:      │  │ Step 5:      │
         │ データ収集    │  │ 状態取得     │  │ リスクチェック│
         │ (Python)     │  │ (Python)     │  │ [v3改訂]     │
         └──────┬───────┘  └──────┬───────┘  │ EWMA相関     │
                │                 │          │ VIXレジーム   │
                ▼                 ▼          └──────┬───────┘
         ┌──────────────────────────────────────────────────┐
         │                  Step 6: Claude CLI               │
         │  [v3改訂] JSON Schema検証 + フォールバック         │
         │  入力: market_data.json + state.json + prompt.md  │
         │  出力: analysis.json (売買判断)                    │
         │  タイムアウト: 120秒 + リトライ2回                 │
         └──────────────────────┬───────────────────────────┘
                                │
                                ▼
                     ┌──────────────────┐
                     │  Step 7:          │
                     │  注文実行         │
                     │  + ブラケット注文 │
                     │  [v3改訂]         │
                     │  limit付きstop    │
                     └──────┬───────────┘
                            │
               ┌────────────┼────────────┐
               ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ Alpaca   │ │ SQLite   │ │ Slack    │
        │ API      │ │ state.db │ │ Webhook  │
        │ (注文)   │ │ [v3改訂] │ │          │
        └──────────┘ │ WAL最適化│ └──────────┘
                     │ バックアップ│
                     └──────────┘
```

### [v3追加] モジュール間データフロー（優先度: MVP）

> ARCH提案: 各モジュール間のデータ型を明示化。暗黙のdict受け渡しを排除し、dataclassesで型安全性を保証する。

```
collect_market_data() → dict[str, BarData]
        │
        ▼
sync_with_alpaca() → PortfolioState
        │
        ▼
check_circuit_breaker(PortfolioState) → bool
        │
        ▼
get_trading_decisions(dict[str, BarData], PortfolioState) → list[TradingDecision]
        │
        ▼
execute_decisions(list[TradingDecision], PortfolioState, str) → list[OrderResult]
```

---

## 2. [v3追加] 型安全モジュールインターフェース（優先度: MVP）

> ARCH提案: trading_agent.pyのモジュール間データ受け渡しが暗黙的で型安全性に欠ける問題を解消。dataclasses + typing.Protocol で全モジュールの入出力型を定義する。Phase 1の初期段階で定義すべき。後から導入するとモジュール全体の改修が必要になる。

```python
# modules/types.py -- 全モジュール共通の型定義
from dataclasses import dataclass, field
from typing import Protocol, Optional
from datetime import date, datetime
from enum import Enum

class MacroRegime(Enum):
    BULL = "bull"
    RANGE = "range"
    BEAR = "bear"

class Action(Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    NO_ACTION = "no_action"

@dataclass(frozen=True)
class BarData:
    symbol: str
    close: float
    volume: int
    ma_50: float
    rsi_14: float
    atr_14: float
    volume_ratio_20d: float

@dataclass(frozen=True)
class PortfolioState:
    equity: float
    cash: float
    buying_power: float
    positions: dict[str, "PositionInfo"]
    daily_pnl_pct: float
    drawdown_pct: float

@dataclass(frozen=True)
class PositionInfo:
    symbol: str
    qty: float
    avg_entry_price: float
    current_price: float
    unrealized_pnl: float
    sector: str

@dataclass(frozen=True)
class TradingDecision:
    symbol: str
    action: Action
    confidence: int
    entry_price: float
    stop_loss: float
    take_profit: float
    reasoning_bull: str
    reasoning_bear: str
    catalyst: str

@dataclass(frozen=True)
class OrderResult:
    symbol: str
    success: bool
    alpaca_order_id: Optional[str]
    client_order_id: str
    filled_qty: float
    error_message: Optional[str]

# Protocol: 各モジュールが満たすべきインターフェース
class DataCollector(Protocol):
    def collect(self, symbols: list[str], mode: str) -> dict[str, BarData]: ...

class StateManager(Protocol):
    def sync(self) -> PortfolioState: ...
    def reconcile(self) -> list[str]: ...

class RiskChecker(Protocol):
    def check_circuit_breaker(self, portfolio: PortfolioState) -> bool: ...
    def calculate_position_size(
        self, entry: float, stop: float, capital: float
    ) -> int: ...

class LLMAnalyzer(Protocol):
    def analyze(
        self, market_data: dict[str, BarData], portfolio: PortfolioState, mode: str
    ) -> list[TradingDecision]: ...

class OrderExecutor(Protocol):
    def execute(
        self, decisions: list[TradingDecision], portfolio: PortfolioState,
        execution_id: str
    ) -> list[OrderResult]: ...
```

**効果:**
- IDEの補完・型チェックが効く（mypy/pyrightでCI検証可能）
- モジュール間の契約が明示的になり、変更の影響範囲が型エラーとして検出される
- テスト時のモック作成が容易（Protocolを満たすテストダブルを作るだけ）
- `frozen=True` により不変オブジェクトとなり、意図しない状態変更を防止

---

## 3. スケジューラ設計

### launchd設定（macOS）

> v2で確立したlaunchd設定を維持。v3ではマイグレーションスクリプトを具体化（ARCH）。

```xml
<!-- launchd/com.alpaca-trading.morning.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.alpaca-trading.morning</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/venv/bin/python</string>
        <string>/path/to/trading_agent.py</string>
        <string>morning</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>0</integer>
        <key>Minute</key>
        <integer>30</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/path/to/logs/morning.log</string>
    <key>StandardErrorPath</key>
    <string>/path/to/logs/morning_error.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>ALPACA_PAPER</key>
        <string>true</string>
    </dict>
</dict>
</plist>
```

**plistファイル一覧:**

| plist | 実行モード | JST時刻 | ET時刻 |
|-------|----------|---------|--------|
| `com.alpaca-trading.pre-market.plist` | pre_market | 23:30 | 09:30 |
| `com.alpaca-trading.morning.plist` | morning | 00:30 | 10:30 |
| `com.alpaca-trading.midday.plist` | midday | 03:00 | 13:00 |
| `com.alpaca-trading.eod.plist` | eod | 05:30 | 15:30 |
| `com.alpaca-trading.health-check.plist` | health_check | 毎時 | - |
| `com.alpaca-trading.daily-report.plist` | daily_report | 06:30 | 16:30 |

### DST（夏時間）対策

```python
from zoneinfo import ZoneInfo
from datetime import datetime
import exchange_calendars as xcals

nyse = xcals.get_calendar("XNYS")

def is_market_open() -> bool:
    """市場営業日かつ市場時間内かを判定（祝日対応）"""
    et_now = datetime.now(ZoneInfo("America/New_York"))
    today = et_now.date()

    if not nyse.is_session(today.isoformat()):
        return False

    market_open = et_now.replace(hour=9, minute=30, second=0)
    market_close = et_now.replace(hour=16, minute=0, second=0)
    return market_open <= et_now <= market_close
```

### [v3改訂] クラウド移行パス（3段階）+ マイグレーションスクリプト（優先度: 追加）

> v2の移行パスに加え、ARCH提案の具体的マイグレーションスクリプトとLambda互換エントリーポイントを追加。DEVILの複雑性警告を踏まえ、Phase 1ではlaunchdのみ、スクリプトはPhase 3以降で実行。

| Stage | 環境 | スケジューラ | 月額コスト | 移行タイミング |
|-------|------|-------------|-----------|---------------|
| 1 | macOS (ローカル) | launchd | $0 | Phase 1-4（ペーパー期間） |
| 2 | VPS (Hetzner/Vultr) | systemd timer | $5-10 | ペーパー運用安定後 |
| 3 | AWS Lambda + EventBridge | EventBridge | $1-5 | リアルマネー移行時 |

**[v3追加] Lambda互換エントリーポイント:**

```python
# trading_agent.py -- CLI + Lambda両対応
import sys

def handler(event=None, context=None):
    """AWS Lambda / ローカル両方で動くエントリーポイント"""
    if event:
        mode = event.get("mode", "morning")
    elif len(sys.argv) > 1:
        mode = sys.argv[1]
    else:
        mode = "morning"
    main(mode)

if __name__ == "__main__":
    handler()
```

**[v3追加] systemd unitファイルテンプレート（deploy/systemd/）:**

```ini
# deploy/systemd/alpaca-trading-morning.service
[Unit]
Description=Alpaca Trading Agent (morning)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=trading
WorkingDirectory=/opt/alpaca-trading
EnvironmentFile=/opt/alpaca-trading/.env
ExecStart=/opt/alpaca-trading/venv/bin/python trading_agent.py morning
StandardOutput=append:/var/log/alpaca-trading/morning.log
StandardError=append:/var/log/alpaca-trading/morning_error.log

[Install]
WantedBy=multi-user.target
```

```ini
# deploy/systemd/alpaca-trading-morning.timer
[Unit]
Description=Alpaca Trading Morning Timer

[Timer]
OnCalendar=Mon..Fri 14:30 UTC
Persistent=true

[Install]
WantedBy=timers.target
```

**[v3追加] VPSマイグレーションスクリプト:**

```bash
#!/bin/bash
# deploy/migrate-to-vps.sh
set -euo pipefail

VPS_HOST=$1
VPS_USER=${2:-trading}
REMOTE_DIR=/opt/alpaca-trading

echo "=== Stage 2: VPS Migration ==="

# 1. リモートディレクトリ作成
ssh ${VPS_USER}@${VPS_HOST} "sudo mkdir -p ${REMOTE_DIR}/{data/state,logs} && sudo chown -R ${VPS_USER} ${REMOTE_DIR}"

# 2. コード同期
rsync -avz --exclude='.env' --exclude='data/' --exclude='logs/' --exclude='__pycache__' \
    ./ ${VPS_USER}@${VPS_HOST}:${REMOTE_DIR}/

# 3. Python環境セットアップ
ssh ${VPS_USER}@${VPS_HOST} "cd ${REMOTE_DIR} && python3 -m venv venv && venv/bin/pip install -r requirements.txt"

# 4. .envを安全に転送
scp .env ${VPS_USER}@${VPS_HOST}:${REMOTE_DIR}/.env
ssh ${VPS_USER}@${VPS_HOST} "chmod 600 ${REMOTE_DIR}/.env"

# 5. DBマイグレーション
scp data/state/trading.db ${VPS_USER}@${VPS_HOST}:${REMOTE_DIR}/data/state/

# 6. systemdユニットのインストール
ssh ${VPS_USER}@${VPS_HOST} "sudo cp ${REMOTE_DIR}/deploy/systemd/*.service ${REMOTE_DIR}/deploy/systemd/*.timer /etc/systemd/system/ && sudo systemctl daemon-reload"

# 7. タイマー有効化
for mode in pre-market morning midday eod health-check daily-report; do
    ssh ${VPS_USER}@${VPS_HOST} "sudo systemctl enable --now alpaca-trading-${mode}.timer"
done

echo "=== Migration complete. Verify with: systemctl list-timers | grep alpaca ==="
```

---

## 4. 実行フロー詳細

### メインオーケストレーター（trading_agent.py）

> v2の骨格を維持しつつ、v3で型安全インターフェース（ARCH）とpydantic-settings設定検証（ARCH）を統合。

```python
# trading_agent.py（骨格）
import sys
import logging
from pathlib import Path

from modules.types import PortfolioState, TradingDecision, OrderResult
from modules.config import AppConfig
from modules.db import get_connection, acquire_lock
from modules.data_collector import collect_market_data
from modules.state_manager import sync_with_alpaca, reconcile_positions
from modules.health_check import run_health_check
from modules.risk_manager import check_circuit_breaker, validate_order
from modules.llm_analyzer import get_trading_decisions
from modules.order_executor import execute_decisions
from modules.alerter import send_alert
from modules.logger import setup_logging  # [v3追加]

def main(mode: str):
    """メインオーケストレーター"""
    config = AppConfig()  # [v3改訂] pydantic-settingsで型安全
    execution_id = f"{date.today().isoformat()}_{mode}"
    setup_logging(config.system.log_dir, execution_id)  # [v3追加]

    # Step 0: 冪等性チェック
    lock_file = acquire_lock(config.system.lock_file_path)
    if is_already_executed(conn, execution_id):
        logging.info(f"Already executed: {execution_id}")
        return

    # 市場休場日チェック
    if not is_market_open() and mode != "health_check":
        logging.info("Market is closed today. Skipping.")
        return

    # Step 1: ヘルスチェック
    if not run_health_check():
        send_alert("Health check failed", level="error")
        sys.exit(1)

    # Step 2: Reconciliation（Alpaca↔DB照合）[v3改訂: 二重API呼出]
    portfolio: PortfolioState = sync_with_alpaca()
    reconcile_positions(alpaca_client, conn)

    # Step 3: 回路ブレーカー確認
    if check_circuit_breaker(portfolio):
        logging.info("Circuit breaker active. Skipping.")
        return

    # Step 4: データ収集
    market_data = collect_market_data(portfolio.watchlist, mode)

    # Step 5: リスクチェック（注文前）[v3改訂: EWMA相関+VIXレジーム]
    # ... 日次損失計算、同時ポジション数確認、相関チェック

    # Step 6: Claude CLI分析 [v3改訂: JSON Schema検証+フォールバック]
    decisions: list[TradingDecision] = get_trading_decisions(
        market_data, portfolio, mode
    )

    # Step 7: 注文実行 [v3改訂: limit付きstop order]
    if mode in ("morning", "eod"):
        results: list[OrderResult] = execute_decisions(
            decisions, portfolio, execution_id
        )

    # Step 8: 後処理 [v3追加: メトリクス記録]
    record_execution_log(conn, execution_id, mode, decisions)
    record_metrics(conn, execution_id)  # [v3追加]
    send_daily_summary_update(conn)

if __name__ == "__main__":
    handler()  # [v3改訂] Lambda互換エントリーポイント
```

### 実行フロー（全ステップ）

```
trading_agent.py <mode>
│
├── [0] 冪等性チェック
│   ├── ファイルロック取得（fcntl.LOCK_EX）
│   ├── 実行ID（日付+モード）で二重実行チェック
│   └── ロック取得失敗 → 別プロセス実行中、即終了
│
├── [1] 市場休場日チェック
│   ├── exchange_calendars で NYSE の営業日判定
│   └── 休場日 → ログ記録して終了（health_checkは除く）
│
├── [2] ヘルスチェック
│   ├── ALPACA_PAPER=true を確認
│   ├── API接続テスト
│   ├── ディスク容量確認
│   └── 前回の実行ログを確認（エラーがあれば通知）
│
├── [3] Reconciliation（照合）[v3改訂: 二重APIコール+sourceカラム]
│   ├── client.get_all_positions() を2回連続呼出（DEVIL提案）
│   ├── 2回の結果が一致する場合のみReconciliation実行
│   ├── ローカルDBのopenポジションと照合
│   ├── 差分検出 → 自動修正（Alpacaを正とする）
│   ├── [v3追加] 大幅な不整合（3件以上）は自動修正停止→アラートのみ
│   └── 不整合があればログ記録 + Slackアラート
│
├── [4] データ収集
│   ├── 保有銘柄 + ウォッチリストの株価データ取得
│   ├── Alpaca News APIでニュース取得
│   ├── FRED APIでマクロ指標取得（日次1回のみ）
│   ├── [v3追加] 決算日カレンダー取得（RISK: 決算接近チェック用）
│   └── データをJSON形式で保存
│
├── [5] リスクチェック（注文前）[v3改訂: EWMA相関、VIXレジーム、決算接近]
│   ├── 回路ブレーカー状態の確認
│   ├── 日次損失の計算
│   ├── 同時ポジション数の確認
│   ├── [v3追加] VIXレジーム判定（相対VIX方式）
│   ├── [v3追加] EWMA相関チェック（相関ブレイクアウト検出）
│   ├── [v3追加] 保有銘柄の決算接近チェック（2営業日以内→縮小指示）
│   └── NG → ログ記録して終了
│
├── [6] Claude CLI分析 [v3改訂: JSON Schema検証+フォールバック+リトライ]
│   ├── プロンプト + データをClaude CLIに渡す
│   ├── subprocess.run(timeout=120)
│   ├── --output-format json で構造化出力を取得
│   ├── [v3追加] _extract_json()でJSON部分を抽出
│   ├── [v3追加] JSON Schemaでバリデーション
│   ├── [v3追加] スキーマ違反時は_sanitize_partial()で部分救済
│   ├── [v3追加] 失敗時はリトライ（最大2回）
│   └── 全リトライ失敗 → ログ記録+アラート+安全終了（注文なし）
│
├── [7] 注文実行 [v3改訂: limit付きstop order]
│   ├── ブラケット注文（OTO）でエントリー + ストップロス + テイクプロフィット
│   ├── [v3追加] ストップロスにlimit_price設定（ATR x 1.0の乖離幅）
│   ├── client_order_id = "{execution_id}_{symbol}_{side}" で冪等性保証
│   ├── Partial Fill検出 → ストップロス数量調整
│   ├── 注文結果をDBに記録
│   └── 注文失敗 → リトライ1回 → 失敗ならログ + Slackアラート
│
└── [8] 後処理 [v3追加: メトリクス記録]
    ├── 実行ログをDBに記録（execution_id付き）
    ├── [v3追加] オブザーバビリティメトリクス記録
    ├── 日次サマリーを更新
    └── エラーがあればSlackアラート送信
```

### モード別の処理

| モード | 主な処理 | 注文 |
|--------|----------|------|
| `pre_market` | ニュース収集・分析、マクロ環境判定 | なし（分析のみ） |
| `morning` | エントリー判断・注文 | 新規エントリー（ブラケット注文） |
| `midday` | ポジション状態確認、リスクチェック | 緊急エグジットのみ |
| `eod` | クロージング判断、タイムストップ確認 | エグジット |

---

## 5. 冪等性の確保

> v2で確立した3重防御を維持。変更なし。

### 5.1 ファイルロック

```python
import fcntl
import sys

def acquire_lock(lock_path="data/state/agent.lock"):
    """同時に1つのエージェントプロセスのみ実行を許可"""
    lock_file = open(lock_path, "w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock_file
    except BlockingIOError:
        logging.error("Another agent instance is running. Exiting.")
        sys.exit(0)
```

### 5.2 実行ID（Execution ID）による二重実行防止

```python
from datetime import date

def get_execution_id(mode: str) -> str:
    return f"{date.today().isoformat()}_{mode}"

def is_already_executed(conn, execution_id: str) -> bool:
    result = conn.execute(
        "SELECT 1 FROM execution_logs WHERE execution_id = ? AND status = 'success'",
        (execution_id,)
    ).fetchone()
    return result is not None
```

### 5.3 Alpaca APIのclient_order_idによる注文冪等性

```python
def create_idempotent_order(symbol, qty, side, execution_id):
    client_order_id = f"{execution_id}_{symbol}_{side}"
    order = LimitOrderRequest(
        symbol=symbol, qty=qty, side=side,
        client_order_id=client_order_id,
        ...
    )
    return client.submit_order(order)
```

> **なぜ3重か**: (1)ファイルロックはプロセス並行を防ぎ、(2)実行IDは同日同モードの再実行を防ぎ、(3)client_order_idはAPI側で注文の重複を防ぐ。

---

## 6. [v3改訂] Reconciliation（照合）パターン（優先度: MVP）

> v2の実装に加え、DEVIL提案の安全性強化を統合: (1) 二重APIコールでレースコンディション対策、(2) sourceカラムで追加元を追跡、(3) 大幅不整合時の自動修正停止。

```python
def reconcile_positions(alpaca_client, db_conn):
    """Alpaca APIとローカルDBのポジションを照合する"""
    reconciliation_issues = []

    # [v3追加] 二重APIコール: レースコンディション対策（DEVIL提案）
    alpaca_pos_1 = {p.symbol: p for p in alpaca_client.get_all_positions()}
    time.sleep(1)
    alpaca_pos_2 = {p.symbol: p for p in alpaca_client.get_all_positions()}

    if set(alpaca_pos_1.keys()) != set(alpaca_pos_2.keys()):
        send_alert("Alpaca positions inconsistent between 2 calls. Skipping reconciliation.",
                    level="warn")
        return []

    alpaca_positions = alpaca_pos_2  # 2回目の結果を使用

    # ローカルDBのopenポジションを取得
    db_positions = get_open_positions(db_conn)

    # 差分検出
    for symbol, db_pos in db_positions.items():
        if symbol not in alpaca_positions:
            close_position_in_db(db_conn, db_pos, reason="reconciliation")
            reconciliation_issues.append(f"CLOSED_MISSING: {symbol}")

    for symbol, alp_pos in alpaca_positions.items():
        if symbol not in db_positions:
            # [v3追加] sourceカラムでreconciliation由来を明示（DEVIL提案）
            insert_position_from_alpaca(db_conn, alp_pos, source="reconciliation")
            reconciliation_issues.append(f"ADDED_MISSING: {symbol}")

        elif db_positions[symbol].qty != float(alp_pos.qty):
            update_position_qty(db_conn, symbol, float(alp_pos.qty))
            reconciliation_issues.append(f"QTY_MISMATCH: {symbol}")

    # [v3追加] 大幅不整合の安全弁（DEVIL提案）
    if len(reconciliation_issues) >= 3:
        send_alert(
            f"CRITICAL: Reconciliation found {len(reconciliation_issues)} issues. "
            "Auto-correction STOPPED. Manual review required.",
            level="critical"
        )
        # 自動修正をロールバック
        db_conn.rollback()
        return reconciliation_issues

    if reconciliation_issues:
        db_conn.commit()
        send_alert(
            f"Reconciliation found {len(reconciliation_issues)} issues: "
            + ", ".join(reconciliation_issues),
            level="warn"
        )

    return reconciliation_issues
```

---

## 7. [v3改訂] Claude CLI呼び出しの堅牢化（優先度: MVP）

> ARCH提案: v2ではJSON不正時に「ログ記録して終了」のみだった。v3ではJSON Schema Validation + 段階的フォールバック + リトライ戦略を実装し、Claude CLI出力の異常がシグナル欠落に直結するリスクを排除する。

```python
# modules/llm_analyzer.py
import json
import subprocess
import logging
from jsonschema import validate, ValidationError
from modules.types import TradingDecision, Action
from modules.alerter import send_alert

# Claude CLI出力のJSON Schema定義
DECISION_SCHEMA = {
    "type": "object",
    "required": ["timestamp", "macro_regime", "decisions"],
    "properties": {
        "macro_regime": {"enum": ["bull", "range", "bear"]},
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["symbol", "action", "sentiment_analysis",
                             "technical_check", "trade_parameters",
                             "reasoning_structured"],
                "properties": {
                    "action": {"enum": ["buy", "sell", "hold", "no_action"]},
                    "sentiment_analysis": {
                        "type": "object",
                        "required": ["overall", "confidence"],
                        "properties": {
                            "overall": {"enum": ["positive", "negative", "neutral"]},
                            "confidence": {"type": "integer", "minimum": 0,
                                           "maximum": 100}
                        }
                    }
                }
            }
        }
    }
}

def call_claude_with_validation(prompt_path: str, data_path: str,
                                 max_retries: int = 2) -> dict | None:
    """Claude CLIを呼び出し、出力をバリデーション付きでパースする"""
    for attempt in range(max_retries):
        try:
            result = subprocess.run(
                ["claude", "-p", "--output-format", "json",
                 "--input-file", data_path, prompt_path],
                capture_output=True, text=True,
                timeout=120
            )

            if result.returncode != 0:
                logging.error(f"Claude CLI exited with {result.returncode}: "
                              f"{result.stderr[:500]}")
                continue

            # stdoutからJSONを抽出（非JSON行を除去）
            raw_output = result.stdout.strip()
            parsed = _extract_json(raw_output)

            if parsed is None:
                logging.error(f"Failed to extract JSON from output "
                              f"(attempt {attempt+1}): {raw_output[:200]}")
                continue

            # JSON Schemaバリデーション
            validate(instance=parsed, schema=DECISION_SCHEMA)
            return parsed

        except subprocess.TimeoutExpired:
            logging.error(f"Claude CLI timeout (attempt {attempt+1})")
            continue
        except ValidationError as e:
            logging.error(f"Schema validation failed (attempt {attempt+1}): "
                          f"{e.message}")
            if parsed and "decisions" in parsed:
                return _sanitize_partial(parsed)
            continue
        except json.JSONDecodeError as e:
            logging.error(f"JSON decode failed (attempt {attempt+1}): {e}")
            continue

    # 全リトライ失敗
    send_alert("Claude CLI failed after all retries", level="error")
    return None


def _extract_json(raw: str) -> dict | None:
    """生の出力からJSON部分を抽出する"""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # 最初の '{' から最後の '}' を抽出
    start = raw.find('{')
    end = raw.rfind('}')
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(raw[start:end+1])
        except json.JSONDecodeError:
            pass
    return None


def _sanitize_partial(parsed: dict) -> dict:
    """部分的に有効なJSONをサニタイズする"""
    valid_decisions = []
    for d in parsed.get("decisions", []):
        if all(k in d for k in ["symbol", "action"]):
            action = d["action"].lower().strip()
            if action not in ("buy", "sell", "hold", "no_action"):
                action = "no_action"
            d["action"] = action
            valid_decisions.append(d)
    parsed["decisions"] = valid_decisions
    return parsed
```

**フォールバック戦略:**

| 失敗パターン | フォールバック | 優先度 |
|-------------|-------------|--------|
| タイムアウト | 1回リトライ後、「注文なし」で安全終了 | MVP |
| JSON不正 | `_extract_json()` で部分抽出を試行 | MVP |
| スキーマ違反（軽微） | `_sanitize_partial()` で有効部分のみ使用 | MVP |
| スキーマ違反（重大） | 「注文なし」で安全終了 | MVP |
| 全リトライ失敗 | Slackアラート + 次回実行で再試行 | MVP |

---

## 8. Claude CLIへの入力（プロンプト概要）

### 出力JSON Schema

> v2で確立したスキーマを維持。変更なし。

```json
{
  "timestamp": "2025-01-15T10:30:00-05:00",
  "macro_regime": "bull|range|bear",
  "macro_indicators": {
    "spy_vs_200ma": 1.05,
    "vix": 18.5,
    "yield_curve_10y2y": 0.15,
    "credit_spread_hy": 320
  },
  "decisions": [
    {
      "symbol": "AAPL",
      "action": "buy|sell|hold|no_action",
      "sentiment_analysis": {
        "overall": "positive|negative|neutral",
        "confidence": 85,
        "news_count_analyzed": 5,
        "key_drivers": ["EPS beat consensus by 8%"],
        "risk_factors": ["China revenue declined 3% YoY"],
        "sentiment_horizon": "5_day"
      },
      "technical_check": {
        "price_vs_50ma": "above|below|near",
        "ma_distance_pct": 2.3,
        "rsi_14": 55,
        "volume_ratio_20d": 1.8,
        "atr_14": 3.2,
        "all_filters_passed": true,
        "failed_filters": []
      },
      "trade_parameters": {
        "suggested_entry_price": 185.50,
        "stop_loss_atr_multiple": 2.0,
        "calculated_stop_loss": 179.10,
        "take_profit_pct": 5.0,
        "calculated_take_profit": 194.78
      },
      "reasoning_structured": {
        "bull_case": "Strong earnings + positive guidance + sector momentum",
        "bear_case": "China exposure risk, RSI approaching overbought",
        "catalyst": "Q1 earnings beat",
        "expected_holding_days": 5
      }
    }
  ],
  "portfolio_risk_assessment": {
    "total_exposure_pct": 45.0,
    "sector_concentration": {"Technology": 2, "Healthcare": 1},
    "daily_pnl_pct": 0.5,
    "drawdown_pct": 2.3,
    "correlation_risk": "low|medium|high"
  },
  "metadata": {
    "model_version": "claude-sonnet-4-5-20250929",
    "prompt_version": "v1.0",
    "input_token_count": 3500,
    "processing_notes": []
  }
}
```

---

## 9. Alpaca APIの使用エンドポイント

### Trading API（ペーパー: https://paper-api.alpaca.markets）

| エンドポイント | 用途 | 頻度 |
|---------------|------|------|
| `GET /v2/account` | 口座残高・購買力の取得 | 毎回実行時 |
| `GET /v2/positions` | 全ポジション一覧（Reconciliation用）[v3改訂: 二重呼出] | 毎回実行時 |
| `GET /v2/orders` | 注文一覧（未約定含む） | 毎回実行時 |
| `POST /v2/orders` | 新規注文（ブラケット注文対応）[v3改訂: limit付きstop] | エントリー/エグジット時 |
| `DELETE /v2/orders/{id}` | 注文キャンセル | 必要時 |
| `DELETE /v2/positions/{symbol}` | ポジションのクローズ | エグジット時 |

### [v3改訂] ブラケット注文（OTO）+ limit付きstop order（優先度: MVP）

> RISK提案: ストップロスにlimit_price（最低約定価格）を設定し、フラッシュクラッシュ時の異常な安値約定を防止。乖離幅はATR x 1.0。

```python
from alpaca.trading.requests import (
    LimitOrderRequest, TakeProfitRequest, StopLossRequest
)

def calculate_stop_limit_prices(entry_price: float, atr: float) -> dict:
    """[v3追加] limit付きstop orderの価格設定（RISK提案）"""
    stop_price = entry_price - (atr * 2.0)
    limit_offset = atr * 1.0  # リミット価格の乖離幅 = ATR x 1.0
    limit_price = stop_price - limit_offset

    # 安全弁: リミット価格がエントリー価格の-8%を下回らない
    absolute_floor = entry_price * 0.92
    limit_price = max(limit_price, absolute_floor)

    return {
        "stop_price": round(stop_price, 2),
        "limit_price": round(limit_price, 2),
    }

# 使用例
prices = calculate_stop_limit_prices(entry_price=185.50, atr=3.2)

order = LimitOrderRequest(
    symbol="AAPL",
    qty=100,
    side="buy",
    type="limit",
    limit_price=185.50,
    time_in_force="day",
    order_class="bracket",
    take_profit=TakeProfitRequest(limit_price=195.00),
    stop_loss=StopLossRequest(
        stop_price=prices["stop_price"],     # 179.10
        limit_price=prices["limit_price"]    # 175.90 (ATR x 1.0の乖離幅)
    ),
    client_order_id=f"{execution_id}_AAPL_buy"
)
```

### [v3追加] WebSocket API（優先度: 将来 -- VPS移行後）

> ARCH提案: VPS移行後（Stage 2）にWebSocketで注文状態をリアルタイム監視。macOS段階では不要（スリープで接続が切れるため）。

```python
# modules/ws_monitor.py -- VPS移行後に導入
import asyncio
from alpaca.trading.stream import TradingStream

class OrderMonitor:
    """WebSocketで注文状態をリアルタイム監視"""

    def __init__(self, api_key: str, secret_key: str, paper: bool = True):
        self.stream = TradingStream(api_key, secret_key, paper=paper)

        @self.stream.subscribe_trade_updates
        async def on_trade_update(data):
            event = data.event
            order = data.order

            if event == "fill":
                logging.info(f"Order filled: {order.symbol} {order.qty}@{order.filled_avg_price}")
                update_trade_status(order.client_order_id, "filled",
                                    order.filled_qty, order.filled_avg_price)
            elif event == "partial_fill":
                logging.warning(f"Partial fill: {order.symbol} "
                                f"{order.filled_qty}/{order.qty}")
                handle_partial_fill(order)
                send_alert(f"Partial fill: {order.symbol}", level="warn")

    async def run(self):
        await self.stream._run_forever()
```

| 機能 | ポーリング（Phase 1-4） | WebSocket（Stage 2以降） |
|------|-----------------|------------------|
| 約定検出 | 次回実行時（数時間後） | リアルタイム |
| Partial Fill | Reconciliationで検出 | 即座に検出・対処 |
| API呼び出し回数 | 毎回 get_orders/get_positions | 常時接続（省API） |

### Market Data API / 外部データAPI

> v2から変更なし。省略。

---

## 10. [v3改訂] リスク管理機能（優先度: MVP/追加の混合）

> v2のリスク管理をベースに、RISK提案の動的リスク管理とDEVILの複雑性警告を統合。MVPでは簡易版、Phase 3以降でフル実装。

### 10.1 [v3追加] VIXレジーム判定（優先度: MVP=簡易版 / 追加=相対VIX）

> RISK提案: VIXの絶対値閾値（v2: 20/30）に加え、相対VIX（VIX/60日移動平均）で市場のボラティリティ構造変化に適応。

**MVP版（Phase 1）:** VIX絶対値のみ
```python
# MVP: 固定閾値でシンプルに
def get_vix_regime_simple(current_vix: float) -> str:
    if current_vix < 20:
        return "low"       # 5ポジション
    elif current_vix < 30:
        return "elevated"  # 3ポジション
    else:
        return "extreme"   # 新規エントリー禁止
```

**追加版（Phase 3以降）:** 相対VIX
```python
def get_vix_regime(current_vix: float, vix_ma_60d: float) -> str:
    """[v3追加] VIXの相対位置でレジーム判定（RISK提案）"""
    vix_ratio = current_vix / vix_ma_60d

    if vix_ratio < 1.0 and current_vix < 25:
        return "low"       # 5ポジション
    elif vix_ratio < 1.5 or current_vix < 30:
        return "elevated"  # 3ポジション
    else:
        return "extreme"   # 新規エントリー禁止

    # 絶対値のフロア: VIX > 35は問答無用で新規禁止
```

**[v3追加] VIXスパイク条件:**
- VIX日次変化率 > +50%: 即座に新規エントリー禁止（1営業日）
- VIX日次変化率 > +30%: ポジション数を3に制限（1営業日）

### 10.2 [v3追加] EWMA相関管理（優先度: 追加）

> RISK提案: 月次更新の静的相関では危機時の相関収束に対応できない。EWMA（指数加重移動平均）相関で日次更新し、相関ブレイクアウトを検出する。

```python
import numpy as np

def calculate_ewma_correlation(returns_matrix: np.ndarray,
                                lambda_: float = 0.94) -> np.ndarray:
    """[v3追加] EWMA相関 -- 直近のデータに重みを置く（RISK提案）
    RiskMetrics方式: 危機時の相関変化を素早く捕捉"""
    n = returns_matrix.shape[0]
    weights = np.array([(1 - lambda_) * lambda_**i for i in range(n-1, -1, -1)])
    weights /= weights.sum()
    weighted_returns = returns_matrix * weights[:, np.newaxis]
    return np.corrcoef(weighted_returns.T)
```

**相関レジーム分類:**

| 相関レジーム | 判定条件 | 最大ポジション | 優先度 |
|------------|---------|-------------|--------|
| 低相関（平常） | 平均ペア相関 < 0.5 かつ VIX < 25 | 5 | 追加 |
| 高相関（警戒） | 平均ペア相関 >= 0.5 または VIX 25-30 | 3 | 追加 |
| 超高相関（危機） | 平均ペア相関 >= 0.7 または VIX > 30 | 1-2 | 追加 |

> **DEVILの複雑性警告への対応:** MVP段階では「同一セクター2銘柄制限」で代替。EWMA相関はPhase 3以降、運用データで必要性が確認されてから導入。

### 10.3 [v3追加] 決算接近チェック（優先度: MVP）

> RISK提案: 保有ポジションの決算2営業日前にポジション縮小を自動指示。

```python
def check_earnings_proximity(positions: list, earnings_calendar: dict) -> list:
    """[v3追加] 保有ポジションの決算接近をチェック（RISK提案）"""
    warnings = []
    for pos in positions:
        earnings_date = earnings_calendar.get(pos.symbol)
        if earnings_date and (earnings_date - today).days <= 2:
            warnings.append({
                "symbol": pos.symbol,
                "earnings_date": earnings_date,
                "action": "reduce_50pct",
                "reason": "earnings_proximity"
            })
    return warnings
```

### 10.4 [v3追加] 段階的撤退の自動化（優先度: MVP）

> RISK提案 + DEVIL提案: 「どのポジションをクローズするか」の判断を機械的スコアリングで自動化。人間の判断もLLMの判断も排除する。

```python
def select_positions_to_close(positions: list, target_count: int) -> list:
    """[v3追加] 縮小対象のポジションを機械的に選定（RISK提案）"""
    if len(positions) <= target_count:
        return []

    n_to_close = len(positions) - target_count

    for pos in positions:
        pos.close_score = 0

        # (1) 保有期間がタイムストップに近い → クローズ優先
        days_held = (today - pos.entry_date).days
        if days_held > pos.time_stop_days * 0.8:
            pos.close_score += 3

        # (2) 含み損が大きい（ストップロスに近い） → クローズ優先
        loss_pct = (pos.current_price - pos.entry_price) / pos.entry_price
        if loss_pct < -0.03:
            pos.close_score += 2

        # (3) セクター重複がある → 重複セクターから優先
        sector_count = sum(1 for p in positions if p.sector == pos.sector)
        if sector_count > 1:
            pos.close_score += 1

        # (4) 直近のLLMセンチメントがネガティブに転換 → クローズ優先
        if pos.latest_sentiment == "negative":
            pos.close_score += 2

    positions_sorted = sorted(positions, key=lambda p: p.close_score, reverse=True)
    return positions_sorted[:n_to_close]
```

**段階的撤退フロー:**

| ドローダウン | アクション | 優先度 |
|------------|-----------|--------|
| 10% <= DD < 12% | select_positions_to_close()で3ポジションに縮小、新規サイズ50% | MVP |
| 12% <= DD < 15% | 1ポジションに縮小、新規エントリー停止、1週間冷却 | MVP |
| DD >= 15% | 全ポジション成行クローズ、無期限停止、CRITICAL アラート | MVP |

### 10.5 [v3追加] サーキットブレーカー段階的強化（優先度: 追加）

> RISK提案: リアル移行時に一気に閾値を50%引き下げるのではなく、段階的に厳格化。

| Stage | Level 1 | Level 2 | Level 3 | Level 4 |
|-------|---------|---------|---------|---------|
| ペーパー | 4% | 7% | 10% | 15% |
| リアル Stage 1 | 3% | 5% | 7.5% | 12% |
| リアル Stage 2 | 2.5% | 4.5% | 6% | 10% |
| リアル Stage 3-4 | 2% | 3.5% | 5% | 10% |

---

## 11. 状態管理の方法

### 信頼のソース

```
Alpaca API = Source of Truth（ポジション、残高、注文状況）
ローカルDB = 補助データ（判断理由、パフォーマンス、ログ）
config.toml = 戦略パラメータ [v3改訂: pydantic-settingsで検証]
```

### [v3改訂] SQLiteデータベース設計

> v2のスキーマに以下を追加: (1) ARCH提案のWAL最適化とバックアップ、(2) DEVIL提案のsourceカラム、(3) ARCH提案のmetricsテーブル。

ファイル: `data/state/trading.db`

```sql
-- ポジション [v3改訂: sourceカラム追加]
CREATE TABLE positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL DEFAULT 'long',
    qty REAL NOT NULL,
    entry_price REAL NOT NULL,
    entry_date TEXT NOT NULL CHECK(entry_date GLOB '????-??-??'),
    stop_loss REAL,
    take_profit REAL,
    strategy_reason TEXT,
    sentiment_score REAL,
    status TEXT NOT NULL DEFAULT 'open',
    close_price REAL,
    close_date TEXT CHECK(close_date IS NULL OR close_date GLOB '????-??-??'),
    close_reason TEXT,  -- tp / sl / time_stop / signal / circuit_breaker / reconciliation
    pnl REAL,
    alpaca_order_id TEXT,
    source TEXT NOT NULL DEFAULT 'agent',  -- [v3追加] 'agent' / 'reconciliation' / 'manual' (DEVIL提案)
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_positions_symbol ON positions(symbol);
CREATE INDEX idx_positions_status ON positions(status);
CREATE INDEX idx_positions_entry_date ON positions(entry_date);

-- 取引履歴
CREATE TABLE trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id INTEGER REFERENCES positions(id),
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    qty REAL NOT NULL,
    price REAL NOT NULL,
    order_type TEXT NOT NULL,
    alpaca_order_id TEXT,
    client_order_id TEXT,
    fill_status TEXT,
    executed_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_trades_symbol ON trades(symbol);
CREATE INDEX idx_trades_position_id ON trades(position_id);
CREATE INDEX idx_trades_executed_at ON trades(executed_at);

-- 日次スナップショット
CREATE TABLE daily_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE CHECK(date GLOB '????-??-??'),
    total_equity REAL NOT NULL,
    cash REAL NOT NULL,
    positions_value REAL NOT NULL,
    daily_pnl REAL,
    daily_pnl_pct REAL,
    drawdown_pct REAL,
    open_positions INTEGER,
    benchmark_spy_close REAL,
    macro_regime TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_daily_snapshots_date ON daily_snapshots(date);

-- エージェント実行ログ
CREATE TABLE execution_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id TEXT NOT NULL,
    mode TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    llm_input_tokens INTEGER,
    llm_output_tokens INTEGER,
    llm_cost_usd REAL,
    llm_model_version TEXT,
    decisions_json TEXT,
    error_message TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_execution_logs_execution_id ON execution_logs(execution_id);
CREATE INDEX idx_execution_logs_mode ON execution_logs(mode);

-- 回路ブレーカー状態
CREATE TABLE circuit_breaker (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    level INTEGER NOT NULL,
    triggered_at TEXT NOT NULL,
    reason TEXT NOT NULL,
    resolved_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_circuit_breaker_level ON circuit_breaker(level);

-- 戦略パラメータ履歴
CREATE TABLE strategy_params (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    param_name TEXT NOT NULL,
    param_value TEXT NOT NULL,
    changed_at TEXT NOT NULL,
    reason TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Reconciliation履歴
CREATE TABLE reconciliation_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id TEXT NOT NULL,
    issue_type TEXT NOT NULL,
    symbol TEXT NOT NULL,
    details TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- スキーマバージョン管理
CREATE TABLE schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT DEFAULT (datetime('now')),
    description TEXT
);

-- [v3追加] オブザーバビリティメトリクス（ARCH提案）
CREATE TABLE metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    execution_id TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL
);
CREATE INDEX idx_metrics_name_ts ON metrics(metric_name, timestamp);
```

### [v3改訂] SQLite WAL最適化 + バックアップ（優先度: MVP）

> ARCH提案: WALチェックポイント設定の最適化、Online Backup APIによる安全なバックアップ、古いデータのアーカイブ。

```python
# modules/db.py
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

def init_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA wal_autocheckpoint=500")  # [v3追加] 500ページ=約2MB
    conn.execute("PRAGMA busy_timeout=5000")        # [v3追加] ロック待ち5秒
    return conn


def backup_db(source_path: str, backup_dir: str) -> str:
    """[v3追加] SQLite Online Backup APIを使用した安全なバックアップ（ARCH提案）"""
    backup_name = f"trading_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    backup_path = Path(backup_dir) / backup_name

    source = sqlite3.connect(source_path)
    dest = sqlite3.connect(str(backup_path))
    with dest:
        source.backup(dest)  # WALモード中でも安全
    dest.close()
    source.close()

    # 古いバックアップの削除（7世代保持）
    backups = sorted(Path(backup_dir).glob("trading_*.db"))
    for old in backups[:-7]:
        old.unlink()

    return str(backup_path)


def vacuum_old_data(conn: sqlite3.Connection, retention_days: int = 90):
    """[v3追加] 古いデータのアーカイブと圧縮（ARCH提案）"""
    cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat()

    conn.execute("""
        UPDATE execution_logs
        SET decisions_json = json_extract(decisions_json, '$.decisions[0].action')
        WHERE created_at < ? AND decisions_json IS NOT NULL
          AND length(decisions_json) > 1000
    """, (cutoff,))

    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.commit()
```

**バックアップスケジュール:**

| タイミング | 方法 | 保持期間 |
|-----------|------|---------|
| 日次（EOD実行後） | `backup_db()` | 7日分 |
| 週次（日曜） | バックアップ + VACUUM | 4週分 |

### マイグレーション戦略

> v2から変更なし。

```python
MIGRATIONS = {
    1: ("CREATE TABLE schema_version ...", "Initial schema version table"),
    2: ("CREATE INDEX idx_positions_symbol ON positions(symbol)", "Add positions index"),
    3: ("ALTER TABLE trades ADD COLUMN client_order_id TEXT", "Add idempotency key"),
    4: ("ALTER TABLE positions ADD COLUMN source TEXT DEFAULT 'agent'", "[v3] Add source column"),
    5: ("CREATE TABLE metrics ...", "[v3] Add metrics table"),
}

def migrate(conn):
    current = conn.execute(
        "SELECT MAX(version) FROM schema_version"
    ).fetchone()[0] or 0
    for version, (sql, desc) in sorted(MIGRATIONS.items()):
        if version > current:
            conn.execute(sql)
            conn.execute(
                "INSERT INTO schema_version (version, description) VALUES (?, ?)",
                (version, desc)
            )
    conn.commit()
```

---

## 12. [v3改訂] 設定管理 -- pydantic-settings検証（優先度: MVP）

> ARCH提案: v2の`tomllib.load()`による辞書返却では型チェック・値域チェック・必須キー検出がない。pydantic-settingsで型安全+バリデーション+デフォルト値+環境変数統合を実現。

### config.toml（v2から変更なし）

```toml
[strategy]
sentiment_confidence_threshold = 70
ma_period = 50
rsi_period = 14
rsi_upper = 70
rsi_lower = 30
volume_compare_period = 20
stop_loss_atr_multiplier = 2.0
take_profit_pct = 5.0
time_stop_days = 10
max_concurrent_positions = 5
max_daily_entries = 2
min_holding_days = 2

[risk]
max_risk_per_trade_pct = 1.5
slippage_factor = 1.3
max_position_pct = 20.0
circuit_breaker_level1_pct = 4.0
circuit_breaker_level2_pct = 7.0
circuit_breaker_level3_pct = 10.0
circuit_breaker_level4_pct = 15.0

[system]
db_path = "data/state/trading.db"
log_dir = "logs"
claude_timeout_seconds = 120
lock_file_path = "data/state/agent.lock"

[alpaca]
paper = true

[alerts]
slack_enabled = true
alert_levels = ["warn", "error", "critical"]
```

### [v3追加] pydantic-settings設定ローダー

```python
# modules/config.py
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class StrategyConfig(BaseSettings):
    sentiment_confidence_threshold: int = Field(
        default=70, ge=50, le=100,
        description="LLMセンチメント確信度の最低閾値"
    )
    ma_period: int = Field(default=50, ge=5, le=500)
    rsi_period: int = Field(default=14, ge=5, le=30)
    rsi_upper: int = Field(default=70, ge=50, le=95)
    rsi_lower: int = Field(default=30, ge=5, le=50)
    volume_compare_period: int = Field(default=20, ge=5, le=60)
    stop_loss_atr_multiplier: float = Field(default=2.0, ge=0.5, le=5.0)
    take_profit_pct: float = Field(default=5.0, ge=1.0, le=20.0)
    time_stop_days: int = Field(default=10, ge=1, le=30)
    max_concurrent_positions: int = Field(default=5, ge=1, le=10)
    max_daily_entries: int = Field(default=2, ge=1, le=5)
    min_holding_days: int = Field(default=2, ge=0, le=10)

class RiskConfig(BaseSettings):
    max_risk_per_trade_pct: float = Field(default=1.0, ge=0.1, le=5.0)
    slippage_factor: float = Field(default=1.3, ge=1.0, le=2.0)
    max_position_pct: float = Field(default=20.0, ge=5.0, le=50.0)
    circuit_breaker_level1_pct: float = Field(default=4.0, ge=1.0, le=10.0)
    circuit_breaker_level2_pct: float = Field(default=7.0, ge=2.0, le=15.0)
    circuit_breaker_level3_pct: float = Field(default=10.0, ge=5.0, le=20.0)
    circuit_breaker_level4_pct: float = Field(default=15.0, ge=10.0, le=30.0)

class SystemConfig(BaseSettings):
    db_path: str = "data/state/trading.db"
    log_dir: str = "logs"
    claude_timeout_seconds: int = Field(default=120, ge=30, le=300)
    lock_file_path: str = "data/state/agent.lock"

class AlpacaConfig(BaseSettings):
    paper: bool = True

class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        toml_file="config.toml",
        env_prefix="TRADING_",
    )
    strategy: StrategyConfig = StrategyConfig()
    risk: RiskConfig = RiskConfig()
    system: SystemConfig = SystemConfig()
    alpaca: AlpacaConfig = AlpacaConfig()
```

---

## 13. エラーハンドリング方針

### エラー分類と対応

| エラー種別 | 対応 | v3変更 |
|-----------|------|--------|
| ネットワークエラー | 3回リトライ（指数バックオフ） | - |
| API認証エラー | 即座にアラート。実行停止 | - |
| レート制限 (429) | Retry-Afterヘッダー参照→待機 | - |
| Claude CLI エラー | [v3改訂] JSON Schema検証+フォールバック+リトライ2回 | ARCH統合 |
| 注文拒否 | ログ記録。次回実行で再判断 | - |
| Partial Fill | ストップロス数量を調整 | - |
| DB書き込みエラー | アラート。注文は実行するがログ欠損 | - |
| 不整合検出 | [v3改訂] 二重APIコール+3件以上は自動修正停止 | DEVIL統合 |
| 市場休場日 | exchange_calendarsで判定、スキップ | - |

### [v3追加] limit付きstop order未約定時のフォールバック（優先度: MVP）

> RISK提案: limit付きstop orderが急落で未約定となった場合の対処フロー。

```
未約定検出 → midday/eod実行時に以下を判断:
  (a) 株価がリミット価格以下で推移中 → 成行注文で即クローズ（損切り確定）
  (b) 株価がストップ-リミットの間 → 新しいlimit付きstop orderを再設定
  (c) 株価がストップ価格以上に回復 → 元のストップロスを維持

Reconciliationで未約定ストップロスを検出する仕組みをorder_executor.pyに追加。
```

---

## 14. [v3改訂] 監視・アラート + オブザーバビリティ

### Slack Webhook実装

> v2から変更なし。

```python
# modules/alerter.py
import os, json, logging, urllib.request

SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")
LEVEL_EMOJI = {
    "info": ":information_source:",
    "warn": ":warning:",
    "error": ":rotating_light:",
    "critical": ":fire:"
}

def send_alert(message: str, level: str = "info"):
    log_func = getattr(logging, level if level != "critical" else "error")
    log_func(f"[ALERT:{level.upper()}] {message}")

    if not SLACK_WEBHOOK_URL or level == "info":
        return

    payload = {"text": f"{LEVEL_EMOJI.get(level, '')} [{level.upper()}] {message}"}
    try:
        req = urllib.request.Request(
            SLACK_WEBHOOK_URL,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        logging.error(f"Failed to send Slack alert: {e}")
```

### [v3追加] ログローテーション + 構造化ロギング（優先度: MVP）

> ARCH提案: v2のテキストベースログをJSON lines形式に改善し、RotatingFileHandlerでローテーションを自動化。

```python
# modules/logger.py
import logging
import logging.handlers
from pathlib import Path

def setup_logging(log_dir: str, execution_id: str):
    """[v3追加] ログローテーション付きのロギング設定（ARCH提案）"""
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # メインログ: 10MB x 5世代ローテーション
    handler = logging.handlers.RotatingFileHandler(
        log_path / "agent.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8"
    )

    # 構造化ログフォーマット（JSON lines）
    formatter = logging.Formatter(
        '{"ts":"%(asctime)s","level":"%(levelname)s",'
        '"module":"%(module)s","func":"%(funcName)s",'
        f'"exec_id":"{execution_id}",'
        '"msg":"%(message)s"}'
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)

    # コンソール出力（開発用）
    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    console.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    root.addHandler(console)
```

**ログレベルガイドライン:**

| レベル | 用途 | 例 |
|--------|------|-----|
| DEBUG | 開発・デバッグ用。本番では無効 | API応答の生データ |
| INFO | 正常な業務フロー | 注文送信: AAPL BUY 30株 |
| WARNING | 異常だが処理は継続可能 | Partial Fill検出 |
| ERROR | 処理が失敗した | Claude CLIタイムアウト |
| CRITICAL | システム全体に影響 | 回路ブレーカーLevel 3発動 |

### [v3追加] オブザーバビリティメトリクス（優先度: 追加）

> ARCH提案: SQLiteにメトリクスを記録し、異常の予兆を検知する。Prometheus/Grafanaは過剰だが、SQLite+簡易スクリプトで実現。

**収集メトリクス:**

| メトリクス名 | 用途 | 優先度 |
|-------------|------|--------|
| `claude_response_time_ms` | LLMレスポンス劣化の検知 | MVP |
| `claude_input_tokens` / `claude_output_tokens` | コスト追跡 | MVP |
| `api_error_count` | API障害の検知 | MVP |
| `reconciliation_issues` | 状態不整合の頻度 | MVP |
| `signal_count` | シグナル頻度の監視 | 追加 |
| `filter_pass_rate` | テクニカルフィルターの通過率 | 追加 |
| `db_size_bytes` | DBファイルの肥大化検知 | 追加 |
| `execution_duration_ms` | 全体の実行時間の監視 | 追加 |

**異常検知（閾値ベース）:**

```python
def check_anomalies(conn):
    """[v3追加] メトリクスの異常を検知してアラート（ARCH提案）"""
    # Claude CLI応答時間が過去7日平均の2倍を超えた
    avg_7d = get_metric_avg(conn, "claude_response_time_ms", days=7)
    latest = get_metric_latest(conn, "claude_response_time_ms")
    if latest > avg_7d * 2:
        send_alert(f"Claude CLI response time anomaly: {latest}ms "
                   f"(7d avg: {avg_7d}ms)", level="warn")

    # シグナル数が過去30日平均の50%未満
    avg_30d = get_metric_avg(conn, "signal_count", days=30)
    latest_week = get_metric_sum(conn, "signal_count", days=7)
    if latest_week < avg_30d * 7 / 30 * 0.5:
        send_alert(f"Signal frequency drop: {latest_week}/week "
                   f"(expected: {avg_30d * 7 / 30:.0f})", level="warn")
```

---

## 15. [v3追加] Phase 0検証ツールキット（優先度: MVP）

> ARCH提案 + QUANT提案: Phase 0はプロジェクトのGo/No-Go判断を担う最重要フェーズ。4,000件のバッチLLM実行を手動管理するのは非現実的。リジューム対応パイプラインを構築する。STRAT提案の時間バイアス検定プロトコルもシステム化する。

### Phase 0パイプラインクラス

```python
# tools/phase0_runner.py
"""Phase 0: LLMセンチメント精度検証パイプライン"""
import json, time, sqlite3, subprocess
from pathlib import Path
from dataclasses import dataclass

@dataclass
class EarningsEvent:
    symbol: str
    date: str
    eps_actual: float
    eps_estimate: float
    revenue_actual: float
    revenue_estimate: float
    news_text: str
    return_5d: float

class Phase0Pipeline:
    def __init__(self, db_path: str = "data/phase0/results.db"):
        self.db = sqlite3.connect(db_path)
        self._init_tables()

    def _init_tables(self):
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS sentiment_results (
                id INTEGER PRIMARY KEY,
                symbol TEXT, event_date TEXT,
                llm_sentiment TEXT, llm_confidence INTEGER,
                finbert_sentiment TEXT, finbert_score REAL,
                vader_sentiment TEXT, vader_score REAL,
                actual_return_5d REAL,
                gold_standard TEXT,
                processed_at TEXT,
                UNIQUE(symbol, event_date)
            )
        """)
        self.db.commit()

    def run_batch(self, events: list[EarningsEvent],
                  batch_size: int = 10, delay: float = 1.0):
        """バッチLLM実行（リジューム対応）"""
        for i, event in enumerate(events):
            if self._already_processed(event):
                continue

            llm_result = self._call_claude(event)
            finbert_result = self._call_finbert(event.news_text)
            vader_result = self._call_vader(event.news_text)
            gold = self._classify_return(event.return_5d)

            self._save_result(event, llm_result, finbert_result,
                              vader_result, gold)

            if (i + 1) % batch_size == 0:
                time.sleep(delay)
                print(f"Processed {i+1}/{len(events)}")

    def generate_report(self) -> str:
        """Go/No-Goレポートの自動生成"""
        results = self.db.execute(
            "SELECT * FROM sentiment_results"
        ).fetchall()

        llm_accuracy = self._calc_directional_accuracy("llm")
        finbert_accuracy = self._calc_directional_accuracy("finbert")
        vader_accuracy = self._calc_directional_accuracy("vader")

        report = f"""# Phase 0 検証レポート
## サンプル数: {len(results)}

## 方向性精度
| モデル | 精度 |
|--------|------|
| Claude LLM | {llm_accuracy:.1%} |
| FinBERT | {finbert_accuracy:.1%} |
| VADER | {vader_accuracy:.1%} |
| ランダム | 33.3% |

## Go/No-Go判定
- LLM精度: {"PASS" if llm_accuracy >= 0.6 else "FAIL"} (基準: >= 60%)
- 判定: {"**GO**" if llm_accuracy >= 0.6 else "**NO-GO**"}
"""
        return report
```

### [v3追加] QUANT提案: バックテスト実装コンポーネント

**tech_score正規化（パーセンタイルランク推奨）:**

```python
import numpy as np
from scipy import stats

def compute_tech_score(
    ma_distances: np.ndarray,
    rsi_values: np.ndarray,
    volume_ratios: np.ndarray,
    weights: tuple = (0.4, 0.3, 0.3)
) -> np.ndarray:
    """[v3追加] テクニカルスコアの計算（QUANT提案）
    パーセンタイルランクで正規化。外れ値に頑健。"""
    w_ma, w_rsi, w_vol = weights
    norm_ma = stats.rankdata(ma_distances, method='average') / len(ma_distances)
    rsi_neutral_score = 1.0 - stats.rankdata(
        np.abs(rsi_values - 50), method='average'
    ) / len(rsi_values)
    norm_vol = stats.rankdata(volume_ratios, method='average') / len(volume_ratios)
    return w_ma * norm_ma + w_rsi * rsi_neutral_score + w_vol * norm_vol
```

**PurgedTimeSeriesSplit（金融時系列向けCV）:**

```python
class PurgedTimeSeriesSplit:
    """[v3追加] 金融時系列向けクロスバリデーション（QUANT提案）
    Lopez de Prado (2018) の簡略化実装。purge/embargo期間でデータリーケージ防止。

    |<-- train -->|<purge>|<-- test -->|<embargo>|
    """
    def __init__(self, n_splits=5, train_period_days=252,
                 test_period_days=63, purge_days=10, embargo_days=5):
        self.n_splits = n_splits
        self.train_period_days = train_period_days
        self.test_period_days = test_period_days
        self.purge_days = purge_days
        self.embargo_days = embargo_days

    def split(self, dates: np.ndarray):
        """Expanding Window + パージ + エンバーゴ"""
        # 実装は tools/phase0_runner.py に含める
        pass
```

**BayesianSharpeEstimator（事前分布感度分析付き）:**

```python
class BayesianSharpeEstimator:
    """[v3追加] シャープレシオのベイズ推定器（QUANT提案）
    共役事前分布（正規-正規モデル）で解析的に事後分布を計算。"""

    def __init__(self, prior_sr_mean: float = 0.0, prior_sr_std: float = 0.5):
        self.typical_sigma = 0.015
        self.prior_mu_mean = prior_sr_mean * self.typical_sigma / np.sqrt(252)
        self.prior_mu_var = (prior_sr_std * self.typical_sigma / np.sqrt(252)) ** 2

    def update(self, daily_returns: np.ndarray) -> dict:
        n = len(daily_returns)
        sample_mean = np.mean(daily_returns)
        sample_var = np.var(daily_returns, ddof=1)

        posterior_precision = 1/self.prior_mu_var + n/sample_var
        posterior_var = 1 / posterior_precision
        posterior_mean = posterior_var * (
            self.prior_mu_mean / self.prior_mu_var + n * sample_mean / sample_var
        )

        posterior_sr_mean = posterior_mean / np.sqrt(sample_var) * np.sqrt(252)
        posterior_sr_std = np.sqrt(posterior_var) / np.sqrt(sample_var) * np.sqrt(252)

        prob_sr_above_05 = 1 - stats.norm.cdf(
            0.5, loc=posterior_sr_mean, scale=posterior_sr_std
        )

        return {
            "posterior_sr_mean": posterior_sr_mean,
            "posterior_sr_std": posterior_sr_std,
            "prob_sr_above_05": prob_sr_above_05,
            "n_observations": n,
            "sample_sr": sample_mean / np.sqrt(sample_var) * np.sqrt(252),
        }

    def sensitivity_analysis(self, daily_returns: np.ndarray) -> dict:
        """[v3追加] 事前分布の感度分析（QUANT提案）
        3つの事前分布で結果がどう変わるかを報告。"""
        priors = [
            ("skeptical", 0.0, 0.3),
            ("neutral", 0.0, 0.5),
            ("optimistic", 0.2, 0.7),
        ]
        results = {}
        for name, sr_mean, sr_std in priors:
            estimator = BayesianSharpeEstimator(sr_mean, sr_std)
            results[name] = estimator.update(daily_returns)
        return results
```

**ConfidenceCalibrator（Platt Scaling + Isotonic）:**

```python
from sklearn.linear_model import LogisticRegression
from sklearn.isotonic import IsotonicRegression
from sklearn.calibration import calibration_curve

class ConfidenceCalibrator:
    """[v3追加] LLM確信度のキャリブレーション（QUANT提案）
    Phase 0のデータで初期キャリブレーション。運用後は月次更新。"""

    def __init__(self, method: str = "platt"):
        self.method = method
        if method == "platt":
            self.model = LogisticRegression(C=1.0)
        else:
            self.model = IsotonicRegression(out_of_bounds="clip")
        self.is_fitted = False

    def fit(self, raw_confidences: np.ndarray, actual_outcomes: np.ndarray):
        if len(raw_confidences) < 50:
            raise ValueError(f"サンプル数{len(raw_confidences)}は不足。最低50件必要。")
        if self.method == "platt":
            self.model.fit(raw_confidences.reshape(-1, 1), actual_outcomes)
        else:
            self.model.fit(raw_confidences, actual_outcomes)
        self.is_fitted = True

    def calibrate(self, raw_confidence: float) -> float:
        if not self.is_fitted:
            return raw_confidence
        if self.method == "platt":
            return self.model.predict_proba(np.array([[raw_confidence]]))[0, 1]
        else:
            return self.model.predict(np.array([raw_confidence]))[0]

    def reliability_diagram(self, raw_confidences, actual_outcomes) -> dict:
        """ECE（Expected Calibration Error）の算出。目標: < 0.05"""
        fraction_positive, mean_predicted = calibration_curve(
            actual_outcomes, raw_confidences, n_bins=5, strategy='uniform'
        )
        bins = np.arange(0.5, 1.05, 0.1)
        bin_counts = np.histogram(raw_confidences, bins=bins)[0]
        ece = np.sum(
            bin_counts / len(raw_confidences) *
            np.abs(fraction_positive - mean_predicted)
        )
        return {"ece": float(ece)}
```

---

## 16. [v3追加] STRAT提案: Alpha Decayモニタリング実装要件（優先度: 追加）

> STRAT提案: LLMセンチメントのエッジ消失速度を月次で追跡し、エッジ半減期を推定する。初月からトラッキング開始。

**実装要件:**

1. **月次精度トラッキング**: LLMセンチメント精度の3ヶ月移動平均を計算
2. **Alpha Decay Warning**: 移動平均が2ヶ月連続低下時にアラート
3. **Alpha Decay Critical**: 移動平均がPhase 0基準（60%）に到達時
4. **Edge Half-Life推定**: 6ヶ月分のデータ蓄積後に回帰分析で推定

```
月次チェック:
  if 精度_3ヶ月MA[t] < 精度_3ヶ月MA[t-1] < 精度_3ヶ月MA[t-2]:
      send_alert("Alpha Decay Warning: 3-month declining trend", level="warn")
  if 精度_3ヶ月MA[t] < Phase0基準(0.60):
      send_alert("Alpha Decay Critical: below Phase 0 baseline", level="error")
```

**エッジ枯渇時のプランC（STRAT提案）:**
- LLMの役割を「エントリーシグナル」から「リスクフィルター」に切替
- テクニカル/モメンタムでエントリー候補を選定、LLMはネガティブリスクのスクリーニングに使用
- プロンプトの差別化: 「コンセンサスとの乖離度」「一時的要因vs構造的要因の判別」に特化

---

## 17. テスト戦略

### [v3改訂] 3層テスト構造 + ミューテーションテスト

> v2の3層テスト構造を維持しつつ、DEVIL提案のミューテーションテストとプロパティベーステストを追加。

```
Layer 1: 単体テスト（pytest）-- 優先度: MVP
├── テクニカルフィルター（MA, RSI計算の正確性）
├── ポジションサイズ計算（ATRベース + スリッページバッファ）
├── 回路ブレーカー判定ロジック
├── 市場休場日判定（exchange_calendars）
├── Reconciliation差分検出
├── JSONスキーマバリデーション [v3追加]
├── 冪等性チェック
├── config.tomlの読み込み・バリデーション [v3改訂: pydantic-settings]
├── [v3追加] 型定義（types.py）の不変条件テスト
└── [v3追加] limit付きstop order価格計算テスト

Layer 2: 結合テスト（pytest + モック）-- 優先度: MVP
├── Alpaca API モック → 注文実行フロー
├── Claude CLI モック → 分析→判断フロー [v3改訂: フォールバック含む]
├── SQLite in-memory DB → 状態管理フロー
├── Reconciliation → DB更新フロー [v3改訂: 二重APIコール含む]
└── エラーハンドリングフロー

Layer 3: E2Eテスト（ペーパートレーディング環境）-- 優先度: MVP
├── 1サイクル全通し
├── [v3追加] カナリアリリース（最初の2週間は1ポジションのみ）
└── ヘルスチェック→アラート送信確認

[v3追加] Layer 4: ミューテーションテスト -- 優先度: 追加
├── risk_manager.pyに mutmut を適用（DEVIL提案）
└── 条件式反転でテストが失敗することを検証

[v3追加] Layer 5: プロパティベーステスト（hypothesis）-- 優先度: 追加
├── 「ポジションサイズは常に0以上」
├── 「ストップロスは常にエントリー価格未満」
└── 「limit_priceは常にstop_price以下」
```

### カバレッジ目標

| モジュール | 目標 | 理由 |
|-----------|------|------|
| risk_manager.py | 95%以上 | ここのバグは実損に直結 |
| order_executor.py | 90%以上 | 注文ミスは取り返しがつかない |
| state_manager.py | 85%以上 | Reconciliationの正確性が重要 |
| llm_analyzer.py | 85%以上 | [v3追加] フォールバック経路の検証 |
| data_collector.py | 70%以上 | 外部API依存部分はモック |
| 全体 | 80%以上 | - |

> **DEVIL警告への対応:** カバレッジ95%は「コードの95%の行が最低1回実行された」ことのみを保証。境界値バグや状態遷移バグはカバレッジでは検出できない。Layer 4（ミューテーションテスト）とLayer 5（プロパティベーステスト）で補完する。ただしLayer 4-5はPhase 3以降の追加項目。

---

## 18. CI/CD

### [v3改訂] GitHub Actions CI

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt -r requirements-dev.txt
      - run: pytest tests/ --cov=modules --cov-report=xml --cov-fail-under=80
      - run: ruff check .
      - run: ruff format --check .
      - run: mypy --strict modules/types.py  # [v3追加] 型チェック

      # [v3追加] config.toml「1変数ずつ」ルールのCI強制（ARCH提案）
      - name: Check config.toml changes
        if: github.event_name == 'pull_request'
        run: |
          CHANGES=$(git diff origin/main -- config.toml | grep '^[+-]' | grep -v '^[+-][+-]' | grep -v '^[+-]\s*#' | wc -l)
          if [ "$CHANGES" -gt 2 ]; then
            echo "ERROR: config.toml changes more than 1 parameter."
            exit 1
          fi
```

---

## 19. [v3改訂] ディレクトリ構成

```
alpaca-trading/
├── CLAUDE.md
├── config.toml
├── .env
├── .gitignore
├── Dockerfile
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml
├── trading_agent.py                  # [v3改訂] Lambda互換エントリーポイント
├── docs/
│   ├── strategy.md
│   ├── system-design.md
│   ├── planning-log.md
│   └── action-plan.md
├── modules/
│   ├── __init__.py
│   ├── types.py                      # [v3追加] 型定義（dataclasses + Protocol）
│   ├── config.py                     # [v3改訂] pydantic-settings
│   ├── db.py                         # [v3改訂] WAL最適化 + バックアップ
│   ├── logger.py                     # [v3追加] 構造化ロギング + ローテーション
│   ├── data_collector.py
│   ├── state_manager.py              # [v3改訂] 二重APIコール + sourceカラム
│   ├── llm_analyzer.py               # [v3改訂] JSON Schema検証 + フォールバック
│   ├── risk_manager.py               # [v3改訂] VIXレジーム + EWMA相関 + 決算接近
│   ├── order_executor.py             # [v3改訂] limit付きstop order
│   ├── alerter.py
│   └── health_check.py
├── prompts/
│   ├── trading_decision.md
│   └── daily_report.md
├── tools/                             # [v3追加] 検証ツールキット
│   ├── phase0_runner.py               # Phase 0検証パイプライン
│   ├── phase0_data_collector.py       # 決算データ収集
│   ├── phase0_report.py               # レポート生成
│   └── weekly_dashboard.py            # [v3追加] メトリクスダッシュボード
├── data/
│   ├── state/
│   │   ├── trading.db
│   │   └── agent.lock
│   ├── phase0/                        # [v3追加] Phase 0専用データ
│   │   ├── results.db
│   │   └── earnings_data/
│   ├── market/
│   └── analysis/
├── logs/
├── tests/
│   ├── conftest.py
│   ├── test_types.py                  # [v3追加]
│   ├── test_risk_manager.py
│   ├── test_order_executor.py
│   ├── test_state_manager.py
│   ├── test_llm_analyzer.py           # [v3追加] フォールバックテスト
│   ├── test_data_collector.py
│   └── test_reconciliation.py
├── deploy/                             # [v3追加] マイグレーション資材
│   ├── launchd/
│   │   └── com.alpaca-trading.*.plist
│   ├── systemd/                       # [v3追加]
│   │   ├── alpaca-trading-*.service
│   │   └── alpaca-trading-*.timer
│   ├── lambda/                        # [v3追加]
│   │   └── handler.py
│   ├── migrate-to-vps.sh             # [v3追加]
│   └── migrate-to-aws.sh             # [v3追加]
├── .github/
│   └── workflows/
│       └── ci.yml                     # [v3改訂] mypy + config.tomlチェック追加
└── .claude/
    └── skills/
```

---

## 20. [v3追加] DEVILの複雑性警告と優先度マトリクス

> DEVIL指摘: v2は「理想的だが実装しきれない」設計。推定開発工数178h + 月次メンテナンス39h/月は個人開発者に過剰。MVP思想で初期実装スコープを縮小し、運用データが必要性を証明した機能のみ追加する。

### 優先度マトリクス

| 機能 | 優先度 | Phase | 推定工数 | 備考 |
|------|--------|-------|---------|------|
| 型安全インターフェース (types.py) | **MVP** | 1 | 4h | 後から導入は困難 |
| pydantic-settings設定検証 | **MVP** | 1 | 4h | 後から導入は困難 |
| JSON Schema検証+フォールバック | **MVP** | 2 | 8h | LLM出力の信頼性 |
| 構造化ロギング+ローテーション | **MVP** | 1 | 2h | 運用必須 |
| SQLite WAL最適化+バックアップ | **MVP** | 1 | 2h | データ保護 |
| Reconciliation安全性強化 | **MVP** | 2 | 4h | 二重APIコール+sourceカラム |
| limit付きstop order | **MVP** | 2 | 4h | リスク保護 |
| 決算接近チェック | **MVP** | 2 | 2h | ギャップリスク防御 |
| 段階的撤退自動化 | **MVP** | 2 | 8h | リスク管理の核心 |
| Phase 0検証パイプライン | **MVP** | 0 | 16h | Go/No-Go判断の基盤 |
| VIXレジーム（簡易版） | **MVP** | 2 | 2h | 固定閾値のみ |
| **MVP合計** | | | **56h** | |
| VIXレジーム（相対VIX） | 追加 | 3 | 4h | EWMA含む |
| EWMA相関管理 | 追加 | 3 | 12h | MVP: セクター制限で代替 |
| オブザーバビリティメトリクス | 追加 | 3 | 8h | DDL先行、記録は段階的 |
| Alpha Decayモニタリング | 追加 | 3 | 8h | 月次精度トラッキング |
| サーキットブレーカー段階的強化 | 追加 | 4+ | 4h | リアル移行時 |
| ミューテーションテスト | 追加 | 3 | 8h | risk_managerのみ |
| プロパティベーステスト | 追加 | 3 | 4h | hypothesis導入 |
| **追加合計** | | | **48h** | |
| WebSocket API | 将来 | VPS移行後 | 16h | Stage 2以降 |
| systemdマイグレーション | 将来 | VPS移行時 | 8h | スクリプト+テスト |
| Lambda/EventBridge | 将来 | リアル移行時 | 16h | Stage 3 |
| BayesianSharpeEstimator | 将来 | Phase 4+ | 8h | MVP: ブートストラップで代替 |
| ConfidenceCalibrator | 将来 | Phase 4+ | 8h | MVP: 生値で運用 |
| PurgedTimeSeriesSplit | 将来 | Phase 4+ | 8h | バックテスト精緻化 |
| **将来合計** | | | **64h** | |

**合計: MVP 56h + 追加 48h + 将来 64h = 168h**

> DEVILの指摘（178h）とほぼ一致。MVP 56hに集中することで、Phase 1-2の開発期間を約1.5週間（フルタイム）に圧縮可能。

### [v3追加] 撤退判断のシステム化（DEVIL提案）

> 撤退基準に抵触した場合、trading_agent.pyが自動的に新規エントリーを停止する仕組み。

```
月次チェックポイントで撤退基準に抵触した場合:
  1. config.toml の max_daily_entries を 0 に自動設定
  2. Slack通知: 「撤退基準に抵触。新規エントリー停止。
     再開するには config.toml の force_resume = true を設定してください」
  3. 再開のハードルを意図的に上げることで、サンクコスト心理に対抗
```

---

## 21. 変更履歴

| バージョン | 日付 | 変更内容 |
|-----------|------|---------|
| v1 | 2026-02-11 | 初版作成 |
| v2 | 2026-02-11 | 5名レビュー統合版。全Python化、cron→launchd移行、SQLiteスキーマ改善、冪等性3重防御、Reconciliation、エラーハンドリング強化、テスト戦略、CI/CD、設定管理分離、Slack監視、ブラケット注文 |
| v3 | 2026-02-11 | 5名v3レビュー統合版。**主要変更:** 型安全モジュールI/F（ARCH）、Claude CLI JSON Schema検証+フォールバック（ARCH）、SQLite WAL最適化+バックアップ（ARCH）、pydantic-settings設定検証（ARCH）、マイグレーションスクリプト具体化（ARCH）、構造化ロギング（ARCH）、Phase 0検証パイプライン（ARCH+QUANT）、オブザーバビリティメトリクス（ARCH）、VIXレジーム判定（RISK）、EWMA相関管理（RISK）、limit付きstop order（RISK）、段階的撤退自動化（RISK）、決算接近チェック（RISK）、サーキットブレーカー段階的強化（RISK）、tech_score正規化（QUANT）、PurgedTimeSeriesSplit（QUANT）、BayesianSharpeEstimator（QUANT）、ConfidenceCalibrator（QUANT）、Phase 0プロトコル精緻化（STRAT）、Alpha Decayモニタリング（STRAT）、Reconciliation安全性強化（DEVIL）、MVP優先度マトリクス（DEVIL）、撤退判断システム化（DEVIL） |

### v3レビュー提案の反映状況

| レビュアー | 主要提案 | 反映状況 | 優先度 |
|-----------|---------|---------|--------|
| **ARCH** | 型安全モジュールインターフェース（dataclasses + Protocol） | 完全反映（セクション2） | MVP |
| ARCH | Claude CLI JSON Schema検証 + フォールバック | 完全反映（セクション7） | MVP |
| ARCH | SQLite WAL最適化 + Online Backup API | 完全反映（セクション11） | MVP |
| ARCH | pydantic-settings設定検証 | 完全反映（セクション12） | MVP |
| ARCH | マイグレーションスクリプト（launchd→systemd→Lambda） | 完全反映（セクション3） | 追加/将来 |
| ARCH | WebSocket API（OrderMonitorクラス） | 完全反映（セクション9） | 将来 |
| ARCH | ログローテーション + 構造化ロギング | 完全反映（セクション14） | MVP |
| ARCH | Phase 0検証ツールキット | 完全反映（セクション15） | MVP |
| ARCH | オブザーバビリティメトリクス | 完全反映（セクション14） | 追加 |
| **QUANT** | Phase 0バックテストパイプライン実装 | 完全反映（セクション15） | MVP |
| QUANT | PurgedTimeSeriesSplitクラス | 完全反映（セクション15） | 将来 |
| QUANT | BayesianSharpeEstimatorクラス | 完全反映（セクション15） | 将来 |
| QUANT | ConfidenceCalibratorクラス | 完全反映（セクション15） | 将来 |
| QUANT | tech_score正規化コード | 完全反映（セクション15） | 追加 |
| **RISK** | VIXレジーム判定（相対VIX） | 完全反映（セクション10.1） | MVP(簡易)/追加(相対) |
| RISK | EWMA相関計算 | 完全反映（セクション10.2） | 追加 |
| RISK | limit付きstop order | 完全反映（セクション9） | MVP |
| RISK | 段階的撤退自動化（select_positions_to_close） | 完全反映（セクション10.4） | MVP |
| RISK | 決算接近チェック | 完全反映（セクション10.3） | MVP |
| RISK | サーキットブレーカー段階的強化 | 完全反映（セクション10.5） | 追加 |
| **STRAT** | Phase 0プロトコル精緻化 | セクション15で統合 | MVP |
| STRAT | Alpha Decayモニタリング | 完全反映（セクション16） | 追加 |
| **DEVIL** | 複雑性爆発の警告（178h開発 + 39h/月メンテナンス） | 優先度マトリクスで対応（セクション20） | - |
| DEVIL | Reconciliation安全性（二重APIコール、sourceカラム） | 完全反映（セクション6） | MVP |
| DEVIL | テストカバレッジ95%の罠（ミューテーションテスト、プロパティベーステスト） | 完全反映（セクション17） | 追加 |
| DEVIL | 撤退判断のシステム化（サンクコスト心理学） | 完全反映（セクション20） | MVP |

### 未反映の提案（戦略文書またはアクションプランで対応）

- STRAT: 銘柄ユニバース段階的拡大の判断基準精緻化
- STRAT: マクロレジーム判定の重み付け最適化（データ蓄積後）
- STRAT: セクターETF補完戦略のリスク等価ポジションサイジング
- STRAT: 決算シーズン外シグナル枯渇問題への3段階アプローチ
- QUANT: シグナル間Mutual Information分析
- QUANT: 多重比較補正のBenjamini-Hochberg法移行
- RISK: ギャップリスク確率分布モデル（Phase 0データ活用）
- RISK: ストレステストの5シナリオ実データ再現
- RISK: テールリスクヘッジ（プロテクティブプット）コスト分析
- DEVIL: Phase 0 Go/No-Go基準の65%引上げ検討
- DEVIL: ベイズ事前分布の4パターン感度分析の全合格条件
