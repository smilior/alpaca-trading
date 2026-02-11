"""テクニカルフィルター実装。

50日MA, RSI(14), 出来高比率(20日), ATR(14) を計算し、
エントリー条件のフィルタリングを行う。
"""

import numpy as np
import pandas as pd

from modules.types import BarData


def calc_sma(closes: pd.Series, period: int) -> pd.Series:
    """単純移動平均を計算する。"""
    return closes.rolling(window=period, min_periods=period).mean()


def calc_rsi(closes: pd.Series, period: int = 14) -> pd.Series:
    """RSI (Relative Strength Index) を計算する。"""
    delta = closes.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)

    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()

    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def calc_atr(highs: pd.Series, lows: pd.Series, closes: pd.Series, period: int = 14) -> pd.Series:
    """ATR (Average True Range) を計算する。"""
    prev_close = closes.shift(1)
    tr1 = highs - lows
    tr2 = (highs - prev_close).abs()
    tr3 = (lows - prev_close).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return true_range.rolling(window=period, min_periods=period).mean()


def calc_volume_ratio(volumes: pd.Series, period: int = 20) -> pd.Series:
    """出来高比率（当日出来高 / 過去N日平均出来高）を計算する。"""
    avg_volume = volumes.rolling(window=period, min_periods=period).mean()
    return volumes / avg_volume.replace(0, np.inf)


def build_bar_data(
    symbol: str,
    df: pd.DataFrame,
    ma_period: int = 50,
    rsi_period: int = 14,
    atr_period: int = 14,
    volume_period: int = 20,
) -> BarData | None:
    """OHLCVデータフレームから最新のBarDataを構築する。

    Args:
        symbol: 銘柄シンボル
        df: カラム ['close', 'high', 'low', 'volume'] を持つDataFrame
        ma_period: 移動平均期間
        rsi_period: RSI期間
        atr_period: ATR期間
        volume_period: 出来高比較期間

    Returns:
        最新のBarData。データ不足の場合はNone。
    """
    if len(df) < max(ma_period, rsi_period, atr_period, volume_period) + 1:
        return None

    ma = calc_sma(df["close"], ma_period)
    rsi = calc_rsi(df["close"], rsi_period)
    atr = calc_atr(df["high"], df["low"], df["close"], atr_period)
    vol_ratio = calc_volume_ratio(df["volume"], volume_period)

    # 最新行
    latest_ma = ma.iloc[-1]
    latest_rsi = rsi.iloc[-1]
    latest_atr = atr.iloc[-1]
    latest_vol = vol_ratio.iloc[-1]

    if any(pd.isna(v) for v in [latest_ma, latest_rsi, latest_atr, latest_vol]):
        return None

    return BarData(
        symbol=symbol,
        close=float(df["close"].iloc[-1]),
        volume=int(df["volume"].iloc[-1]),
        ma_50=float(latest_ma),
        rsi_14=float(latest_rsi),
        atr_14=float(latest_atr),
        volume_ratio_20d=float(latest_vol),
        timestamp=df.index[-1] if hasattr(df.index[-1], "isoformat") else None,
    )


def check_entry_filters(
    bar: BarData,
    rsi_lower: int = 30,
    rsi_upper: int = 70,
) -> tuple[bool, list[str]]:
    """エントリーフィルターを適用する。

    Args:
        bar: BarData
        rsi_lower: RSI下限（これ以下は売られすぎ）
        rsi_upper: RSI上限（これ以上は買われすぎ）

    Returns:
        (全フィルター通過, 失敗したフィルター名のリスト)
    """
    failed: list[str] = []

    # フィルター1: 株価がMA50より上
    if bar.close <= bar.ma_50:
        failed.append("price_below_ma50")

    # フィルター2: RSIが過熱圏でない
    if bar.rsi_14 >= rsi_upper:
        failed.append("rsi_overbought")

    # フィルター3: RSIが売られすぎでない（ロングの場合）
    if bar.rsi_14 <= rsi_lower:
        failed.append("rsi_oversold")

    return len(failed) == 0, failed
