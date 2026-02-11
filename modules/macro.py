"""マクロレジーム判定（2変数MVPモデル）。

S&P500 vs 200日MA + VIX の2変数でブル/ベア/レンジを判定する。
ヒステリシス: 確定には3営業日連続で同一判定を要求。
"""

from collections import deque

from modules.types import MacroRegime, VixRegime


def classify_spy_regime(spy_close: float, spy_ma200: float) -> MacroRegime:
    """SPY vs 200日MAでレジームを判定する。

    Args:
        spy_close: SPYの終値
        spy_ma200: SPYの200日移動平均

    Returns:
        MacroRegime
    """
    if spy_ma200 <= 0:
        return MacroRegime.RANGE

    ratio = spy_close / spy_ma200
    if ratio > 1.02:  # 200日MAを2%以上上回る
        return MacroRegime.BULL
    elif ratio < 0.98:  # 200日MAを2%以上下回る
        return MacroRegime.BEAR
    else:
        return MacroRegime.RANGE


def classify_vix_regime(
    vix: float,
    threshold_elevated: float = 20.0,
    threshold_extreme: float = 30.0,
) -> VixRegime:
    """VIXレベルでレジームを判定する。

    Args:
        vix: VIX指数の値
        threshold_elevated: 警戒閾値
        threshold_extreme: 極端閾値

    Returns:
        VixRegime
    """
    if vix >= threshold_extreme:
        return VixRegime.EXTREME
    elif vix >= threshold_elevated:
        return VixRegime.ELEVATED
    else:
        return VixRegime.LOW


def determine_macro_regime(spy_close: float, spy_ma200: float, vix: float) -> MacroRegime:
    """2変数でマクロレジームを判定する。

    判定ルール:
    - 2変数が同一方向ならその判定
    - 不一致ならレンジ

    Args:
        spy_close: SPYの終値
        spy_ma200: SPYの200日移動平均
        vix: VIX指数の値

    Returns:
        MacroRegime
    """
    spy_regime = classify_spy_regime(spy_close, spy_ma200)

    # VIXが極端 -> ベア寄り
    if vix >= 30:
        vix_signal = MacroRegime.BEAR
    elif vix <= 15:
        vix_signal = MacroRegime.BULL
    else:
        vix_signal = MacroRegime.RANGE

    # 2変数が一致 -> その判定
    if spy_regime == vix_signal:
        return spy_regime

    # 不一致 -> レンジ
    return MacroRegime.RANGE


def max_positions_for_vix(vix_regime: VixRegime) -> int:
    """VIXレジームに応じた最大ポジション数を返す。

    Args:
        vix_regime: VixRegime

    Returns:
        最大ポジション数
    """
    match vix_regime:
        case VixRegime.LOW:
            return 5
        case VixRegime.ELEVATED:
            return 3
        case VixRegime.EXTREME:
            return 0  # 新規エントリー禁止


class RegimeTracker:
    """ヒステリシス付きレジームトラッカー。

    確定には3営業日連続で同一判定を要求する。
    """

    def __init__(self, consecutive_days: int = 3) -> None:
        self._consecutive_days = consecutive_days
        self._history: deque[MacroRegime] = deque(maxlen=consecutive_days)
        self._confirmed: MacroRegime = MacroRegime.RANGE

    @property
    def confirmed_regime(self) -> MacroRegime:
        """確定済みレジームを返す。"""
        return self._confirmed

    def update(self, regime: MacroRegime) -> MacroRegime:
        """新しいレジーム判定を追加し、確定レジームを更新する。

        Args:
            regime: 当日のレジーム判定

        Returns:
            確定済みレジーム
        """
        self._history.append(regime)

        # 3日連続で同一判定なら確定
        if len(self._history) >= self._consecutive_days and len(set(self._history)) == 1:
            self._confirmed = regime

        return self._confirmed
