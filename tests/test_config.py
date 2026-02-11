"""modules/config.py のテスト。"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from modules.config import (
    AlertsConfig,
    AlpacaConfig,
    AppConfig,
    MacroConfig,
    RiskConfig,
    StrategyConfig,
    SystemConfig,
    load_config,
)


class TestStrategyConfig:
    def test_defaults(self) -> None:
        config = StrategyConfig()
        assert config.sentiment_confidence_threshold == 70
        assert config.ma_period == 50
        assert config.rsi_period == 14
        assert config.rsi_upper == 70
        assert config.rsi_lower == 30

    def test_valid_custom_values(self) -> None:
        config = StrategyConfig(
            sentiment_confidence_threshold=80,
            ma_period=200,
            rsi_upper=80,
            rsi_lower=20,
        )
        assert config.sentiment_confidence_threshold == 80
        assert config.ma_period == 200

    def test_rsi_lower_ge_upper_raises(self) -> None:
        """rsi_lower == rsi_upper (both within valid range) triggers model validator."""
        with pytest.raises(ValidationError, match="rsi_lower.*must be < rsi_upper"):
            StrategyConfig(rsi_lower=50, rsi_upper=50)

    def test_rsi_lower_gt_upper_raises(self) -> None:
        """rsi_lower > rsi_upper (both within valid range) triggers model validator."""
        with pytest.raises(ValidationError, match="rsi_lower.*must be < rsi_upper"):
            StrategyConfig(rsi_lower=50, rsi_upper=50)

    def test_rsi_out_of_range_raises(self) -> None:
        """rsi_lower exceeding field range triggers field validation."""
        with pytest.raises(ValidationError):
            StrategyConfig(rsi_lower=80, rsi_upper=60)

    def test_out_of_range_threshold(self) -> None:
        with pytest.raises(ValidationError):
            StrategyConfig(sentiment_confidence_threshold=49)

    def test_out_of_range_threshold_high(self) -> None:
        with pytest.raises(ValidationError):
            StrategyConfig(sentiment_confidence_threshold=101)

    def test_out_of_range_ma_period(self) -> None:
        with pytest.raises(ValidationError):
            StrategyConfig(ma_period=4)

    def test_out_of_range_stop_loss(self) -> None:
        with pytest.raises(ValidationError):
            StrategyConfig(stop_loss_atr_multiplier=0.1)


class TestRiskConfig:
    def test_defaults(self) -> None:
        config = RiskConfig()
        assert config.max_risk_per_trade_pct == 1.5
        assert config.circuit_breaker_level1_pct == 4.0

    def test_valid_circuit_breaker_levels(self) -> None:
        config = RiskConfig(
            circuit_breaker_level1_pct=3.0,
            circuit_breaker_level2_pct=6.0,
            circuit_breaker_level3_pct=9.0,
            circuit_breaker_level4_pct=12.0,
        )
        assert config.circuit_breaker_level1_pct == 3.0

    def test_non_increasing_circuit_breaker_raises(self) -> None:
        with pytest.raises(ValidationError, match="strictly increasing"):
            RiskConfig(
                circuit_breaker_level1_pct=5.0,
                circuit_breaker_level2_pct=5.0,
                circuit_breaker_level3_pct=10.0,
                circuit_breaker_level4_pct=15.0,
            )

    def test_decreasing_circuit_breaker_raises(self) -> None:
        with pytest.raises(ValidationError, match="strictly increasing"):
            RiskConfig(
                circuit_breaker_level1_pct=5.0,
                circuit_breaker_level2_pct=4.0,
                circuit_breaker_level3_pct=10.0,
                circuit_breaker_level4_pct=15.0,
            )

    def test_out_of_range_slippage(self) -> None:
        with pytest.raises(ValidationError):
            RiskConfig(slippage_factor=0.5)


class TestMacroConfig:
    def test_defaults(self) -> None:
        config = MacroConfig()
        assert config.vix_threshold_elevated == 20.0
        assert config.vix_threshold_extreme == 30.0
        assert config.macro_ma_period == 200
        assert config.atr_period == 14


class TestSystemConfig:
    def test_defaults(self) -> None:
        config = SystemConfig()
        assert config.db_path == "data/state/trading.db"
        assert config.log_dir == "logs"
        assert config.claude_timeout_seconds == 120

    def test_custom_timeout(self) -> None:
        config = SystemConfig(claude_timeout_seconds=60)
        assert config.claude_timeout_seconds == 60

    def test_out_of_range_timeout(self) -> None:
        with pytest.raises(ValidationError):
            SystemConfig(claude_timeout_seconds=10)


class TestAlpacaConfig:
    def test_default_paper_true(self) -> None:
        config = AlpacaConfig()
        assert config.paper is True


class TestAlertsConfig:
    def test_defaults(self) -> None:
        config = AlertsConfig()
        assert config.slack_enabled is False
        assert config.alert_levels == ["warn", "error", "critical"]


class TestAppConfig:
    def test_from_toml(self, sample_config: AppConfig) -> None:
        assert sample_config.strategy.sentiment_confidence_threshold == 70
        assert sample_config.risk.max_risk_per_trade_pct == 1.5
        assert sample_config.alpaca.paper is True

    def test_nested_config_accessible(self, sample_config: AppConfig) -> None:
        assert sample_config.system.db_path == ":memory:"
        assert sample_config.alerts.slack_enabled is False

    def test_defaults_without_toml(self) -> None:
        config = AppConfig()
        assert config.strategy.ma_period == 50
        assert config.risk.slippage_factor == 1.3


class TestLoadConfig:
    def test_load_from_path(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[strategy]
ma_period = 100

[risk]
max_risk_per_trade_pct = 2.0

[system]
db_path = ":memory:"

[alpaca]
paper = true

[alerts]
slack_enabled = false
"""
        )
        config = load_config(config_file)
        assert config.strategy.ma_period == 100
        assert config.risk.max_risk_per_trade_pct == 2.0

    def test_load_default(self) -> None:
        config = load_config()
        assert isinstance(config, AppConfig)
