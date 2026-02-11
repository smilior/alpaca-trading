"""modules/llm_analyzer.py のテスト。

Claude CLIの呼び出しはモックし、JSON Schema Validationと
フォールバック動作をテストする。
"""

import pytest

from modules.llm_analyzer import (
    DECISION_SCHEMA,
    _build_input_data,
    _extract_json,
    _parse_decisions,
    _sanitize_partial,
)
from modules.types import Action, BarData, PortfolioState, PositionInfo


def _sample_market_data() -> dict[str, BarData]:
    return {
        "AAPL": BarData(
            symbol="AAPL",
            close=185.0,
            volume=1000000,
            ma_50=180.0,
            rsi_14=55.0,
            atr_14=3.2,
            volume_ratio_20d=1.5,
        ),
    }


def _sample_portfolio() -> PortfolioState:
    return PortfolioState(
        equity=100000.0,
        cash=60000.0,
        buying_power=120000.0,
        positions={},
        daily_pnl_pct=0.5,
        drawdown_pct=2.0,
    )


class TestExtractJson:
    def test_clean_json(self) -> None:
        raw = '{"decisions": []}'
        result = _extract_json(raw)
        assert result == {"decisions": []}

    def test_json_with_prefix(self) -> None:
        raw = 'Here is the analysis:\n{"decisions": [{"symbol": "AAPL"}]}'
        result = _extract_json(raw)
        assert result is not None
        assert "decisions" in result

    def test_invalid_json(self) -> None:
        raw = "This is not JSON at all"
        result = _extract_json(raw)
        assert result is None

    def test_partial_json(self) -> None:
        raw = '{"decisions": ['
        result = _extract_json(raw)
        assert result is None


class TestSanitizePartial:
    def test_valid_decisions(self) -> None:
        parsed = {
            "decisions": [
                {"symbol": "AAPL", "action": "buy"},
                {"symbol": "MSFT", "action": "hold"},
            ]
        }
        result = _sanitize_partial(parsed)
        assert len(result["decisions"]) == 2

    def test_invalid_action_replaced(self) -> None:
        parsed = {"decisions": [{"symbol": "AAPL", "action": "INVALID"}]}
        result = _sanitize_partial(parsed)
        assert result["decisions"][0]["action"] == "no_action"

    def test_missing_symbol_filtered(self) -> None:
        parsed = {
            "decisions": [
                {"action": "buy"},  # missing symbol
                {"symbol": "AAPL", "action": "buy"},
            ]
        }
        result = _sanitize_partial(parsed)
        assert len(result["decisions"]) == 1
        assert result["decisions"][0]["symbol"] == "AAPL"


class TestBuildInputData:
    def test_structure(self) -> None:
        data = _build_input_data(_sample_market_data(), _sample_portfolio(), "morning")
        assert data["mode"] == "morning"
        assert "AAPL" in data["market_data"]
        assert data["portfolio"]["equity"] == 100000.0

    def test_with_positions(self) -> None:
        pos = PositionInfo(
            symbol="GOOGL",
            qty=10,
            avg_entry_price=140.0,
            current_price=145.0,
            unrealized_pnl=50.0,
            sector="Technology",
        )
        portfolio = PortfolioState(
            equity=100000.0,
            cash=50000.0,
            buying_power=100000.0,
            positions={"GOOGL": pos},
            daily_pnl_pct=0.5,
            drawdown_pct=1.0,
        )
        data = _build_input_data(_sample_market_data(), portfolio, "eod")
        assert "GOOGL" in data["portfolio"]["positions"]


class TestParseDecisions:
    def test_valid_buy(self) -> None:
        raw = [
            {
                "symbol": "AAPL",
                "action": "buy",
                "sentiment_analysis": {"overall": "positive", "confidence": 85},
                "trade_parameters": {
                    "suggested_entry_price": 185.0,
                    "calculated_stop_loss": 179.0,
                    "calculated_take_profit": 194.0,
                },
                "reasoning_structured": {
                    "bull_case": "Strong earnings",
                    "bear_case": "High valuation",
                    "catalyst": "Q1 beat",
                    "expected_holding_days": 5,
                },
            }
        ]
        decisions = _parse_decisions(raw, _sample_market_data())
        assert len(decisions) == 1
        assert decisions[0].symbol == "AAPL"
        assert decisions[0].action == Action.BUY
        assert decisions[0].confidence == 85
        assert decisions[0].stop_loss == 179.0

    def test_invalid_action_fallback(self) -> None:
        raw = [
            {
                "symbol": "AAPL",
                "action": "invalid_action",
                "sentiment_analysis": {"confidence": 50},
                "reasoning_structured": {
                    "bull_case": "",
                    "bear_case": "",
                    "catalyst": "",
                },
            }
        ]
        decisions = _parse_decisions(raw, _sample_market_data())
        assert decisions[0].action == Action.NO_ACTION

    def test_missing_trade_params(self) -> None:
        raw = [
            {
                "symbol": "AAPL",
                "action": "buy",
                "sentiment_analysis": {"confidence": 80},
                "reasoning_structured": {
                    "bull_case": "Good",
                    "bear_case": "Bad",
                    "catalyst": "Earnings",
                },
            }
        ]
        decisions = _parse_decisions(raw, _sample_market_data())
        assert decisions[0].entry_price == 185.0  # falls back to bar.close


class TestDecisionSchema:
    def test_schema_structure(self) -> None:
        assert "decisions" in DECISION_SCHEMA["properties"]
        assert DECISION_SCHEMA["type"] == "object"

    def test_valid_payload(self) -> None:
        from jsonschema import validate

        payload = {
            "macro_regime": "bull",
            "decisions": [
                {
                    "symbol": "AAPL",
                    "action": "buy",
                    "sentiment_analysis": {
                        "overall": "positive",
                        "confidence": 85,
                    },
                    "reasoning_structured": {
                        "bull_case": "Strong earnings",
                        "bear_case": "Valuation risk",
                        "catalyst": "Q1 results",
                    },
                }
            ],
        }
        validate(instance=payload, schema=DECISION_SCHEMA)  # should not raise

    def test_invalid_action(self) -> None:
        from jsonschema import ValidationError, validate

        payload = {
            "decisions": [
                {
                    "symbol": "AAPL",
                    "action": "invalid",
                    "sentiment_analysis": {"overall": "positive", "confidence": 50},
                    "reasoning_structured": {
                        "bull_case": "",
                        "bear_case": "",
                        "catalyst": "",
                    },
                }
            ],
        }
        with pytest.raises(ValidationError):
            validate(instance=payload, schema=DECISION_SCHEMA)
