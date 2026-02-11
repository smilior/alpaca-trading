"""pydantic-settings による型安全な設定管理。

config.toml を読み込み、型・値域・必須キーをバリデーション。
環境変数 TRADING_* で個別オーバーライド可能。
"""

from pathlib import Path
from typing import Any, ClassVar

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource
from pydantic_settings.main import TomlConfigSettingsSource


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
            raise ValueError(f"rsi_lower ({self.rsi_lower}) must be < rsi_upper ({self.rsi_upper})")
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
                raise ValueError(f"Circuit breaker levels must be strictly increasing: {levels}")
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

    _toml_file_path: ClassVar[str | None] = None

    strategy: StrategyConfig = StrategyConfig()
    risk: RiskConfig = RiskConfig()
    macro: MacroConfig = MacroConfig()
    system: SystemConfig = SystemConfig()
    alpaca: AlpacaConfig = AlpacaConfig()
    alerts: AlertsConfig = AlertsConfig()

    def __init__(self, _toml_file: str | None = None, **kwargs: Any) -> None:
        if _toml_file is not None:
            AppConfig._toml_file_path = _toml_file
        super().__init__(**kwargs)
        AppConfig._toml_file_path = None

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        toml_file = cls._toml_file_path or "config.toml"
        return (
            init_settings,
            env_settings,
            TomlConfigSettingsSource(settings_cls, toml_file=Path(toml_file)),
        )


def load_config(toml_path: str | Path | None = None) -> AppConfig:
    """設定をロードする。

    Args:
        toml_path: config.tomlのパス。Noneの場合はデフォルトパス。

    Returns:
        バリデーション済みのAppConfig
    """
    if toml_path is not None:
        return AppConfig(_toml_file=str(toml_path))
    return AppConfig()
