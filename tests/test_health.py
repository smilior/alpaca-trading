"""ヘルスチェックモジュールのテスト。"""

import os
import sqlite3
from datetime import datetime, timedelta
from unittest.mock import patch

from modules.config import AppConfig
from modules.health import (
    HealthReport,
    check_circuit_breaker_status,
    check_db_integrity,
    check_disk_space,
    check_execution_staleness,
    check_paper_trading,
    check_recent_errors,
    run_full_health_check,
)


class TestCheckPaperTrading:
    def test_paper_true(self):
        with patch.dict(os.environ, {"ALPACA_PAPER": "true"}):
            result = check_paper_trading()
            assert result.ok is True
            assert result.name == "paper_trading"

    def test_paper_false(self):
        with patch.dict(os.environ, {"ALPACA_PAPER": "false"}):
            result = check_paper_trading()
            assert result.ok is False

    def test_paper_not_set(self):
        with patch.dict(os.environ, {}, clear=True):
            result = check_paper_trading()
            assert result.ok is False


class TestCheckDbIntegrity:
    def test_all_tables_present(self, in_memory_db: sqlite3.Connection):
        result = check_db_integrity(in_memory_db)
        assert result.ok is True
        assert "9 tables" in result.message

    def test_missing_table(self, in_memory_db: sqlite3.Connection):
        in_memory_db.execute("DROP TABLE IF EXISTS metrics")
        result = check_db_integrity(in_memory_db)
        assert result.ok is False
        assert "metrics" in result.message


class TestCheckExecutionStaleness:
    def test_no_previous_executions(self, in_memory_db: sqlite3.Connection):
        result = check_execution_staleness(in_memory_db)
        assert result.ok is True
        assert "first run" in result.message

    def test_recent_execution(self, in_memory_db: sqlite3.Connection):
        now = datetime.now().isoformat()
        in_memory_db.execute(
            "INSERT INTO execution_logs (execution_id, mode, started_at, status) "
            "VALUES ('test_1', 'morning', ?, 'success')",
            (now,),
        )
        in_memory_db.commit()
        result = check_execution_staleness(in_memory_db)
        assert result.ok is True

    def test_stale_execution(self, in_memory_db: sqlite3.Connection):
        old = (datetime.now() - timedelta(hours=30)).isoformat()
        in_memory_db.execute(
            "INSERT INTO execution_logs (execution_id, mode, started_at, status) "
            "VALUES ('test_old', 'morning', ?, 'success')",
            (old,),
        )
        in_memory_db.commit()
        result = check_execution_staleness(in_memory_db, max_staleness_hours=26)
        assert result.ok is False


class TestCheckCircuitBreakerStatus:
    def test_no_active_breaker(self, in_memory_db: sqlite3.Connection):
        result = check_circuit_breaker_status(in_memory_db)
        assert result.ok is True
        assert "No active" in result.message

    def test_level1_active(self, in_memory_db: sqlite3.Connection):
        in_memory_db.execute(
            "INSERT INTO circuit_breaker (level, triggered_at, drawdown_pct, reason) "
            "VALUES (1, ?, 4.5, 'Drawdown exceeded L1')",
            (datetime.now().isoformat(),),
        )
        in_memory_db.commit()
        result = check_circuit_breaker_status(in_memory_db)
        assert result.ok is True  # L1 is warning, not failure
        assert "Level 1" in result.message

    def test_level3_active(self, in_memory_db: sqlite3.Connection):
        in_memory_db.execute(
            "INSERT INTO circuit_breaker (level, triggered_at, drawdown_pct, reason) "
            "VALUES (3, ?, 10.5, 'Drawdown exceeded L3')",
            (datetime.now().isoformat(),),
        )
        in_memory_db.commit()
        result = check_circuit_breaker_status(in_memory_db)
        assert result.ok is False
        assert "Level 3" in result.message


class TestCheckRecentErrors:
    def test_no_errors(self, in_memory_db: sqlite3.Connection):
        result = check_recent_errors(in_memory_db)
        assert result.ok is True
        assert "0 errors" in result.message

    def test_many_errors(self, in_memory_db: sqlite3.Connection):
        now = datetime.now().isoformat()
        for i in range(5):
            in_memory_db.execute(
                "INSERT INTO execution_logs (execution_id, mode, started_at, status) "
                "VALUES (?, 'morning', ?, 'error')",
                (f"err_{i}", now),
            )
        in_memory_db.commit()
        result = check_recent_errors(in_memory_db)
        assert result.ok is False
        assert "5 errors" in result.message


class TestCheckDiskSpace:
    def test_enough_space(self, tmp_path):
        result = check_disk_space(str(tmp_path / "test.db"), min_mb=1)
        assert result.ok is True

    def test_threshold_extreme(self, tmp_path):
        # Require unrealistic amount to trigger failure
        result = check_disk_space(str(tmp_path / "test.db"), min_mb=999_999_999)
        assert result.ok is False


class TestHealthReport:
    def test_all_ok(self):
        from modules.health import HealthCheckResult

        report = HealthReport(
            checks=[
                HealthCheckResult("a", True, "ok"),
                HealthCheckResult("b", True, "ok"),
            ]
        )
        assert report.all_ok is True
        assert len(report.failed) == 0

    def test_some_failed(self):
        from modules.health import HealthCheckResult

        report = HealthReport(
            checks=[
                HealthCheckResult("a", True, "ok"),
                HealthCheckResult("b", False, "bad"),
            ]
        )
        assert report.all_ok is False
        assert len(report.failed) == 1

    def test_summary(self):
        from modules.health import HealthCheckResult

        report = HealthReport(
            checks=[
                HealthCheckResult("test_a", True, "all good"),
                HealthCheckResult("test_b", False, "broken"),
            ]
        )
        summary = report.summary()
        assert "1/2 passed" in summary
        assert "[OK] test_a" in summary
        assert "[FAIL] test_b" in summary


class TestRunFullHealthCheck:
    @patch("modules.health.check_api_connectivity")
    def test_full_check(self, mock_api, sample_config: AppConfig, in_memory_db: sqlite3.Connection):
        from modules.health import HealthCheckResult

        mock_api.return_value = HealthCheckResult("api_connectivity", True, "Connected")

        with patch.dict(os.environ, {"ALPACA_PAPER": "true"}):
            report = run_full_health_check(sample_config, in_memory_db)

        assert len(report.checks) == 7
        assert report.timestamp != ""
        # paper_trading + api + db_integrity + staleness + circuit_breaker + errors + disk
        names = [c.name for c in report.checks]
        assert "paper_trading" in names
        assert "api_connectivity" in names
        assert "db_integrity" in names
