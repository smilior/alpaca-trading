# ARCH レビュー v3: システム設計観点からの深掘り改善提案

> 「それ、実装できる？」 -- v2で構造的弱点は解消された。v3では運用品質とメンテナビリティを追求する。

---

## エグゼクティブサマリー

v2ではv1の構造的弱点（シェルスクリプト混在、cron信頼性、インデックス欠如、冪等性ゼロ、テスト不在）を全て解消した。v3では**「動くシステム」から「安心して運用できるシステム」への品質向上**に焦点を当てる。具体的には、(1) trading_agent.pyのモジュール間インターフェースが暗黙的で型安全性に欠ける問題、(2) Claude CLI呼び出しのJSON出力パースが脆弱で異常出力時のフォールバックが未設計の問題、(3) SQLite WALモードの並行アクセス性能とバックアップ戦略の未定義、(4) config.tomlのスキーマバリデーション不在、(5) launchd→systemd→EventBridgeの具体的マイグレーションスクリプトの欠如、(6) Alpaca WebSocket APIの未活用、(7) ログローテーションの未設計、(8) Phase 0検証ツールキットの不在、(9) Observability（構造化ログ、メトリクス収集）の不在、の9つの論点を掘り下げる。

---

## v2からの残課題と新規論点

### 論点1: trading_agent.pyのモジュール間インターフェース設計

#### 現状の問題

v2のtrading_agent.pyは骨格コードのみで、各モジュール間のデータ受け渡しが暗黙的。具体的には:

- `collect_market_data()` が返す `market_data` の型が未定義。dict? pandas DataFrame? 独自クラス?
- `sync_with_alpaca()` が返す `portfolio` の構造が不明確。呼び出し側が内部構造を知っている前提になっている
- `get_trading_decisions()` が返す `decisions` のリスト要素が、Claude CLI出力のJSON構造そのまま（strやdictの混在リスク）
- `execute_decisions()` のエラー時に何が返るのか、呼び出し元がどうハンドルするのかが未定義
- モジュール間の依存関係が関数シグネチャから読み取れないため、変更時の影響範囲が把握できない

これは「動く」段階では問題にならないが、Phase 2以降でモジュールを個別に修正・テスト・改善していく際に致命的になる。それ、実装できる？ -- できる。dataclassesとProtocolを使えば、実装コストはほぼゼロだ。

#### 改善提案

**dataclasses + typing.Protocol で型安全なインターフェースを定義する。**

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
- テスト時のモック作成が容易になる（Protocolを満たすテストダブルを作るだけ）
- `frozen=True` により不変オブジェクトとなり、意図しない状態変更を防止

#### 実装コスト見積もり

- 作業量: 小（types.pyの作成 + 各モジュールのシグネチャ修正）
- Phase 1の初期段階で定義すべき。後から導入するとモジュール全体の改修が必要になる
- CI追加: `mypy --strict modules/` を `.github/workflows/ci.yml` に1行追加

---

### 論点2: Claude CLI呼び出しの堅牢化

#### 現状の問題

v2では `subprocess.run(timeout=120)` + `json.loads(result.stdout)` で Claude CLIの出力をパースしている。これには以下の脆弱性がある:

1. **JSON以外の出力が混入するケース**: Claude CLIは `--output-format json` でもstderrにログを出すことがある。stdoutに混入した場合、`json.loads()` が失敗する
2. **部分的なJSON**: タイムアウト寸前で出力が途中で切れた場合、不完全なJSONが返る
3. **スキーマ違反**: JSONとしてはvalidだが、期待するフィールドが欠けている（例: `decisions` キーがない）
4. **LLMのハルシネーション**: sentimentが "positive" の代わりに "very positive" と返される等、Enumの値域外の出力
5. **フォールバック戦略がない**: パース失敗時は「ログ記録して終了（注文なし）」だが、日に4回の実行のうち1回がパース失敗した場合、その日のシグナルを全て見逃す可能性がある

#### 改善提案

**JSON Schema Validation + 段階的フォールバック + リトライ戦略を実装する。**

```python
# modules/llm_analyzer.py
import json
import subprocess
from jsonschema import validate, ValidationError
from modules.types import TradingDecision, Action

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
            # スキーマ違反でもdecisionsキーがあれば部分的に使う
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
    # 方法1: そのままパース
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # 方法2: 最初の '{' から最後の '}' を抽出
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
            # actionのenum値を正規化
            action = d["action"].lower().strip()
            if action not in ("buy", "sell", "hold", "no_action"):
                action = "no_action"
            d["action"] = action
            valid_decisions.append(d)
    parsed["decisions"] = valid_decisions
    return parsed
```

**フォールバック戦略:**

| 失敗パターン | フォールバック |
|-------------|-------------|
| タイムアウト | 1回リトライ後、「注文なし」で安全終了 |
| JSON不正 | `_extract_json()` で部分抽出を試行 |
| スキーマ違反（軽微） | `_sanitize_partial()` で有効部分のみ使用 |
| スキーマ違反（重大） | 「注文なし」で安全終了 |
| 全リトライ失敗 | Slackアラート + 次回実行（midday/eod）で再試行 |

#### 実装コスト見積もり

- 作業量: 小～中（jsonschemaパッケージ追加 + バリデーションロジック100行程度）
- Phase 2のClaude CLI統合時に**必ず**組み込むこと
- `jsonschema` を `requirements.txt` に追加

---

### 論点3: SQLite WALモードの並行アクセス性能とバックアップ戦略

#### 現状の問題

v2で `PRAGMA journal_mode=WAL` を有効化しているが、以下が未検討:

1. **WALモードの並行アクセス特性**: WALモードは「複数リーダー + 1ライター」を許可するが、ヘルスチェック（毎時）とトレーディングエージェント（日次4回）が同時にDBアクセスした場合のロック待ち動作が未定義。特に、Reconciliationが長時間のトランザクションを保持する場合、ヘルスチェックが遅延する可能性がある
2. **WALファイルの肥大化**: WALモードではチェックポイント（WALファイルの内容をメインDBに書き戻す）が自動で行われるが、`wal_autocheckpoint` のデフォルト値（1000ページ）が適切かの検討がない
3. **バックアップ戦略の完全欠如**: DBファイルが破損した場合の復旧手段がない。ファイルコピーではWALモード中のDB整合性が保証されない
4. **DBファイルの肥大化対策**: `decisions_json TEXT` にClaude CLIの全出力を保存するため、3ヶ月の運用でDBが数百MBに膨らむ可能性がある

#### 改善提案

```python
# modules/db.py に追加

import sqlite3
from pathlib import Path
from datetime import datetime

def init_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    # WALチェックポイントの設定（500ページ = 約2MB）
    conn.execute("PRAGMA wal_autocheckpoint=500")
    # busy_timeout: 他プロセスのロック待ち上限（5秒）
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def backup_db(source_path: str, backup_dir: str) -> str:
    """SQLite Online Backup APIを使用した安全なバックアップ"""
    backup_name = f"trading_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    backup_path = Path(backup_dir) / backup_name

    source = sqlite3.connect(source_path)
    dest = sqlite3.connect(str(backup_path))
    with dest:
        source.backup(dest)  # Online Backup API -- WALモード中でも安全
    dest.close()
    source.close()

    # 古いバックアップの削除（7世代保持）
    backups = sorted(Path(backup_dir).glob("trading_*.db"))
    for old in backups[:-7]:
        old.unlink()

    return str(backup_path)


def vacuum_old_data(conn: sqlite3.Connection, retention_days: int = 90):
    """古いデータのアーカイブと圧縮"""
    cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat()

    # decisions_jsonの古いエントリを圧縮（全文ではなくサマリーに置換）
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
| 月次 | フルバックアップ（外部ストレージ） | 3ヶ月分 |

**DBサイズ管理:**

- `decisions_json` は90日経過後にサマリーに圧縮
- `execution_logs` のステータスが `success` かつ90日以上前のレコードは `decisions_json` をNULLに
- 月次で `VACUUM` を実行してファイルサイズを回収

#### 実装コスト見積もり

- WAL設定最適化: 極小（PRAGMA 2行追加）
- バックアップ: 小（Online Backup APIは10行程度）
- データアーカイブ: 小（SQLクエリ + cron/launchdで週次実行）
- Phase 1のDB初期化時に組み込む

---

### 論点4: config.tomlのスキーマバリデーション

#### 現状の問題

v2で `.env`（シークレット）と `config.toml`（戦略パラメータ）の2層管理が導入されたが、config.tomlの読み込みは `tomllib.load()` でdictを返すだけで:

1. **型チェックなし**: `sentiment_confidence_threshold = "seventy"` でも読み込みは成功する
2. **値域チェックなし**: `max_risk_per_trade_pct = -5.0` を設定しても検出されない
3. **必須キーの検出なし**: `[strategy]` セクションが丸ごとなくても気づかない
4. **デフォルト値の管理がない**: キーが欠けた場合のフォールバックが未定義
5. **パラメータ変更の検出**: 「1変数ずつ」ルールをCIで強制する仕組みが未実装

それ、実装できる？ -- pydantic-settings を使えば、型安全 + バリデーション + デフォルト値 + 環境変数統合が全て解決する。

#### 改善提案

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
    take_profit_atr_multiplier: float = Field(default=3.0, ge=1.0, le=10.0)
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
    paper: bool = True  # デフォルトはペーパー。リアルへの切替はこのフラグ

class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        toml_file="config.toml",
        env_prefix="TRADING_",  # 環境変数でのオーバーライドも可能
    )
    strategy: StrategyConfig = StrategyConfig()
    risk: RiskConfig = RiskConfig()
    system: SystemConfig = SystemConfig()
    alpaca: AlpacaConfig = AlpacaConfig()

# 使用例
config = AppConfig()
# config.strategy.sentiment_confidence_threshold -> 70 (int, validated)
# config.risk.max_risk_per_trade_pct -> 1.0 (float, 0.1-5.0の範囲保証)
# config.alpaca.paper -> True (bool)
```

**「1変数ずつ」ルールのCI強制:**

```yaml
# .github/workflows/ci.yml に追加
- name: Check config.toml changes
  if: github.event_name == 'pull_request'
  run: |
    CHANGES=$(git diff origin/main -- config.toml | grep '^[+-]' | grep -v '^[+-][+-]' | grep -v '^[+-]\s*#' | wc -l)
    if [ "$CHANGES" -gt 2 ]; then
      echo "ERROR: config.toml changes more than 1 parameter. Found $CHANGES changed lines."
      echo "Rule: Change only 1 variable at a time."
      exit 1
    fi
```

#### 実装コスト見積もり

- pydantic-settings導入: 小（`pip install pydantic-settings` + 上記コード70行程度）
- CI追加: 極小（YAMLに5行追加）
- Phase 1のconfig.toml実装時に**同時に**導入すべき。後から導入すると既存のconfig読み込みコードの全面改修が必要
- `requirements.txt` に `pydantic-settings>=2.0` を追加

---

### 論点5: launchd → systemd → EventBridge の具体的マイグレーションスクリプト

#### 現状の問題

v2で3段階のクラウド移行パス（macOS launchd → VPS systemd → AWS EventBridge）が定義されたが、**具体的な移行スクリプトや手順書が一切ない**。移行パスの存在は安心材料になるが、いざ移行する段階で「何をすればいいか」がゼロから設計になる。

特に問題なのは:
- launchdのplistファイルはバージョン管理されるが、systemdのunitファイルとの対応関係が未定義
- EventBridgeへの移行はLambda関数のハンドラーが必要だが、trading_agent.pyの `main()` がCLI引数に依存しており、Lambda互換でない
- 環境変数（.env）の管理がステージごとに異なる（ローカルファイル → VPSの/etc/environment → AWS Secrets Manager）
- Docker化は「Phase 1で作っておくとよい」と記載されているが、Dockerfileの設計がそのままでは動かない（.env、data/ディレクトリのマウント等）

#### 改善提案

**1. エントリーポイントの統一（CLI + Lambda互換）:**

```python
# trading_agent.py
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

**2. systemd unitファイルのテンプレート:**

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

**3. マイグレーションスクリプト:**

```bash
#!/bin/bash
# deploy/migrate-to-vps.sh
# Usage: ./migrate-to-vps.sh <vps-host> <vps-user>

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

**4. ディレクトリ構成への追加:**

```
deploy/
├── launchd/                      # Stage 1: macOS（既存）
│   └── com.alpaca-trading.*.plist
├── systemd/                      # Stage 2: VPS
│   ├── alpaca-trading-*.service
│   └── alpaca-trading-*.timer
├── lambda/                       # Stage 3: AWS
│   ├── handler.py
│   └── template.yaml            # SAM テンプレート
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── migrate-to-vps.sh
└── migrate-to-aws.sh
```

#### 実装コスト見積もり

- systemdテンプレート: 小（plistからの1:1変換）
- マイグレーションスクリプト: 小～中（上記シェルスクリプト50行 + テスト）
- Lambda互換エントリーポイント: 極小（handler()関数の追加）
- Phase 1で `deploy/` ディレクトリとテンプレートを用意し、Phase 3（VPS移行時）に実行

---

### 論点6: Alpaca WebSocket APIの活用検討

#### 現状の問題

v2ではAlpaca APIとの通信が全てREST（ポーリング）ベースになっている。特に問題なのは:

1. **注文状態の確認**: 注文送信後、約定確認のために `GET /v2/orders` をポーリングする必要があるが、ポーリング間隔と約定タイミングのギャップでPartial Fillの検出が遅れる
2. **Reconciliation**: 毎回実行時に `get_all_positions()` を呼んでいるが、ストップロス約定やテイクプロフィット約定がリアルタイムで検出されない。次回実行（数時間後）まで気づかない
3. **API呼び出し回数**: 日次4回 x 複数エンドポイントで、レートリミット（200 req/min）にはかからないが、バックテストやリスタート時には集中する

#### 改善提案

**Phase 1-4（ポーリング）とPhase 5以降（WebSocket）の2段階で導入する。**

Phase 1-4は現行のREST APIのままで十分。ただし、**VPS移行後（Stage 2）にWebSocketを導入すべき**。理由: WebSocketは常時接続が前提であり、macOSのスリープ環境では接続が頻繁に切れるため。

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
            event = data.event  # "new", "fill", "partial_fill", "canceled"
            order = data.order

            if event == "fill":
                logging.info(f"Order filled: {order.symbol} {order.qty}@{order.filled_avg_price}")
                # DBを即座に更新
                update_trade_status(order.client_order_id, "filled",
                                    order.filled_qty, order.filled_avg_price)

            elif event == "partial_fill":
                logging.warning(f"Partial fill: {order.symbol} "
                                f"{order.filled_qty}/{order.qty}")
                handle_partial_fill(order)
                send_alert(f"Partial fill: {order.symbol}", level="warn")

            elif event == "canceled":
                logging.info(f"Order canceled: {order.symbol}")
                update_trade_status(order.client_order_id, "canceled", 0, 0)

    async def run(self):
        await self.stream._run_forever()
```

**WebSocketのメリット:**

| 機能 | ポーリング（現行） | WebSocket（将来） |
|------|-----------------|------------------|
| 約定検出 | 次回実行時（数時間後） | リアルタイム（ミリ秒） |
| Partial Fill | 次回Reconciliationで検出 | 即座に検出・対処 |
| ストップロス約定 | Reconciliationで事後検出 | 即座にDB更新・アラート |
| API呼び出し回数 | 毎回 get_orders/get_positions | 常時接続（省API） |

#### 実装コスト見積もり

- WebSocket監視: 中（alpaca-pyのTradingStreamラッパー + 常駐プロセス管理）
- VPS移行後に導入。macOS段階では不要
- 常駐プロセスはsystemdの `Type=simple` で管理

---

### 論点7: ログローテーションとアーカイブ戦略

#### 現状の問題

v2で基本的なロギング設定は定義されているが:

1. **ログローテーションが未設計**: `agent_YYYY-MM-DD.log` は日付でファイル分割されるが、古いファイルの削除ルールがない。3ヶ月で約90ファイル蓄積
2. **ログレベルの使い分けが未定義**: 何をDEBUGに、何をINFOに記録するか
3. **構造化ログでない**: テキストベースのログは `grep` で検索困難。特にトラブルシュート時にexecution_idでフィルタリングしたいが、フリーテキストでは難しい
4. **ログとDBの重複**: execution_logsテーブルとログファイルに同じ情報が二重記録される

#### 改善提案

```python
# modules/logger.py
import logging
import logging.handlers
from pathlib import Path

def setup_logging(log_dir: str, execution_id: str):
    """ログローテーション付きのロギング設定"""
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # メインログ: 10MB x 5世代ローテーション
    handler = logging.handlers.RotatingFileHandler(
        log_path / "agent.log",
        maxBytes=10 * 1024 * 1024,  # 10MB
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
| DEBUG | 開発・デバッグ用。本番では無効 | API応答の生データ、計算の中間値 |
| INFO | 正常な業務フロー | 「Reconciliation完了、差分0件」「注文送信: AAPL BUY 30株」 |
| WARNING | 異常だが処理は継続可能 | 「Partial Fill検出」「APIリトライ中」 |
| ERROR | 処理が失敗した | 「Claude CLIタイムアウト」「注文拒否」 |
| CRITICAL | システム全体に影響 | 「DB接続不能」「回路ブレーカーLevel 3発動」 |

**ログアーカイブ:**
- 30日以上前のログファイルをgzip圧縮
- 90日以上前のログファイルを削除
- launchd/systemdの週次ジョブで実行

**将来のstructlog導入** (Phase 5以降):

```python
# structlogへの段階的移行
import structlog
logger = structlog.get_logger()
logger.info("order_submitted", symbol="AAPL", qty=30, side="buy",
            execution_id="2025-01-15_morning")
```

structlogは後方互換性があるため、標準loggingからの段階的移行が可能。VPS移行後にstructlog + JSON出力に切り替えることで、ログ集約ツール（Loki等）との連携が容易になる。

#### 実装コスト見積もり

- RotatingFileHandler: 極小（上記コード20行）
- ログレベルガイドライン適用: 小（各モジュールのlogging呼び出しをレビュー）
- gzipアーカイブ: 極小（launchd週次ジョブ + `gzip` コマンド）
- structlog移行: 中（Phase 5以降で検討）
- Phase 1のロギング設定時に組み込む

---

### 論点8: Phase 0用の検証ツールキット設計

#### 現状の問題

v2のaction-planでPhase 0（alpha仮説の事前検証）が最重要タスクとして定義されたが、**具体的な実行パイプラインの設計がない**。Phase 0で必要な作業:

1. 過去決算データ4,000件の収集（yfinance + Alpaca News API）
2. 4,000件に対するClaude CLIのバッチ実行（レートリミット対応、リジューム機能）
3. FinBERT/VADERでの同一データセンチメント分析（ローカル実行）
4. 結果の集計・統計検定（カイ二乗検定、キャリブレーションプロット）
5. Go/No-Goレポートの自動生成

これを手動で実行するのは現実的でない。4,000件のAPI呼び出しを手動管理し、途中で失敗した場合のリジュームを考えると、専用パイプラインが必要。それ、実装できる？ -- 必要なのは100行程度のバッチ実行スクリプトだ。

#### 改善提案

```python
# tools/phase0_runner.py
"""Phase 0: LLMセンチメント精度検証パイプライン"""
import json
import time
import sqlite3
import subprocess
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
    return_5d: float  # 5日後リターン（ゴールドスタンダード）

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
            # 既に処理済みならスキップ（リジューム機能）
            if self._already_processed(event):
                continue

            # Claude CLIでセンチメント分析
            llm_result = self._call_claude(event)

            # FinBERTでセンチメント分析
            finbert_result = self._call_finbert(event.news_text)

            # VADERでセンチメント分析
            vader_result = self._call_vader(event.news_text)

            # ゴールドスタンダード判定
            gold = self._classify_return(event.return_5d)

            # 結果をDBに保存
            self._save_result(event, llm_result, finbert_result,
                              vader_result, gold)

            # レートリミット対策
            if (i + 1) % batch_size == 0:
                time.sleep(delay)
                print(f"Processed {i+1}/{len(events)}")

    def generate_report(self) -> str:
        """Go/No-Goレポートの自動生成"""
        results = self.db.execute(
            "SELECT * FROM sentiment_results"
        ).fetchall()

        # 方向性精度の計算
        llm_accuracy = self._calc_directional_accuracy("llm")
        finbert_accuracy = self._calc_directional_accuracy("finbert")
        vader_accuracy = self._calc_directional_accuracy("vader")

        # カイ二乗検定
        chi2_vs_random = self._chi_square_test("llm", "random")
        chi2_vs_finbert = self._chi_square_test("llm", "finbert")

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
- vs FinBERT: {"PASS" if chi2_vs_finbert.pvalue < 0.05 else "FAIL"} (p={chi2_vs_finbert.pvalue:.4f})
- vs Random: {"PASS" if chi2_vs_random.pvalue < 0.05 else "FAIL"} (p={chi2_vs_random.pvalue:.4f})

## 判定: {"**GO** - Phase 1に進む" if llm_accuracy >= 0.6 else "**NO-GO** - 戦略再設計が必要"}
"""
        return report
```

**ディレクトリ構成への追加:**

```
tools/
├── phase0_runner.py          # Phase 0検証パイプライン
├── phase0_data_collector.py  # 決算データ収集
├── phase0_report.py          # レポート生成
└── backtest_runner.py        # ウォークフォワードバックテスト（Phase 4）
data/
├── phase0/                   # Phase 0専用データ
│   ├── results.db            # 検証結果DB
│   └── earnings_data/        # 決算データキャッシュ
├── state/                    # 本番DB
└── market/                   # 市場データキャッシュ
```

#### 実装コスト見積もり

- バッチ実行パイプライン: 中（上記Phase0Pipelineで200行程度）
- データ収集スクリプト: 小（yfinance + Alpaca News APIのラッパー）
- FinBERT/VADER実行: 小（Hugging Face transformers + vaderSentiment パッケージ）
- レポート生成: 小（Markdownテンプレート + 統計計算）
- **Phase 0の最初のタスクとして構築すべき**。検証パイプラインなしにPhase 0は実行できない

---

### 論点9: Observability -- 構造化ログ、メトリクス収集の具体設計

#### 現状の問題

v2では「Prometheus/Grafanaは過剰」としてSlack Webhook + SQLite daily_snapshotsのみでモニタリングを設計しているが:

1. **トラブルシュートが困難**: テキストログの `grep` では、特定のexecution_idに関連するイベントを横断的に追跡できない
2. **トレンド分析ができない**: daily_snapshotsは日次の点データのみ。「過去1週間でClaude CLIのレスポンス時間が増加傾向にある」等の検知ができない
3. **アラートが事後的**: 異常が発生してからSlackに通知するだけで、異常の予兆を検知する仕組みがない
4. **メトリクスの定義が不十分**: 何を測定すべきかのリストがない

Prometheus/Grafanaは確かに過剰だが、**SQLiteにメトリクスを追加記録し、簡単なダッシュボードスクリプトで可視化する**のはPhase 1でも十分実装可能。

#### 改善提案

**収集すべきメトリクス:**

```sql
-- メトリクステーブル（daily_snapshotsの補完）
CREATE TABLE metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    execution_id TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL
);
CREATE INDEX idx_metrics_name_ts ON metrics(metric_name, timestamp);
```

| メトリクス名 | 単位 | 用途 |
|-------------|------|------|
| `claude_response_time_ms` | ms | LLMレスポンス劣化の検知 |
| `claude_input_tokens` | count | コスト追跡 |
| `claude_output_tokens` | count | コスト追跡 |
| `api_call_count` | count | レートリミット接近の予兆検知 |
| `api_error_count` | count | API障害の検知 |
| `reconciliation_issues` | count | 状態不整合の頻度 |
| `signal_count` | count | シグナル頻度の監視（低下はユニバースの問題を示唆） |
| `filter_pass_rate` | % | テクニカルフィルターの通過率（パラメータ調整の判断材料） |
| `db_size_bytes` | bytes | DBファイルの肥大化検知 |
| `execution_duration_ms` | ms | 全体の実行時間の監視 |

**週次ダッシュボードスクリプト:**

```python
# tools/weekly_dashboard.py
def generate_weekly_dashboard(conn, output_path: str):
    """SQLiteメトリクスから週次ダッシュボードを生成"""
    # Claude CLIレスポンス時間のトレンド
    response_times = conn.execute("""
        SELECT date(timestamp) as day,
               avg(metric_value) as avg_ms,
               max(metric_value) as max_ms
        FROM metrics
        WHERE metric_name = 'claude_response_time_ms'
          AND timestamp > datetime('now', '-7 days')
        GROUP BY day
    """).fetchall()

    # APIコストの週次集計
    costs = conn.execute("""
        SELECT sum(metric_value) * 3.0 / 1000000 as input_cost_usd
        FROM metrics
        WHERE metric_name = 'claude_input_tokens'
          AND timestamp > datetime('now', '-7 days')
    """).fetchone()

    # Markdownレポート出力
    # ...
```

**異常検知（閾値ベース）:**

```python
def check_anomalies(conn):
    """メトリクスの異常を検知してアラート"""
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

#### 実装コスト見積もり

- metricsテーブル + 記録ロジック: 小（DDL + 各モジュールにメトリクス記録を数行追加）
- 週次ダッシュボード: 小（SQLクエリ + Markdownテンプレート、100行程度）
- 異常検知: 小（閾値チェック + 既存のalerter.pyを活用）
- Phase 2でデータ収集と同時に組み込む。Phase 1ではメトリクステーブルのDDLのみ用意

---

## 最終提言

v2で構造的弱点が解消された今、v3で最も重要な改善を優先順位順に3つ挙げる。

### 1. モジュール間インターフェースの型定義（Phase 1で必須）

`modules/types.py` にdataclasses + Protocolで全モジュールの入出力型を定義せよ。これは最初に設計すべきであり、後から導入するとモジュール全体の改修が必要になる。型定義があれば、(a) テストのモック作成が容易になり、(b) CIで `mypy --strict` により型不整合を自動検出でき、(c) モジュール単体での開発・改善が安全になる。v2で「テストなしにペーパートレーディングを開始してはならない」と合意したが、型定義なしにテストを書くのは砂上の楼閣だ。**実装コストはほぼゼロ（types.py 1ファイル）で、見返りはプロジェクト全期間に渡る。**

### 2. Claude CLI出力のJSON Schema Validation + フォールバック戦略（Phase 2で必須）

Claude CLIの出力は「たいてい正しい」が「常に正しい」保証はない。LLMの出力を無検証で信頼するのは、このシステム全体の中で最も危険な設計判断だ。JSON Schema Validationを入れ、部分的に有効な出力を救済するフォールバック戦略を実装することで、CLIの異常出力が注文の欠落に直結するリスクを排除する。jsonschemaパッケージの導入コストは極小。**「それ、実装できる？」 -- 30分で実装できる。やらない理由がない。**

### 3. Phase 0検証ツールキットの構築（Phase 0の最初のタスク）

Phase 0はこのプロジェクトのGo/No-Go判断を担う最重要フェーズだが、4,000件のバッチLLM実行を手動で管理するのは非現実的。リジューム対応のバッチ実行パイプライン、FinBERT/VADERのローカル実行環境、結果集計・統計検定・レポート生成の自動化ツールを**Phase 0の最初の1-2日で構築すべき**。ツールキットなしでPhase 0を実行するのは、テスト基盤なしにテストを書くようなものだ。

---

*「それ、実装できる？」 -- v3の全提案は、v2と同様に個人開発者が1人で実装可能な範囲に収めている。ただし、v3の提案の大半は「やらなくても動く」が「やっておけば運用が楽になる」類のものだ。運用フェーズに入ってから「やっておけばよかった」と後悔するのが最悪のパターンであり、Phase 1の初期段階でtypes.pyとJSON Schema Validationを入れておくだけで、その後12ヶ月の運用品質が決定的に変わる。*
