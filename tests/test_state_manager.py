"""state_manager モジュールのテスト。"""

from datetime import date
from unittest.mock import MagicMock

import pytest

from modules.state_manager import AlpacaStateManager
from modules.types import Action, OrderResult, PortfolioState, TradingDecision


@pytest.fixture
def state_manager(in_memory_db, sample_config):
    """テスト用StateManager。"""
    mock_client = MagicMock()
    return AlpacaStateManager(sample_config, in_memory_db, trading_client=mock_client)


@pytest.fixture
def mock_account():
    """モックAlpacaアカウント。"""
    account = MagicMock()
    account.equity = "100000.00"
    account.cash = "50000.00"
    account.buying_power = "100000.00"
    return account


@pytest.fixture
def mock_position():
    """モックAlpacaポジション。"""
    pos = MagicMock()
    pos.symbol = "AAPL"
    pos.qty = "10"
    pos.avg_entry_price = "150.00"
    pos.current_price = "155.00"
    pos.unrealized_pl = "50.00"
    return pos


class TestSync:
    def test_sync_returns_portfolio_state(self, state_manager, mock_account, mock_position):
        """syncはPortfolioStateを返す。"""
        client = state_manager._get_client()
        client.get_account.return_value = mock_account
        client.get_all_positions.return_value = [mock_position]

        result = state_manager.sync()

        assert isinstance(result, PortfolioState)
        assert result.equity == 100000.0
        assert result.cash == 50000.0
        assert result.buying_power == 100000.0
        assert "AAPL" in result.positions
        assert result.positions["AAPL"].qty == 10.0

    def test_sync_empty_positions(self, state_manager, mock_account):
        """ポジションなしの場合。"""
        client = state_manager._get_client()
        client.get_account.return_value = mock_account
        client.get_all_positions.return_value = []

        result = state_manager.sync()

        assert len(result.positions) == 0
        assert result.equity == 100000.0

    def test_sync_calculates_hwm(self, state_manager, in_memory_db, mock_account):
        """HWMをdaily_snapshotsから算出する。"""
        # 前日のスナップショットを挿入（HWM=110000）
        in_memory_db.execute(
            """INSERT INTO daily_snapshots (date, total_equity, cash, positions_value,
               high_water_mark, open_positions)
               VALUES ('2024-01-01', 110000, 50000, 60000, 110000, 2)"""
        )
        in_memory_db.commit()

        client = state_manager._get_client()
        client.get_account.return_value = mock_account
        client.get_all_positions.return_value = []

        result = state_manager.sync()

        # 前日HWM(110000) > 現在equity(100000) → HWM=110000
        assert result.high_water_mark == 110000.0
        assert result.drawdown_pct > 0

    def test_sync_daily_pnl_pct(self, state_manager, in_memory_db, mock_account):
        """日次PnL%を算出する。"""
        in_memory_db.execute(
            """INSERT INTO daily_snapshots (date, total_equity, cash, positions_value,
               open_positions)
               VALUES ('2024-01-01', 95000, 50000, 45000, 2)"""
        )
        in_memory_db.commit()

        client = state_manager._get_client()
        client.get_account.return_value = mock_account
        client.get_all_positions.return_value = []

        result = state_manager.sync()

        # (100000 - 95000) / 95000 * 100 ≈ 5.26%
        assert abs(result.daily_pnl_pct - 5.263) < 0.1


class TestReconcile:
    def test_reconcile_no_issues(self, state_manager):
        """差異なしの場合。"""
        client = state_manager._get_client()
        client.get_all_positions.return_value = []

        issues = state_manager.reconcile()
        assert issues == []

    def test_reconcile_added_missing(self, state_manager, mock_position):
        """Alpacaにあるが、DBにないポジション。"""
        client = state_manager._get_client()
        client.get_all_positions.return_value = [mock_position]

        issues = state_manager.reconcile()

        assert len(issues) == 1
        assert "ADDED_MISSING" in issues[0]
        assert "AAPL" in issues[0]

    def test_reconcile_closed_missing(self, state_manager, in_memory_db):
        """DBにあるが、Alpacaにないポジション。"""
        in_memory_db.execute(
            """INSERT INTO positions (symbol, qty, entry_price, entry_date, status, sector)
               VALUES ('AAPL', 10, 150.0, '2024-01-01', 'open', 'Technology')"""
        )
        in_memory_db.commit()

        client = state_manager._get_client()
        client.get_all_positions.return_value = []

        issues = state_manager.reconcile()

        assert len(issues) == 1
        assert "CLOSED_MISSING" in issues[0]

    def test_reconcile_auto_fix_under_threshold(self, state_manager, in_memory_db):
        """3件未満なら自動修正。"""
        in_memory_db.execute(
            """INSERT INTO positions (symbol, qty, entry_price, entry_date, status, sector)
               VALUES ('AAPL', 10, 150.0, '2024-01-01', 'open', 'Technology')"""
        )
        in_memory_db.commit()

        client = state_manager._get_client()
        client.get_all_positions.return_value = []

        state_manager.reconcile()

        # 自動修正: closedに更新されるはず
        row = in_memory_db.execute("SELECT status FROM positions WHERE symbol = 'AAPL'").fetchone()
        assert row["status"] == "closed"

    def test_reconcile_no_auto_fix_over_threshold(self, state_manager, in_memory_db):
        """3件以上なら自動修正しない。"""
        for symbol in ["AAPL", "MSFT", "GOOGL"]:
            in_memory_db.execute(
                f"""INSERT INTO positions (symbol, qty, entry_price, entry_date, status, sector)
                   VALUES ('{symbol}', 10, 150.0, '2024-01-01', 'open', 'Technology')"""
            )
        in_memory_db.commit()

        client = state_manager._get_client()
        client.get_all_positions.return_value = []

        issues = state_manager.reconcile()

        assert len(issues) == 3
        # 自動修正されていない
        row = in_memory_db.execute("SELECT status FROM positions WHERE symbol = 'AAPL'").fetchone()
        assert row["status"] == "open"

    def test_reconcile_api_inconsistency(self, state_manager):
        """2回のAPI呼び出しが不一致の場合、中断。"""
        pos1 = MagicMock()
        pos1.symbol = "AAPL"
        pos1.qty = "10"

        pos2 = MagicMock()
        pos2.symbol = "AAPL"
        pos2.qty = "15"

        client = state_manager._get_client()
        client.get_all_positions.side_effect = [[pos1], [pos2]]

        issues = state_manager.reconcile()

        assert len(issues) == 1
        assert "API_INCONSISTENT" in issues[0]

    def test_reconcile_qty_mismatch(self, state_manager, in_memory_db):
        """数量不一致の検出。"""
        in_memory_db.execute(
            """INSERT INTO positions (symbol, qty, entry_price, entry_date, status, sector)
               VALUES ('AAPL', 5, 150.0, '2024-01-01', 'open', 'Technology')"""
        )
        in_memory_db.commit()

        pos = MagicMock()
        pos.symbol = "AAPL"
        pos.qty = "10"

        client = state_manager._get_client()
        client.get_all_positions.return_value = [pos]

        issues = state_manager.reconcile()

        assert len(issues) == 1
        assert "QTY_MISMATCH" in issues[0]


class TestPositionCRUD:
    def test_open_position(self, state_manager, in_memory_db):
        """ポジションをオープンする。"""
        decision = TradingDecision(
            symbol="AAPL",
            action=Action.BUY,
            confidence=85,
            entry_price=150.0,
            stop_loss=145.0,
            take_profit=165.0,
            reasoning_bull="Strong earnings",
            reasoning_bear="Valuation concern",
            catalyst="Q4 earnings",
        )
        order_result = OrderResult(
            symbol="AAPL",
            success=True,
            alpaca_order_id="order-123",
            client_order_id="exec_AAPL_buy",
            filled_qty=10,
            filled_price=150.50,
        )

        pos_id = state_manager.open_position(decision, order_result)

        assert pos_id > 0
        row = in_memory_db.execute("SELECT * FROM positions WHERE id = ?", (pos_id,)).fetchone()
        assert row["symbol"] == "AAPL"
        assert row["qty"] == 10
        assert row["entry_price"] == 150.50
        assert row["status"] == "open"

    def test_close_position(self, state_manager, in_memory_db):
        """ポジションをクローズする。"""
        in_memory_db.execute(
            """INSERT INTO positions (symbol, qty, entry_price, entry_date, status, sector)
               VALUES ('AAPL', 10, 150.0, '2024-01-01', 'open', 'Technology')"""
        )
        in_memory_db.commit()

        state_manager.close_position("AAPL", "tp", 160.0)

        row = in_memory_db.execute("SELECT * FROM positions WHERE symbol = 'AAPL'").fetchone()
        assert row["status"] == "closed"
        assert row["close_price"] == 160.0
        assert row["close_reason"] == "tp"
        assert row["pnl"] == (160.0 - 150.0) * 10

    def test_close_nonexistent_position(self, state_manager):
        """存在しないポジションのクローズ。"""
        # Should not raise, just log warning
        state_manager.close_position("ZZZZZ", "tp", 100.0)

    def test_get_open_positions(self, state_manager, in_memory_db):
        """オープンポジション取得。"""
        in_memory_db.execute(
            """INSERT INTO positions (symbol, qty, entry_price, entry_date, status, sector)
               VALUES ('AAPL', 10, 150.0, '2024-01-01', 'open', 'Technology')"""
        )
        in_memory_db.execute(
            """INSERT INTO positions (symbol, qty, entry_price, entry_date, status, sector)
               VALUES ('MSFT', 5, 300.0, '2024-01-01', 'closed', 'Technology')"""
        )
        in_memory_db.commit()

        positions = state_manager.get_open_positions()

        assert len(positions) == 1
        assert "AAPL" in positions
        assert positions["AAPL"].qty == 10.0


class TestSnapshotAndTrades:
    def test_save_daily_snapshot(self, state_manager, in_memory_db):
        """daily_snapshotを保存する。"""
        portfolio = PortfolioState(
            equity=100000.0,
            cash=50000.0,
            buying_power=100000.0,
            positions={},
            daily_pnl_pct=1.5,
            drawdown_pct=2.0,
            high_water_mark=102000.0,
        )

        state_manager.save_daily_snapshot(portfolio, "bull", 18.5)

        row = in_memory_db.execute(
            "SELECT * FROM daily_snapshots ORDER BY date DESC LIMIT 1"
        ).fetchone()
        assert row["total_equity"] == 100000.0
        assert row["macro_regime"] == "bull"
        assert row["vix_close"] == 18.5

    def test_save_daily_snapshot_upsert(self, state_manager, in_memory_db):
        """同日の2回目の保存はUPSERTになる。"""
        portfolio = PortfolioState(
            equity=100000.0,
            cash=50000.0,
            buying_power=100000.0,
            positions={},
            daily_pnl_pct=1.0,
            drawdown_pct=0.0,
        )
        state_manager.save_daily_snapshot(portfolio, "bull", 18.0)

        portfolio2 = PortfolioState(
            equity=101000.0,
            cash=49000.0,
            buying_power=98000.0,
            positions={},
            daily_pnl_pct=2.0,
            drawdown_pct=0.0,
        )
        state_manager.save_daily_snapshot(portfolio2, "range", 22.0)

        rows = in_memory_db.execute(
            "SELECT COUNT(*) FROM daily_snapshots WHERE date = ?",
            (date.today().isoformat(),),
        ).fetchone()
        assert rows[0] == 1

        row = in_memory_db.execute(
            "SELECT total_equity FROM daily_snapshots WHERE date = ?",
            (date.today().isoformat(),),
        ).fetchone()
        assert row["total_equity"] == 101000.0

    def test_record_trade(self, state_manager, in_memory_db):
        """取引を記録する。"""
        # FK制約のためにpositionを先に作成
        in_memory_db.execute(
            """INSERT INTO positions (symbol, qty, entry_price, entry_date, status, sector)
               VALUES ('AAPL', 10, 150.0, '2024-01-01', 'open', 'Technology')"""
        )
        in_memory_db.commit()
        pos_id = in_memory_db.execute("SELECT id FROM positions LIMIT 1").fetchone()["id"]

        order_result = OrderResult(
            symbol="AAPL",
            success=True,
            alpaca_order_id="order-123",
            client_order_id="exec_AAPL_buy",
            filled_qty=10,
            filled_price=150.0,
        )

        state_manager.record_trade(order_result, position_id=pos_id)

        row = in_memory_db.execute("SELECT * FROM trades WHERE symbol = 'AAPL'").fetchone()
        assert row["qty"] == 10
        assert row["price"] == 150.0
        assert row["client_order_id"] == "exec_AAPL_buy"


class TestExecutionLog:
    def test_check_execution_id_not_exists(self, state_manager):
        """存在しないexecution_id。"""
        assert state_manager.check_execution_id("nonexistent") is False

    def test_check_execution_id_exists(self, state_manager):
        """存在するexecution_id。"""
        state_manager.record_execution_log(
            execution_id="test-123",
            mode="morning",
            status="running",
            started_at="2024-01-01T09:00:00",
        )

        assert state_manager.check_execution_id("test-123") is True

    def test_record_execution_log_insert_then_update(self, state_manager, in_memory_db):
        """execution_logの挿入→更新。"""
        state_manager.record_execution_log(
            execution_id="test-123",
            mode="morning",
            status="running",
            started_at="2024-01-01T09:00:00",
        )

        state_manager.record_execution_log(
            execution_id="test-123",
            mode="morning",
            status="success",
            started_at="2024-01-01T09:00:00",
            completed_at="2024-01-01T09:05:00",
            execution_time_ms=300000,
        )

        row = in_memory_db.execute(
            "SELECT * FROM execution_logs WHERE execution_id = 'test-123'"
        ).fetchone()
        assert row["status"] == "success"
        assert row["execution_time_ms"] == 300000

    def test_get_today_entry_count(self, state_manager, in_memory_db):
        """当日エントリー数カウント。"""
        today = date.today().isoformat()
        in_memory_db.execute(
            f"""INSERT INTO positions (symbol, qty, entry_price, entry_date, status, sector)
               VALUES ('AAPL', 10, 150.0, '{today}', 'open', 'Technology')"""
        )
        in_memory_db.execute(
            f"""INSERT INTO positions (symbol, qty, entry_price, entry_date, status, sector)
               VALUES ('MSFT', 5, 300.0, '{today}', 'open', 'Technology')"""
        )
        in_memory_db.commit()

        assert state_manager.get_today_entry_count() == 2
