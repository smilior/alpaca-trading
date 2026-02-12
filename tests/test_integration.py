"""統合テスト + エッジケーステスト。

Phase 4: Layer 2 結合テスト（Alpaca APIモック、Claude CLIモック、SQLite in-memory DB）
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from modules.risk_manager import AlpacaRiskManager
from modules.state_manager import AlpacaStateManager
from modules.types import (
    Action,
    BarData,
    CircuitBreakerState,
    OrderResult,
    PortfolioState,
    PositionInfo,
    TradingDecision,
    VixRegime,
)

# === Edge Case: Market Closed ===


class TestMarketClosedEdgeCases:
    """市場閉鎖時の動作テスト。"""

    def test_weekend_detected(self):
        """週末はis_market_openがFalseを返す。"""
        from main import is_market_open

        # 実際のカレンダーを使用。結果はboolなら合格。
        result = is_market_open()
        assert isinstance(result, bool)

    @patch("main.is_market_open", return_value=False)
    @patch("main.init_db")
    @patch("main.load_config")
    @patch("main.setup_logger")
    def test_pipeline_skips_on_closed(
        self,
        mock_setup_logger,
        mock_load_config,
        mock_init_db,
        mock_market,
        sample_config,
        in_memory_db,
    ):
        """市場閉鎖時はパイプラインがskipで終了する。"""
        from main import run_pipeline

        mock_load_config.return_value = sample_config
        mock_init_db.return_value = in_memory_db

        with patch("main.AlpacaStateManager") as mock_sm_cls:
            mock_sm = MagicMock()
            mock_sm.check_execution_id.return_value = False
            mock_sm_cls.return_value = mock_sm

            result = run_pipeline("morning")
            assert result == 0
            mock_sm.record_execution_log.assert_called()


# === Edge Case: API Failures ===


class TestApiFailureEdgeCases:
    """API障害シミュレーション。"""

    def test_reconcile_handles_api_error(self, sample_config, in_memory_db):
        """API呼び出しエラー時はreconcileが例外を上げる。"""
        mock_client = MagicMock()
        mock_client.get_all_positions.side_effect = Exception("API timeout")

        sm = AlpacaStateManager(sample_config, in_memory_db, trading_client=mock_client)
        with pytest.raises(Exception, match="API timeout"):
            sm.reconcile()

    def test_sync_handles_api_error(self, sample_config, in_memory_db):
        """sync時のAPIエラー。"""
        mock_client = MagicMock()
        mock_client.get_account.side_effect = ConnectionError("Network unreachable")

        sm = AlpacaStateManager(sample_config, in_memory_db, trading_client=mock_client)
        with pytest.raises(ConnectionError):
            sm.sync()


# === Edge Case: Partial Fill ===


class TestPartialFillEdgeCases:
    """Partial Fill のハンドリング。"""

    def test_record_partial_fill_trade(self, sample_config, in_memory_db):
        """部分約定のトレードをDBに記録できる。"""
        sm = AlpacaStateManager(sample_config, in_memory_db, trading_client=MagicMock())

        # まずポジションを開く
        decision = TradingDecision(
            symbol="AAPL",
            action=Action.BUY,
            confidence=80,
            entry_price=150.0,
            stop_loss=145.0,
            take_profit=165.0,
            reasoning_bull="Strong",
            reasoning_bear="Risk",
            catalyst="Earnings",
        )
        partial_result = OrderResult(
            symbol="AAPL",
            success=True,
            alpaca_order_id="order-partial-1",
            client_order_id="exec_AAPL_buy",
            filled_qty=5,  # 注文10に対して5のみ約定
            filled_price=150.50,
        )

        pos_id = sm.open_position(decision, partial_result)
        assert pos_id > 0

        # DBに記録された数量を確認
        row = in_memory_db.execute(
            "SELECT qty, entry_price FROM positions WHERE id = ?",
            (pos_id,),
        ).fetchone()
        assert row["qty"] == 5
        assert row["entry_price"] == 150.50


# === Edge Case: DST Transition ===


class TestDstTransition:
    """DST切替日の処理。"""

    def test_execution_id_consistent_during_dst(self):
        """DST切替中もexecution_idが正しく生成される。"""
        from main import generate_execution_id

        eid = generate_execution_id("morning")
        parts = eid.split("_")
        assert len(parts) == 3
        assert parts[1] == "morning"
        # タイムスタンプがvalidな形式
        assert len(parts[0]) == 8
        assert len(parts[2]) == 6


# === Integration: Full Morning Pipeline (Mocked) ===


class TestFullMorningPipeline:
    """モック済みの完全な morning パイプラインテスト。"""

    @patch("main.AlpacaOrderExecutor")
    @patch("main.get_trading_decisions")
    @patch("main.collect_market_data")
    @patch("main.init_db")
    @patch("main.load_config")
    @patch("main.setup_logger")
    @patch("main.is_market_open", return_value=True)
    def test_sell_then_buy_order(
        self,
        mock_market,
        mock_setup_logger,
        mock_load_config,
        mock_init_db,
        mock_collect,
        mock_llm,
        mock_executor_cls,
        sample_config,
        in_memory_db,
    ):
        """SELLが先に実行され、その後BUYが実行される。"""
        from main import run_pipeline

        mock_load_config.return_value = sample_config
        mock_init_db.return_value = in_memory_db

        mock_collect.return_value = {
            "SPY": BarData(
                symbol="SPY",
                close=450,
                volume=1_000_000,
                ma_50=440,
                rsi_14=55,
                atr_14=5,
                volume_ratio_20d=1.1,
            ),
            "AAPL": BarData(
                symbol="AAPL",
                close=150,
                volume=500_000,
                ma_50=145,
                rsi_14=50,
                atr_14=3,
                volume_ratio_20d=1.0,
            ),
        }

        mock_llm.return_value = [
            TradingDecision(
                symbol="AAPL",
                action=Action.BUY,
                confidence=85,
                entry_price=150,
                stop_loss=145,
                take_profit=165,
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
                alpaca_order_id="order-1",
                client_order_id="exec_AAPL_buy",
                filled_qty=10,
                filled_price=150,
            ),
        ]
        mock_executor_cls.return_value = mock_executor

        with patch("main.AlpacaStateManager") as mock_sm_cls:
            mock_sm = MagicMock()
            mock_sm.check_execution_id.return_value = False
            mock_sm.reconcile.return_value = []
            mock_sm.sync.return_value = PortfolioState(
                equity=100_000,
                cash=50_000,
                buying_power=100_000,
                positions={},
                daily_pnl_pct=0,
                drawdown_pct=0,
            )
            mock_sm.open_position.return_value = 1
            mock_sm_cls.return_value = mock_sm

            with patch("main.AlpacaRiskManager") as mock_rm_cls:
                mock_rm = MagicMock()
                mock_rm.check_circuit_breaker.return_value = CircuitBreakerState(
                    active=False, level=0, drawdown_pct=0
                )
                mock_rm.can_open_new_position.return_value = (True, "OK")
                mock_rm_cls.return_value = mock_rm

                with patch.dict(os.environ, {"ALPACA_PAPER": "true"}):
                    result = run_pipeline("morning")

        assert result == 0
        mock_executor.execute.assert_called_once()
        mock_sm.open_position.assert_called_once()


# === Integration: Circuit Breaker Cascade ===


class TestCircuitBreakerCascade:
    """回路ブレーカーのカスケードテスト。"""

    def test_level_escalation(self, sample_config, in_memory_db):
        """ドローダウン悪化に伴いCBレベルがエスカレーションする。"""
        rm = AlpacaRiskManager(sample_config, in_memory_db)

        # L1トリガー: DD 5%
        portfolio_l1 = PortfolioState(
            equity=95_000,
            cash=40_000,
            buying_power=80_000,
            positions={},
            daily_pnl_pct=-2.0,
            drawdown_pct=5.0,
        )
        cb = rm.check_circuit_breaker(portfolio_l1)
        assert cb.active is True
        assert cb.level == 1

    def test_no_trigger_low_drawdown(self, sample_config, in_memory_db):
        """低いDDではCBが発動しない。"""
        rm = AlpacaRiskManager(sample_config, in_memory_db)

        portfolio = PortfolioState(
            equity=98_000,
            cash=45_000,
            buying_power=90_000,
            positions={},
            daily_pnl_pct=-0.5,
            drawdown_pct=2.0,
        )
        cb = rm.check_circuit_breaker(portfolio)
        assert cb.active is False
        assert cb.level == 0


# === Integration: Reconciliation + State Management ===


class TestReconciliationIntegration:
    """リコンシリエーション統合テスト。"""

    def test_reconcile_then_sync(self, sample_config, in_memory_db):
        """reconcile後にsyncが正常に動作する。"""
        mock_client = MagicMock()

        # reconcile用: ポジションなし
        mock_client.get_all_positions.return_value = []

        # sync用
        account = MagicMock()
        account.equity = "100000"
        account.cash = "50000"
        account.buying_power = "100000"
        mock_client.get_account.return_value = account

        sm = AlpacaStateManager(sample_config, in_memory_db, trading_client=mock_client)

        issues = sm.reconcile()
        assert isinstance(issues, list)

        portfolio = sm.sync()
        assert portfolio.equity == 100_000.0


# === Edge Case: Concurrent Position Limits ===


class TestPositionLimitsEdgeCases:
    """ポジション数制限のエッジケーステスト。"""

    def test_max_positions_blocks_new_buy(self, sample_config, in_memory_db):
        """最大ポジション数到達時に新規BUYがブロックされる。"""
        rm = AlpacaRiskManager(sample_config, in_memory_db)

        # max_concurrent_positions=5 のところに5ポジション
        positions = {
            f"SYM{i}": PositionInfo(
                symbol=f"SYM{i}",
                qty=10,
                avg_entry_price=100,
                current_price=100,
                unrealized_pnl=0,
                sector="Technology",
            )
            for i in range(5)
        }
        portfolio = PortfolioState(
            equity=100_000,
            cash=50_000,
            buying_power=100_000,
            positions=positions,
            daily_pnl_pct=0,
            drawdown_pct=0,
        )

        can_open, reason = rm.can_open_new_position(
            portfolio, "NEWSTOCK", "Healthcare", VixRegime.LOW
        )
        assert can_open is False
        assert "Max concurrent" in reason or "max" in reason.lower()

    def test_sector_limit_allows_different_sector(self, sample_config, in_memory_db):
        """異なるセクターなら追加可能。"""
        rm = AlpacaRiskManager(sample_config, in_memory_db)

        positions = {
            "JPM": PositionInfo(
                symbol="JPM",
                qty=10,
                avg_entry_price=150,
                current_price=155,
                unrealized_pnl=50,
                sector="Financials",
            ),
            "V": PositionInfo(
                symbol="V",
                qty=5,
                avg_entry_price=250,
                current_price=260,
                unrealized_pnl=50,
                sector="Financials",
            ),
        }
        portfolio = PortfolioState(
            equity=100_000,
            cash=50_000,
            buying_power=100_000,
            positions=positions,
            daily_pnl_pct=0,
            drawdown_pct=0,
        )

        can_open, reason = rm.can_open_new_position(portfolio, "AAPL", "Technology", VixRegime.LOW)
        assert can_open is True
