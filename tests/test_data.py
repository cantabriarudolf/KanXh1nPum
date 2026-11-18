"""Data layer: alignment, lookahead safety, and cache fidelity.

Fixtures are synthetic and hand-checkable on purpose. A test that reads real market
data proves the network works, not that the code is right.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from kx.data import (
    DataAlignmentError,
    DataNotCached,
    build_market_frame,
    load_series,
    write_series,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _series(name: str) -> pd.Series:
    return load_series(FIXTURES / name)


def test_market_frame_joins_price_fx_and_cpi() -> None:
    frame = build_market_frame(
        price=_series("price_tiny.csv"),
        fx=_series("fx_tiny.csv"),
        cpi=_series("cpi_tiny.csv"),
    )

    assert list(frame.columns) == ["price_usd", "fx_clp_per_usd", "cpi"]
    assert frame.index.equals(_series("price_tiny.csv").index)
    assert frame["price_usd"].tolist() == [100.0, 102.0, 101.0, 105.0, 106.0]
    assert not frame.isna().any().any()


def test_missing_fx_is_forward_filled_never_back_filled() -> None:
    frame = build_market_frame(price=_series("price_tiny.csv"), fx=_series("fx_tiny.csv"))

    # 2024-01-03 has no FX quote of its own: the last known one (01-02, 900) applies.
    assert frame.loc["2024-01-03", "fx_clp_per_usd"] == 900.0
    # 2024-01-04 has its own quote and must not inherit the later 905.
    assert frame.loc["2024-01-04", "fx_clp_per_usd"] == 910.0


def test_future_fx_never_leaks_into_the_past() -> None:
    with pytest.raises(DataAlignmentError, match="fx_clp_per_usd"):
        build_market_frame(price=_series("price_tiny.csv"), fx=_series("fx_future_only.csv"))


def test_cpi_is_held_flat_between_monthly_prints() -> None:
    frame = build_market_frame(
        price=_series("price_tiny.csv"),
        fx=_series("fx_tiny.csv"),
        cpi=_series("cpi_tiny.csv"),
    )

    # Every price date sits inside January, so the January print holds all week.
    assert frame["cpi"].tolist() == [100.0] * 5


def test_price_series_must_be_sorted_and_unique() -> None:
    unsorted = pd.Series([1.0, 2.0], index=pd.to_datetime(["2024-01-05", "2024-01-02"]))
    with pytest.raises(DataAlignmentError, match="sorted"):
        build_market_frame(price=unsorted, fx=_series("fx_tiny.csv"))

    duplicated = pd.Series([1.0, 2.0], index=pd.to_datetime(["2024-01-02", "2024-01-02"]))
    with pytest.raises(DataAlignmentError, match="unique"):
        build_market_frame(price=duplicated, fx=_series("fx_tiny.csv"))


def test_csv_cache_roundtrip_is_lossless(tmp_path: Path) -> None:
    original = _series("price_tiny.csv")
    original.iloc[0] = 0.1 + 0.2  # 0.30000000000000004: punishes imprecise CSV writers

    path = tmp_path / "series.csv"
    write_series(original, path)
    restored = load_series(path)

    assert restored.equals(original)
    assert isinstance(restored.index, pd.DatetimeIndex)


def test_cache_miss_names_the_command_that_fixes_it(tmp_path: Path) -> None:
    with pytest.raises(DataNotCached, match="kx data fetch"):
        load_series(tmp_path / "nope.csv")
