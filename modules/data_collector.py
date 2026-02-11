"""市場データ収集モジュール。

Alpaca Market Data API + yfinance でOHLCVを取得し、
テクニカル指標を計算してBarDataを返す。
"""

import logging
import os
from datetime import datetime, timedelta

import pandas as pd
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestBarRequest
from alpaca.data.timeframe import TimeFrame

from modules.config import AppConfig
from modules.technical import build_bar_data
from modules.types import BarData

logger = logging.getLogger("trading_agent")


def _get_data_client() -> StockHistoricalDataClient:
    """Alpaca Market Data クライアントを取得する。"""
    api_key = os.environ.get("ALPACA_API_KEY", "")
    secret_key = os.environ.get("ALPACA_SECRET_KEY", "")
    return StockHistoricalDataClient(api_key=api_key, secret_key=secret_key)


def fetch_bars_alpaca(
    symbols: list[str],
    days: int = 100,
    client: StockHistoricalDataClient | None = None,
) -> dict[str, pd.DataFrame]:
    """Alpaca APIからバーデータを取得する。

    Args:
        symbols: 銘柄シンボルのリスト
        days: 取得する営業日数（テクニカル計算に十分な期間）
        client: Alpacaクライアント（テスト用注入）

    Returns:
        {symbol: DataFrame(open, high, low, close, volume)}
    """
    if client is None:
        client = _get_data_client()

    # カレンダー日数で余裕を持って取得（営業日 ≈ カレンダー日 * 5/7 + バッファ）
    calendar_days = int(days * 7 / 5) + 10
    start = datetime.now() - timedelta(days=calendar_days)

    request = StockBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=TimeFrame.Day,
        start=start,
    )

    bars = client.get_stock_bars(request)
    result: dict[str, pd.DataFrame] = {}

    for symbol in symbols:
        try:
            if hasattr(bars, "data"):
                symbol_bars = bars.data.get(symbol, [])
            else:
                symbol_bars = bars.get(symbol, [])
            if not symbol_bars:
                logger.warning(f"No bar data for {symbol}")
                continue

            records = []
            for bar in symbol_bars:
                records.append(
                    {
                        "timestamp": bar.timestamp,
                        "open": float(bar.open),
                        "high": float(bar.high),
                        "low": float(bar.low),
                        "close": float(bar.close),
                        "volume": int(bar.volume),
                    }
                )

            df = pd.DataFrame(records)
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.set_index("timestamp").sort_index()
            result[symbol] = df
        except Exception:
            logger.exception(f"Error processing bars for {symbol}")

    return result


def collect_market_data(
    symbols: list[str],
    config: AppConfig | None = None,
    client: StockHistoricalDataClient | None = None,
) -> dict[str, BarData]:
    """銘柄リストの市場データを収集し、テクニカル指標付きBarDataを返す。

    Args:
        symbols: 銘柄シンボルのリスト
        config: AppConfig（テクニカル指標パラメータ用）
        client: Alpacaクライアント（テスト用注入）

    Returns:
        {symbol: BarData}
    """
    if config is None:
        config = AppConfig()

    ma_period = config.strategy.ma_period
    rsi_period = config.strategy.rsi_period
    atr_period = config.macro.atr_period
    volume_period = config.strategy.volume_compare_period

    # テクニカル計算に十分なデータ量を確保
    required_days = max(ma_period, rsi_period, atr_period, volume_period) + 20
    bars_data = fetch_bars_alpaca(symbols, days=required_days, client=client)

    result: dict[str, BarData] = {}
    for symbol, df in bars_data.items():
        bar = build_bar_data(
            symbol=symbol,
            df=df,
            ma_period=ma_period,
            rsi_period=rsi_period,
            atr_period=atr_period,
            volume_period=volume_period,
        )
        if bar is not None:
            result[symbol] = bar
        else:
            logger.warning(f"Insufficient data to compute indicators for {symbol}")

    logger.info(f"Collected market data for {len(result)}/{len(symbols)} symbols")
    return result


def fetch_latest_price(
    symbol: str,
    client: StockHistoricalDataClient | None = None,
) -> float | None:
    """最新の終値を取得する。"""
    if client is None:
        client = _get_data_client()
    try:
        request = StockLatestBarRequest(symbol_or_symbols=[symbol])
        bars = client.get_stock_latest_bar(request)
        bar = bars.get(symbol)
        if bar:
            return float(bar.close)
    except Exception:
        logger.exception(f"Error fetching latest price for {symbol}")
    return None
