"""modules/universe.py のテスト。"""

from modules.universe import (
    DEFAULT_UNIVERSE,
    get_all_sectors,
    get_sector,
    get_sectors_map,
    get_symbols,
    get_symbols_by_sector,
)


class TestUniverse:
    def test_get_symbols_returns_list(self) -> None:
        symbols = get_symbols()
        assert isinstance(symbols, list)
        assert len(symbols) == 30
        assert "AAPL" in symbols
        assert "MSFT" in symbols

    def test_get_sector(self) -> None:
        assert get_sector("AAPL") == "Technology"
        assert get_sector("JPM") == "Financials"
        assert get_sector("UNKNOWN") == "Unknown"

    def test_get_sectors_map(self) -> None:
        mapping = get_sectors_map()
        assert mapping["AAPL"] == "Technology"
        assert len(mapping) == 30

    def test_get_symbols_by_sector(self) -> None:
        tech = get_symbols_by_sector("Technology")
        assert "AAPL" in tech
        assert "MSFT" in tech
        assert len(tech) >= 4

    def test_get_all_sectors(self) -> None:
        sectors = get_all_sectors()
        assert "Technology" in sectors
        assert "Healthcare" in sectors
        assert "Energy" in sectors
        assert len(sectors) >= 9

    def test_universe_has_sector_diversity(self) -> None:
        sectors = set(s["sector"] for s in DEFAULT_UNIVERSE)
        assert len(sectors) >= 9  # 9+ sectors
