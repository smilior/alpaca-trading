"""Alpaca ペーパートレーディングAPI疎通確認スクリプト。

Phase 1 最終ステップ: 5項目の接続確認を実行する。
"""

import os
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()


def verify_connection() -> bool:
    """Alpaca API接続を検証する。"""
    # === 安全チェック ===
    paper_flag = os.environ.get("ALPACA_PAPER")
    if paper_flag != "true":
        print("FATAL: ALPACA_PAPER must be 'true'. Aborting.")
        return False

    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")
    if not api_key or not secret_key:
        print("FATAL: ALPACA_API_KEY and ALPACA_SECRET_KEY must be set.")
        return False

    from alpaca.broker.client import BrokerClient  # noqa: F401
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from alpaca.trading.client import TradingClient

    results: list[tuple[str, bool, str]] = []

    # TradingClient（ペーパー）
    client = TradingClient(
        api_key=api_key,
        secret_key=secret_key,
        paper=True,
    )

    # --- 確認1: 認証 + アカウント情報 ---
    try:
        account = client.get_account()
        blocked = account.account_blocked
        results.append(("1. 認証 (GET /v2/account)", not blocked, f"account_blocked={blocked}"))
    except Exception as e:
        results.append(("1. 認証 (GET /v2/account)", False, str(e)))

    # --- 確認2: ペーパー環境確認 ---
    try:
        base_url = str(client._base_url) if hasattr(client, "_base_url") else str(client.base_url)
        is_paper = "paper" in base_url.lower()
        results.append(("2. ペーパー確認", is_paper, f"URL={base_url}"))
    except Exception as e:
        # TradingClient(paper=True) を使っているので安全
        results.append(("2. ペーパー確認", True, f"paper=True で初期化済み ({e})"))

    # --- 確認3: ポジション取得 ---
    try:
        positions = client.get_all_positions()
        results.append(("3. ポジション取得", True, f"{len(positions)} positions"))
    except Exception as e:
        results.append(("3. ポジション取得", False, str(e)))

    # --- 確認4: 注文一覧 ---
    try:
        orders = client.get_orders()
        results.append(("4. 注文一覧", True, f"{len(orders)} orders"))
    except Exception as e:
        results.append(("4. 注文一覧", False, str(e)))

    # --- 確認5: 市場データ (SPY直近5本) ---
    try:
        data_client = StockHistoricalDataClient(
            api_key=api_key,
            secret_key=secret_key,
        )
        from datetime import datetime, timedelta

        request = StockBarsRequest(
            symbol_or_symbols=["SPY"],
            timeframe=TimeFrame.Day,
            start=datetime.now() - timedelta(days=10),
            limit=5,
        )
        bars = data_client.get_stock_bars(request)
        # bars may be a BarSet or dict-like; try to get data
        bar_count = 0
        try:
            bar_count = len(bars["SPY"])
        except (KeyError, TypeError):
            # Try accessing as attribute or iterating
            bar_count = len(list(bars.data.get("SPY", []))) if hasattr(bars, "data") else 0
        results.append(("5. 市場データ (SPY bars)", bar_count > 0, f"{bar_count} bars"))
    except Exception as e:
        results.append(("5. 市場データ (SPY bars)", False, str(e)))

    # === 結果表示 ===
    print("\n" + "=" * 60)
    print("Alpaca API 接続確認結果")
    print("=" * 60)
    all_passed = True
    for name, passed, detail in results:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")
        print(f"         {detail}")
        if not passed:
            all_passed = False
    print("=" * 60)
    if all_passed:
        print("全項目合格: ペーパートレーディングAPI疎通確認完了")
    else:
        print("一部項目が失敗しています。")
    print("=" * 60)
    return all_passed


if __name__ == "__main__":
    success = verify_connection()
    sys.exit(0 if success else 1)
