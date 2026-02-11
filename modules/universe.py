"""銘柄ユニバース管理。

S&P500大型株の中から流動性条件を満たす銘柄を選定する。
初期30銘柄でスタートし、シグナル頻度に応じて拡大する。
"""

# S&P500大型株ユニバース（初期30銘柄）
# 選定基準: 出来高100万株以上、時価総額$10B以上、スプレッド0.05%以内
# セクター分散を考慮して選定
DEFAULT_UNIVERSE: list[dict[str, str]] = [
    # Technology
    {"symbol": "AAPL", "sector": "Technology"},
    {"symbol": "MSFT", "sector": "Technology"},
    {"symbol": "NVDA", "sector": "Technology"},
    {"symbol": "GOOGL", "sector": "Technology"},
    {"symbol": "META", "sector": "Technology"},
    {"symbol": "AVGO", "sector": "Technology"},
    # Healthcare
    {"symbol": "UNH", "sector": "Healthcare"},
    {"symbol": "JNJ", "sector": "Healthcare"},
    {"symbol": "LLY", "sector": "Healthcare"},
    # Financials
    {"symbol": "JPM", "sector": "Financials"},
    {"symbol": "V", "sector": "Financials"},
    {"symbol": "MA", "sector": "Financials"},
    # Consumer Discretionary
    {"symbol": "AMZN", "sector": "Consumer Discretionary"},
    {"symbol": "TSLA", "sector": "Consumer Discretionary"},
    {"symbol": "HD", "sector": "Consumer Discretionary"},
    # Communication Services
    {"symbol": "NFLX", "sector": "Communication Services"},
    {"symbol": "DIS", "sector": "Communication Services"},
    # Industrials
    {"symbol": "CAT", "sector": "Industrials"},
    {"symbol": "GE", "sector": "Industrials"},
    {"symbol": "UNP", "sector": "Industrials"},
    # Consumer Staples
    {"symbol": "PG", "sector": "Consumer Staples"},
    {"symbol": "KO", "sector": "Consumer Staples"},
    {"symbol": "PEP", "sector": "Consumer Staples"},
    # Energy
    {"symbol": "XOM", "sector": "Energy"},
    {"symbol": "CVX", "sector": "Energy"},
    # Utilities
    {"symbol": "NEE", "sector": "Utilities"},
    {"symbol": "SO", "sector": "Utilities"},
    # Real Estate
    {"symbol": "PLD", "sector": "Real Estate"},
    # Materials
    {"symbol": "LIN", "sector": "Materials"},
    {"symbol": "APD", "sector": "Materials"},
]

# ベンチマーク ETF
BENCHMARK_SYMBOLS: list[str] = ["SPY", "RSP"]

# マクロ指標用シンボル
MACRO_SYMBOLS: list[str] = ["SPY"]  # S&P500 proxy for 200-day MA


def get_symbols() -> list[str]:
    """ユニバースのシンボル一覧を返す。"""
    return [s["symbol"] for s in DEFAULT_UNIVERSE]


def get_sector(symbol: str) -> str:
    """シンボルのセクターを返す。不明な場合は'Unknown'。"""
    for s in DEFAULT_UNIVERSE:
        if s["symbol"] == symbol:
            return s["sector"]
    return "Unknown"


def get_sectors_map() -> dict[str, str]:
    """シンボル→セクターのマッピングを返す。"""
    return {s["symbol"]: s["sector"] for s in DEFAULT_UNIVERSE}


def get_symbols_by_sector(sector: str) -> list[str]:
    """指定セクターのシンボル一覧を返す。"""
    return [s["symbol"] for s in DEFAULT_UNIVERSE if s["sector"] == sector]


def get_all_sectors() -> list[str]:
    """全セクター名一覧を返す（重複なし）。"""
    return list(dict.fromkeys(s["sector"] for s in DEFAULT_UNIVERSE))
