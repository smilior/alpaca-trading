# Phase 1 技術仕様書: 環境構築・基盤整備

> action-plan.md Phase 1（Week 4-5）の具体的な技術仕様。
> system-design.md v3 および strategy.md v3 の設計方針に準拠。

---

## 1. ディレクトリ構成

Phase 1 完了時に以下の構成を確立する。Phase 2以降で追加されるファイルも含めた全体像を示す。

```
alpaca-trading/
├── CLAUDE.md                          # プロジェクト指示書（既存）
├── config.toml                        # 戦略パラメータ（git管理）
├── pyproject.toml                     # プロジェクトメタデータ + ツール設定
├── requirements.txt                   # 本番依存パッケージ
├── requirements-dev.txt               # 開発依存パッケージ
├── .env                               # APIキー等（.gitignoreで除外）
├── .env.example                       # .envのテンプレート（git管理）
├── .gitignore
├── trading_agent.py                   # メインオーケストラ（Phase 4で実装）
│
├── modules/                           # ★Phase 1で作成するPythonパッケージ
│   ├── __init__.py
│   ├── types.py                       # 型定義（dataclasses + Protocol）
│   ├── config.py                      # pydantic-settings設定ローダー
│   ├── db.py                          # SQLite接続・初期化・マイグレーション
│   └── logger.py                      # 構造化ロギング + ローテーション
│
├── tests/                             # ★Phase 1でテスト基盤構築
│   ├── __init__.py
│   ├── conftest.py                    # 共通フィクスチャ（in-memory DB等）
│   ├── test_types.py                  # 型定義のテスト
│   ├── test_config.py                 # 設定ローダーのテスト
│   └── test_db.py                     # DB初期化・マイグレーションのテスト
│
├── data/
│   ├── state/                         # SQLite DB + ロックファイル
│   │   └── .gitkeep
│   ├── phase0/                        # Phase 0検証データ（Phase 0で使用）
│   │   └── .gitkeep
│   ├── market/                        # 市場データキャッシュ（Phase 2で使用）
│   │   └── .gitkeep
│   └── analysis/                      # LLM分析結果（Phase 2で使用）
│       └── .gitkeep
│
├── logs/                              # ログ出力先
│   └── .gitkeep
│
├── prompts/                           # LLMプロンプト（Phase 2で作成）
│   └── .gitkeep
│
├── tools/                             # 検証ツールキット（Phase 0で作成済み想定）
│   └── .gitkeep
│
├── deploy/                            # デプロイ設定（Phase 4以降）
│   ├── launchd/
│   │   └── .gitkeep
│   └── systemd/                       # VPS移行時用
│       └── .gitkeep
│
├── docs/                              # ドキュメント（既存）
│   ├── strategy.md
│   ├── system-design.md
│   ├── planning-log.md
│   ├── action-plan.md
│   └── phase1-technical-spec.md       # 本ドキュメント
│
└── .claude/                           # Claude Code設定（既存）
    └── skills/
```

### Phase 1で作成するファイル一覧

| ファイル | 目的 | 優先度 |
|---------|------|--------|
| `pyproject.toml` | プロジェクトメタデータ・ツール設定 | 必須(MVP) |
| `requirements.txt` | 本番依存パッケージ | 必須(MVP) |
| `requirements-dev.txt` | 開発依存パッケージ | 必須(MVP) |
| `config.toml` | 戦略パラメータ | 必須(MVP) |
| `.env.example` | 環境変数テンプレート | 必須(MVP) |
| `.gitignore` | git除外設定 | 必須(MVP) |
| `modules/__init__.py` | パッケージ初期化 | 必須(MVP) |
| `modules/types.py` | 型定義 | 必須(MVP) |
| `modules/config.py` | 設定ローダー | 必須(MVP) |
| `modules/db.py` | DB接続・初期化 | 必須(MVP) |
| `modules/logger.py` | ロギング設定 | 必須(MVP) |
| `tests/conftest.py` | テストフィクスチャ | 必須(MVP) |
| `tests/test_types.py` | 型テスト | 必須(MVP) |
| `tests/test_config.py` | 設定テスト | 必須(MVP) |
| `tests/test_db.py` | DBテスト | 必須(MVP) |

---

## 2. 依存パッケージ

### requirements.txt（本番）

```
# Alpaca SDK
alpaca-py>=0.21.0,<1.0.0

# 設定管理
pydantic>=2.5.0,<3.0.0
pydantic-settings>=2.1.0,<3.0.0

# データ取得
yfinance>=0.2.30,<1.0.0

# LLM出力バリデーション
jsonschema>=4.20.0,<5.0.0

# 市場カレンダー
exchange-calendars>=4.5.0,<5.0.0

# テクニカル指標（Phase 2で使用）
pandas>=2.1.0,<3.0.0
numpy>=1.26.0,<2.0.0

# マクロデータ（Phase 2で使用）
fredapi>=0.5.0,<1.0.0
```

### requirements-dev.txt（開発）

```
-r requirements.txt

# テスト
pytest>=7.4.0,<9.0.0
pytest-cov>=4.1.0,<6.0.0

# リンター・フォーマッター
ruff>=0.1.0,<1.0.0

# 型チェック
mypy>=1.8.0,<2.0.0

# Phase 0用ベースラインモデル（Phase 0で使用）
# transformers>=4.36.0,<5.0.0
# torch>=2.1.0
# vaderSentiment>=3.3.2
```

### pyproject.toml

```toml
[project]
name = "alpaca-trading"
version = "0.1.0"
description = "Alpaca API を使った米国株自動売買システム"
requires-python = ">=3.11"

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--cov=modules --cov-report=term-missing --cov-fail-under=80"

[tool.ruff]
target-version = "py311"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "SIM"]

[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_configs = true

[[tool.mypy.overrides]]
module = ["alpaca.*", "yfinance.*", "fredapi.*", "exchange_calendars.*"]
ignore_missing_imports = true
```

---

## 3. 環境変数（.env）

### .env.example

```bash
# === Alpaca API ===
# ペーパートレーディング用キー（https://app.alpaca.markets/paper/dashboard/overview）
ALPACA_API_KEY=PKXXXXXXXXXXXXXXXXXX
ALPACA_SECRET_KEY=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
# 安全弁: true以外の値を設定するとエラーで起動停止
ALPACA_PAPER=true

# === Anthropic API ===
ANTHROPIC_API_KEY=sk-ant-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

# === Slack通知（追加機能・任意） ===
# SLACK_WEBHOOK_URL=https://hooks.slack.com/services/XXX/YYY/ZZZ

# === FRED API（Phase 2で使用・任意） ===
# FRED_API_KEY=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
```

### .gitignore

```gitignore
# 環境変数（絶対にコミットしない）
.env

# データ
data/state/*.db
data/state/*.db-wal
data/state/*.db-shm
data/state/agent.lock
data/phase0/*.db
data/market/
data/analysis/

# ログ
logs/

# Python
__pycache__/
*.pyc
*.pyo
.mypy_cache/
.pytest_cache/
.ruff_cache/
*.egg-info/
dist/
build/
venv/
.venv/

# macOS
.DS_Store

# IDE
.idea/
.vscode/
```

---

## 4. 設定管理（config.toml + pydantic-settings）

### config.toml

system-design.md v3 セクション12に準拠。全12パラメータをgit管理する。

```toml
[strategy]
sentiment_confidence_threshold = 70    # LLM確信度閾値 (50-100)
ma_period = 50                         # 移動平均期間 (5-500)
rsi_period = 14                        # RSI期間 (5-30)
rsi_upper = 70                         # RSI上限 (50-95)
rsi_lower = 30                         # RSI下限 (5-50)
volume_compare_period = 20             # 出来高比較期間 (5-60)
stop_loss_atr_multiplier = 2.0         # ストップロス ATR倍率 (0.5-5.0)
take_profit_pct = 5.0                  # テイクプロフィット % (1.0-20.0)
time_stop_days = 10                    # タイムストップ 営業日 (1-30)
max_concurrent_positions = 5           # 最大同時ポジション数 (1-10)
max_daily_entries = 2                  # 1日最大新規エントリー数 (1-5)
min_holding_days = 2                   # 最小保有日数 (0-10)

[risk]
max_risk_per_trade_pct = 1.5           # 1トレードあたり最大リスク % (0.1-5.0)
slippage_factor = 1.3                  # スリッページ係数 (1.0-2.0)
max_position_pct = 20.0               # 1ポジション最大資金比率 % (5.0-50.0)
circuit_breaker_level1_pct = 4.0       # 回路ブレーカー L1 (1.0-10.0)
circuit_breaker_level2_pct = 7.0       # 回路ブレーカー L2 (2.0-15.0)
circuit_breaker_level3_pct = 10.0      # 回路ブレーカー L3 (5.0-20.0)
circuit_breaker_level4_pct = 15.0      # 回路ブレーカー L4 (10.0-30.0)

[macro]
vix_threshold_elevated = 20            # VIX警戒閾値
vix_threshold_extreme = 30             # VIX極端閾値
macro_ma_period = 200                  # マクロレジーム判定用MA期間
atr_period = 14                        # ATR期間

[system]
db_path = "data/state/trading.db"
log_dir = "logs"
claude_timeout_seconds = 120           # Claude CLI タイムアウト (30-300)
lock_file_path = "data/state/agent.lock"

[alpaca]
paper = true                           # ★必ずtrue。falseへの変更は手動+複数確認必須

[alerts]
slack_enabled = false                  # 追加機能。初期はfalse
alert_levels = ["warn", "error", "critical"]
```

### modules/config.py APIインターフェース

```python
"""pydantic-settings による型安全な設定管理。

config.toml を読み込み、型・値域・必須キーをバリデーション。
環境変数 TRADING_* で個別オーバーライド可能。
"""

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class StrategyConfig(BaseSettings):
    sentiment_confidence_threshold: int = Field(default=70, ge=50, le=100)
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

    @model_validator(mode="after")
    def validate_rsi_range(self) -> "StrategyConfig":
        if self.rsi_lower >= self.rsi_upper:
            raise ValueError(
                f"rsi_lower ({self.rsi_lower}) must be < rsi_upper ({self.rsi_upper})"
            )
        return self


class RiskConfig(BaseSettings):
    max_risk_per_trade_pct: float = Field(default=1.5, ge=0.1, le=5.0)
    slippage_factor: float = Field(default=1.3, ge=1.0, le=2.0)
    max_position_pct: float = Field(default=20.0, ge=5.0, le=50.0)
    circuit_breaker_level1_pct: float = Field(default=4.0, ge=1.0, le=10.0)
    circuit_breaker_level2_pct: float = Field(default=7.0, ge=2.0, le=15.0)
    circuit_breaker_level3_pct: float = Field(default=10.0, ge=5.0, le=20.0)
    circuit_breaker_level4_pct: float = Field(default=15.0, ge=10.0, le=30.0)

    @model_validator(mode="after")
    def validate_circuit_breaker_order(self) -> "RiskConfig":
        levels = [
            self.circuit_breaker_level1_pct,
            self.circuit_breaker_level2_pct,
            self.circuit_breaker_level3_pct,
            self.circuit_breaker_level4_pct,
        ]
        for i in range(len(levels) - 1):
            if levels[i] >= levels[i + 1]:
                raise ValueError(
                    f"Circuit breaker levels must be strictly increasing: {levels}"
                )
        return self


class MacroConfig(BaseSettings):
    vix_threshold_elevated: float = Field(default=20.0, ge=10.0, le=40.0)
    vix_threshold_extreme: float = Field(default=30.0, ge=20.0, le=80.0)
    macro_ma_period: int = Field(default=200, ge=50, le=500)
    atr_period: int = Field(default=14, ge=5, le=30)


class SystemConfig(BaseSettings):
    db_path: str = "data/state/trading.db"
    log_dir: str = "logs"
    claude_timeout_seconds: int = Field(default=120, ge=30, le=300)
    lock_file_path: str = "data/state/agent.lock"


class AlpacaConfig(BaseSettings):
    paper: bool = True


class AlertsConfig(BaseSettings):
    slack_enabled: bool = False
    alert_levels: list[str] = ["warn", "error", "critical"]


class AppConfig(BaseSettings):
    """アプリケーション全体の設定。

    読み込み優先順: 環境変数 > config.toml > デフォルト値
    """
    model_config = SettingsConfigDict(
        toml_file="config.toml",
        env_prefix="TRADING_",
    )

    strategy: StrategyConfig = StrategyConfig()
    risk: RiskConfig = RiskConfig()
    macro: MacroConfig = MacroConfig()
    system: SystemConfig = SystemConfig()
    alpaca: AlpacaConfig = AlpacaConfig()
    alerts: AlertsConfig = AlertsConfig()
```

---

## 5. データスキーマ（SQLite）

### データベースファイル

- パス: `data/state/trading.db`
- エンコーディング: UTF-8
- ジャーナルモード: WAL
- 日付フォーマット: ISO 8601（`YYYY-MM-DD` / `YYYY-MM-DDTHH:MM:SS`）

### PRAGMA設定

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA wal_autocheckpoint = 500;   -- 500ページ（約2MB）ごとにチェックポイント
PRAGMA busy_timeout = 5000;        -- ロック待ち5秒
```

### テーブル定義

#### 5.1 positions（ポジション管理）

```sql
CREATE TABLE positions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol           TEXT    NOT NULL,
    side             TEXT    NOT NULL DEFAULT 'long'
                             CHECK(side IN ('long', 'short')),
    qty              REAL    NOT NULL CHECK(qty > 0),
    entry_price      REAL    NOT NULL CHECK(entry_price > 0),
    entry_date       TEXT    NOT NULL CHECK(entry_date GLOB '????-??-??'),
    stop_loss        REAL    CHECK(stop_loss IS NULL OR stop_loss > 0),
    take_profit      REAL    CHECK(take_profit IS NULL OR take_profit > 0),
    strategy_reason  TEXT,
    sentiment_score  REAL    CHECK(sentiment_score IS NULL
                             OR (sentiment_score >= 0 AND sentiment_score <= 100)),
    status           TEXT    NOT NULL DEFAULT 'open'
                             CHECK(status IN ('open', 'closed')),
    close_price      REAL    CHECK(close_price IS NULL OR close_price > 0),
    close_date       TEXT    CHECK(close_date IS NULL OR close_date GLOB '????-??-??'),
    close_reason     TEXT    CHECK(close_reason IS NULL
                             OR close_reason IN ('tp', 'sl', 'time_stop',
                                                 'signal', 'circuit_breaker',
                                                 'reconciliation', 'manual',
                                                 'earnings_proximity',
                                                 'drawdown_reduction')),
    pnl              REAL,
    alpaca_order_id  TEXT,
    source           TEXT    NOT NULL DEFAULT 'agent'
                             CHECK(source IN ('agent', 'reconciliation', 'manual')),
    sector           TEXT,
    created_at       TEXT    DEFAULT (datetime('now')),
    updated_at       TEXT    DEFAULT (datetime('now'))
);

CREATE INDEX idx_positions_symbol     ON positions(symbol);
CREATE INDEX idx_positions_status     ON positions(status);
CREATE INDEX idx_positions_entry_date ON positions(entry_date);
CREATE INDEX idx_positions_sector     ON positions(sector);
```

| カラム | 型 | 説明 |
|--------|------|------|
| id | INTEGER PK | 自動採番 |
| symbol | TEXT | 銘柄シンボル（例: "AAPL"） |
| side | TEXT | 'long' / 'short' |
| qty | REAL | 保有株数 |
| entry_price | REAL | 平均エントリー価格 |
| entry_date | TEXT | エントリー日（YYYY-MM-DD） |
| stop_loss | REAL | ストップロス価格 |
| take_profit | REAL | テイクプロフィット価格 |
| strategy_reason | TEXT | エントリー理由（JSON文字列） |
| sentiment_score | REAL | LLMセンチメントスコア（0-100） |
| status | TEXT | 'open' / 'closed' |
| close_price | REAL | 決済価格 |
| close_date | TEXT | 決済日（YYYY-MM-DD） |
| close_reason | TEXT | 決済理由コード |
| pnl | REAL | 実現損益（USD） |
| alpaca_order_id | TEXT | Alpaca注文ID |
| source | TEXT | レコード追加元 |
| sector | TEXT | GICSセクター |
| created_at | TEXT | レコード作成日時 |
| updated_at | TEXT | レコード更新日時 |

#### 5.2 trades（取引履歴）

```sql
CREATE TABLE trades (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id      INTEGER REFERENCES positions(id),
    symbol           TEXT    NOT NULL,
    side             TEXT    NOT NULL CHECK(side IN ('buy', 'sell')),
    qty              REAL    NOT NULL CHECK(qty > 0),
    price            REAL    NOT NULL CHECK(price > 0),
    order_type       TEXT    NOT NULL
                             CHECK(order_type IN ('market', 'limit',
                                                  'stop', 'stop_limit')),
    alpaca_order_id  TEXT,
    client_order_id  TEXT    UNIQUE,
    fill_status      TEXT    CHECK(fill_status IS NULL
                             OR fill_status IN ('filled', 'partial', 'canceled')),
    executed_at      TEXT,
    created_at       TEXT    DEFAULT (datetime('now'))
);

CREATE INDEX idx_trades_symbol          ON trades(symbol);
CREATE INDEX idx_trades_position_id     ON trades(position_id);
CREATE INDEX idx_trades_executed_at     ON trades(executed_at);
CREATE INDEX idx_trades_client_order_id ON trades(client_order_id);
```

#### 5.3 daily_snapshots（日次スナップショット）

```sql
CREATE TABLE daily_snapshots (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    date                 TEXT    NOT NULL UNIQUE CHECK(date GLOB '????-??-??'),
    total_equity         REAL    NOT NULL,
    cash                 REAL    NOT NULL,
    positions_value      REAL    NOT NULL,
    daily_pnl            REAL,
    daily_pnl_pct        REAL,
    drawdown_pct         REAL,
    high_water_mark      REAL,
    open_positions       INTEGER,
    benchmark_spy_close  REAL,
    macro_regime         TEXT    CHECK(macro_regime IS NULL
                                 OR macro_regime IN ('bull', 'range', 'bear')),
    vix_close            REAL,
    created_at           TEXT    DEFAULT (datetime('now'))
);

CREATE INDEX idx_daily_snapshots_date ON daily_snapshots(date);
```

#### 5.4 execution_logs（実行ログ）

```sql
CREATE TABLE execution_logs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id      TEXT    NOT NULL UNIQUE,
    mode              TEXT    NOT NULL
                              CHECK(mode IN ('pre_market', 'morning',
                                             'midday', 'eod',
                                             'health_check', 'daily_report')),
    started_at        TEXT    NOT NULL,
    completed_at      TEXT,
    status            TEXT    NOT NULL
                              CHECK(status IN ('running', 'success',
                                               'error', 'skipped')),
    llm_input_tokens  INTEGER,
    llm_output_tokens INTEGER,
    llm_cost_usd      REAL,
    llm_model_version TEXT,
    decisions_json    TEXT,
    error_message     TEXT,
    execution_time_ms INTEGER,
    created_at        TEXT    DEFAULT (datetime('now'))
);

CREATE INDEX idx_execution_logs_execution_id ON execution_logs(execution_id);
CREATE INDEX idx_execution_logs_mode         ON execution_logs(mode);
CREATE INDEX idx_execution_logs_status       ON execution_logs(status);
```

#### 5.5 circuit_breaker（回路ブレーカー状態）

```sql
CREATE TABLE circuit_breaker (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    level        INTEGER NOT NULL CHECK(level BETWEEN 1 AND 4),
    triggered_at TEXT    NOT NULL,
    drawdown_pct REAL    NOT NULL,
    reason       TEXT    NOT NULL,
    resolved_at  TEXT,
    created_at   TEXT    DEFAULT (datetime('now'))
);

CREATE INDEX idx_circuit_breaker_level        ON circuit_breaker(level);
CREATE INDEX idx_circuit_breaker_triggered_at  ON circuit_breaker(triggered_at);
```

#### 5.6 strategy_params（パラメータ変更履歴）

```sql
CREATE TABLE strategy_params (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    param_name  TEXT    NOT NULL,
    old_value   TEXT,
    new_value   TEXT    NOT NULL,
    changed_at  TEXT    NOT NULL CHECK(changed_at GLOB '????-??-??*'),
    reason      TEXT,
    created_at  TEXT    DEFAULT (datetime('now'))
);

CREATE INDEX idx_strategy_params_name ON strategy_params(param_name);
```

#### 5.7 reconciliation_logs（照合履歴）

```sql
CREATE TABLE reconciliation_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id  TEXT    NOT NULL,
    issue_type    TEXT    NOT NULL
                          CHECK(issue_type IN ('CLOSED_MISSING',
                                               'ADDED_MISSING',
                                               'QTY_MISMATCH')),
    symbol        TEXT    NOT NULL,
    details       TEXT,
    auto_fixed    INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT    DEFAULT (datetime('now'))
);

CREATE INDEX idx_reconciliation_execution ON reconciliation_logs(execution_id);
```

#### 5.8 metrics（オブザーバビリティメトリクス）

```sql
CREATE TABLE metrics (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     TEXT    NOT NULL DEFAULT (datetime('now')),
    execution_id  TEXT    NOT NULL,
    metric_name   TEXT    NOT NULL,
    metric_value  REAL    NOT NULL
);

CREATE INDEX idx_metrics_name_ts ON metrics(metric_name, timestamp);
```

#### 5.9 schema_version（スキーマバージョン管理）

```sql
CREATE TABLE schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT    DEFAULT (datetime('now')),
    description TEXT
);

-- 初期バージョン
INSERT INTO schema_version (version, description)
VALUES (1, 'Initial schema: Phase 1 foundation');
```

### ER図（概念）

```
positions 1──N trades           (position_id FK)
positions 1──N reconciliation_logs (symbol経由)
execution_logs 1──N metrics     (execution_id経由)
execution_logs 1──N reconciliation_logs (execution_id経由)

daily_snapshots    -- 独立（日次スナップショット）
circuit_breaker    -- 独立（回路ブレーカーイベント）
strategy_params    -- 独立（パラメータ変更監査ログ）
schema_version     -- 独立（マイグレーション管理）
```

---

## 6. 型安全インターフェース（modules/types.py）

system-design.md v3 セクション2に準拠。全モジュールの入出力をdataclassesで定義し、Protocol でモジュール契約を明示する。

### データ型

```python
"""全モジュール共通の型定義。

frozen=True により不変オブジェクトを保証。
モジュール間の暗黙的なdict受け渡しを排除する。
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional, Protocol


# === Enums ===

class MacroRegime(Enum):
    BULL = "bull"
    RANGE = "range"
    BEAR = "bear"


class Action(Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    NO_ACTION = "no_action"


class VixRegime(Enum):
    LOW = "low"             # 5ポジション
    ELEVATED = "elevated"   # 3ポジション
    EXTREME = "extreme"     # 新規エントリー禁止


# === Data Classes ===

@dataclass(frozen=True)
class BarData:
    """1銘柄の市場データスナップショット。"""
    symbol: str
    close: float
    volume: int
    ma_50: float
    rsi_14: float
    atr_14: float
    volume_ratio_20d: float
    timestamp: datetime | None = None


@dataclass(frozen=True)
class PositionInfo:
    """1ポジションの情報。"""
    symbol: str
    qty: float
    avg_entry_price: float
    current_price: float
    unrealized_pnl: float
    sector: str
    entry_date: date | None = None


@dataclass(frozen=True)
class PortfolioState:
    """ポートフォリオ全体の状態。"""
    equity: float
    cash: float
    buying_power: float
    positions: dict[str, PositionInfo]
    daily_pnl_pct: float
    drawdown_pct: float
    high_water_mark: float = 0.0


@dataclass(frozen=True)
class TradingDecision:
    """LLM分析による売買判断。"""
    symbol: str
    action: Action
    confidence: int          # 0-100
    entry_price: float
    stop_loss: float
    take_profit: float
    reasoning_bull: str
    reasoning_bear: str
    catalyst: str
    expected_holding_days: int = 5


@dataclass(frozen=True)
class OrderResult:
    """注文実行の結果。"""
    symbol: str
    success: bool
    alpaca_order_id: str | None
    client_order_id: str
    filled_qty: float
    filled_price: float | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class CircuitBreakerState:
    """回路ブレーカーの現在状態。"""
    active: bool
    level: int              # 0=正常, 1-4=各レベル
    drawdown_pct: float
    cooldown_until: date | None = None
```

### Protocol定義（モジュール契約）

```python
# === Protocols ===

class DataCollector(Protocol):
    """市場データ収集モジュールの契約。"""
    def collect(self, symbols: list[str], mode: str) -> dict[str, BarData]: ...


class StateManager(Protocol):
    """状態管理モジュールの契約。"""
    def sync(self) -> PortfolioState: ...
    def reconcile(self) -> list[str]: ...


class RiskChecker(Protocol):
    """リスク管理モジュールの契約。"""
    def check_circuit_breaker(self, portfolio: PortfolioState) -> CircuitBreakerState: ...
    def calculate_position_size(
        self, entry: float, stop: float, capital: float
    ) -> int: ...
    def validate_sector_exposure(
        self, portfolio: PortfolioState, new_symbol: str, new_sector: str
    ) -> bool: ...


class LLMAnalyzer(Protocol):
    """LLM分析モジュールの契約。"""
    def analyze(
        self,
        market_data: dict[str, BarData],
        portfolio: PortfolioState,
        mode: str,
    ) -> list[TradingDecision]: ...


class OrderExecutor(Protocol):
    """注文実行モジュールの契約。"""
    def execute(
        self,
        decisions: list[TradingDecision],
        portfolio: PortfolioState,
        execution_id: str,
    ) -> list[OrderResult]: ...
```

### データフロー

```
collect_market_data() → dict[str, BarData]
        │
        ▼
sync_with_alpaca() → PortfolioState
        │
        ▼
check_circuit_breaker(PortfolioState) → CircuitBreakerState
        │
        ▼
get_trading_decisions(dict[str, BarData], PortfolioState) → list[TradingDecision]
        │
        ▼
execute_decisions(list[TradingDecision], PortfolioState, str) → list[OrderResult]
```

---

## 7. ロギング設定（modules/logger.py）

### 仕様

| 項目 | 値 |
|------|-----|
| フォーマット | JSON Lines |
| ファイル | `logs/agent.log` |
| ローテーション | 10MB x 5世代 |
| エンコーディング | UTF-8 |
| コンソール出力 | WARNING以上のみ |

### ログエントリのスキーマ

```json
{
  "ts": "2026-03-01T10:30:15",
  "level": "INFO",
  "module": "order_executor",
  "func": "execute_bracket_order",
  "exec_id": "2026-03-01_morning",
  "msg": "Order submitted: AAPL BUY 30 shares"
}
```

### ログレベルガイドライン

| レベル | 用途 | 例 |
|--------|------|-----|
| DEBUG | 開発・デバッグ用 | API応答の生データ |
| INFO | 正常な業務フロー | `注文送信: AAPL BUY 30株` |
| WARNING | 異常だが処理継続可能 | `Partial Fill検出`, `Reconciliation差分1件` |
| ERROR | 処理失敗 | `Claude CLIタイムアウト`, `注文拒否` |
| CRITICAL | システム全体に影響 | `回路ブレーカーLevel 3発動`, `DB書き込み失敗` |

---

## 8. DB初期化・マイグレーション（modules/db.py）

### APIインターフェース

```python
"""SQLite データベース管理モジュール。

- WALモードでの初期化
- スキーママイグレーション（バージョンベース）
- Online Backup API によるバックアップ
"""

import sqlite3
from pathlib import Path


def init_db(db_path: str) -> sqlite3.Connection:
    """DB接続を初期化する。存在しない場合はスキーマを作成。

    Args:
        db_path: SQLiteファイルパス

    Returns:
        設定済みのConnection
    """
    ...


def migrate(conn: sqlite3.Connection) -> None:
    """未適用のマイグレーションを順次実行する。

    schema_versionテーブルの最大バージョン番号を確認し、
    それより新しいマイグレーションを昇順で適用する。
    """
    ...


def backup_db(source_path: str, backup_dir: str) -> str:
    """Online Backup APIで安全にバックアップ。

    7世代保持。古いバックアップは自動削除。

    Returns:
        バックアップファイルパス
    """
    ...


def get_connection(db_path: str) -> sqlite3.Connection:
    """接続取得のショートカット。init_db + migrate を実行。"""
    ...
```

### マイグレーション管理

```python
MIGRATIONS: dict[int, tuple[str, str]] = {
    1: (
        """
        -- 全テーブル作成（Phase 1初期スキーマ）
        -- positions, trades, daily_snapshots, execution_logs,
        -- circuit_breaker, strategy_params, reconciliation_logs,
        -- metrics, schema_version
        """,
        "Initial schema: Phase 1 foundation"
    ),
    # Phase 2以降のマイグレーション例:
    # 2: ("ALTER TABLE ...", "Add xyz column"),
}
```

マイグレーション方針:
- **前方互換のみ**: `ALTER TABLE ADD COLUMN` 等。カラム削除はしない
- **トランザクション内実行**: 各マイグレーションは1トランザクションで実行
- **schema_versionテーブルで管理**: 適用済みバージョンを記録

---

## 9. Alpaca API接続確認仕様

Phase 1の最終ステップとして、ペーパートレーディングアカウントとの疎通を確認する。

### 確認項目

| # | 確認内容 | APIエンドポイント | 合格条件 |
|---|---------|-----------------|---------|
| 1 | 認証 | `GET /v2/account` | ステータス200、`account_blocked=false` |
| 2 | ペーパー確認 | レスポンスのURL | `paper-api.alpaca.markets` |
| 3 | ポジション取得 | `GET /v2/positions` | ステータス200（空配列でOK） |
| 4 | 注文一覧 | `GET /v2/orders` | ステータス200 |
| 5 | 市場データ | bars取得 | SPYの直近5本のバーデータ取得 |

### 安全確認

```python
# 接続テスト時の安全チェック
assert os.environ.get("ALPACA_PAPER") == "true", "ALPACA_PAPER must be true"
assert "paper-api" in client._base_url, "Must use paper trading URL"
```

---

## 10. テスト基盤

### conftest.py フィクスチャ

```python
"""テスト共通フィクスチャ。"""

import sqlite3
import pytest
from modules.config import AppConfig
from modules.db import init_db


@pytest.fixture
def in_memory_db() -> sqlite3.Connection:
    """テスト用のin-memory SQLiteデータベース。"""
    conn = init_db(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def sample_config(tmp_path) -> AppConfig:
    """テスト用のconfig.toml付き設定。"""
    config_file = tmp_path / "config.toml"
    config_file.write_text("""
[strategy]
sentiment_confidence_threshold = 70
ma_period = 50

[risk]
max_risk_per_trade_pct = 1.5

[system]
db_path = ":memory:"
log_dir = "logs"

[alpaca]
paper = true

[alerts]
slack_enabled = false
""")
    return AppConfig(_toml_file=str(config_file))
```

### テストカバレッジ目標（Phase 1）

| モジュール | 目標カバレッジ | 理由 |
|-----------|-------------|------|
| `modules/types.py` | 100% | 型の不変条件テスト |
| `modules/config.py` | 95%+ | バリデーション全パスを網羅 |
| `modules/db.py` | 90%+ | マイグレーション・バックアップのテスト |
| `modules/logger.py` | 80%+ | ファイル出力の確認 |

### テスト実行コマンド

```bash
# 全テスト実行 + カバレッジ
pytest tests/ --cov=modules --cov-report=term-missing --cov-fail-under=80

# 型チェック
mypy --strict modules/types.py

# リンター
ruff check .
ruff format --check .
```

---

## 11. Phase 1 タスク実行順序

Phase 1の各タスクの依存関係と推奨実行順序。

```
[1] Python仮想環境 + 依存パッケージ
    │
    ├──[2] .env + .gitignore + .env.example
    │
    ├──[3] pyproject.toml
    │
    └──[4] config.toml
         │
         ├──[5] modules/types.py（型定義）
         │       │
         │       ├──[6] modules/config.py（設定ローダー）
         │       │
         │       ├──[7] modules/db.py（DB初期化）
         │       │
         │       └──[8] modules/logger.py（ロギング）
         │
         └──[9] tests/conftest.py + 各テスト
              │
              └──[10] Alpaca API接続確認
```

### 工数見積もり（合計20h）

| # | タスク | 推定工数 |
|---|--------|---------|
| 1 | Python仮想環境 + パッケージ | 1h |
| 2 | .env / .gitignore / .env.example | 0.5h |
| 3 | pyproject.toml | 0.5h |
| 4 | config.toml | 1h |
| 5 | modules/types.py | 3h |
| 6 | modules/config.py | 3h |
| 7 | modules/db.py（初期化 + マイグレーション） | 4h |
| 8 | modules/logger.py | 1.5h |
| 9 | テスト基盤 + 各テスト | 4h |
| 10 | Alpaca API接続確認 | 1.5h |
| **合計** | | **20h** |

---

## 12. Phase 1 撤退基準

action-plan.md の Phase 1 独立撤退基準に準拠。

| 条件 | アクション |
|------|-----------|
| Alpaca API接続が3日以上確立できない | 代替プラットフォーム検討（Interactive Brokers等） |
| 基盤構築がWeek 5終了時に完了しない | スコープを再評価（MVP最小構成に絞り込み） |

### Phase 1 完了条件チェックリスト

- [ ] `pytest tests/` が全件パス（カバレッジ80%以上）
- [ ] `mypy --strict modules/types.py` がエラーなし
- [ ] `ruff check . && ruff format --check .` がエラーなし
- [ ] `config.toml` のバリデーションが正常動作
- [ ] SQLite DBの全テーブルが作成される
- [ ] ログファイルがJSON Lines形式で出力される
- [ ] Alpaca ペーパートレーディングAPIの疎通確認済み
- [ ] `.env` が `.gitignore` に含まれ、git管理されていないことを確認
