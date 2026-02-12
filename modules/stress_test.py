"""ストレステストモジュール。

5つのヒストリカルシナリオで回路ブレーカーとリスク管理の動作を検証する。
各シナリオの日次リターン系列をシミュレーションし、ドローダウンと
回路ブレーカー発動を記録する。
"""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("trading_agent")


@dataclass(frozen=True)
class ScenarioDay:
    """シナリオの1日分のデータ。"""

    day: int
    spy_return_pct: float
    vix: float


@dataclass(frozen=True)
class Scenario:
    """ストレステストシナリオ定義。"""

    name: str
    description: str
    days: list[ScenarioDay]


@dataclass
class ScenarioResult:
    """シナリオの実行結果。"""

    scenario_name: str
    initial_equity: float = 100_000.0
    max_drawdown_pct: float = 0.0
    final_equity: float = 0.0
    circuit_breaker_triggers: list[dict[str, object]] = field(default_factory=list)
    daily_equity: list[float] = field(default_factory=list)

    @property
    def total_return_pct(self) -> float:
        if self.initial_equity <= 0:
            return 0.0
        return (self.final_equity - self.initial_equity) / self.initial_equity * 100

    @property
    def passed(self) -> bool:
        """ストレステスト合格: max DD < 20%。"""
        return self.max_drawdown_pct < 20.0


# === 5つのヒストリカルシナリオ定義 ===

# 1. COVID-19 クラッシュ (2020-03): S&P500 -33.9%, VIX 14->82
COVID_CRASH = Scenario(
    name="COVID-19 Crash (2020-03)",
    description="S&P500 -33.9% in 23 trading days, VIX spiked to 82",
    days=[
        ScenarioDay(1, -3.4, 40),
        ScenarioDay(2, -4.9, 54),
        ScenarioDay(3, 4.6, 47),
        ScenarioDay(4, -2.8, 50),
        ScenarioDay(5, -7.6, 58),
        ScenarioDay(6, 9.4, 54),
        ScenarioDay(7, -5.2, 62),
        ScenarioDay(8, -9.5, 75),
        ScenarioDay(9, 6.0, 66),
        ScenarioDay(10, -4.3, 72),
        ScenarioDay(11, -12.0, 82),
        ScenarioDay(12, 9.3, 70),
        ScenarioDay(13, -3.4, 65),
        ScenarioDay(14, -5.2, 68),
        ScenarioDay(15, 0.5, 61),
        ScenarioDay(16, -4.3, 63),
        ScenarioDay(17, 6.2, 55),
        ScenarioDay(18, -3.4, 58),
        ScenarioDay(19, 2.3, 50),
        ScenarioDay(20, 1.2, 46),
    ],
)

# 2. インフレショック (2022 H1): S&P500 -23.6%, 「茹でガエル」パターン
INFLATION_SHOCK = Scenario(
    name="Inflation Shock (2022-H1)",
    description="S&P500 -23.6% over 6 months, gradual grind down",
    days=[
        ScenarioDay(1, -1.1, 22),
        ScenarioDay(2, -0.8, 23),
        ScenarioDay(3, 0.5, 22),
        ScenarioDay(4, -1.5, 25),
        ScenarioDay(5, -0.3, 24),
        ScenarioDay(6, -1.2, 26),
        ScenarioDay(7, 0.8, 25),
        ScenarioDay(8, -1.0, 27),
        ScenarioDay(9, -0.6, 28),
        ScenarioDay(10, -1.8, 30),
        ScenarioDay(11, 1.2, 28),
        ScenarioDay(12, -0.9, 29),
        ScenarioDay(13, -1.4, 31),
        ScenarioDay(14, 0.3, 30),
        ScenarioDay(15, -2.1, 33),
        ScenarioDay(16, -0.7, 32),
        ScenarioDay(17, 1.5, 30),
        ScenarioDay(18, -1.3, 31),
        ScenarioDay(19, -0.8, 32),
        ScenarioDay(20, -1.6, 34),
    ],
)

# 3. SVB危機 (2023-03): セクター固有ショック
SVB_CRISIS = Scenario(
    name="SVB Crisis (2023-03)",
    description="Sector-specific shock: Financials -15%, broader market -5%",
    days=[
        ScenarioDay(1, -1.8, 22),
        ScenarioDay(2, -4.6, 30),
        ScenarioDay(3, -1.5, 28),
        ScenarioDay(4, 1.6, 26),
        ScenarioDay(5, 2.3, 24),
        ScenarioDay(6, -0.7, 23),
        ScenarioDay(7, 1.4, 22),
        ScenarioDay(8, -1.1, 24),
        ScenarioDay(9, 0.9, 22),
        ScenarioDay(10, 1.8, 20),
    ],
)

# 4. 円キャリーアンワインド (2024-08): VIX 16->65, V字回復
YEN_CARRY_UNWIND = Scenario(
    name="Yen Carry Unwind (2024-08)",
    description="VIX spike 16->65, V-shaped recovery in 5 days",
    days=[
        ScenarioDay(1, -1.4, 23),
        ScenarioDay(2, -3.0, 38),
        ScenarioDay(3, -4.2, 65),
        ScenarioDay(4, 2.3, 35),
        ScenarioDay(5, 2.1, 27),
        ScenarioDay(6, 1.0, 23),
        ScenarioDay(7, 0.5, 20),
        ScenarioDay(8, 1.2, 18),
        ScenarioDay(9, -0.3, 17),
        ScenarioDay(10, 0.8, 16),
    ],
)

# 5. フラッシュクラッシュ (2010-05): 流動性枯渇
FLASH_CRASH = Scenario(
    name="Flash Crash (2010-05)",
    description="Intraday -9%, recovered most by close, -3.2% on the day",
    days=[
        ScenarioDay(1, -3.2, 40),
        ScenarioDay(2, 1.1, 32),
        ScenarioDay(3, -1.4, 28),
        ScenarioDay(4, 2.6, 24),
        ScenarioDay(5, 0.5, 22),
        ScenarioDay(6, -0.8, 24),
        ScenarioDay(7, 1.2, 22),
        ScenarioDay(8, -0.3, 21),
        ScenarioDay(9, 0.7, 20),
        ScenarioDay(10, 0.4, 19),
    ],
)

ALL_SCENARIOS = [COVID_CRASH, INFLATION_SHOCK, SVB_CRISIS, YEN_CARRY_UNWIND, FLASH_CRASH]


def _simulate_cb_levels(drawdown_pct: float, thresholds: dict[int, float]) -> int:
    """ドローダウンから回路ブレーカーレベルを判定する。"""
    for level in (4, 3, 2, 1):
        if drawdown_pct >= thresholds[level]:
            return level
    return 0


def run_scenario(
    scenario: Scenario,
    initial_equity: float = 100_000.0,
    position_exposure_pct: float = 80.0,
    cb_thresholds: dict[int, float] | None = None,
) -> ScenarioResult:
    """1シナリオを実行する。

    ポートフォリオがposition_exposure_pctの市場エクスポージャーを持つと仮定し、
    日次リターンを適用。CBがトリガーされたらエクスポージャーを削減する。

    Args:
        scenario: シナリオ定義
        initial_equity: 初期資金
        position_exposure_pct: 株式エクスポージャー%
        cb_thresholds: CBレベル別ドローダウン閾値 (default: 4/7/10/15%)
    """
    if cb_thresholds is None:
        cb_thresholds = {1: 4.0, 2: 7.0, 3: 10.0, 4: 15.0}

    result = ScenarioResult(
        scenario_name=scenario.name,
        initial_equity=initial_equity,
    )

    equity = initial_equity
    hwm = initial_equity
    exposure = position_exposure_pct / 100.0
    cb_active = False

    for day in scenario.days:
        # CB発動中はエクスポージャーを段階的に削減
        if cb_active:
            exposure = min(exposure, 0.3)  # 最大30%に制限

        # 日次リターン適用
        market_return = day.spy_return_pct / 100.0
        portfolio_return = market_return * exposure
        equity *= 1 + portfolio_return

        result.daily_equity.append(equity)

        # HWM更新 + ドローダウン計算
        hwm = max(hwm, equity)
        drawdown_pct = (hwm - equity) / hwm * 100 if hwm > 0 else 0.0
        result.max_drawdown_pct = max(result.max_drawdown_pct, drawdown_pct)

        # CBレベル判定
        cb_level = _simulate_cb_levels(drawdown_pct, cb_thresholds)
        if cb_level > 0 and not cb_active:
            cb_active = True
            result.circuit_breaker_triggers.append(
                {
                    "day": day.day,
                    "level": cb_level,
                    "drawdown_pct": round(drawdown_pct, 2),
                    "vix": day.vix,
                }
            )
            logger.info(
                f"[{scenario.name}] Day {day.day}: CB L{cb_level} triggered "
                f"(DD={drawdown_pct:.1f}%, VIX={day.vix})"
            )

            # L3以上: 全ポジションクローズ
            if cb_level >= 3:
                exposure = 0.0

    result.final_equity = equity
    return result


def run_all_stress_tests(
    initial_equity: float = 100_000.0,
    cb_thresholds: dict[int, float] | None = None,
) -> list[ScenarioResult]:
    """全5シナリオを実行する。"""
    results = []
    for scenario in ALL_SCENARIOS:
        result = run_scenario(scenario, initial_equity, cb_thresholds=cb_thresholds)
        results.append(result)

    return results


def format_stress_test_report(results: list[ScenarioResult]) -> str:
    """結果をフォーマットする。"""
    lines = ["=== Stress Test Report ===", ""]

    all_passed = all(r.passed for r in results)
    lines.append(f"Overall: {'PASS' if all_passed else 'FAIL'}")
    lines.append(f"Scenarios: {sum(1 for r in results if r.passed)}/{len(results)} passed")
    lines.append("")

    for r in results:
        status = "PASS" if r.passed else "FAIL"
        lines.append(f"[{status}] {r.scenario_name}")
        lines.append(f"  Max DD: {r.max_drawdown_pct:.1f}%")
        lines.append(f"  Return: {r.total_return_pct:.1f}%")
        lines.append(f"  Final:  ${r.final_equity:,.0f}")
        if r.circuit_breaker_triggers:
            for t in r.circuit_breaker_triggers:
                lines.append(
                    f"  CB L{t['level']} Day {t['day']}: DD={t['drawdown_pct']}%, VIX={t['vix']}"
                )
        lines.append("")

    return "\n".join(lines)
