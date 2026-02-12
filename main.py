"""トレーディングエージェント オーケストレーター。

cron実行のエントリポイント。ファイルロック + execution_id + client_order_id の
冪等性3層で安全な自動実行を実現する。

Usage:
    python main.py morning      # 朝の分析+売買
    python main.py midday       # 日中モニタリング
    python main.py eod          # EODスナップショット
    python main.py health_check # ヘルスチェック
"""

import argparse
import fcntl
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import date, datetime

from modules.config import AppConfig, load_config
from modules.data_collector import collect_market_data
from modules.db import init_db
from modules.health import run_full_health_check
from modules.llm_analyzer import get_trading_decisions
from modules.logger import setup_logger
from modules.macro import classify_vix_regime, determine_macro_regime
from modules.order_executor import AlpacaOrderExecutor
from modules.risk_manager import AlpacaRiskManager
from modules.state_manager import AlpacaStateManager
from modules.types import Action
from modules.universe import get_sector, get_symbols

logger = logging.getLogger("trading_agent")

VALID_MODES = ("morning", "midday", "eod", "health_check")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """引数パース。"""
    parser = argparse.ArgumentParser(description="Trading Agent Orchestrator")
    parser.add_argument(
        "mode",
        choices=VALID_MODES,
        help="Execution mode",
    )
    return parser.parse_args(argv)


def generate_execution_id(mode: str) -> str:
    """execution_id生成。format: {date}_{mode}_{timestamp}"""
    now = datetime.now()
    return f"{now.strftime('%Y%m%d')}_{mode}_{now.strftime('%H%M%S')}"


def is_market_open() -> bool:
    """市場オープン確認 (exchange_calendars)。"""
    try:
        import exchange_calendars as xcals

        nyse = xcals.get_calendar("XNYS")
        today = date.today()
        return nyse.is_session(today.isoformat())
    except Exception as e:
        logger.warning(f"Could not check market calendar: {e}")
        return True  # フォールバック: 実行を許可


def run_health_check(config: AppConfig, conn: sqlite3.Connection) -> bool:
    """包括的ヘルスチェック: paper, API, DB, 実行ログ, 回路ブレーカー, ディスク。"""
    logger.info("Running health check...")
    report = run_full_health_check(config, conn)
    logger.info(report.summary())
    return report.all_ok


def run_pipeline(mode: str) -> int:
    """メインパイプライン実行。

    Returns:
        0: 成功, 1: エラー
    """
    start_time = time.time()

    # === 1. 設定読込 + ロガー初期化 + DB接続 ===
    config = load_config()
    setup_logger(log_dir=config.system.log_dir)
    conn = init_db(config.system.db_path)

    # === 2. execution_id生成 + 重複チェック ===
    execution_id = generate_execution_id(mode)
    state_manager = AlpacaStateManager(config, conn)

    if state_manager.check_execution_id(execution_id):
        logger.warning(f"Execution {execution_id} already exists, skipping")
        conn.close()
        return 0

    # 実行ログ開始記録
    state_manager.record_execution_log(
        execution_id=execution_id,
        mode=mode,
        status="running",
        started_at=datetime.now().isoformat(),
    )

    try:
        # === 3. ヘルスチェック ===
        if mode == "health_check":
            success = run_health_check(config, conn)
            status = "success" if success else "error"
            _finalize_execution(state_manager, execution_id, mode, status, start_time)
            conn.close()
            return 0 if success else 1

        # === 4. 市場オープン確認 ===
        if not is_market_open():
            logger.info("Market is closed today, skipping")
            _finalize_execution(state_manager, execution_id, mode, "skipped", start_time)
            conn.close()
            return 0

        # === 5. Reconciliation ===
        issues = state_manager.reconcile()
        if issues:
            logger.info(f"Reconciliation found {len(issues)} issues")

        # === 6. Portfolio sync ===
        portfolio = state_manager.sync()
        logger.info(
            f"Portfolio synced: equity=${portfolio.equity:,.2f}, "
            f"drawdown={portfolio.drawdown_pct:.1f}%"
        )

        # === 7. リスクプレチェック ===
        risk_manager = AlpacaRiskManager(config, conn)
        cb_state = risk_manager.check_circuit_breaker(portfolio)
        if cb_state.active:
            logger.warning(f"Circuit breaker L{cb_state.level} active, limiting operations")

        # === 8. マクロデータ取得 ===
        macro_data = collect_market_data(["SPY"], config)
        spy_bar = macro_data.get("SPY")
        spy_close = spy_bar.close if spy_bar else 0
        spy_ma200 = spy_bar.ma_50 if spy_bar else 0  # MA200 from data collector
        vix = 20.0  # VIXデフォルト値（Phase 4でyfinance連携予定）

        macro_regime = determine_macro_regime(spy_close, spy_ma200, vix)
        vix_regime = classify_vix_regime(vix)
        logger.info(f"Macro: regime={macro_regime.value}, VIX={vix} ({vix_regime.value})")

        # === 9. モード別処理 ===
        decisions_json = None

        if mode in ("morning", "midday"):
            # 市場データ収集
            symbols = get_symbols()
            market_data = collect_market_data(symbols, config)
            logger.info(f"Collected data for {len(market_data)} symbols")

            if mode == "morning" and not cb_state.active:
                # LLM分析
                decisions = get_trading_decisions(
                    market_data=market_data,
                    portfolio=portfolio,
                    mode=mode,
                    timeout=config.system.claude_timeout_seconds,
                )
                logger.info(f"LLM returned {len(decisions)} decisions")

                # リスクフィルタリング
                filtered = []
                for d in decisions:
                    if d.action == Action.BUY:
                        sector = get_sector(d.symbol)
                        can_open, reason = risk_manager.can_open_new_position(
                            portfolio, d.symbol, sector, vix_regime
                        )
                        if can_open:
                            filtered.append(d)
                        else:
                            logger.info(f"Filtered out BUY {d.symbol}: {reason}")
                    elif d.action == Action.SELL:
                        filtered.append(d)

                # 注文執行
                if filtered:
                    executor = AlpacaOrderExecutor(config)
                    results = executor.execute(filtered, portfolio, execution_id)

                    for result in results:
                        if result.success:
                            # BUY結果をDBに記録
                            buy_decision = next(
                                (d for d in filtered if d.symbol == result.symbol),
                                None,
                            )
                            if buy_decision and buy_decision.action == Action.BUY:
                                pos_id = state_manager.open_position(buy_decision, result)
                                state_manager.record_trade(result, pos_id)
                            elif buy_decision and buy_decision.action == Action.SELL:
                                state_manager.close_position(
                                    result.symbol, "signal", result.filled_price or 0
                                )
                                state_manager.record_trade(result, 0)
                        else:
                            logger.error(f"Order failed: {result.symbol} - {result.error_message}")

                decisions_json = json.dumps(
                    [
                        {
                            "symbol": d.symbol,
                            "action": d.action.value,
                            "confidence": d.confidence,
                        }
                        for d in decisions
                    ]
                )

        elif mode == "eod":
            # EOD: daily snapshot保存
            state_manager.save_daily_snapshot(portfolio, macro_regime.value, vix)
            logger.info("EOD snapshot saved")

        # === 10. 完了記録 ===
        _finalize_execution(
            state_manager,
            execution_id,
            mode,
            "success",
            start_time,
            decisions_json=decisions_json,
        )
        conn.close()
        return 0

    except Exception as e:
        logger.exception(f"Pipeline error in {mode}: {e}")
        _finalize_execution(
            state_manager,
            execution_id,
            mode,
            "error",
            start_time,
            error_message=str(e),
        )
        conn.close()
        return 1


def _finalize_execution(
    state_manager: AlpacaStateManager,
    execution_id: str,
    mode: str,
    status: str,
    start_time: float,
    decisions_json: str | None = None,
    error_message: str | None = None,
) -> None:
    """実行ログの最終更新。"""
    elapsed_ms = int((time.time() - start_time) * 1000)
    state_manager.record_execution_log(
        execution_id=execution_id,
        mode=mode,
        status=status,
        started_at=datetime.now().isoformat(),
        completed_at=datetime.now().isoformat(),
        decisions_json=decisions_json,
        error_message=error_message,
        execution_time_ms=elapsed_ms,
    )
    logger.info(f"Execution {execution_id} completed: status={status}, elapsed={elapsed_ms}ms")


def main(argv: list[str] | None = None) -> int:
    """メインエントリポイント（ファイルロック付き）。"""
    args = parse_args(argv)
    mode = args.mode

    # 設定を先読み（ロックファイルパス取得のため）
    config = load_config()
    lock_path = config.system.lock_file_path

    # ロックファイルのディレクトリを作成
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)

    lock_fd = open(lock_path, "w")  # noqa: SIM115
    try:
        # 排他ロック（ノンブロッキング）
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print(f"Another instance is running (lock: {lock_path})", file=sys.stderr)
        lock_fd.close()
        return 1

    try:
        return run_pipeline(mode)
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()


if __name__ == "__main__":
    sys.exit(main())
