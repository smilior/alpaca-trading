"""main.py オーケストレーターのテスト。"""

import os
from unittest.mock import MagicMock, patch

import pytest

from main import (
    generate_execution_id,
    is_market_open,
    main,
    parse_args,
    run_health_check,
    run_pipeline,
)
from modules.types import (
    Action,
    BarData,
    CircuitBreakerState,
    OrderResult,
    PortfolioState,
    TradingDecision,
)


class TestParseArgs:
    def test_valid_modes(self):
        """有効なモードを受け付ける。"""
        for mode in ("morning", "midday", "eod", "health_check"):
            args = parse_args([mode])
            assert args.mode == mode

    def test_invalid_mode(self):
        """無効なモードで例外。"""
        with pytest.raises(SystemExit):
            parse_args(["invalid_mode"])


class TestGenerateExecutionId:
    def test_format(self):
        """execution_idのフォーマット。"""
        eid = generate_execution_id("morning")
        parts = eid.split("_")
        assert len(parts) == 3
        assert parts[1] == "morning"
        assert len(parts[0]) == 8  # YYYYMMDD
        assert len(parts[2]) == 6  # HHMMSS


class TestIsMarketOpen:
    def test_market_open_returns_bool(self):
        """市場オープン確認はboolを返す。"""
        result = is_market_open()
        assert isinstance(result, bool)

    def test_fallback_on_error(self):
        """エラー時はTrueを返す（フォールバック）。"""
        import exchange_calendars

        with patch.object(exchange_calendars, "get_calendar", side_effect=Exception("error")):
            result = is_market_open()
            assert result is True


class TestRunHealthCheck:
    def test_success(self, sample_config, in_memory_db):
        """ヘルスチェック成功。"""
        mock_client = MagicMock()
        account = MagicMock()
        account.equity = "100000"
        account.cash = "50000"
        account.buying_power = "100000"
        mock_client.get_account.return_value = account
        mock_client.get_all_positions.return_value = []

        sm = _make_state_manager(sample_config, in_memory_db, mock_client)

        with patch.dict(os.environ, {"ALPACA_PAPER": "true"}):
            result = run_health_check(sm)

        assert result is True

    def test_failure_not_paper(self, sample_config, in_memory_db):
        """ALPACA_PAPER != true → 失敗。"""
        mock_client = MagicMock()
        sm = _make_state_manager(sample_config, in_memory_db, mock_client)

        with patch.dict(os.environ, {"ALPACA_PAPER": "false"}):
            result = run_health_check(sm)

        assert result is False

    def test_failure_api_error(self, sample_config, in_memory_db):
        """API接続エラー → 失敗。"""
        mock_client = MagicMock()
        mock_client.get_account.side_effect = Exception("Connection refused")

        sm = _make_state_manager(sample_config, in_memory_db, mock_client)

        with patch.dict(os.environ, {"ALPACA_PAPER": "true"}):
            result = run_health_check(sm)

        assert result is False


class TestRunPipeline:
    @patch("main.AlpacaOrderExecutor")
    @patch("main.get_trading_decisions")
    @patch("main.collect_market_data")
    @patch("main.init_db")
    @patch("main.load_config")
    @patch("main.setup_logger")
    @patch("main.is_market_open")
    def test_morning_pipeline(
        self,
        mock_market_open,
        mock_setup_logger,
        mock_load_config,
        mock_init_db,
        mock_collect,
        mock_llm,
        mock_executor_cls,
        sample_config,
        in_memory_db,
    ):
        """morningモードの正常フロー。"""
        mock_market_open.return_value = True
        mock_load_config.return_value = sample_config
        mock_init_db.return_value = in_memory_db

        mock_collect.return_value = {
            "SPY": BarData(
                symbol="SPY",
                close=450.0,
                volume=1000000,
                ma_50=440.0,
                rsi_14=55.0,
                atr_14=5.0,
                volume_ratio_20d=1.1,
            ),
            "AAPL": BarData(
                symbol="AAPL",
                close=150.0,
                volume=500000,
                ma_50=145.0,
                rsi_14=50.0,
                atr_14=3.0,
                volume_ratio_20d=1.0,
            ),
        }

        mock_llm.return_value = [
            TradingDecision(
                symbol="AAPL",
                action=Action.BUY,
                confidence=85,
                entry_price=150.0,
                stop_loss=145.0,
                take_profit=165.0,
                reasoning_bull="Strong",
                reasoning_bear="Risk",
                catalyst="Earnings",
            ),
        ]

        mock_executor = MagicMock()
        mock_executor.execute.return_value = [
            OrderResult(
                symbol="AAPL",
                success=True,
                alpaca_order_id="order-123",
                client_order_id="exec_AAPL_buy",
                filled_qty=10,
                filled_price=150.0,
            ),
        ]
        mock_executor_cls.return_value = mock_executor

        with patch("main.AlpacaStateManager") as mock_sm_cls:
            mock_sm = MagicMock()
            mock_sm.check_execution_id.return_value = False
            mock_sm.reconcile.return_value = []
            mock_sm.sync.return_value = PortfolioState(
                equity=100000.0,
                cash=50000.0,
                buying_power=100000.0,
                positions={},
                daily_pnl_pct=0.0,
                drawdown_pct=0.0,
            )
            mock_sm.open_position.return_value = 1
            mock_sm_cls.return_value = mock_sm

            with patch("main.AlpacaRiskManager") as mock_rm_cls:
                mock_rm = MagicMock()
                mock_rm.check_circuit_breaker.return_value = CircuitBreakerState(
                    active=False, level=0, drawdown_pct=0.0
                )
                mock_rm.can_open_new_position.return_value = (True, "OK")
                mock_rm_cls.return_value = mock_rm

                with patch.dict(os.environ, {"ALPACA_PAPER": "true"}):
                    result = run_pipeline("morning")

        assert result == 0

    @patch("main.init_db")
    @patch("main.load_config")
    @patch("main.setup_logger")
    @patch("main.is_market_open")
    def test_eod_pipeline(
        self,
        mock_market_open,
        mock_setup_logger,
        mock_load_config,
        mock_init_db,
        sample_config,
        in_memory_db,
    ):
        """eodモードの正常フロー。"""
        mock_market_open.return_value = True
        mock_load_config.return_value = sample_config
        mock_init_db.return_value = in_memory_db

        with patch("main.AlpacaStateManager") as mock_sm_cls:
            mock_sm = MagicMock()
            mock_sm.check_execution_id.return_value = False
            mock_sm.reconcile.return_value = []
            mock_sm.sync.return_value = PortfolioState(
                equity=100000.0,
                cash=50000.0,
                buying_power=100000.0,
                positions={},
                daily_pnl_pct=0.0,
                drawdown_pct=0.0,
            )
            mock_sm_cls.return_value = mock_sm

            with patch("main.AlpacaRiskManager") as mock_rm_cls:
                mock_rm = MagicMock()
                mock_rm.check_circuit_breaker.return_value = CircuitBreakerState(
                    active=False, level=0, drawdown_pct=0.0
                )
                mock_rm_cls.return_value = mock_rm

                with patch("main.collect_market_data") as mock_collect:
                    mock_collect.return_value = {
                        "SPY": BarData(
                            symbol="SPY",
                            close=450.0,
                            volume=1000000,
                            ma_50=440.0,
                            rsi_14=55.0,
                            atr_14=5.0,
                            volume_ratio_20d=1.1,
                        ),
                    }

                    result = run_pipeline("eod")

        assert result == 0
        mock_sm.save_daily_snapshot.assert_called_once()

    @patch("main.init_db")
    @patch("main.load_config")
    @patch("main.setup_logger")
    @patch("main.is_market_open")
    def test_market_closed_skips(
        self,
        mock_market_open,
        mock_setup_logger,
        mock_load_config,
        mock_init_db,
        sample_config,
        in_memory_db,
    ):
        """市場閉鎖日はスキップ。"""
        mock_market_open.return_value = False
        mock_load_config.return_value = sample_config
        mock_init_db.return_value = in_memory_db

        with patch("main.AlpacaStateManager") as mock_sm_cls:
            mock_sm = MagicMock()
            mock_sm.check_execution_id.return_value = False
            mock_sm_cls.return_value = mock_sm

            result = run_pipeline("morning")

        assert result == 0

    @patch("main.init_db")
    @patch("main.load_config")
    @patch("main.setup_logger")
    def test_duplicate_execution_skips(
        self,
        mock_setup_logger,
        mock_load_config,
        mock_init_db,
        sample_config,
        in_memory_db,
    ):
        """execution_id重複はスキップ。"""
        mock_load_config.return_value = sample_config
        mock_init_db.return_value = in_memory_db

        with patch("main.AlpacaStateManager") as mock_sm_cls:
            mock_sm = MagicMock()
            mock_sm.check_execution_id.return_value = True
            mock_sm_cls.return_value = mock_sm

            result = run_pipeline("morning")

        assert result == 0

    @patch("main.init_db")
    @patch("main.load_config")
    @patch("main.setup_logger")
    def test_health_check_mode(
        self,
        mock_setup_logger,
        mock_load_config,
        mock_init_db,
        sample_config,
        in_memory_db,
    ):
        """health_checkモード。"""
        mock_load_config.return_value = sample_config
        mock_init_db.return_value = in_memory_db

        with patch("main.AlpacaStateManager") as mock_sm_cls:
            mock_sm = MagicMock()
            mock_sm.check_execution_id.return_value = False
            mock_sm.sync.return_value = PortfolioState(
                equity=100000.0,
                cash=50000.0,
                buying_power=100000.0,
                positions={},
                daily_pnl_pct=0.0,
                drawdown_pct=0.0,
            )
            mock_sm_cls.return_value = mock_sm

            with patch.dict(os.environ, {"ALPACA_PAPER": "true"}):
                result = run_pipeline("health_check")

        assert result == 0

    @patch("main.init_db")
    @patch("main.load_config")
    @patch("main.setup_logger")
    @patch("main.is_market_open")
    def test_pipeline_error_handling(
        self,
        mock_market_open,
        mock_setup_logger,
        mock_load_config,
        mock_init_db,
        sample_config,
        in_memory_db,
    ):
        """パイプラインエラーのハンドリング。"""
        mock_market_open.return_value = True
        mock_load_config.return_value = sample_config
        mock_init_db.return_value = in_memory_db

        with patch("main.AlpacaStateManager") as mock_sm_cls:
            mock_sm = MagicMock()
            mock_sm.check_execution_id.return_value = False
            mock_sm.reconcile.side_effect = Exception("DB error")
            mock_sm_cls.return_value = mock_sm

            result = run_pipeline("morning")

        assert result == 1


class TestMainEntrypoint:
    @patch("main.run_pipeline")
    @patch("main.load_config")
    def test_main_with_lock(self, mock_load_config, mock_run_pipeline, sample_config, tmp_path):
        """ファイルロック付きのメインエントリポイント。"""
        lock_path = str(tmp_path / "agent.lock")
        sample_config.system.lock_file_path = lock_path
        mock_load_config.return_value = sample_config
        mock_run_pipeline.return_value = 0

        result = main(["morning"])

        assert result == 0
        mock_run_pipeline.assert_called_once_with("morning")


def _make_state_manager(config, conn, client):
    """テスト用StateManager作成ヘルパー。"""
    from modules.state_manager import AlpacaStateManager

    return AlpacaStateManager(config, conn, trading_client=client)
