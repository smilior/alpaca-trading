"""バックテストモジュールのテスト。"""

import numpy as np

from modules.backtest import (
    BacktestResult,
    CostModel,
    FoldResult,
    PerformanceMetrics,
    TimeSeriesFold,
    bootstrap_sharpe_ci,
    calculate_max_drawdown,
    calculate_profit_factor,
    calculate_sharpe_ratio,
    calculate_sortino_ratio,
    evaluate_returns,
    format_backtest_report,
    purged_time_series_split,
)


class TestPurgedTimeSeriesSplit:
    def test_basic_split(self):
        """基本的な分割。"""
        folds = purged_time_series_split(
            n_samples=600,
            n_splits=3,
            train_size=252,
            test_size=63,
            purge_days=10,
            embargo_days=5,
        )
        assert len(folds) > 0
        for f in folds:
            # purge + embargo が守られている
            assert f.test_start >= f.train_end + 15

    def test_five_folds(self):
        folds = purged_time_series_split(n_samples=1000, n_splits=5)
        assert len(folds) == 5
        for i, f in enumerate(folds):
            assert f.fold_number == i + 1

    def test_no_overlap(self):
        """train と test が重複しない。"""
        folds = purged_time_series_split(n_samples=800, n_splits=3)
        for f in folds:
            assert f.train_end < f.test_start

    def test_insufficient_data(self):
        """データが少なすぎると空リスト。"""
        folds = purged_time_series_split(n_samples=50, n_splits=5, train_size=252)
        assert len(folds) == 0

    def test_expanding_window(self):
        """後のフォールドほどトレーニング期間が広がる（expanding）。"""
        folds = purged_time_series_split(n_samples=1000, n_splits=3)
        if len(folds) >= 2:
            train_sizes = [f.train_end - f.train_start for f in folds]
            assert train_sizes[-1] >= train_sizes[0]


class TestCostModel:
    def test_total_cost_pct(self):
        model = CostModel(spread_bps=3.0, slippage_bps=2.0)
        assert abs(model.total_cost_pct - 0.05) < 0.001

    def test_round_trip_cost(self):
        model = CostModel(spread_bps=3.0, slippage_bps=2.0)
        cost = model.round_trip_cost(10_000)
        # 10,000 * 0.05% * 2 = 10
        assert abs(cost - 10.0) < 0.1


class TestSharpeRatio:
    def test_positive_returns(self):
        """一定の正のリターン → 高いSR。"""
        returns = [0.001] * 252  # 毎日+0.1%
        sr = calculate_sharpe_ratio(returns)
        assert sr > 2.0

    def test_zero_returns(self):
        returns = [0.0] * 100
        sr = calculate_sharpe_ratio(returns)
        assert sr == 0.0

    def test_volatile_returns(self):
        """高ボラティリティ → 低いSR。"""
        returns = [0.05, -0.05] * 126  # 大きな振れ
        sr = calculate_sharpe_ratio(returns)
        assert abs(sr) < 1.0

    def test_few_samples(self):
        sr = calculate_sharpe_ratio([0.01])
        assert sr == 0.0


class TestSortinoRatio:
    def test_all_positive(self):
        """全て正のリターン → inf or 非常に高い。"""
        returns = [0.001] * 100
        sr = calculate_sortino_ratio(returns)
        assert sr == float("inf") or sr > 10

    def test_mixed_returns(self):
        returns = [0.01, -0.005, 0.008, -0.003, 0.012] * 50
        sr = calculate_sortino_ratio(returns)
        assert sr > 0


class TestMaxDrawdown:
    def test_no_drawdown(self):
        dd = calculate_max_drawdown([100, 101, 102, 103])
        assert dd == 0.0

    def test_simple_drawdown(self):
        dd = calculate_max_drawdown([100, 110, 90, 95])
        # HWM=110, lowest=90 → DD=(110-90)/110=18.18%
        assert abs(dd - 18.18) < 0.1

    def test_single_point(self):
        dd = calculate_max_drawdown([100])
        assert dd == 0.0


class TestProfitFactor:
    def test_all_profits(self):
        pf = calculate_profit_factor([100, 50, 200])
        assert pf == float("inf")

    def test_all_losses(self):
        pf = calculate_profit_factor([-100, -50])
        assert pf == 0.0

    def test_mixed(self):
        pf = calculate_profit_factor([100, -50, 200, -30])
        # gains=300, losses=80 → PF=3.75
        assert abs(pf - 3.75) < 0.01


class TestBootstrapSharpeCi:
    def test_returns_three_values(self):
        returns = list(np.random.default_rng(42).normal(0.001, 0.01, 252))
        point, lower, upper = bootstrap_sharpe_ci(returns)
        assert lower <= point <= upper

    def test_ci_positive_for_good_returns(self):
        returns = list(np.random.default_rng(42).normal(0.002, 0.005, 252))
        _, lower, _ = bootstrap_sharpe_ci(returns)
        assert lower > 0  # 良いリターンなら下限もプラス

    def test_few_samples(self):
        point, lower, upper = bootstrap_sharpe_ci([0.01, 0.02])
        assert point == lower == upper


class TestEvaluateReturns:
    def test_basic_evaluation(self):
        returns = [0.001] * 252
        equity = [100_000 * (1.001**i) for i in range(253)]
        pnls = [100, -50, 80, -30, 120]

        metrics = evaluate_returns(returns, pnls, equity, 252)
        assert metrics.total_return_pct > 0
        assert metrics.sharpe_ratio > 0
        assert metrics.total_trades == 5
        assert metrics.win_rate_pct == 60.0

    def test_empty_returns(self):
        metrics = evaluate_returns([], [], [], 0)
        assert metrics.total_return_pct == 0.0
        assert metrics.sharpe_ratio == 0.0


class TestFormatReport:
    def test_report_contains_key_info(self):
        fold = TimeSeriesFold(1, 0, 252, 267, 330)
        fold_result = FoldResult(
            fold=fold,
            metrics=PerformanceMetrics(sharpe_ratio=1.2, total_return_pct=15.0, total_trades=50),
        )
        result = BacktestResult(
            folds=[fold_result],
            aggregate_metrics=PerformanceMetrics(
                total_return_pct=15.0,
                annualized_return_pct=15.0,
                sharpe_ratio=1.2,
                sortino_ratio=1.5,
                max_drawdown_pct=8.0,
                profit_factor=2.1,
                win_rate_pct=58.0,
                total_trades=50,
                trading_days=252,
            ),
            sharpe_ci=(1.2, 0.5, 1.9),
            deflated_sharpe=0.84,
        )
        report = format_backtest_report(result)
        assert "Backtest Report" in report
        assert "Sharpe Ratio: 1.20" in report
        assert "Deflated SR" in report
        assert "Fold 1" in report
