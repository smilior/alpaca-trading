"""SQLite データベース管理モジュール。

- WALモードでの初期化
- スキーママイグレーション（バージョンベース）
- Online Backup API によるバックアップ
"""

import sqlite3
from datetime import datetime
from pathlib import Path

# === DDL: Phase 1 初期スキーマ ===

_SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS positions (
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

CREATE INDEX IF NOT EXISTS idx_positions_symbol     ON positions(symbol);
CREATE INDEX IF NOT EXISTS idx_positions_status     ON positions(status);
CREATE INDEX IF NOT EXISTS idx_positions_entry_date ON positions(entry_date);
CREATE INDEX IF NOT EXISTS idx_positions_sector     ON positions(sector);

CREATE TABLE IF NOT EXISTS trades (
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

CREATE INDEX IF NOT EXISTS idx_trades_symbol          ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_position_id     ON trades(position_id);
CREATE INDEX IF NOT EXISTS idx_trades_executed_at     ON trades(executed_at);
CREATE INDEX IF NOT EXISTS idx_trades_client_order_id ON trades(client_order_id);

CREATE TABLE IF NOT EXISTS daily_snapshots (
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

CREATE INDEX IF NOT EXISTS idx_daily_snapshots_date ON daily_snapshots(date);

CREATE TABLE IF NOT EXISTS execution_logs (
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

CREATE INDEX IF NOT EXISTS idx_execution_logs_execution_id ON execution_logs(execution_id);
CREATE INDEX IF NOT EXISTS idx_execution_logs_mode         ON execution_logs(mode);
CREATE INDEX IF NOT EXISTS idx_execution_logs_status       ON execution_logs(status);

CREATE TABLE IF NOT EXISTS circuit_breaker (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    level        INTEGER NOT NULL CHECK(level BETWEEN 1 AND 4),
    triggered_at TEXT    NOT NULL,
    drawdown_pct REAL    NOT NULL,
    reason       TEXT    NOT NULL,
    resolved_at  TEXT,
    created_at   TEXT    DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_circuit_breaker_level        ON circuit_breaker(level);
CREATE INDEX IF NOT EXISTS idx_circuit_breaker_triggered_at  ON circuit_breaker(triggered_at);

CREATE TABLE IF NOT EXISTS strategy_params (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    param_name  TEXT    NOT NULL,
    old_value   TEXT,
    new_value   TEXT    NOT NULL,
    changed_at  TEXT    NOT NULL CHECK(changed_at GLOB '????-??-??*'),
    reason      TEXT,
    created_at  TEXT    DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_strategy_params_name ON strategy_params(param_name);

CREATE TABLE IF NOT EXISTS reconciliation_logs (
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

CREATE INDEX IF NOT EXISTS idx_reconciliation_execution ON reconciliation_logs(execution_id);

CREATE TABLE IF NOT EXISTS metrics (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     TEXT    NOT NULL DEFAULT (datetime('now')),
    execution_id  TEXT    NOT NULL,
    metric_name   TEXT    NOT NULL,
    metric_value  REAL    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_metrics_name_ts ON metrics(metric_name, timestamp);

CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT    DEFAULT (datetime('now')),
    description TEXT
);
"""

# マイグレーション定義: {バージョン: (SQL, 説明)}
MIGRATIONS: dict[int, tuple[str, str]] = {
    1: (_SCHEMA_V1, "Initial schema: Phase 1 foundation"),
}


def _set_pragmas(conn: sqlite3.Connection) -> None:
    """PRAGMA設定を適用する。"""
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA wal_autocheckpoint = 500")
    conn.execute("PRAGMA busy_timeout = 5000")


def _get_current_version(conn: sqlite3.Connection) -> int:
    """現在のスキーマバージョンを取得する。テーブルがなければ0を返す。"""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    )
    if cursor.fetchone() is None:
        return 0
    cursor = conn.execute("SELECT MAX(version) FROM schema_version")
    row = cursor.fetchone()
    return row[0] if row and row[0] is not None else 0


def init_db(db_path: str) -> sqlite3.Connection:
    """DB接続を初期化する。存在しない場合はスキーマを作成。

    Args:
        db_path: SQLiteファイルパス（":memory:" も可）

    Returns:
        設定済みのConnection
    """
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _set_pragmas(conn)
    migrate(conn)
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    """未適用のマイグレーションを順次実行する。

    schema_versionテーブルの最大バージョン番号を確認し、
    それより新しいマイグレーションを昇順で適用する。
    """
    current = _get_current_version(conn)

    for version in sorted(MIGRATIONS.keys()):
        if version <= current:
            continue
        sql, description = MIGRATIONS[version]
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_version (version, description) VALUES (?, ?)",
            (version, description),
        )
        conn.commit()


def backup_db(source_path: str, backup_dir: str) -> str:
    """Online Backup APIで安全にバックアップ。

    7世代保持。古いバックアップは自動削除。

    Returns:
        バックアップファイルパス
    """
    backup_path = Path(backup_dir)
    backup_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest_file = backup_path / f"trading_backup_{timestamp}.db"

    source_conn = sqlite3.connect(source_path)
    dest_conn = sqlite3.connect(str(dest_file))
    try:
        source_conn.backup(dest_conn)
    finally:
        dest_conn.close()
        source_conn.close()

    # 7世代保持: 古いバックアップを削除
    backups = sorted(backup_path.glob("trading_backup_*.db"))
    while len(backups) > 7:
        backups.pop(0).unlink()

    return str(dest_file)


def get_connection(db_path: str) -> sqlite3.Connection:
    """接続取得のショートカット。init_db + migrate を実行。"""
    return init_db(db_path)
