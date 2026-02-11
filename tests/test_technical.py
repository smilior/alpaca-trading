"""modules/technical.py のテスト。"""

import numpy as np
import pandas as pd
import pytest

from modules.technical import (
    build_bar_data,
    calc_atr,
    calc_rsi,
    calc_sma,
    calc_volume_ratio,
    check_entry_filters,
)
from modules.types import BarData


class TestCalcSma:
    def test_basic(self) -> None:
        closes = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
        sma = calc_sma(closes, 3)
        assert sma.iloc[-1] == pytest.approx(40.0)  # (30+40+50)/3
        assert pd.isna(sma.iloc[0])  # not enough data

    def test_period_equals_length(self) -> None:
        closes = pd.Series([1.0, 2.0, 3.0])
        sma = calc_sma(closes, 3)
        assert sma.iloc[-1] == pytest.approx(2.0)


class TestCalcRsi:
    def test_all_gains(self) -> None:
        # 連続上昇 -> RSI は 100 に近い
        closes = pd.Series(list(range(1, 20)), dtype=float)
        rsi = calc_rsi(closes, 14)
        assert rsi.iloc[-1] > 90

    def test_all_losses(self) -> None:
        # 連続下落 -> RSI は 0 に近い
        closes = pd.Series(list(range(20, 1, -1)), dtype=float)
        rsi = calc_rsi(closes, 14)
        assert rsi.iloc[-1] < 10

    def test_mixed(self) -> None:
        np.random.seed(42)
        closes = pd.Series(100 + np.cumsum(np.random.randn(50)))
        rsi = calc_rsi(closes, 14)
        last_rsi = rsi.iloc[-1]
        assert 0 <= last_rsi <= 100


class TestCalcAtr:
    def test_basic(self) -> None:
        n = 30
        highs = pd.Series([110.0] * n)
        lows = pd.Series([90.0] * n)
        closes = pd.Series([100.0] * n)
        atr = calc_atr(highs, lows, closes, 14)
        # TR = high - low = 20 for all, so ATR should be 20
        assert atr.iloc[-1] == pytest.approx(20.0)


class TestCalcVolumeRatio:
    def test_basic(self) -> None:
        volumes = pd.Series([100] * 20 + [200])
        ratio = calc_volume_ratio(volumes, 20)
        # avg over last 20 = 100 (excluding last), ratio = 200/105 approx
        # actually rolling includes the current, so avg = (100*19+200)/20 = 105
        assert ratio.iloc[-1] > 1.0

    def test_constant_volume(self) -> None:
        volumes = pd.Series([100.0] * 25)
        ratio = calc_volume_ratio(volumes, 20)
        assert ratio.iloc[-1] == pytest.approx(1.0)


class TestBuildBarData:
    def _make_df(self, n: int = 60) -> pd.DataFrame:
        np.random.seed(42)
        close = 100 + np.cumsum(np.random.randn(n) * 0.5)
        high = close + np.abs(np.random.randn(n))
        low = close - np.abs(np.random.randn(n))
        volume = np.random.randint(100000, 500000, n)
        dates = pd.date_range("2026-01-01", periods=n, freq="B")
        return pd.DataFrame(
            {"open": close, "high": high, "low": low, "close": close, "volume": volume},
            index=dates,
        )

    def test_returns_bar_data(self) -> None:
        df = self._make_df(60)
        bar = build_bar_data("AAPL", df)
        assert bar is not None
        assert isinstance(bar, BarData)
        assert bar.symbol == "AAPL"
        assert bar.close > 0
        assert 0 <= bar.rsi_14 <= 100

    def test_insufficient_data(self) -> None:
        df = self._make_df(60).iloc[:10]
        bar = build_bar_data("AAPL", df)
        assert bar is None

    def test_custom_periods(self) -> None:
        df = self._make_df(100)
        bar = build_bar_data("MSFT", df, ma_period=20, rsi_period=7)
        assert bar is not None
        assert bar.symbol == "MSFT"


class TestCheckEntryFilters:
    def test_all_pass(self) -> None:
        bar = BarData(
            symbol="AAPL",
            close=155.0,
            volume=1000000,
            ma_50=150.0,  # close > ma_50
            rsi_14=55.0,  # between 30-70
            atr_14=3.0,
            volume_ratio_20d=1.2,
        )
        passed, failed = check_entry_filters(bar)
        assert passed is True
        assert failed == []

    def test_price_below_ma(self) -> None:
        bar = BarData(
            symbol="AAPL",
            close=145.0,
            volume=1000000,
            ma_50=150.0,  # close < ma_50
            rsi_14=55.0,
            atr_14=3.0,
            volume_ratio_20d=1.2,
        )
        passed, failed = check_entry_filters(bar)
        assert passed is False
        assert "price_below_ma50" in failed

    def test_rsi_overbought(self) -> None:
        bar = BarData(
            symbol="AAPL",
            close=155.0,
            volume=1000000,
            ma_50=150.0,
            rsi_14=75.0,  # > 70
            atr_14=3.0,
            volume_ratio_20d=1.2,
        )
        passed, failed = check_entry_filters(bar)
        assert passed is False
        assert "rsi_overbought" in failed

    def test_rsi_oversold(self) -> None:
        bar = BarData(
            symbol="AAPL",
            close=155.0,
            volume=1000000,
            ma_50=150.0,
            rsi_14=25.0,  # < 30
            atr_14=3.0,
            volume_ratio_20d=1.2,
        )
        passed, failed = check_entry_filters(bar)
        assert passed is False
        assert "rsi_oversold" in failed

    def test_multiple_failures(self) -> None:
        bar = BarData(
            symbol="AAPL",
            close=145.0,
            volume=1000000,
            ma_50=150.0,
            rsi_14=75.0,
            atr_14=3.0,
            volume_ratio_20d=1.2,
        )
        passed, failed = check_entry_filters(bar)
        assert passed is False
        assert len(failed) == 2
