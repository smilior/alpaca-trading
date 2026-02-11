"""modules/data_collector.py のテスト。

Alpaca APIはモックし、データ変換ロジックをテストする。
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from modules.data_collector import (
    collect_market_data,
    fetch_bars_alpaca,
    fetch_latest_price,
)
from modules.types import BarData


def _make_bar(timestamp, o, h, lo, c, v):
    """Alpaca Bar風オブジェクトを返す。"""
    return SimpleNamespace(timestamp=timestamp, open=o, high=h, low=lo, close=c, volume=v)


def _make_bars_response(symbol_data: dict):
    """Alpaca get_stock_bars レスポンスのモック。"""
    resp = MagicMock()
    resp.data = symbol_data
    return resp


class TestFetchBarsAlpaca:
    def test_returns_dataframe(self) -> None:
        ts = [datetime(2026, 1, i + 1) for i in range(5)]
        bars_list = [_make_bar(t, 100, 105, 95, 102, 1000000) for t in ts]
        mock_client = MagicMock()
        mock_client.get_stock_bars.return_value = _make_bars_response({"AAPL": bars_list})

        result = fetch_bars_alpaca(["AAPL"], days=10, client=mock_client)
        assert "AAPL" in result
        df = result["AAPL"]
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 5
        assert list(df.columns) == ["open", "high", "low", "close", "volume"]

    def test_missing_symbol_skipped(self) -> None:
        mock_client = MagicMock()
        mock_client.get_stock_bars.return_value = _make_bars_response({"AAPL": []})

        result = fetch_bars_alpaca(["AAPL", "MSFT"], days=10, client=mock_client)
        assert "MSFT" not in result

    def test_empty_response(self) -> None:
        mock_client = MagicMock()
        mock_client.get_stock_bars.return_value = _make_bars_response({})

        result = fetch_bars_alpaca(["AAPL"], days=10, client=mock_client)
        assert result == {}

    def test_no_data_attribute_fallback(self) -> None:
        """bars.data が無い場合の dict フォールバック。"""
        ts = [datetime(2026, 1, i + 1) for i in range(3)]
        bars_list = [_make_bar(t, 100, 105, 95, 102, 500000) for t in ts]
        mock_resp = MagicMock(spec=[])  # no .data attribute
        mock_resp.get = MagicMock(return_value=bars_list)

        mock_client = MagicMock()
        mock_client.get_stock_bars.return_value = mock_resp

        result = fetch_bars_alpaca(["AAPL"], days=10, client=mock_client)
        assert "AAPL" in result
        assert len(result["AAPL"]) == 3

    def test_exception_in_processing(self) -> None:
        """バー処理中の例外はスキップされる。"""
        bad_bar = SimpleNamespace(timestamp=datetime(2026, 1, 1))
        # open属性がないのでfloat(bar.open)でエラー

        mock_client = MagicMock()
        mock_client.get_stock_bars.return_value = _make_bars_response({"AAPL": [bad_bar]})

        result = fetch_bars_alpaca(["AAPL"], days=10, client=mock_client)
        assert "AAPL" not in result


class TestCollectMarketData:
    def test_returns_bar_data(self) -> None:
        """十分なデータがある場合、BarDataを返す。"""
        import numpy as np

        n = 70
        np.random.seed(42)
        close = 100 + np.cumsum(np.random.randn(n) * 0.5)
        ts = [datetime(2026, 1, 1) + pd.Timedelta(days=i) for i in range(n)]
        bars_list = [
            _make_bar(ts[i], close[i], close[i] + 1, close[i] - 1, close[i], 100000)
            for i in range(n)
        ]

        mock_client = MagicMock()
        mock_client.get_stock_bars.return_value = _make_bars_response({"AAPL": bars_list})

        result = collect_market_data(["AAPL"], client=mock_client)
        assert "AAPL" in result
        assert isinstance(result["AAPL"], BarData)

    def test_insufficient_data_excluded(self) -> None:
        """データ不足の銘柄は除外される。"""
        ts = [datetime(2026, 1, i + 1) for i in range(5)]
        bars_list = [_make_bar(t, 100, 105, 95, 102, 100000) for t in ts]

        mock_client = MagicMock()
        mock_client.get_stock_bars.return_value = _make_bars_response({"AAPL": bars_list})

        result = collect_market_data(["AAPL"], client=mock_client)
        assert "AAPL" not in result


class TestFetchLatestPrice:
    def test_returns_price(self) -> None:
        mock_bar = SimpleNamespace(close=185.50)
        mock_client = MagicMock()
        mock_client.get_stock_latest_bar.return_value = {"AAPL": mock_bar}

        price = fetch_latest_price("AAPL", client=mock_client)
        assert price == pytest.approx(185.50)

    def test_no_data_returns_none(self) -> None:
        mock_client = MagicMock()
        mock_client.get_stock_latest_bar.return_value = {}

        price = fetch_latest_price("AAPL", client=mock_client)
        assert price is None

    def test_exception_returns_none(self) -> None:
        mock_client = MagicMock()
        mock_client.get_stock_latest_bar.side_effect = Exception("API error")

        price = fetch_latest_price("AAPL", client=mock_client)
        assert price is None
