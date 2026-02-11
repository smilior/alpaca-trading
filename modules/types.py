"""全モジュール共通の型定義。

frozen=True により不変オブジェクトを保証。
モジュール間の暗黙的なdict受け渡しを排除する。
"""

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Protocol

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
    LOW = "low"  # 5ポジション
    ELEVATED = "elevated"  # 3ポジション
    EXTREME = "extreme"  # 新規エントリー禁止


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
    confidence: int  # 0-100
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
    level: int  # 0=正常, 1-4=各レベル
    drawdown_pct: float
    cooldown_until: date | None = None


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
    def calculate_position_size(self, entry: float, stop: float, capital: float) -> int: ...
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
