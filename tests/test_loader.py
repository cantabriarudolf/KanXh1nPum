"""Loader: assembling the app's frame and reporting how fresh it is."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from kx.data import DataNotCached, load_series, write_series
from kx.loader import load_market

FIXTURES = Path(__file__).parent / "fixtures"


def write_cache(directory: Path, with_cpi: bool = True, price: pd.Series | None = None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    default_price = load_series(FIXTURES / "price_tiny.csv")
    write_series(price if price is not None else default_price, directory / "SPY.csv")
    write_series(load_series(FIXTURES / "fx_tiny.csv"), directory / "CLP_X.csv")
    if with_cpi:
        write_series(load_series(FIXTURES / "cpi_tiny.csv"), directory / "CPI_CHL.csv")
    return directory


def test_loads_the_cached_trio(tmp_path: Path) -> None:
    write_cache(tmp_path)

    data = load_market(tmp_path)

    assert data.symbol == "SPY"
    assert list(data.frame.columns) == ["price_usd", "fx_clp_per_usd", "cpi"]
    assert data.first == pd.Timestamp("2024-01-02")
    assert data.last == pd.Timestamp("2024-01-08")
    assert data.cpi_last == pd.Timestamp("2024-03-01")


def test_missing_cache_says_which_command_to_run(tmp_path: Path) -> None:
    with pytest.raises(DataNotCached, match="kx data fetch"):
        load_market(tmp_path)


def test_cpi_is_optional_and_reported_as_absent(tmp_path: Path) -> None:
    write_cache(tmp_path, with_cpi=False)

    data = load_market(tmp_path)

    assert data.cpi_last is None
    assert "cpi" not in data.frame.columns
    assert data.cpi_is_stale is False


def test_stale_cpi_is_flagged_when_it_lags_prices_by_more_than_a_year(tmp_path: Path) -> None:
    prices = pd.Series(
        [100.0, 110.0, 120.0],
        index=pd.DatetimeIndex(["2024-01-02", "2025-06-02", "2025-12-02"]),
    )
    write_cache(tmp_path, price=prices)

    # The fixture CPI stops at 2024-03-01, so 2025-12-02 is far past the last print.
    assert load_market(tmp_path).cpi_is_stale is True
