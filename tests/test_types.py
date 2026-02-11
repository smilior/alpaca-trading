"""modules/types.py のテスト。"""

from dataclasses import FrozenInstanceError
from datetime import date, datetime

import pytest

from modules.types import (
    Action,
    BarData,
    CircuitBreakerState,
    MacroRegime,
    OrderResult,
    PortfolioState,
    PositionInfo,
    TradingDecision,
    VixRegime,
)


class TestEnums:
    def test_macro_regime_values(self) -> None:
        assert MacroRegime.BULL.value == "bull"
        assert MacroRegime.RANGE.value == "range"
        assert MacroRegime.BEAR.value == "bear"

    def test_action_values(self) -> None:
        assert Action.BUY.value == "buy"
        assert Action.SELL.value == "sell"
        assert Action.HOLD.value == "hold"
        assert Action.NO_ACTION.value == "no_action"

    def test_vix_regime_values(self) -> None:
        assert VixRegime.LOW.value == "low"
        assert VixRegime.ELEVATED.value == "elevated"
        assert VixRegime.EXTREME.value == "extreme"


class TestBarData:
    def test_create(self) -> None:
        bar = BarData(
            symbol="AAPL",
            close=150.0,
            volume=1000000,
            ma_50=148.0,
            rsi_14=55.0,
            atr_14=3.5,
            volume_ratio_20d=1.2,
        )
        assert bar.symbol == "AAPL"
        assert bar.close == 150.0
        assert bar.timestamp is None

    def test_with_timestamp(self) -> None:
        ts = datetime(2026, 1, 15, 10, 30)
        bar = BarData(
            symbol="MSFT",
            close=400.0,
            volume=500000,
            ma_50=395.0,
            rsi_14=60.0,
            atr_14=5.0,
            volume_ratio_20d=0.8,
            timestamp=ts,
        )
        assert bar.timestamp == ts

    def test_frozen(self) -> None:
        bar = BarData(
            symbol="AAPL",
            close=150.0,
            volume=1000000,
            ma_50=148.0,
            rsi_14=55.0,
            atr_14=3.5,
            volume_ratio_20d=1.2,
        )
        with pytest.raises(FrozenInstanceError):
            bar.close = 200.0  # type: ignore[misc]


class TestPositionInfo:
    def test_create(self) -> None:
        pos = PositionInfo(
            symbol="GOOGL",
            qty=10.0,
            avg_entry_price=140.0,
            current_price=145.0,
            unrealized_pnl=50.0,
            sector="Technology",
        )
        assert pos.symbol == "GOOGL"
        assert pos.entry_date is None

    def test_with_entry_date(self) -> None:
        pos = PositionInfo(
            symbol="TSLA",
            qty=5.0,
            avg_entry_price=250.0,
            current_price=260.0,
            unrealized_pnl=50.0,
            sector="Consumer Discretionary",
            entry_date=date(2026, 1, 10),
        )
        assert pos.entry_date == date(2026, 1, 10)

    def test_frozen(self) -> None:
        pos = PositionInfo(
            symbol="GOOGL",
            qty=10.0,
            avg_entry_price=140.0,
            current_price=145.0,
            unrealized_pnl=50.0,
            sector="Technology",
        )
        with pytest.raises(FrozenInstanceError):
            pos.qty = 20.0  # type: ignore[misc]


class TestPortfolioState:
    def test_create(self) -> None:
        portfolio = PortfolioState(
            equity=100000.0,
            cash=50000.0,
            buying_power=100000.0,
            positions={},
            daily_pnl_pct=0.5,
            drawdown_pct=1.0,
        )
        assert portfolio.equity == 100000.0
        assert portfolio.high_water_mark == 0.0
        assert portfolio.positions == {}

    def test_with_positions(self) -> None:
        pos = PositionInfo(
            symbol="AAPL",
            qty=10.0,
            avg_entry_price=150.0,
            current_price=155.0,
            unrealized_pnl=50.0,
            sector="Technology",
        )
        portfolio = PortfolioState(
            equity=100000.0,
            cash=50000.0,
            buying_power=100000.0,
            positions={"AAPL": pos},
            daily_pnl_pct=0.5,
            drawdown_pct=1.0,
            high_water_mark=101000.0,
        )
        assert "AAPL" in portfolio.positions
        assert portfolio.high_water_mark == 101000.0


class TestTradingDecision:
    def test_create(self) -> None:
        decision = TradingDecision(
            symbol="AAPL",
            action=Action.BUY,
            confidence=85,
            entry_price=150.0,
            stop_loss=145.0,
            take_profit=160.0,
            reasoning_bull="Strong earnings",
            reasoning_bear="High valuation",
            catalyst="Q1 earnings beat",
        )
        assert decision.expected_holding_days == 5
        assert decision.action == Action.BUY

    def test_frozen(self) -> None:
        decision = TradingDecision(
            symbol="AAPL",
            action=Action.BUY,
            confidence=85,
            entry_price=150.0,
            stop_loss=145.0,
            take_profit=160.0,
            reasoning_bull="Strong earnings",
            reasoning_bear="High valuation",
            catalyst="Q1 earnings beat",
        )
        with pytest.raises(FrozenInstanceError):
            decision.confidence = 90  # type: ignore[misc]


class TestOrderResult:
    def test_success(self) -> None:
        result = OrderResult(
            symbol="AAPL",
            success=True,
            alpaca_order_id="abc-123",
            client_order_id="cli-001",
            filled_qty=10.0,
            filled_price=150.0,
        )
        assert result.success is True
        assert result.error_message is None

    def test_failure(self) -> None:
        result = OrderResult(
            symbol="AAPL",
            success=False,
            alpaca_order_id=None,
            client_order_id="cli-002",
            filled_qty=0.0,
            error_message="Insufficient buying power",
        )
        assert result.success is False
        assert result.filled_price is None


class TestCircuitBreakerState:
    def test_normal(self) -> None:
        state = CircuitBreakerState(
            active=False,
            level=0,
            drawdown_pct=1.5,
        )
        assert state.active is False
        assert state.cooldown_until is None

    def test_triggered(self) -> None:
        state = CircuitBreakerState(
            active=True,
            level=2,
            drawdown_pct=7.5,
            cooldown_until=date(2026, 2, 15),
        )
        assert state.active is True
        assert state.level == 2
