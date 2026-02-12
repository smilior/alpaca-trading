"""ポートフォリオ状態管理モジュール。

Alpaca API + SQLite DB の橋渡し。
口座同期、リコンシリエーション、ポジションCRUDを担う。
"""

import contextlib
import logging
import os
import sqlite3
from datetime import date, datetime

from modules.config import AppConfig
from modules.types import (
    OrderResult,
    PortfolioState,
    PositionInfo,
    TradingDecision,
)
from modules.universe import get_sector

logger = logging.getLogger("trading_agent")


def _get_trading_client():  # type: ignore[no-untyped-def]
    """Alpaca Trading クライアントを取得する。"""
    from alpaca.trading.client import TradingClient

    api_key = os.environ.get("ALPACA_API_KEY", "")
    secret_key = os.environ.get("ALPACA_SECRET_KEY", "")
    paper = os.environ.get("ALPACA_PAPER", "true").lower() == "true"
    return TradingClient(api_key=api_key, secret_key=secret_key, paper=paper)


class AlpacaStateManager:
    """StateManager Protocol の実装。"""

    def __init__(
        self,
        config: AppConfig,
        conn: sqlite3.Connection,
        trading_client: object | None = None,
    ) -> None:
        self._config = config
        self._conn = conn
        self._client = trading_client

    def _get_client(self) -> object:
        if self._client is None:
            self._client = _get_trading_client()
        return self._client

    # === Core Protocol Methods ===

    def sync(self) -> PortfolioState:
        """Alpaca口座+ポジション取得、daily_snapshotsからHWM/DD算出。"""
        client = self._get_client()
        account = client.get_account()  # type: ignore[union-attr]
        alpaca_positions = client.get_all_positions()  # type: ignore[union-attr]

        equity = float(account.equity)  # type: ignore[union-attr]
        cash = float(account.cash)  # type: ignore[union-attr]
        buying_power = float(account.buying_power)  # type: ignore[union-attr]

        positions: dict[str, PositionInfo] = {}
        for pos in alpaca_positions:
            symbol = pos.symbol
            positions[symbol] = PositionInfo(
                symbol=symbol,
                qty=float(pos.qty),
                avg_entry_price=float(pos.avg_entry_price),
                current_price=float(pos.current_price),
                unrealized_pnl=float(pos.unrealized_pl),
                sector=get_sector(symbol),
            )

        # HWMとドローダウンをdaily_snapshotsから算出
        high_water_mark = self._get_high_water_mark(equity)
        drawdown_pct = (
            ((high_water_mark - equity) / high_water_mark * 100) if high_water_mark > 0 else 0.0
        )

        # 日次PnL%を算出
        daily_pnl_pct = self._get_daily_pnl_pct(equity)

        return PortfolioState(
            equity=equity,
            cash=cash,
            buying_power=buying_power,
            positions=positions,
            daily_pnl_pct=daily_pnl_pct,
            drawdown_pct=drawdown_pct,
            high_water_mark=high_water_mark,
        )

    def reconcile(self) -> list[str]:
        """2回API呼び出し→DB比較→3件未満なら自動修正→reconciliation_logsに記録。"""
        client = self._get_client()
        issues: list[str] = []

        # 2回API呼び出しで確認
        alpaca_positions_1 = {
            p.symbol: float(p.qty)
            for p in client.get_all_positions()  # type: ignore[union-attr]
        }
        alpaca_positions_2 = {
            p.symbol: float(p.qty)
            for p in client.get_all_positions()  # type: ignore[union-attr]
        }

        # 2回の結果が一致しなければ中断
        if alpaca_positions_1 != alpaca_positions_2:
            issues.append("API_INCONSISTENT: Two API calls returned different results")
            logger.warning("Reconciliation aborted: API results inconsistent")
            return issues

        alpaca_positions = alpaca_positions_1
        db_positions = self.get_open_positions()

        discrepancies: list[dict[str, str]] = []

        # Alpacaにあるが、DBにない
        for symbol, qty in alpaca_positions.items():
            if symbol not in db_positions:
                discrepancies.append(
                    {
                        "issue_type": "ADDED_MISSING",
                        "symbol": symbol,
                        "details": f"In Alpaca (qty={qty}) but missing from DB",
                    }
                )

        # DBにあるが、Alpacaにない
        for symbol in db_positions:
            if symbol not in alpaca_positions:
                discrepancies.append(
                    {
                        "issue_type": "CLOSED_MISSING",
                        "symbol": symbol,
                        "details": "In DB but missing from Alpaca",
                    }
                )

        # 数量不一致
        for symbol in set(alpaca_positions) & set(db_positions):
            alpaca_qty = alpaca_positions[symbol]
            db_qty = db_positions[symbol].qty
            if abs(alpaca_qty - db_qty) > 0.001:
                discrepancies.append(
                    {
                        "issue_type": "QTY_MISMATCH",
                        "symbol": symbol,
                        "details": f"Alpaca qty={alpaca_qty}, DB qty={db_qty}",
                    }
                )

        # 3件未満なら自動修正
        auto_fix = len(discrepancies) < 3

        execution_id = f"reconcile_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        for d in discrepancies:
            issue_msg = f"{d['issue_type']}: {d['symbol']} - {d['details']}"
            issues.append(issue_msg)
            logger.warning(f"Reconciliation issue: {issue_msg}")

            if auto_fix:
                self._auto_fix(d, alpaca_positions)

            self._conn.execute(
                """INSERT INTO reconciliation_logs
                   (execution_id, issue_type, symbol, details, auto_fixed)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    execution_id,
                    d["issue_type"],
                    d["symbol"],
                    d["details"],
                    1 if auto_fix else 0,
                ),
            )

        self._conn.commit()

        if discrepancies and not auto_fix:
            logger.error(
                f"Reconciliation found {len(discrepancies)} issues "
                "(>= 3, manual intervention required)"
            )

        return issues

    # === Position CRUD ===

    def open_position(self, decision: TradingDecision, order_result: OrderResult) -> int:
        """positionsテーブルにINSERT。"""
        cursor = self._conn.execute(
            """INSERT INTO positions
               (symbol, side, qty, entry_price, entry_date, stop_loss, take_profit,
                strategy_reason, sentiment_score, status, alpaca_order_id, sector)
               VALUES (?, 'long', ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)""",
            (
                decision.symbol,
                order_result.filled_qty,
                order_result.filled_price or decision.entry_price,
                date.today().isoformat(),
                decision.stop_loss,
                decision.take_profit,
                decision.catalyst,
                decision.confidence,
                order_result.alpaca_order_id,
                get_sector(decision.symbol),
            ),
        )
        self._conn.commit()
        position_id = cursor.lastrowid
        logger.info(
            f"Opened position {position_id}: {decision.symbol} "
            f"qty={order_result.filled_qty} @ {order_result.filled_price}"
        )
        return position_id if position_id is not None else 0

    def close_position(self, symbol: str, reason: str, close_price: float) -> None:
        """positions UPDATE (status=closed, pnl計算)。"""
        row = self._conn.execute(
            "SELECT id, entry_price, qty FROM positions WHERE symbol = ? AND status = 'open'",
            (symbol,),
        ).fetchone()
        if row is None:
            logger.warning(f"No open position found for {symbol}")
            return

        position_id = row["id"]
        entry_price = row["entry_price"]
        qty = row["qty"]
        pnl = (close_price - entry_price) * qty

        self._conn.execute(
            """UPDATE positions
               SET status = 'closed', close_price = ?, close_date = ?,
                   close_reason = ?, pnl = ?, updated_at = datetime('now')
               WHERE id = ?""",
            (close_price, date.today().isoformat(), reason, pnl, position_id),
        )
        self._conn.commit()
        logger.info(f"Closed position {position_id}: {symbol} reason={reason} pnl={pnl:.2f}")

    def get_open_positions(self) -> dict[str, PositionInfo]:
        """positions WHERE status='open'。"""
        rows = self._conn.execute(
            """SELECT symbol, qty, entry_price, stop_loss, sector, entry_date
               FROM positions WHERE status = 'open'"""
        ).fetchall()

        positions: dict[str, PositionInfo] = {}
        for row in rows:
            symbol = row["symbol"]
            entry_date_val = None
            if row["entry_date"]:
                with contextlib.suppress(ValueError):
                    entry_date_val = date.fromisoformat(row["entry_date"])
            positions[symbol] = PositionInfo(
                symbol=symbol,
                qty=float(row["qty"]),
                avg_entry_price=float(row["entry_price"]),
                current_price=float(row["entry_price"]),  # DB only; live price from sync
                unrealized_pnl=0.0,
                sector=row["sector"] or get_sector(symbol),
                entry_date=entry_date_val,
            )
        return positions

    # === Snapshot & Trade Recording ===

    def save_daily_snapshot(
        self,
        portfolio: PortfolioState,
        macro_regime: str,
        vix: float,
    ) -> None:
        """daily_snapshots INSERT/UPSERT。"""
        today = date.today().isoformat()
        self._conn.execute(
            """INSERT INTO daily_snapshots
               (date, total_equity, cash, positions_value, daily_pnl_pct,
                drawdown_pct, high_water_mark, open_positions, macro_regime, vix_close)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(date) DO UPDATE SET
                   total_equity = excluded.total_equity,
                   cash = excluded.cash,
                   positions_value = excluded.positions_value,
                   daily_pnl_pct = excluded.daily_pnl_pct,
                   drawdown_pct = excluded.drawdown_pct,
                   high_water_mark = excluded.high_water_mark,
                   open_positions = excluded.open_positions,
                   macro_regime = excluded.macro_regime,
                   vix_close = excluded.vix_close""",
            (
                today,
                portfolio.equity,
                portfolio.cash,
                portfolio.equity - portfolio.cash,
                portfolio.daily_pnl_pct,
                portfolio.drawdown_pct,
                portfolio.high_water_mark,
                len(portfolio.positions),
                macro_regime,
                vix,
            ),
        )
        self._conn.commit()
        logger.info(f"Saved daily snapshot for {today}")

    def record_trade(self, order_result: OrderResult, position_id: int) -> None:
        """trades INSERT。"""
        side = "buy" if order_result.filled_qty > 0 else "sell"
        self._conn.execute(
            """INSERT INTO trades
               (position_id, symbol, side, qty, price, order_type,
                alpaca_order_id, client_order_id, fill_status, executed_at)
               VALUES (?, ?, ?, ?, ?, 'limit', ?, ?, 'filled', datetime('now'))""",
            (
                position_id,
                order_result.symbol,
                side,
                abs(order_result.filled_qty),
                order_result.filled_price or 0,
                order_result.alpaca_order_id,
                order_result.client_order_id,
            ),
        )
        self._conn.commit()

    # === Execution Log ===

    def check_execution_id(self, execution_id: str) -> bool:
        """execution_logs重複チェック。Trueなら既に存在する。"""
        row = self._conn.execute(
            "SELECT 1 FROM execution_logs WHERE execution_id = ?",
            (execution_id,),
        ).fetchone()
        return row is not None

    def record_execution_log(
        self,
        execution_id: str,
        mode: str,
        status: str,
        started_at: str,
        completed_at: str | None = None,
        decisions_json: str | None = None,
        error_message: str | None = None,
        execution_time_ms: int | None = None,
    ) -> None:
        """execution_logs INSERT/UPDATE。"""
        existing = self._conn.execute(
            "SELECT 1 FROM execution_logs WHERE execution_id = ?",
            (execution_id,),
        ).fetchone()

        if existing:
            self._conn.execute(
                """UPDATE execution_logs
                   SET completed_at = ?, status = ?, decisions_json = ?,
                       error_message = ?, execution_time_ms = ?
                   WHERE execution_id = ?""",
                (
                    completed_at,
                    status,
                    decisions_json,
                    error_message,
                    execution_time_ms,
                    execution_id,
                ),
            )
        else:
            self._conn.execute(
                """INSERT INTO execution_logs
                   (execution_id, mode, started_at, status, decisions_json,
                    error_message, execution_time_ms)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    execution_id,
                    mode,
                    started_at,
                    status,
                    decisions_json,
                    error_message,
                    execution_time_ms,
                ),
            )
        self._conn.commit()

    def get_today_entry_count(self) -> int:
        """当日エントリー数カウント。"""
        today = date.today().isoformat()
        row = self._conn.execute(
            "SELECT COUNT(*) FROM positions WHERE entry_date = ? AND status IN ('open', 'closed')",
            (today,),
        ).fetchone()
        return row[0] if row else 0

    # === Internal Helpers ===

    def _get_high_water_mark(self, current_equity: float) -> float:
        """daily_snapshotsからHWMを算出。"""
        row = self._conn.execute(
            "SELECT MAX(high_water_mark) as hwm FROM daily_snapshots"
        ).fetchone()
        prev_hwm = float(row["hwm"]) if row and row["hwm"] is not None else 0.0
        return max(prev_hwm, current_equity)

    def _get_daily_pnl_pct(self, current_equity: float) -> float:
        """前日のequityと比較して日次PnL%を算出。"""
        row = self._conn.execute(
            "SELECT total_equity FROM daily_snapshots ORDER BY date DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return 0.0
        prev_equity = float(row["total_equity"])
        if prev_equity <= 0:
            return 0.0
        return (current_equity - prev_equity) / prev_equity * 100

    def _auto_fix(self, discrepancy: dict[str, str], alpaca_positions: dict[str, float]) -> None:
        """差異を自動修正する。"""
        symbol = discrepancy["symbol"]
        issue_type = discrepancy["issue_type"]

        if issue_type == "CLOSED_MISSING":
            # DBにあるがAlpacaにない → DB側をclosedに
            self._conn.execute(
                """UPDATE positions SET status = 'closed', close_date = ?,
                   close_reason = 'reconciliation', updated_at = datetime('now')
                   WHERE symbol = ? AND status = 'open'""",
                (date.today().isoformat(), symbol),
            )
            logger.info(f"Auto-fixed: closed {symbol} in DB (not in Alpaca)")

        elif issue_type == "ADDED_MISSING":
            # Alpacaにあるが、DBにない → DBにINSERT（entry_price=0.01は推定不可のため暫定値）
            qty = alpaca_positions.get(symbol, 0)
            self._conn.execute(
                """INSERT INTO positions
                   (symbol, side, qty, entry_price, entry_date, status, source, sector)
                   VALUES (?, 'long', ?, 0.01, ?, 'open', 'reconciliation', ?)""",
                (symbol, qty, date.today().isoformat(), get_sector(symbol)),
            )
            logger.info(f"Auto-fixed: added {symbol} to DB (from Alpaca)")

        elif issue_type == "QTY_MISMATCH":
            # 数量をAlpaca側に合わせる
            qty = alpaca_positions.get(symbol, 0)
            self._conn.execute(
                """UPDATE positions SET qty = ?, updated_at = datetime('now')
                   WHERE symbol = ? AND status = 'open'""",
                (qty, symbol),
            )
            logger.info(f"Auto-fixed: updated {symbol} qty to {qty}")
