"""risk_manager モジュールのテスト。"""

from datetime import date

import pytest

from modules.risk_manager import AlpacaRiskManager
from modules.types import PortfolioState, PositionInfo, VixRegime


@pytest.fixture
def risk_manager(in_memory_db, sample_config):
    """テスト用RiskManager。"""
    return AlpacaRiskManager(sample_config, in_memory_db)


def _make_portfolio(
    equity: float = 100000.0,
    drawdown_pct: float = 0.0,
    positions: dict | None = None,
) -> PortfolioState:
    """テスト用PortfolioState作成。"""
    return PortfolioState(
        equity=equity,
        cash=50000.0,
        buying_power=100000.0,
        positions=positions or {},
        daily_pnl_pct=0.0,
        drawdown_pct=drawdown_pct,
        high_water_mark=equity + equity * drawdown_pct / 100,
    )


def _make_position(symbol: str = "AAPL", sector: str = "Technology") -> PositionInfo:
    """テスト用PositionInfo作成。"""
    return PositionInfo(
        symbol=symbol,
        qty=10,
        avg_entry_price=150.0,
        current_price=155.0,
        unrealized_pnl=50.0,
        sector=sector,
    )


class TestCircuitBreaker:
    def test_no_circuit_breaker(self, risk_manager):
        """ドローダウンなし→CB不発。"""
        portfolio = _make_portfolio(drawdown_pct=2.0)
        result = risk_manager.check_circuit_breaker(portfolio)

        assert result.active is False
        assert result.level == 0

    def test_level1_triggered(self, risk_manager):
        """L1: 4%→トリガー。"""
        portfolio = _make_portfolio(drawdown_pct=4.5)
        result = risk_manager.check_circuit_breaker(portfolio)

        assert result.active is True
        assert result.level == 1
        assert result.cooldown_until is not None

    def test_level2_triggered(self, risk_manager):
        """L2: 7%→トリガー。"""
        portfolio = _make_portfolio(drawdown_pct=8.0)
        result = risk_manager.check_circuit_breaker(portfolio)

        assert result.active is True
        assert result.level == 2

    def test_level3_triggered(self, risk_manager):
        """L3: 10%→トリガー。"""
        portfolio = _make_portfolio(drawdown_pct=12.0)
        result = risk_manager.check_circuit_breaker(portfolio)

        assert result.active is True
        assert result.level == 3

    def test_level4_triggered(self, risk_manager):
        """L4: 15%→無期限停止。"""
        portfolio = _make_portfolio(drawdown_pct=16.0)
        result = risk_manager.check_circuit_breaker(portfolio)

        assert result.active is True
        assert result.level == 4
        assert result.cooldown_until is None  # 無期限

    def test_boundary_exact_l1(self, risk_manager):
        """境界値: ちょうど4.0%でL1トリガー。"""
        portfolio = _make_portfolio(drawdown_pct=4.0)
        result = risk_manager.check_circuit_breaker(portfolio)

        assert result.active is True
        assert result.level == 1

    def test_boundary_just_below_l1(self, risk_manager):
        """境界値: 3.9%ではCB不発。"""
        portfolio = _make_portfolio(drawdown_pct=3.9)
        result = risk_manager.check_circuit_breaker(portfolio)

        assert result.active is False
        assert result.level == 0

    def test_cooldown_still_active(self, risk_manager, in_memory_db):
        """クールダウン中は既存CBを返す。"""
        # 直近でL1をトリガー
        in_memory_db.execute(
            """INSERT INTO circuit_breaker (level, triggered_at, drawdown_pct, reason)
               VALUES (1, datetime('now'), 4.5, 'test')"""
        )
        in_memory_db.commit()

        portfolio = _make_portfolio(drawdown_pct=2.0)  # もう回復している
        result = risk_manager.check_circuit_breaker(portfolio)

        # クールダウン中なのでまだactive
        assert result.active is True
        assert result.level == 1


class TestPositionSizing:
    def test_basic_sizing(self, risk_manager):
        """基本的なポジションサイジング。"""
        # capital=100000, risk=1.5%, entry=100, stop=95
        # risk_amount = 100000 * 0.015 = 1500
        # price_risk = 5, adjusted = 5 * 1.3 = 6.5
        # raw_shares = 1500 / 6.5 ≈ 230
        # max_position_pct=20% → max_value=20000 → max_shares=200
        # min(230, 200) = 200
        result = risk_manager.calculate_position_size(100.0, 95.0, 100000.0)
        assert result > 0
        assert result == 200  # capped by max_position_pct

    def test_max_position_pct_cap(self, risk_manager):
        """max_position_pctによる上限。"""
        # capital=100000, max_position_pct=20%, entry=10
        # max_position_value = 20000, max_shares = 2000
        # risk calc: risk=1500, price_risk=1*1.3=1.3, raw=1153
        # min(1153, 2000) = 1153
        result = risk_manager.calculate_position_size(10.0, 9.0, 100000.0)
        assert result == 1153

    def test_zero_price_risk(self, risk_manager):
        """entry == stop → 0株。"""
        result = risk_manager.calculate_position_size(100.0, 100.0, 100000.0)
        assert result == 0

    def test_small_capital(self, risk_manager):
        """少額資金。"""
        # capital=10000, risk=150, entry=50, stop=40
        # price_risk=10*1.3=13, raw=150/13≈11.5 → 11
        # max_value=2000, max_shares=40 → min(11, 40)=11
        result = risk_manager.calculate_position_size(50.0, 40.0, 10000.0)
        assert result == 11

    def test_very_tight_stop(self, risk_manager):
        """タイトなストップ→大きなポジション。"""
        # capital=100000, risk=1500, entry=100, stop=99.5
        # price_risk=0.5*1.3=0.65, raw=1500/0.65≈2307
        # max_value=20000, max_shares=200 → min(2307,200)=200
        result = risk_manager.calculate_position_size(100.0, 99.5, 100000.0)
        assert result == 200


class TestSectorExposure:
    def test_under_limit(self, risk_manager):
        """セクター上限以下→許可。"""
        portfolio = _make_portfolio(positions={"AAPL": _make_position("AAPL", "Technology")})
        assert risk_manager.validate_sector_exposure(portfolio, "MSFT", "Technology") is True

    def test_tech_limit_3(self, risk_manager):
        """Technology上限は3。"""
        positions = {
            "AAPL": _make_position("AAPL", "Technology"),
            "MSFT": _make_position("MSFT", "Technology"),
        }
        portfolio = _make_portfolio(positions=positions)
        assert risk_manager.validate_sector_exposure(portfolio, "GOOGL", "Technology") is True

    def test_tech_at_limit(self, risk_manager):
        """Technologyが3で上限到達。"""
        positions = {
            "AAPL": _make_position("AAPL", "Technology"),
            "MSFT": _make_position("MSFT", "Technology"),
            "GOOGL": _make_position("GOOGL", "Technology"),
        }
        portfolio = _make_portfolio(positions=positions)
        assert risk_manager.validate_sector_exposure(portfolio, "NVDA", "Technology") is False

    def test_non_tech_limit_2(self, risk_manager):
        """非Technology上限は2。"""
        positions = {
            "JPM": _make_position("JPM", "Financials"),
            "V": _make_position("V", "Financials"),
        }
        portfolio = _make_portfolio(positions=positions)
        assert risk_manager.validate_sector_exposure(portfolio, "MA", "Financials") is False

    def test_empty_portfolio(self, risk_manager):
        """空ポートフォリオ→許可。"""
        portfolio = _make_portfolio()
        assert risk_manager.validate_sector_exposure(portfolio, "AAPL", "Technology") is True


class TestDailyEntryLimit:
    def test_under_limit(self, risk_manager, in_memory_db):
        """上限以下→許可。"""
        assert risk_manager.check_daily_entry_limit(in_memory_db) is True

    def test_at_limit(self, risk_manager, in_memory_db):
        """上限到達→拒否。"""
        today = date.today().isoformat()
        for symbol in ["AAPL", "MSFT"]:
            in_memory_db.execute(
                f"""INSERT INTO positions (symbol, qty, entry_price, entry_date, status, sector)
                   VALUES ('{symbol}', 10, 150.0, '{today}', 'open', 'Technology')"""
            )
        in_memory_db.commit()

        assert risk_manager.check_daily_entry_limit(in_memory_db) is False


class TestCanOpenNewPosition:
    def test_all_checks_pass(self, risk_manager):
        """全チェックパス→許可。"""
        portfolio = _make_portfolio()
        can_open, reason = risk_manager.can_open_new_position(
            portfolio, "AAPL", "Technology", VixRegime.LOW
        )
        assert can_open is True
        assert reason == "OK"

    def test_circuit_breaker_blocks(self, risk_manager):
        """CB発動→拒否。"""
        portfolio = _make_portfolio(drawdown_pct=5.0)
        can_open, reason = risk_manager.can_open_new_position(
            portfolio, "AAPL", "Technology", VixRegime.LOW
        )
        assert can_open is False
        assert "Circuit breaker" in reason

    def test_vix_extreme_blocks(self, risk_manager):
        """VIX EXTREME→拒否。"""
        portfolio = _make_portfolio()
        can_open, reason = risk_manager.can_open_new_position(
            portfolio, "AAPL", "Technology", VixRegime.EXTREME
        )
        assert can_open is False
        assert "VIX regime" in reason

    def test_duplicate_position_blocks(self, risk_manager):
        """重複ポジション→拒否。"""
        portfolio = _make_portfolio(positions={"AAPL": _make_position("AAPL", "Technology")})
        can_open, reason = risk_manager.can_open_new_position(
            portfolio, "AAPL", "Technology", VixRegime.LOW
        )
        assert can_open is False
        assert "Already have" in reason

    def test_max_positions_blocks(self, risk_manager):
        """最大ポジション数→拒否（VIXはLOWでも設定上限で拒否）。"""
        positions = {f"SYM{i}": _make_position(f"SYM{i}", f"Sector{i}") for i in range(5)}
        portfolio = _make_portfolio(positions=positions)
        can_open, reason = risk_manager.can_open_new_position(
            portfolio, "NEW", "NewSector", VixRegime.LOW
        )
        assert can_open is False
        # VIX LOW allows 5 = max_concurrent_positions, so either check blocks
        assert "positions" in reason.lower()

    def test_sector_exposure_blocks(self, risk_manager):
        """セクター集中→拒否。"""
        positions = {
            "JPM": _make_position("JPM", "Financials"),
            "V": _make_position("V", "Financials"),
        }
        portfolio = _make_portfolio(positions=positions)
        can_open, reason = risk_manager.can_open_new_position(
            portfolio, "MA", "Financials", VixRegime.LOW
        )
        assert can_open is False
        assert "Sector exposure" in reason

    def test_daily_limit_blocks(self, risk_manager, in_memory_db):
        """日次エントリー制限→拒否。"""
        today = date.today().isoformat()
        for symbol in ["AAPL", "MSFT"]:
            in_memory_db.execute(
                f"""INSERT INTO positions (symbol, qty, entry_price, entry_date, status, sector)
                   VALUES ('{symbol}', 10, 150.0, '{today}', 'open', 'Technology')"""
            )
        in_memory_db.commit()

        portfolio = _make_portfolio()
        can_open, reason = risk_manager.can_open_new_position(
            portfolio, "GOOGL", "Technology", VixRegime.LOW
        )
        assert can_open is False
        assert "Daily entry" in reason

    def test_vix_elevated_limits(self, risk_manager):
        """VIX ELEVATED→3ポジション制限。"""
        positions = {f"SYM{i}": _make_position(f"SYM{i}", f"Sector{i}") for i in range(3)}
        portfolio = _make_portfolio(positions=positions)
        can_open, reason = risk_manager.can_open_new_position(
            portfolio, "NEW", "NewSector", VixRegime.ELEVATED
        )
        assert can_open is False
        assert "VIX regime" in reason
