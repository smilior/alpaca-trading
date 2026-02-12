"""order_executor モジュールのテスト。"""

import os
from unittest.mock import MagicMock, patch

import pytest

from modules.order_executor import AlpacaOrderExecutor
from modules.types import Action, PortfolioState, PositionInfo, TradingDecision


@pytest.fixture
def mock_client():
    """モックAlpaca TradingClient。"""
    client = MagicMock()
    order = MagicMock()
    order.id = "order-uuid-123"
    client.submit_order.return_value = order
    return client


@pytest.fixture
def executor(sample_config, mock_client):
    """テスト用OrderExecutor。"""
    with patch.dict(os.environ, {"ALPACA_PAPER": "true"}):
        return AlpacaOrderExecutor(sample_config, trading_client=mock_client)


@pytest.fixture
def portfolio():
    """テスト用PortfolioState。"""
    return PortfolioState(
        equity=100000.0,
        cash=50000.0,
        buying_power=100000.0,
        positions={
            "AAPL": PositionInfo(
                symbol="AAPL",
                qty=10,
                avg_entry_price=150.0,
                current_price=155.0,
                unrealized_pnl=50.0,
                sector="Technology",
            ),
        },
        daily_pnl_pct=0.0,
        drawdown_pct=0.0,
    )


def _make_buy_decision(symbol: str = "MSFT") -> TradingDecision:
    return TradingDecision(
        symbol=symbol,
        action=Action.BUY,
        confidence=85,
        entry_price=300.0,
        stop_loss=290.0,
        take_profit=330.0,
        reasoning_bull="Strong growth",
        reasoning_bear="Valuation high",
        catalyst="Cloud revenue",
    )


def _make_sell_decision(symbol: str = "AAPL") -> TradingDecision:
    return TradingDecision(
        symbol=symbol,
        action=Action.SELL,
        confidence=75,
        entry_price=155.0,
        stop_loss=0.0,
        take_profit=0.0,
        reasoning_bull="n/a",
        reasoning_bear="Signal to exit",
        catalyst="Stop loss hit",
    )


class TestPaperTradingSafety:
    def test_paper_config_required(self, sample_config):
        """config.paper=Falseで例外。"""
        sample_config.alpaca.paper = False
        with (
            pytest.raises(RuntimeError, match="SAFETY"),
            patch.dict(os.environ, {"ALPACA_PAPER": "true"}),
        ):
            AlpacaOrderExecutor(sample_config)

    def test_env_paper_required(self, sample_config):
        """ALPACA_PAPER != 'true' で例外。"""
        with (
            pytest.raises(RuntimeError, match="SAFETY"),
            patch.dict(os.environ, {"ALPACA_PAPER": "false"}),
        ):
            AlpacaOrderExecutor(sample_config)


class TestExecuteBuy:
    def test_successful_buy_bracket_order(self, executor, mock_client, portfolio):
        """ブラケット注文の成功。"""
        decision = _make_buy_decision()
        result = executor._execute_buy(decision, portfolio, "exec-001")

        assert result.success is True
        assert result.symbol == "MSFT"
        assert result.alpaca_order_id == "order-uuid-123"
        assert result.client_order_id == "exec-001_MSFT_buy"
        mock_client.submit_order.assert_called_once()

    def test_buy_order_retry(self, executor, mock_client, portfolio):
        """最初の試行失敗→リトライ成功。"""
        order = MagicMock()
        order.id = "order-retry-123"
        mock_client.submit_order.side_effect = [Exception("Network error"), order]

        decision = _make_buy_decision()
        result = executor._execute_buy(decision, portfolio, "exec-002")

        assert result.success is True
        assert mock_client.submit_order.call_count == 2

    def test_buy_order_both_attempts_fail(self, executor, mock_client, portfolio):
        """2回とも失敗。"""
        mock_client.submit_order.side_effect = [
            Exception("Error 1"),
            Exception("Error 2"),
        ]

        decision = _make_buy_decision()
        result = executor._execute_buy(decision, portfolio, "exec-003")

        assert result.success is False
        assert result.error_message is not None

    def test_buy_zero_qty(self, executor, portfolio):
        """計算結果が0株の場合。"""
        decision = TradingDecision(
            symbol="MSFT",
            action=Action.BUY,
            confidence=85,
            entry_price=300.0,
            stop_loss=300.0,  # entry == stop → 0株
            take_profit=330.0,
            reasoning_bull="",
            reasoning_bear="",
            catalyst="",
        )
        result = executor._execute_buy(decision, portfolio, "exec-004")

        assert result.success is False
        assert "quantity is 0" in result.error_message

    def test_bracket_order_parameters(self, executor, mock_client, portfolio):
        """ブラケット注文のパラメータ検証。"""
        decision = _make_buy_decision()
        executor._execute_buy(decision, portfolio, "exec-005")

        call_args = mock_client.submit_order.call_args
        order_req = call_args[0][0]

        assert order_req.symbol == "MSFT"
        assert order_req.limit_price == 300.0
        assert order_req.client_order_id == "exec-005_MSFT_buy"


class TestExecuteSell:
    def test_successful_sell(self, executor, mock_client, portfolio):
        """マーケット売り注文の成功。"""
        decision = _make_sell_decision()
        result = executor._execute_sell(decision, portfolio, "exec-001")

        assert result.success is True
        assert result.symbol == "AAPL"
        assert result.client_order_id == "exec-001_AAPL_sell"

    def test_sell_no_position(self, executor, portfolio):
        """ポジションなしの売り注文。"""
        decision = _make_sell_decision("ZZZZZ")
        result = executor._execute_sell(decision, portfolio, "exec-002")

        assert result.success is False
        assert "No open position" in result.error_message

    def test_sell_retry(self, executor, mock_client, portfolio):
        """売り注文のリトライ。"""
        order = MagicMock()
        order.id = "sell-retry-123"
        mock_client.submit_order.side_effect = [Exception("Error"), order]

        decision = _make_sell_decision()
        result = executor._execute_sell(decision, portfolio, "exec-003")

        assert result.success is True


class TestExecuteOrdering:
    def test_sell_before_buy(self, executor, mock_client, portfolio):
        """SELL注文がBUY注文より先に処理される。"""
        call_order = []

        def track_calls(request):
            call_order.append(request.symbol)
            order = MagicMock()
            order.id = f"order-{request.symbol}"
            return order

        mock_client.submit_order.side_effect = track_calls

        decisions = [
            _make_buy_decision("MSFT"),
            _make_sell_decision("AAPL"),
        ]
        with patch.dict(os.environ, {"ALPACA_PAPER": "true"}):
            results = executor.execute(decisions, portfolio, "exec-001")

        assert len(results) == 2
        assert call_order[0] == "AAPL"  # SELL first
        assert call_order[1] == "MSFT"  # BUY second

    def test_execute_empty_decisions(self, executor, portfolio):
        """空のdecisionsリスト。"""
        with patch.dict(os.environ, {"ALPACA_PAPER": "true"}):
            results = executor.execute([], portfolio, "exec-empty")
        assert results == []

    def test_client_order_id_format(self, executor, mock_client, portfolio):
        """client_order_idのフォーマット。"""
        decision = _make_buy_decision("NVDA")
        result = executor._execute_buy(decision, portfolio, "20240101_morning_090000")

        assert result.client_order_id == "20240101_morning_090000_NVDA_buy"
