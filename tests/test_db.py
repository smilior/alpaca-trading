"""modules/db.py のテスト。"""

import sqlite3
from pathlib import Path

import pytest

from modules.db import (
    MIGRATIONS,
    _get_current_version,
    backup_db,
    get_connection,
    init_db,
    migrate,
)

# 期待する9テーブル
EXPECTED_TABLES = [
    "positions",
    "trades",
    "daily_snapshots",
    "execution_logs",
    "circuit_breaker",
    "strategy_params",
    "reconciliation_logs",
    "metrics",
    "schema_version",
]


class TestInitDb:
    def test_creates_all_tables(self, in_memory_db: sqlite3.Connection) -> None:
        cursor = in_memory_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row["name"] for row in cursor.fetchall()]
        for table in EXPECTED_TABLES:
            assert table in tables, f"Table {table} not found"

    def test_wal_mode(self, in_memory_db: sqlite3.Connection) -> None:
        cursor = in_memory_db.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        # in-memory DBではWALが適用されない場合がある（memory）
        assert mode in ("wal", "memory")

    def test_foreign_keys_enabled(self, in_memory_db: sqlite3.Connection) -> None:
        cursor = in_memory_db.execute("PRAGMA foreign_keys")
        assert cursor.fetchone()[0] == 1

    def test_creates_file_db(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test.db")
        conn = init_db(db_path)
        try:
            assert Path(db_path).exists()
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = [row["name"] for row in cursor.fetchall()]
            for table in EXPECTED_TABLES:
                assert table in tables
        finally:
            conn.close()

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "subdir" / "nested" / "test.db")
        conn = init_db(db_path)
        try:
            assert Path(db_path).exists()
        finally:
            conn.close()

    def test_row_factory(self, in_memory_db: sqlite3.Connection) -> None:
        assert in_memory_db.row_factory == sqlite3.Row


class TestMigrate:
    def test_schema_version_recorded(self, in_memory_db: sqlite3.Connection) -> None:
        cursor = in_memory_db.execute("SELECT version, description FROM schema_version")
        row = cursor.fetchone()
        assert row["version"] == 1
        assert row["description"] == "Initial schema: Phase 1 foundation"

    def test_get_current_version(self, in_memory_db: sqlite3.Connection) -> None:
        version = _get_current_version(in_memory_db)
        assert version == 1

    def test_get_current_version_no_table(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            version = _get_current_version(conn)
            assert version == 0
        finally:
            conn.close()

    def test_idempotent(self, in_memory_db: sqlite3.Connection) -> None:
        """2回migrateしてもエラーにならない。"""
        migrate(in_memory_db)
        version = _get_current_version(in_memory_db)
        assert version == 1


class TestTableConstraints:
    def test_positions_check_side(self, in_memory_db: sqlite3.Connection) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            in_memory_db.execute(
                "INSERT INTO positions (symbol, side, qty, entry_price, entry_date) "
                "VALUES ('AAPL', 'invalid', 10, 150, '2026-01-15')"
            )

    def test_positions_check_qty_positive(self, in_memory_db: sqlite3.Connection) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            in_memory_db.execute(
                "INSERT INTO positions (symbol, side, qty, entry_price, entry_date) "
                "VALUES ('AAPL', 'long', -1, 150, '2026-01-15')"
            )

    def test_positions_valid_insert(self, in_memory_db: sqlite3.Connection) -> None:
        in_memory_db.execute(
            "INSERT INTO positions (symbol, side, qty, entry_price, entry_date) "
            "VALUES ('AAPL', 'long', 10, 150, '2026-01-15')"
        )
        in_memory_db.commit()
        cursor = in_memory_db.execute("SELECT * FROM positions WHERE symbol='AAPL'")
        row = cursor.fetchone()
        assert row["symbol"] == "AAPL"
        assert row["status"] == "open"

    def test_trades_fk_constraint(self, in_memory_db: sqlite3.Connection) -> None:
        # position_id=999は存在しないのでFK違反
        with pytest.raises(sqlite3.IntegrityError):
            in_memory_db.execute(
                "INSERT INTO trades (position_id, symbol, side, qty, price, order_type) "
                "VALUES (999, 'AAPL', 'buy', 10, 150, 'market')"
            )

    def test_trades_valid_insert(self, in_memory_db: sqlite3.Connection) -> None:
        # まずpositionを作成
        in_memory_db.execute(
            "INSERT INTO positions (symbol, side, qty, entry_price, entry_date) "
            "VALUES ('AAPL', 'long', 10, 150, '2026-01-15')"
        )
        in_memory_db.commit()
        cursor = in_memory_db.execute("SELECT id FROM positions WHERE symbol='AAPL'")
        position_id = cursor.fetchone()["id"]
        in_memory_db.execute(
            "INSERT INTO trades (position_id, symbol, side, qty, price, order_type) "
            "VALUES (?, 'AAPL', 'buy', 10, 150, 'market')",
            (position_id,),
        )
        in_memory_db.commit()

    def test_daily_snapshots_unique_date(self, in_memory_db: sqlite3.Connection) -> None:
        in_memory_db.execute(
            "INSERT INTO daily_snapshots (date, total_equity, cash, positions_value) "
            "VALUES ('2026-01-15', 100000, 50000, 50000)"
        )
        in_memory_db.commit()
        with pytest.raises(sqlite3.IntegrityError):
            in_memory_db.execute(
                "INSERT INTO daily_snapshots (date, total_equity, cash, positions_value) "
                "VALUES ('2026-01-15', 101000, 51000, 50000)"
            )

    def test_execution_logs_valid_insert(self, in_memory_db: sqlite3.Connection) -> None:
        in_memory_db.execute(
            "INSERT INTO execution_logs (execution_id, mode, started_at, status) "
            "VALUES ('2026-01-15_morning', 'morning', '2026-01-15T09:30:00', 'running')"
        )
        in_memory_db.commit()
        cursor = in_memory_db.execute("SELECT * FROM execution_logs")
        row = cursor.fetchone()
        assert row["execution_id"] == "2026-01-15_morning"

    def test_circuit_breaker_valid_insert(self, in_memory_db: sqlite3.Connection) -> None:
        in_memory_db.execute(
            "INSERT INTO circuit_breaker (level, triggered_at, drawdown_pct, reason) "
            "VALUES (1, '2026-01-15T14:00:00', 4.5, 'Daily loss exceeded L1')"
        )
        in_memory_db.commit()

    def test_circuit_breaker_invalid_level(self, in_memory_db: sqlite3.Connection) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            in_memory_db.execute(
                "INSERT INTO circuit_breaker (level, triggered_at, drawdown_pct, reason) "
                "VALUES (5, '2026-01-15T14:00:00', 20.0, 'Invalid level')"
            )

    def test_metrics_valid_insert(self, in_memory_db: sqlite3.Connection) -> None:
        in_memory_db.execute(
            "INSERT INTO metrics (execution_id, metric_name, metric_value) "
            "VALUES ('exec-001', 'llm_latency_ms', 1500.0)"
        )
        in_memory_db.commit()

    def test_strategy_params_valid_insert(self, in_memory_db: sqlite3.Connection) -> None:
        in_memory_db.execute(
            "INSERT INTO strategy_params (param_name, old_value, new_value, changed_at, reason) "
            "VALUES ('ma_period', '50', '100', '2026-01-15T10:00:00', 'Performance review')"
        )
        in_memory_db.commit()

    def test_reconciliation_logs_valid_insert(self, in_memory_db: sqlite3.Connection) -> None:
        in_memory_db.execute(
            "INSERT INTO reconciliation_logs (execution_id, issue_type, symbol, details) "
            "VALUES ('exec-001', 'QTY_MISMATCH', 'AAPL', 'DB=10, Alpaca=12')"
        )
        in_memory_db.commit()


class TestBackupDb:
    def test_backup_creates_file(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "source.db")
        backup_dir = str(tmp_path / "backups")
        conn = init_db(db_path)
        conn.execute(
            "INSERT INTO positions (symbol, side, qty, entry_price, entry_date) "
            "VALUES ('AAPL', 'long', 10, 150, '2026-01-15')"
        )
        conn.commit()
        conn.close()

        result = backup_db(db_path, backup_dir)
        assert Path(result).exists()

        # バックアップの中身を確認
        backup_conn = sqlite3.connect(result)
        backup_conn.row_factory = sqlite3.Row
        cursor = backup_conn.execute("SELECT * FROM positions WHERE symbol='AAPL'")
        row = cursor.fetchone()
        assert row["qty"] == 10.0
        backup_conn.close()

    def test_backup_rotation(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "source.db")
        backup_dir = str(tmp_path / "backups")
        conn = init_db(db_path)
        conn.close()

        # 10個のバックアップを作成
        for _i in range(10):
            backup_db(db_path, backup_dir)

        # 7世代のみ残る
        backups = list(Path(backup_dir).glob("trading_backup_*.db"))
        assert len(backups) <= 7


class TestGetConnection:
    def test_returns_connection(self) -> None:
        conn = get_connection(":memory:")
        try:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='positions'"
            )
            assert cursor.fetchone() is not None
        finally:
            conn.close()


class TestMigrationsDict:
    def test_migration_v1_exists(self) -> None:
        assert 1 in MIGRATIONS
        sql, desc = MIGRATIONS[1]
        assert "positions" in sql
        assert "trades" in sql
        assert desc == "Initial schema: Phase 1 foundation"
