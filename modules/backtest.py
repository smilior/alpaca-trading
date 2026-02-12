"""バックテストモジュール。

PurgedTimeSeriesSplit によるウォークフォワード検証。
コストモデル（スプレッド + スリッページ）適用済みのパフォーマンス評価を行う。
"""

import logging
import math
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger("trading_agent")


# === PurgedTimeSeriesSplit ===


@dataclass(frozen=True)
class TimeSeriesFold:
    """ウォークフォワードの1フォールド。"""

    fold_number: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int


def purged_time_series_split(
    n_samples: int,
    n_splits: int = 5,
    train_size: int = 252,
    test_size: int = 63,
    purge_days: int = 10,
    embargo_days: int = 5,
) -> list[TimeSeriesFold]:
    """PurgedTimeSeriesSplit。

    各フォールドでtrain/testを分割し、purge（漏洩防止）と
    embargo（情報漏洩防止）を適用する。Expanding window方式。

    Args:
        n_samples: データ全体の日数
        n_splits: フォールド数
        train_size: 最小トレーニング期間（日）
        test_size: テスト期間（日）
        purge_days: purge日数（最大保有期間分）
        embargo_days: embargo日数

    Returns:
        フォールドのリスト
    """
    folds = []
    gap = purge_days + embargo_days

    for i in range(n_splits):
        test_end = n_samples - (n_splits - 1 - i) * test_size
        test_start = test_end - test_size

        if test_start < 0:
            continue

        train_end = test_start - gap
        train_start = max(0, train_end - train_size - i * test_size)

        if train_end <= train_start:
            continue

        folds.append(
            TimeSeriesFold(
                fold_number=i + 1,
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
            )
        )

    return folds


# === コストモデル ===


@dataclass(frozen=True)
class CostModel:
    """取引コストモデル。"""

    spread_bps: float = 3.0  # スプレッド (basis points)
    slippage_bps: float = 2.0  # スリッページ (basis points)

    @property
    def total_cost_pct(self) -> float:
        """片道コスト%。"""
        return (self.spread_bps + self.slippage_bps) / 100

    def round_trip_cost(self, trade_value: float) -> float:
        """往復コスト（エントリー + エグジット）。"""
        return trade_value * self.total_cost_pct * 2 / 100


# === パフォーマンス指標 ===


@dataclass
class PerformanceMetrics:
    """バックテストのパフォーマンス指標。"""

    total_return_pct: float = 0.0
    annualized_return_pct: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    profit_factor: float = 0.0
    win_rate_pct: float = 0.0
    total_trades: int = 0
    trading_days: int = 0


def calculate_sharpe_ratio(
    returns: list[float],
    risk_free_rate: float = 0.0,
    annualize: bool = True,
) -> float:
    """シャープレシオを計算する。

    Args:
        returns: 日次リターンのリスト（%表記ではなく小数）
        risk_free_rate: 年間リスクフリーレート（小数）
        annualize: 年率化するか
    """
    if len(returns) < 2:
        return 0.0

    arr = np.array(returns, dtype=np.float64)
    daily_rf = risk_free_rate / 252

    excess = arr - daily_rf
    mean_excess = float(np.mean(excess))
    std = float(np.std(excess, ddof=1))

    if std == 0:
        return 0.0

    sr = mean_excess / std
    if annualize:
        sr *= math.sqrt(252)
    return sr


def calculate_sortino_ratio(
    returns: list[float],
    risk_free_rate: float = 0.0,
) -> float:
    """ソルティノレシオを計算する。"""
    if len(returns) < 2:
        return 0.0

    arr = np.array(returns, dtype=np.float64)
    daily_rf = risk_free_rate / 252

    excess = arr - daily_rf
    mean_excess = float(np.mean(excess))

    downside = arr[arr < 0]
    if len(downside) == 0:
        return float("inf") if mean_excess > 0 else 0.0

    downside_std = float(np.std(downside, ddof=1))
    if downside_std == 0:
        return 0.0

    return mean_excess / downside_std * math.sqrt(252)


def calculate_max_drawdown(equity_curve: list[float]) -> float:
    """最大ドローダウン%を計算する。"""
    if len(equity_curve) < 2:
        return 0.0

    hwm = equity_curve[0]
    max_dd = 0.0
    for eq in equity_curve:
        hwm = max(hwm, eq)
        if hwm > 0:
            dd = (hwm - eq) / hwm * 100
            max_dd = max(max_dd, dd)
    return max_dd


def calculate_profit_factor(trade_pnls: list[float]) -> float:
    """プロフィットファクター = 総利益 / 総損失。"""
    gains = sum(p for p in trade_pnls if p > 0)
    losses = abs(sum(p for p in trade_pnls if p < 0))
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return gains / losses


# === ブートストラップ信頼区間 ===


def bootstrap_sharpe_ci(
    returns: list[float],
    n_bootstrap: int = 1000,
    confidence: float = 0.95,
    seed: int = 42,
) -> tuple[float, float, float]:
    """ブートストラップ法でシャープレシオの信頼区間を推定する。

    Returns:
        (点推定, 下限, 上限)
    """
    if len(returns) < 10:
        sr = calculate_sharpe_ratio(returns)
        return sr, sr, sr

    rng = np.random.default_rng(seed)
    arr = np.array(returns, dtype=np.float64)
    n = len(arr)

    bootstrap_srs = []
    for _ in range(n_bootstrap):
        sample = rng.choice(arr, size=n, replace=True)
        sr = calculate_sharpe_ratio(sample.tolist())
        bootstrap_srs.append(sr)

    alpha = (1 - confidence) / 2
    lower = float(np.percentile(bootstrap_srs, alpha * 100))
    upper = float(np.percentile(bootstrap_srs, (1 - alpha) * 100))
    point = calculate_sharpe_ratio(returns)

    return point, lower, upper


# === メインバックテストエンジン ===


@dataclass
class BacktestTrade:
    """バックテスト内の1取引。"""

    day: int
    symbol: str
    entry_price: float
    exit_price: float
    qty: int
    pnl: float
    cost: float


@dataclass
class FoldResult:
    """1フォールドの結果。"""

    fold: TimeSeriesFold
    metrics: PerformanceMetrics
    trades: list[BacktestTrade] = field(default_factory=list)
    daily_returns: list[float] = field(default_factory=list)


@dataclass
class BacktestResult:
    """全フォールドの統合結果。"""

    folds: list[FoldResult] = field(default_factory=list)
    aggregate_metrics: PerformanceMetrics = field(default_factory=PerformanceMetrics)
    sharpe_ci: tuple[float, float, float] = (0.0, 0.0, 0.0)
    deflated_sharpe: float = 0.0
    deflation_coefficient: float = 0.7


def evaluate_returns(
    daily_returns: list[float],
    trade_pnls: list[float],
    equity_curve: list[float],
    trading_days: int,
    cost_model: CostModel | None = None,
) -> PerformanceMetrics:
    """日次リターンからパフォーマンス指標を算出する。"""
    if not daily_returns:
        return PerformanceMetrics()

    total_return = 1.0
    for r in daily_returns:
        total_return *= 1 + r
    total_return_pct = (total_return - 1) * 100

    years = trading_days / 252 if trading_days > 0 else 1.0
    annualized = (total_return ** (1 / years) - 1) * 100 if years > 0 else 0.0

    return PerformanceMetrics(
        total_return_pct=total_return_pct,
        annualized_return_pct=annualized,
        sharpe_ratio=calculate_sharpe_ratio(daily_returns),
        sortino_ratio=calculate_sortino_ratio(daily_returns),
        max_drawdown_pct=calculate_max_drawdown(equity_curve) if equity_curve else 0.0,
        profit_factor=calculate_profit_factor(trade_pnls) if trade_pnls else 0.0,
        win_rate_pct=(sum(1 for p in trade_pnls if p > 0) / len(trade_pnls) * 100)
        if trade_pnls
        else 0.0,
        total_trades=len(trade_pnls),
        trading_days=trading_days,
    )


def format_backtest_report(result: BacktestResult) -> str:
    """バックテスト結果をフォーマットする。"""
    m = result.aggregate_metrics
    sr_point, sr_low, sr_high = result.sharpe_ci

    lines = [
        "=== Backtest Report ===",
        "",
        f"Folds: {len(result.folds)}",
        f"Total Trades: {m.total_trades}",
        f"Trading Days: {m.trading_days}",
        "",
        "--- Performance ---",
        f"Total Return: {m.total_return_pct:.1f}%",
        f"Annualized Return: {m.annualized_return_pct:.1f}%",
        f"Sharpe Ratio: {m.sharpe_ratio:.2f}",
        f"  Bootstrap CI ({95}%): [{sr_low:.2f}, {sr_high:.2f}]",
        f"  Deflated SR (x{result.deflation_coefficient}): {result.deflated_sharpe:.2f}",
        f"Sortino Ratio: {m.sortino_ratio:.2f}",
        f"Max Drawdown: {m.max_drawdown_pct:.1f}%",
        f"Profit Factor: {m.profit_factor:.2f}",
        f"Win Rate: {m.win_rate_pct:.1f}%",
        "",
        "--- Per Fold ---",
    ]

    for fr in result.folds:
        fm = fr.metrics
        lines.append(
            f"  Fold {fr.fold.fold_number}: SR={fm.sharpe_ratio:.2f}, "
            f"Return={fm.total_return_pct:.1f}%, Trades={fm.total_trades}"
        )

    return "\n".join(lines)
