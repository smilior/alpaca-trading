"""Claude CLIを使ったLLM分析モジュール。

Claude CLIを呼び出し、JSON Schema Validationとフォールバック戦略で
堅牢にトレーディング判断を取得する。
"""

import json
import logging
import subprocess
from pathlib import Path

from jsonschema import ValidationError, validate

from modules.types import Action, BarData, PortfolioState, TradingDecision

logger = logging.getLogger("trading_agent")

# Claude CLI出力のJSON Schema定義
DECISION_SCHEMA: dict = {
    "type": "object",
    "required": ["decisions"],
    "properties": {
        "macro_regime": {"enum": ["bull", "range", "bear"]},
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "symbol",
                    "action",
                    "sentiment_analysis",
                    "reasoning_structured",
                ],
                "properties": {
                    "symbol": {"type": "string"},
                    "action": {"enum": ["buy", "sell", "hold", "no_action"]},
                    "sentiment_analysis": {
                        "type": "object",
                        "required": ["overall", "confidence"],
                        "properties": {
                            "overall": {"enum": ["positive", "negative", "neutral"]},
                            "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
                        },
                    },
                    "technical_check": {
                        "type": "object",
                        "properties": {
                            "price_vs_50ma": {"enum": ["above", "below", "near"]},
                            "rsi_14": {"type": "number"},
                            "atr_14": {"type": "number"},
                            "all_filters_passed": {"type": "boolean"},
                        },
                    },
                    "trade_parameters": {
                        "type": "object",
                        "properties": {
                            "suggested_entry_price": {"type": "number", "minimum": 0},
                            "calculated_stop_loss": {"type": "number", "minimum": 0},
                            "calculated_take_profit": {"type": "number", "minimum": 0},
                        },
                    },
                    "reasoning_structured": {
                        "type": "object",
                        "required": ["bull_case", "bear_case", "catalyst"],
                        "properties": {
                            "bull_case": {"type": "string"},
                            "bear_case": {"type": "string"},
                            "catalyst": {"type": "string"},
                            "expected_holding_days": {"type": "integer", "minimum": 1},
                        },
                    },
                },
            },
        },
    },
}


def _unwrap_cli_json(raw: str) -> str:
    """Claude CLI の --output-format json ラッパーを解除する。

    Claude CLI は {"type":"result","result":"..."} 形式で出力する。
    result フィールドに実際のLLMレスポンスが格納されている。
    """
    try:
        outer = json.loads(raw)
        if isinstance(outer, dict) and "result" in outer:
            return str(outer["result"])
    except (json.JSONDecodeError, TypeError):
        pass
    return raw


def _extract_json(raw: str) -> dict | None:
    """生の出力からJSON部分を抽出する。"""
    # Claude CLI ラッパー解除
    text = _unwrap_cli_json(raw)

    # まず全体をパース
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 最初の '{' から最後の '}' を抽出
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    return None


def _sanitize_partial(parsed: dict) -> dict:
    """部分的に有効なJSONをサニタイズする。"""
    valid_decisions = []
    for d in parsed.get("decisions", []):
        if all(k in d for k in ["symbol", "action"]):
            action = str(d["action"]).lower().strip()
            if action not in ("buy", "sell", "hold", "no_action"):
                action = "no_action"
            d["action"] = action
            valid_decisions.append(d)
    parsed["decisions"] = valid_decisions
    return parsed


def _build_input_data(
    market_data: dict[str, BarData],
    portfolio: PortfolioState,
    mode: str,
) -> dict:
    """Claude CLIに渡す入力データを構築する。"""
    symbols_data = {}
    for symbol, bar in market_data.items():
        symbols_data[symbol] = {
            "close": bar.close,
            "volume": bar.volume,
            "ma_50": bar.ma_50,
            "rsi_14": bar.rsi_14,
            "atr_14": bar.atr_14,
            "volume_ratio_20d": bar.volume_ratio_20d,
        }

    positions_data = {}
    for symbol, pos in portfolio.positions.items():
        positions_data[symbol] = {
            "qty": pos.qty,
            "avg_entry_price": pos.avg_entry_price,
            "current_price": pos.current_price,
            "unrealized_pnl": pos.unrealized_pnl,
            "sector": pos.sector,
        }

    return {
        "mode": mode,
        "market_data": symbols_data,
        "portfolio": {
            "equity": portfolio.equity,
            "cash": portfolio.cash,
            "buying_power": portfolio.buying_power,
            "daily_pnl_pct": portfolio.daily_pnl_pct,
            "drawdown_pct": portfolio.drawdown_pct,
            "positions": positions_data,
        },
    }


def call_claude_with_validation(
    prompt_text: str,
    input_data: str,
    max_retries: int = 2,
    timeout: int = 120,
) -> dict | None:
    """Claude CLIを呼び出し、出力をバリデーション付きでパースする。

    Args:
        prompt_text: プロンプトテキスト
        input_data: 入力データ（JSON文字列）
        max_retries: 最大リトライ回数
        timeout: タイムアウト秒数

    Returns:
        バリデーション済みの辞書。失敗時はNone。
    """
    full_prompt = f"{prompt_text}\n\n## 入力データ\n\n```json\n{input_data}\n```"

    for attempt in range(max_retries):
        parsed = None
        try:
            result = subprocess.run(
                ["claude", "-p"],
                input=full_prompt,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            if result.returncode != 0:
                logger.error(
                    f"Claude CLI exited with {result.returncode} "
                    f"(attempt {attempt + 1}): {result.stderr[:500]}"
                )
                continue

            raw_output = result.stdout.strip()
            parsed = _extract_json(raw_output)

            if parsed is None:
                logger.error(f"Failed to extract JSON (attempt {attempt + 1}): {raw_output[:200]}")
                continue

            # JSON Schemaバリデーション
            validate(instance=parsed, schema=DECISION_SCHEMA)
            return parsed

        except subprocess.TimeoutExpired:
            logger.error(f"Claude CLI timeout (attempt {attempt + 1})")
            continue
        except ValidationError as e:
            logger.error(f"Schema validation failed (attempt {attempt + 1}): {e.message}")
            if parsed and "decisions" in parsed:
                return _sanitize_partial(parsed)
            continue
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode failed (attempt {attempt + 1}): {e}")
            continue

    # 全リトライ失敗
    logger.error("Claude CLI failed after all retries")
    return None


def _parse_decisions(
    raw_decisions: list[dict], market_data: dict[str, BarData]
) -> list[TradingDecision]:
    """LLM出力の生decisionsリストをTradingDecisionに変換する。"""
    decisions: list[TradingDecision] = []
    for d in raw_decisions:
        symbol = d.get("symbol", "")
        action_str = d.get("action", "no_action")
        try:
            action = Action(action_str)
        except ValueError:
            action = Action.NO_ACTION

        sentiment = d.get("sentiment_analysis") or {}
        confidence = sentiment.get("confidence", 0)
        trade_params = d.get("trade_parameters") or {}
        reasoning = d.get("reasoning_structured") or {}

        # 市場データからデフォルト値を取得
        bar = market_data.get(symbol)
        entry_price = trade_params.get("suggested_entry_price", bar.close if bar else 0)
        stop_loss = trade_params.get("calculated_stop_loss", 0)
        take_profit = trade_params.get("calculated_take_profit", 0)

        decisions.append(
            TradingDecision(
                symbol=symbol,
                action=action,
                confidence=confidence,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reasoning_bull=reasoning.get("bull_case", ""),
                reasoning_bear=reasoning.get("bear_case", ""),
                catalyst=reasoning.get("catalyst", ""),
                expected_holding_days=reasoning.get("expected_holding_days", 5),
            )
        )
    return decisions


def get_trading_decisions(
    market_data: dict[str, BarData],
    portfolio: PortfolioState,
    mode: str,
    prompt_path: str | None = None,
    timeout: int = 120,
) -> list[TradingDecision]:
    """LLM分析を実行し、トレーディング判断を取得する。

    Args:
        market_data: 銘柄ごとのBarData
        portfolio: ポートフォリオ状態
        mode: 実行モード（morning, midday, eod等）
        prompt_path: プロンプトファイルパス
        timeout: Claude CLIタイムアウト

    Returns:
        TradingDecisionのリスト
    """
    if prompt_path is None:
        prompt_path = str(Path(__file__).parent.parent / "prompts" / "trading_decision.md")

    prompt_text = Path(prompt_path).read_text(encoding="utf-8")
    input_data = json.dumps(
        _build_input_data(market_data, portfolio, mode),
        ensure_ascii=False,
        indent=2,
    )

    result = call_claude_with_validation(
        prompt_text=prompt_text,
        input_data=input_data,
        timeout=timeout,
    )

    if result is None:
        logger.error("No valid decisions from LLM analysis")
        return []

    raw_decisions = result.get("decisions", [])
    return _parse_decisions(raw_decisions, market_data)
