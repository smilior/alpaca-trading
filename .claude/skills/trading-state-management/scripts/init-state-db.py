#!/usr/bin/env python3
"""
トレーディングボットのSQLiteデータベースを初期化するスクリプト。

使用方法:
    python init-state-db.py --db-path data/state/trading.db

テーブル一覧:
    - positions: ポジション管理
    - orders: 注文記録
    - trades: 約定済み取引
    - daily_performance: 日次パフォーマンス
    - strategy_params: 戦略パラメータ履歴
    - execution_logs: 実行ログ
"""

import argparse
import os
import sqlite3
import sys
from datetime import datetime

SCHEMA_SQL = """
-- ポジション管理
CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('long', 'short')),
    qty REAL NOT NULL,
    avg_entry_price REAL NOT NULL,
    current_price REAL,
    unrealized_pnl REAL,
    stop_loss_price REAL,
    take_profit_price REAL,
    strategy TEXT,
    entry_date TEXT NOT NULL,
    last_updated TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open', 'closed')),
    close_date TEXT,
    close_price REAL,
    realized_pnl REAL,
    close_reason TEXT,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol);
CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status);
CREATE INDEX IF NOT EXISTS idx_positions_entry_date ON positions(entry_date);

-- 注文記録
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alpaca_order_id TEXT UNIQUE,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('buy', 'sell')),
    qty REAL NOT NULL,
    order_type TEXT NOT NULL CHECK(order_type IN
        ('market', 'limit', 'stop', 'stop_limit', 'trailing_stop')),
    limit_price REAL,
    stop_price REAL,
    trail_percent REAL,
    time_in_force TEXT NOT NULL DEFAULT 'day',
    status TEXT NOT NULL DEFAULT 'new',
    filled_qty REAL DEFAULT 0,
    filled_avg_price REAL,
    submitted_at TEXT NOT NULL,
    filled_at TEXT,
    canceled_at TEXT,
    expired_at TEXT,
    strategy TEXT,
    signal_score REAL,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(symbol);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_submitted_at ON orders(submitted_at);
CREATE INDEX IF NOT EXISTS idx_orders_alpaca_id ON orders(alpaca_order_id);

-- 約定済み取引
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER REFERENCES orders(id),
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('buy', 'sell')),
    qty REAL NOT NULL,
    price REAL NOT NULL,
    total_value REAL NOT NULL,
    commission REAL DEFAULT 0,
    slippage REAL DEFAULT 0,
    pnl REAL,
    pnl_pct REAL,
    holding_period_days INTEGER,
    strategy TEXT,
    entry_reason TEXT,
    exit_reason TEXT,
    timestamp TEXT NOT NULL,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp);
CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades(strategy);

-- 日次パフォーマンス
CREATE TABLE IF NOT EXISTS daily_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,
    portfolio_value REAL NOT NULL,
    cash REAL NOT NULL,
    positions_value REAL NOT NULL,
    daily_pnl REAL NOT NULL,
    daily_return_pct REAL NOT NULL,
    cumulative_return_pct REAL NOT NULL,
    drawdown_pct REAL NOT NULL,
    max_drawdown_pct REAL NOT NULL,
    trade_count INTEGER DEFAULT 0,
    win_count INTEGER DEFAULT 0,
    loss_count INTEGER DEFAULT 0,
    sharpe_ratio_30d REAL,
    benchmark_return_pct REAL,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_daily_perf_date ON daily_performance(date);

-- 戦略パラメータ履歴
CREATE TABLE IF NOT EXISTS strategy_params (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name TEXT NOT NULL,
    params_json TEXT NOT NULL,
    version TEXT NOT NULL,
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    change_reason TEXT,
    performance_before TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_strategy_params_name ON strategy_params(strategy_name);
CREATE INDEX IF NOT EXISTS idx_strategy_params_effective ON strategy_params(effective_from);

-- 実行ログ
CREATE TABLE IF NOT EXISTS execution_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    event_type TEXT NOT NULL,
    details_json TEXT,
    level TEXT NOT NULL DEFAULT 'info'
        CHECK(level IN ('debug', 'info', 'warning', 'error', 'critical')),
    agent_version TEXT,
    execution_time_ms INTEGER,
    tokens_used INTEGER,
    cost_usd REAL
);

CREATE INDEX IF NOT EXISTS idx_exec_logs_timestamp ON execution_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_exec_logs_level ON execution_logs(level);
CREATE INDEX IF NOT EXISTS idx_exec_logs_event ON execution_logs(event_type);

-- メタデータテーブル（スキーマバージョン管理）
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

INITIAL_DATA_SQL = """
-- スキーマバージョン
INSERT OR REPLACE INTO schema_meta (key, value, updated_at)
VALUES ('schema_version', '1.0', datetime('now'));

INSERT OR REPLACE INTO schema_meta (key, value, updated_at)
VALUES ('created_at', datetime('now'), datetime('now'));

INSERT OR REPLACE INTO schema_meta (key, value, updated_at)
VALUES ('description', 'Alpaca Trading Bot State Database', datetime('now'));
"""


def init_database(db_path: str, force: bool = False) -> None:
    """データベースを初期化する"""

    # ディレクトリ作成
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    # 既存チェック
    if os.path.exists(db_path) and not force:
        print(f"データベースが既に存在します: {db_path}")
        print("上書きするには --force オプションを使用してください")
        sys.exit(1)

    if os.path.exists(db_path) and force:
        backup_path = f"{db_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        os.rename(db_path, backup_path)
        print(f"既存DBをバックアップ: {backup_path}")

    # DB作成
    conn = sqlite3.connect(db_path)
    try:
        # WALモード有効化（読み書きの並行処理を改善）
        conn.execute("PRAGMA journal_mode=WAL")

        # スキーマ作成
        conn.executescript(SCHEMA_SQL)
        print("テーブル作成完了")

        # 初期データ投入
        conn.executescript(INITIAL_DATA_SQL)
        print("初期データ投入完了")

        conn.commit()

        # テーブル一覧の確認
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]
        print(f"\n作成されたテーブル ({len(tables)}個):")
        for table in tables:
            cursor = conn.execute(f"PRAGMA table_info({table})")
            columns = cursor.fetchall()
            print(f"  - {table} ({len(columns)} columns)")

        print(f"\nデータベース初期化完了: {db_path}")

    except Exception as e:
        print(f"エラー: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="トレーディングボットのSQLiteデータベースを初期化"
    )
    parser.add_argument(
        "--db-path",
        default="data/state/trading.db",
        help="データベースファイルのパス（デフォルト: data/state/trading.db）"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="既存のデータベースを上書きする（バックアップ作成後）"
    )

    args = parser.parse_args()
    init_database(args.db_path, args.force)


if __name__ == "__main__":
    main()
