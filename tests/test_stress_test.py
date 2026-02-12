"""ストレステストモジュールのテスト。"""

from modules.stress_test import (
    ALL_SCENARIOS,
    COVID_CRASH,
    FLASH_CRASH,
    INFLATION_SHOCK,
    SVB_CRISIS,
    YEN_CARRY_UNWIND,
    ScenarioResult,
    format_stress_test_report,
    run_all_stress_tests,
    run_scenario,
)


class TestScenarioDefinitions:
    def test_all_scenarios_have_data(self):
        assert len(ALL_SCENARIOS) == 5
        for s in ALL_SCENARIOS:
            assert len(s.days) > 0
            assert s.name
            assert s.description

    def test_covid_crash_is_severe(self):
        """COVID-19シナリオは深刻な下落を含む。"""
        min_return = min(d.spy_return_pct for d in COVID_CRASH.days)
        assert min_return < -10  # 1日で-10%超の下落がある
        max_vix = max(d.vix for d in COVID_CRASH.days)
        assert max_vix >= 80


class TestRunScenario:
    def test_covid_triggers_circuit_breaker(self):
        result = run_scenario(COVID_CRASH)
        assert result.max_drawdown_pct > 4.0  # 少なくともL1は発動
        assert len(result.circuit_breaker_triggers) > 0
        assert result.final_equity < result.initial_equity

    def test_flash_crash_limited_damage(self):
        """フラッシュクラッシュは短期ショックなのでDD < 20%"""
        result = run_scenario(FLASH_CRASH)
        assert result.max_drawdown_pct < 20.0
        assert result.passed is True

    def test_svb_crisis_moderate(self):
        result = run_scenario(SVB_CRISIS)
        assert result.max_drawdown_pct < 20.0

    def test_yen_carry_v_recovery(self):
        result = run_scenario(YEN_CARRY_UNWIND)
        assert len(result.daily_equity) == len(YEN_CARRY_UNWIND.days)

    def test_inflation_shock_gradual(self):
        """茹でガエルパターンでもCBは発動する。"""
        result = run_scenario(INFLATION_SHOCK)
        assert result.max_drawdown_pct > 3.0

    def test_custom_thresholds(self):
        """カスタム閾値でCB発動タイミングが変わる。"""
        tight = {1: 1.0, 2: 2.0, 3: 3.0, 4: 5.0}
        result = run_scenario(SVB_CRISIS, cb_thresholds=tight)
        # タイトな閾値ならCBが早期発動する
        assert len(result.circuit_breaker_triggers) > 0

    def test_zero_exposure_no_loss(self):
        """エクスポージャー0%なら損失なし。"""
        result = run_scenario(COVID_CRASH, position_exposure_pct=0.0)
        assert result.max_drawdown_pct == 0.0
        assert result.final_equity == result.initial_equity

    def test_daily_equity_tracked(self):
        result = run_scenario(FLASH_CRASH)
        assert len(result.daily_equity) == len(FLASH_CRASH.days)


class TestScenarioResult:
    def test_total_return_pct(self):
        r = ScenarioResult(
            scenario_name="test",
            initial_equity=100_000,
            final_equity=110_000,
        )
        assert abs(r.total_return_pct - 10.0) < 0.01

    def test_passed_under_threshold(self):
        r = ScenarioResult(scenario_name="test", max_drawdown_pct=15.0)
        assert r.passed is True

    def test_failed_over_threshold(self):
        r = ScenarioResult(scenario_name="test", max_drawdown_pct=25.0)
        assert r.passed is False


class TestRunAllStressTests:
    def test_returns_five_results(self):
        results = run_all_stress_tests()
        assert len(results) == 5


class TestFormatReport:
    def test_report_format(self):
        results = run_all_stress_tests()
        report = format_stress_test_report(results)
        assert "Stress Test Report" in report
        assert "COVID" in report
        assert "Max DD:" in report
