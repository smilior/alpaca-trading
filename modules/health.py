"""ヘルスチェックモジュール。

DB整合性、API疎通、実行ログの鮮度、回路ブレーカー状態、
ディスク容量を包括的に検査する。
"""

import logging
import os
import shutil
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from modules.config import AppConfig

logger = logging.getLogger("trading_agent")


@dataclass(frozen=True)
class HealthCheckResult:
    """ヘルスチェック結果。"""

    name: str
    ok: bool
    message: str


@dataclass
class HealthReport:
    """ヘルスチェック全体レポート。"""

    checks: list[HealthCheckResult] = field(default_factory=list)
    timestamp: str = ""

    @property
    def all_ok(self) -> bool:
        return all(c.ok for c in self.checks)

    @property
    def failed(self) -> list[HealthCheckResult]:
        return [c for c in self.checks if not c.ok]

    def summary(self) -> str:
        total = len(self.checks)
        passed = sum(1 for c in self.checks if c.ok)
        lines = [f"Health Check: {passed}/{total} passed"]
        for c in self.checks:
            status = "OK" if c.ok else "FAIL"
            lines.append(f"  [{status}] {c.name}: {c.message}")
        return "\n".join(lines)


def check_paper_trading() -> HealthCheckResult:
    """ALPACA_PAPER=true を確認。"""
    env_paper = os.environ.get("ALPACA_PAPER", "").lower()
    if env_paper == "true":
        return HealthCheckResult("paper_trading", True, "ALPACA_PAPER=true")
    return HealthCheckResult(
        "paper_trading", False, f"ALPACA_PAPER={env_paper!r} (expected 'true')"
    )


def check_api_connectivity(config: AppConfig) -> HealthCheckResult:
    """Alpaca API 疎通確認。"""
    try:
        from alpaca.trading.client import TradingClient

        client = TradingClient(
            api_key=os.environ.get("ALPACA_API_KEY", ""),
            secret_key=os.environ.get("ALPACA_SECRET_KEY", ""),
            paper=config.alpaca.paper,
        )
        account = client.get_account()
        equity = float(account.equity)  # type: ignore[union-attr]
        return HealthCheckResult(
            "api_connectivity",
            True,
            f"Connected: equity=${equity:,.2f}",
        )
    except Exception as e:
        return HealthCheckResult("api_connectivity", False, f"API error: {e}")


def check_db_integrity(conn: sqlite3.Connection) -> HealthCheckResult:
    """DB整合性チェック (PRAGMA integrity_check + テーブル存在確認)。"""
    try:
        row = conn.execute("PRAGMA integrity_check").fetchone()
        integrity = row[0] if row else "unknown"
        if integrity != "ok":
            return HealthCheckResult("db_integrity", False, f"integrity_check: {integrity}")

        expected_tables = {
            "positions",
            "trades",
            "daily_snapshots",
            "execution_logs",
            "circuit_breaker",
            "strategy_params",
            "reconciliation_logs",
            "metrics",
            "schema_version",
        }
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        actual_tables = {row[0] for row in rows}
        missing = expected_tables - actual_tables
        if missing:
            return HealthCheckResult(
                "db_integrity", False, f"Missing tables: {', '.join(sorted(missing))}"
            )
        return HealthCheckResult("db_integrity", True, "All 9 tables present, integrity OK")
    except Exception as e:
        return HealthCheckResult("db_integrity", False, f"DB error: {e}")


def check_execution_staleness(
    conn: sqlite3.Connection,
    max_staleness_hours: int = 26,
) -> HealthCheckResult:
    """最終実行からの経過時間を検査。

    max_staleness_hours のデフォルトは26h（1営業日+バッファ）。
    """
    try:
        row = conn.execute(
            "SELECT MAX(started_at) as last_run FROM execution_logs WHERE status = 'success'"
        ).fetchone()
        if row is None or row["last_run"] is None:
            return HealthCheckResult(
                "execution_staleness", True, "No previous executions (first run)"
            )

        last_run = datetime.fromisoformat(row["last_run"])
        elapsed = datetime.now() - last_run
        hours = elapsed.total_seconds() / 3600

        if hours > max_staleness_hours:
            return HealthCheckResult(
                "execution_staleness",
                False,
                f"Last success: {hours:.1f}h ago (threshold: {max_staleness_hours}h)",
            )
        return HealthCheckResult(
            "execution_staleness",
            True,
            f"Last success: {hours:.1f}h ago",
        )
    except Exception as e:
        return HealthCheckResult("execution_staleness", False, f"Error: {e}")


def check_circuit_breaker_status(conn: sqlite3.Connection) -> HealthCheckResult:
    """回路ブレーカーの現在の状態を確認。"""
    try:
        row = conn.execute(
            """SELECT level, triggered_at, drawdown_pct
               FROM circuit_breaker
               WHERE resolved_at IS NULL
               ORDER BY level DESC LIMIT 1"""
        ).fetchone()
        if row is None:
            return HealthCheckResult("circuit_breaker", True, "No active circuit breaker")

        level = row["level"]
        dd = row["drawdown_pct"]
        triggered = row["triggered_at"]
        return HealthCheckResult(
            "circuit_breaker",
            level < 3,  # L1,L2 は警告だが稼働可、L3以上は問題
            f"Level {level} active (DD={dd:.1f}%, triggered={triggered})",
        )
    except Exception as e:
        return HealthCheckResult("circuit_breaker", False, f"Error: {e}")


def check_recent_errors(conn: sqlite3.Connection, hours: int = 24) -> HealthCheckResult:
    """直近のエラー実行回数を確認。"""
    try:
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        row = conn.execute(
            "SELECT COUNT(*) FROM execution_logs WHERE status = 'error' AND started_at > ?",
            (cutoff,),
        ).fetchone()
        error_count = row[0] if row else 0
        if error_count >= 3:
            return HealthCheckResult(
                "recent_errors",
                False,
                f"{error_count} errors in last {hours}h (threshold: 3)",
            )
        return HealthCheckResult("recent_errors", True, f"{error_count} errors in last {hours}h")
    except Exception as e:
        return HealthCheckResult("recent_errors", False, f"Error: {e}")


def check_disk_space(db_path: str, min_mb: int = 100) -> HealthCheckResult:
    """DBディレクトリのディスク空き容量を確認。"""
    try:
        dir_path = os.path.dirname(os.path.abspath(db_path))
        usage = shutil.disk_usage(dir_path)
        free_mb = usage.free / (1024 * 1024)
        if free_mb < min_mb:
            return HealthCheckResult(
                "disk_space",
                False,
                f"Free: {free_mb:.0f}MB (minimum: {min_mb}MB)",
            )
        return HealthCheckResult("disk_space", True, f"Free: {free_mb:.0f}MB")
    except Exception as e:
        return HealthCheckResult("disk_space", False, f"Error: {e}")


def run_full_health_check(
    config: AppConfig,
    conn: sqlite3.Connection,
) -> HealthReport:
    """全ヘルスチェックを実行してレポートを返す。"""
    report = HealthReport(timestamp=datetime.now().isoformat())

    report.checks.append(check_paper_trading())
    report.checks.append(check_api_connectivity(config))
    report.checks.append(check_db_integrity(conn))
    report.checks.append(check_execution_staleness(conn))
    report.checks.append(check_circuit_breaker_status(conn))
    report.checks.append(check_recent_errors(conn))
    report.checks.append(check_disk_space(config.system.db_path))

    status = "ALL OK" if report.all_ok else f"{len(report.failed)} FAILED"
    logger.info(f"Health check completed: {status}")
    for c in report.failed:
        logger.warning(f"Health check FAIL: {c.name} - {c.message}")

    return report
