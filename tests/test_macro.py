"""modules/macro.py のテスト。"""

from modules.macro import (
    RegimeTracker,
    classify_spy_regime,
    classify_vix_regime,
    determine_macro_regime,
    max_positions_for_vix,
)
from modules.types import MacroRegime, VixRegime


class TestClassifySpyRegime:
    def test_bull(self) -> None:
        assert classify_spy_regime(410.0, 400.0) == MacroRegime.BULL

    def test_bear(self) -> None:
        assert classify_spy_regime(390.0, 400.0) == MacroRegime.BEAR

    def test_range(self) -> None:
        assert classify_spy_regime(401.0, 400.0) == MacroRegime.RANGE

    def test_zero_ma(self) -> None:
        assert classify_spy_regime(400.0, 0.0) == MacroRegime.RANGE


class TestClassifyVixRegime:
    def test_low(self) -> None:
        assert classify_vix_regime(15.0) == VixRegime.LOW

    def test_elevated(self) -> None:
        assert classify_vix_regime(25.0) == VixRegime.ELEVATED

    def test_extreme(self) -> None:
        assert classify_vix_regime(35.0) == VixRegime.EXTREME

    def test_boundary_elevated(self) -> None:
        assert classify_vix_regime(20.0) == VixRegime.ELEVATED

    def test_boundary_extreme(self) -> None:
        assert classify_vix_regime(30.0) == VixRegime.EXTREME


class TestDetermineMacroRegime:
    def test_bull_consensus(self) -> None:
        # SPY above MA200 + VIX low
        result = determine_macro_regime(spy_close=410.0, spy_ma200=400.0, vix=12.0)
        assert result == MacroRegime.BULL

    def test_bear_consensus(self) -> None:
        # SPY below MA200 + VIX extreme
        result = determine_macro_regime(spy_close=380.0, spy_ma200=400.0, vix=35.0)
        assert result == MacroRegime.BEAR

    def test_disagreement_range(self) -> None:
        # SPY above MA200 but VIX extreme
        result = determine_macro_regime(spy_close=410.0, spy_ma200=400.0, vix=35.0)
        assert result == MacroRegime.RANGE

    def test_neutral_range(self) -> None:
        # SPY near MA200 + moderate VIX
        result = determine_macro_regime(spy_close=401.0, spy_ma200=400.0, vix=18.0)
        assert result == MacroRegime.RANGE


class TestMaxPositionsForVix:
    def test_low(self) -> None:
        assert max_positions_for_vix(VixRegime.LOW) == 5

    def test_elevated(self) -> None:
        assert max_positions_for_vix(VixRegime.ELEVATED) == 3

    def test_extreme(self) -> None:
        assert max_positions_for_vix(VixRegime.EXTREME) == 0


class TestRegimeTracker:
    def test_initial_state(self) -> None:
        tracker = RegimeTracker()
        assert tracker.confirmed_regime == MacroRegime.RANGE

    def test_3_day_confirmation(self) -> None:
        tracker = RegimeTracker(consecutive_days=3)
        tracker.update(MacroRegime.BULL)
        assert tracker.confirmed_regime == MacroRegime.RANGE  # not confirmed yet
        tracker.update(MacroRegime.BULL)
        assert tracker.confirmed_regime == MacroRegime.RANGE  # still not
        tracker.update(MacroRegime.BULL)
        assert tracker.confirmed_regime == MacroRegime.BULL  # confirmed!

    def test_interruption_resets(self) -> None:
        tracker = RegimeTracker(consecutive_days=3)
        tracker.update(MacroRegime.BULL)
        tracker.update(MacroRegime.BULL)
        tracker.update(MacroRegime.RANGE)  # interruption
        assert tracker.confirmed_regime == MacroRegime.RANGE  # not BULL

    def test_transition(self) -> None:
        tracker = RegimeTracker(consecutive_days=3)
        # Confirm BULL
        for _ in range(3):
            tracker.update(MacroRegime.BULL)
        assert tracker.confirmed_regime == MacroRegime.BULL
        # Transition to BEAR
        for _ in range(3):
            tracker.update(MacroRegime.BEAR)
        assert tracker.confirmed_regime == MacroRegime.BEAR
