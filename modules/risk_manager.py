"""リスク管理モジュール。

4段階サーキットブレーカー、ポジションサイジング、
セクター集中チェック、日次エントリー制限を担う。
"""

import logging
import math
import sqlite3
from datetime import date, datetime, timedelta

from modules.config import AppConfig
from modules.macro import max_positions_for_vix
from modules.types import CircuitBreakerState, PortfolioState, VixRegime

logger = logging.getLogger("trading_agent")

# クールダウン期間（営業日ベースだが簡易的にカレンダー日で管理）
_COOLDOWN_HOURS: dict[int, int | None] = {
    1: 48,  # L1: 48時間
    2: 72,  # L2: 3営業日 ≈ 72時間
    3: 168,  # L3: 7日
    4: None,  # L4: 無期限（手動解除のみ）
}


class AlpacaRiskManager:
    """RiskChecker Protocol の実装。"""

    def __init__(self, config: AppConfig, conn: sqlite3.Connection) -> None:
        self._config = config
        self._conn = conn

    def check_circuit_breaker(self, portfolio: PortfolioState) -> CircuitBreakerState:
        """4段階CB (4%/7%/10%/15%)、クールダウン期間管理。"""
        dd = portfolio.drawdown_pct
        risk = self._config.risk

        thresholds = [
            (4, risk.circuit_breaker_level4_pct),
            (3, risk.circuit_breaker_level3_pct),
            (2, risk.circuit_breaker_level2_pct),
            (1, risk.circuit_breaker_level1_pct),
        ]

        # 現在のドローダウンに基づくレベル判定
        current_level = 0
        for level, threshold in thresholds:
            if dd >= threshold:
                current_level = level
                break

        # 既存のアクティブCBをチェック
        active_cb = self._get_active_cb()
        if active_cb is not None and active_cb["cooldown_until"] is not None:
            cooldown_date = date.fromisoformat(active_cb["cooldown_until"])
            if date.today() < cooldown_date:
                return CircuitBreakerState(
                    active=True,
                    level=active_cb["level"],
                    drawdown_pct=dd,
                    cooldown_until=cooldown_date,
                )
            # クールダウン期間終了 → 解除
            self._resolve_cb(active_cb["id"])

        if current_level == 0:
            return CircuitBreakerState(active=False, level=0, drawdown_pct=dd, cooldown_until=None)

        # 新しいCBをトリガー
        cooldown_until = self._calculate_cooldown(current_level)
        self._record_cb(current_level, dd, cooldown_until)

        logger.warning(
            f"Circuit breaker L{current_level} triggered: "
            f"drawdown={dd:.1f}%, cooldown_until={cooldown_until}"
        )

        return CircuitBreakerState(
            active=True,
            level=current_level,
            drawdown_pct=dd,
            cooldown_until=cooldown_until,
        )

    def calculate_position_size(self, entry: float, stop: float, capital: float) -> int:
        """リスク額 = capital × 1.5% / (entry-stop) × slippage、max_position_pct上限。"""
        risk = self._config.risk
        risk_per_trade = capital * risk.max_risk_per_trade_pct / 100

        price_risk = abs(entry - stop)
        if price_risk <= 0:
            logger.warning("Price risk is zero or negative, returning 0 shares")
            return 0

        adjusted_risk = price_risk * risk.slippage_factor
        raw_shares = risk_per_trade / adjusted_risk

        # max_position_pctによる上限
        max_position_value = capital * risk.max_position_pct / 100
        max_shares_by_value = max_position_value / entry if entry > 0 else 0

        shares = min(raw_shares, max_shares_by_value)
        result = max(0, math.floor(shares))

        logger.debug(
            f"Position size: entry={entry}, stop={stop}, capital={capital}, "
            f"risk_amount={risk_per_trade:.2f}, shares={result}"
        )
        return result

    def validate_sector_exposure(
        self, portfolio: PortfolioState, new_symbol: str, new_sector: str
    ) -> bool:
        """セクター集中チェック（上限2、Tech=3）。"""
        max_per_sector = 2
        if new_sector == "Technology":
            max_per_sector = 3

        sector_count = 0
        for pos in portfolio.positions.values():
            if pos.sector == new_sector:
                sector_count += 1

        if sector_count >= max_per_sector:
            logger.info(
                f"Sector exposure limit reached: {new_sector} has "
                f"{sector_count}/{max_per_sector} positions"
            )
            return False
        return True

    def check_daily_entry_limit(self, conn: sqlite3.Connection) -> bool:
        """当日エントリー数 < max_daily_entries。"""
        today = date.today().isoformat()
        row = conn.execute(
            "SELECT COUNT(*) FROM positions WHERE entry_date = ?",
            (today,),
        ).fetchone()
        count = row[0] if row else 0
        limit = self._config.strategy.max_daily_entries
        if count >= limit:
            logger.info(f"Daily entry limit reached: {count}/{limit}")
            return False
        return True

    def can_open_new_position(
        self,
        portfolio: PortfolioState,
        symbol: str,
        sector: str,
        vix_regime: VixRegime,
    ) -> tuple[bool, str]:
        """全リスクチェック統合。"""
        # 1. サーキットブレーカー
        cb = self.check_circuit_breaker(portfolio)
        if cb.active:
            return False, f"Circuit breaker L{cb.level} active (DD={cb.drawdown_pct:.1f}%)"

        # 2. VIXレジームによるポジション数制限
        max_pos = max_positions_for_vix(vix_regime)
        current_pos = len(portfolio.positions)
        if current_pos >= max_pos:
            return False, (
                f"VIX regime {vix_regime.value}: max {max_pos} positions, current {current_pos}"
            )

        # 3. 最大同時ポジション数
        config_max = self._config.strategy.max_concurrent_positions
        if current_pos >= config_max:
            return False, f"Max concurrent positions reached: {current_pos}/{config_max}"

        # 4. 重複ポジション
        if symbol in portfolio.positions:
            return False, f"Already have open position in {symbol}"

        # 5. セクター集中
        if not self.validate_sector_exposure(portfolio, symbol, sector):
            return False, f"Sector exposure limit for {sector}"

        # 6. 日次エントリー制限
        if not self.check_daily_entry_limit(self._conn):
            return False, "Daily entry limit reached"

        return True, "OK"

    # === Internal Helpers ===

    def _get_active_cb(self) -> dict | None:
        """未解除のサーキットブレーカーを取得。"""
        row = self._conn.execute(
            """SELECT id, level, triggered_at, drawdown_pct
               FROM circuit_breaker
               WHERE resolved_at IS NULL
               ORDER BY triggered_at DESC LIMIT 1"""
        ).fetchone()
        if row is None:
            return None

        level = row["level"]
        cooldown_hours = _COOLDOWN_HOURS.get(level)
        triggered_at = datetime.fromisoformat(row["triggered_at"])

        cooldown_until: str | None = None
        if cooldown_hours is not None:
            cooldown_until = (triggered_at + timedelta(hours=cooldown_hours)).date().isoformat()

        return {
            "id": row["id"],
            "level": level,
            "drawdown_pct": row["drawdown_pct"],
            "cooldown_until": cooldown_until,
        }

    def _resolve_cb(self, cb_id: int) -> None:
        """サーキットブレーカーを解除する。"""
        self._conn.execute(
            "UPDATE circuit_breaker SET resolved_at = datetime('now') WHERE id = ?",
            (cb_id,),
        )
        self._conn.commit()
        logger.info(f"Circuit breaker {cb_id} resolved")

    def _calculate_cooldown(self, level: int) -> date | None:
        """クールダウン終了日を計算する。"""
        hours = _COOLDOWN_HOURS.get(level)
        if hours is None:
            return None  # L4は無期限
        return (datetime.now() + timedelta(hours=hours)).date()

    def _record_cb(self, level: int, drawdown_pct: float, cooldown_until: date | None) -> None:
        """サーキットブレーカーをDBに記録する。"""
        reason = f"Drawdown {drawdown_pct:.1f}% exceeded L{level} threshold"
        self._conn.execute(
            """INSERT INTO circuit_breaker (level, triggered_at, drawdown_pct, reason)
               VALUES (?, datetime('now'), ?, ?)""",
            (level, drawdown_pct, reason),
        )
        self._conn.commit()
