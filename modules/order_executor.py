"""注文執行モジュール。

ブラケット注文（limit入場 + stop-limit SL + limit TP）でエントリー、
マーケット売り注文でエグジット。SELL先→BUY後の順で処理。
"""

import logging
import os

from modules.config import AppConfig
from modules.types import (
    Action,
    OrderResult,
    PortfolioState,
    TradingDecision,
)

logger = logging.getLogger("trading_agent")


def _get_trading_client():  # type: ignore[no-untyped-def]
    """Alpaca Trading クライアントを取得する。"""
    from alpaca.trading.client import TradingClient

    api_key = os.environ.get("ALPACA_API_KEY", "")
    secret_key = os.environ.get("ALPACA_SECRET_KEY", "")
    paper = os.environ.get("ALPACA_PAPER", "true").lower() == "true"
    return TradingClient(api_key=api_key, secret_key=secret_key, paper=paper)


class AlpacaOrderExecutor:
    """OrderExecutor Protocol の実装。"""

    def __init__(
        self,
        config: AppConfig,
        trading_client: object | None = None,
    ) -> None:
        self._config = config
        self._client = trading_client
        self._verify_paper_trading()

    def _get_client(self) -> object:
        if self._client is None:
            self._client = _get_trading_client()
        return self._client

    def execute(
        self,
        decisions: list[TradingDecision],
        portfolio: PortfolioState,
        execution_id: str,
    ) -> list[OrderResult]:
        """SELL先→BUY後の順で処理。"""
        self._verify_paper_trading()

        results: list[OrderResult] = []

        # SELL注文を先に処理（資金を開放）
        sell_decisions = [d for d in decisions if d.action == Action.SELL]
        buy_decisions = [d for d in decisions if d.action == Action.BUY]

        for decision in sell_decisions:
            result = self._execute_sell(decision, portfolio, execution_id)
            results.append(result)

        for decision in buy_decisions:
            result = self._execute_buy(decision, portfolio, execution_id)
            results.append(result)

        return results

    def _execute_buy(
        self,
        decision: TradingDecision,
        portfolio: PortfolioState,
        execution_id: str,
    ) -> OrderResult:
        """ブラケット注文（limit入場 + stop-limit SL + limit TP）。"""
        from alpaca.trading.enums import OrderClass, OrderSide, OrderType, TimeInForce
        from alpaca.trading.requests import (
            LimitOrderRequest,
            StopLossRequest,
            TakeProfitRequest,
        )

        client = self._get_client()
        symbol = decision.symbol
        client_order_id = f"{execution_id}_{symbol}_buy"

        # ストップロスのリミット価格を計算
        # limit = stop - ATR*1.0 相当、ただし floor = entry * 0.92
        atr_buffer = abs(decision.entry_price - decision.stop_loss) * 0.5
        sl_limit = decision.stop_loss - atr_buffer
        sl_floor = decision.entry_price * 0.92
        sl_limit_price = max(sl_limit, sl_floor)

        # ポジションサイズはrisk_managerで事前計算される想定だが
        # decision.entry_priceとcapitalからフォールバック計算
        qty = self._calculate_qty(decision, portfolio)
        if qty <= 0:
            return OrderResult(
                symbol=symbol,
                success=False,
                alpaca_order_id=None,
                client_order_id=client_order_id,
                filled_qty=0,
                error_message="Calculated quantity is 0",
            )

        order_request = LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            time_in_force=TimeInForce.DAY,
            limit_price=round(decision.entry_price, 2),
            order_class=OrderClass.BRACKET,
            stop_loss=StopLossRequest(
                stop_price=round(decision.stop_loss, 2),
                limit_price=round(sl_limit_price, 2),
            ),
            take_profit=TakeProfitRequest(
                limit_price=round(decision.take_profit, 2),
            ),
            client_order_id=client_order_id,
        )

        for attempt in range(2):  # 最大1回リトライ
            try:
                order = client.submit_order(order_request)  # type: ignore[union-attr]
                logger.info(
                    f"BUY bracket order submitted: {symbol} qty={qty} "
                    f"entry={decision.entry_price} SL={decision.stop_loss} "
                    f"TP={decision.take_profit} (attempt {attempt + 1})"
                )
                return OrderResult(
                    symbol=symbol,
                    success=True,
                    alpaca_order_id=str(order.id),
                    client_order_id=client_order_id,
                    filled_qty=qty,
                    filled_price=decision.entry_price,
                )
            except Exception as e:
                logger.error(f"BUY order failed for {symbol} (attempt {attempt + 1}): {e}")
                if attempt == 1:
                    return OrderResult(
                        symbol=symbol,
                        success=False,
                        alpaca_order_id=None,
                        client_order_id=client_order_id,
                        filled_qty=0,
                        error_message=str(e),
                    )
        # Unreachable but satisfies type checker
        return OrderResult(
            symbol=symbol,
            success=False,
            alpaca_order_id=None,
            client_order_id=client_order_id,
            filled_qty=0,
            error_message="Unknown error",
        )

    def _execute_sell(
        self,
        decision: TradingDecision,
        portfolio: PortfolioState,
        execution_id: str,
    ) -> OrderResult:
        """マーケット売り注文。"""
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import MarketOrderRequest

        client = self._get_client()
        symbol = decision.symbol
        client_order_id = f"{execution_id}_{symbol}_sell"

        position = portfolio.positions.get(symbol)
        if position is None:
            return OrderResult(
                symbol=symbol,
                success=False,
                alpaca_order_id=None,
                client_order_id=client_order_id,
                filled_qty=0,
                error_message=f"No open position for {symbol}",
            )

        qty = int(position.qty)
        order_request = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
            client_order_id=client_order_id,
        )

        for attempt in range(2):
            try:
                order = client.submit_order(order_request)  # type: ignore[union-attr]
                logger.info(
                    f"SELL market order submitted: {symbol} qty={qty} (attempt {attempt + 1})"
                )
                return OrderResult(
                    symbol=symbol,
                    success=True,
                    alpaca_order_id=str(order.id),
                    client_order_id=client_order_id,
                    filled_qty=qty,
                    filled_price=position.current_price,
                )
            except Exception as e:
                logger.error(f"SELL order failed for {symbol} (attempt {attempt + 1}): {e}")
                if attempt == 1:
                    return OrderResult(
                        symbol=symbol,
                        success=False,
                        alpaca_order_id=None,
                        client_order_id=client_order_id,
                        filled_qty=0,
                        error_message=str(e),
                    )

        return OrderResult(
            symbol=symbol,
            success=False,
            alpaca_order_id=None,
            client_order_id=client_order_id,
            filled_qty=0,
            error_message="Unknown error",
        )

    def _verify_paper_trading(self) -> None:
        """config.alpaca.paper=True AND env ALPACA_PAPER=true を強制。"""
        if not self._config.alpaca.paper:
            raise RuntimeError("SAFETY: config.alpaca.paper must be True for paper trading")

        env_paper = os.environ.get("ALPACA_PAPER", "true").lower()
        if env_paper != "true":
            raise RuntimeError("SAFETY: ALPACA_PAPER environment variable must be 'true'")

    def _calculate_qty(self, decision: TradingDecision, portfolio: PortfolioState) -> int:
        """ポジションサイズのフォールバック計算。"""
        risk = self._config.risk
        capital = portfolio.equity
        risk_amount = capital * risk.max_risk_per_trade_pct / 100

        price_risk = abs(decision.entry_price - decision.stop_loss)
        if price_risk <= 0:
            return 0

        adjusted_risk = price_risk * risk.slippage_factor
        shares = risk_amount / adjusted_risk

        max_value = capital * risk.max_position_pct / 100
        max_shares = max_value / decision.entry_price if decision.entry_price > 0 else 0

        return max(0, int(min(shares, max_shares)))
