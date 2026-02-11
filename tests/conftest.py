"""テスト共通フィクスチャ。"""

import sqlite3
from pathlib import Path

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
def sample_config(tmp_path: Path) -> AppConfig:
    """テスト用のconfig.toml付き設定。"""
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
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

[macro]
vix_threshold_elevated = 20
vix_threshold_extreme = 30
macro_ma_period = 200
atr_period = 14

[system]
db_path = ":memory:"
log_dir = "logs"
claude_timeout_seconds = 120
lock_file_path = "data/state/agent.lock"

[alpaca]
paper = true

[alerts]
slack_enabled = false
alert_levels = ["warn", "error", "critical"]
"""
    )
    return AppConfig(_toml_file=str(config_file))
