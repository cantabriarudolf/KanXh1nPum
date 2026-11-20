"""Joining price, FX and CPI into one honest frame.

Rules that matter more than the code:

* FX is forward-filled, never backward-filled. A missing quote means "the last one
  known still applies", not "somebody will tell us what it was".
* If forward-filling cannot answer (the series starts later), we refuse instead of
  inventing a number. Silent NaN propagation is how a backtest becomes fiction.
"""

from __future__ import annotations

import pandas as pd

from kx.data.errors import DataAlignmentError

PRICE = "price_usd"
FX = "fx_clp_per_usd"
CPI = "cpi"


def _validate(series: pd.Series, name: str) -> None:
    if not isinstance(series.index, pd.DatetimeIndex):
        raise DataAlignmentError(f"{name} must use a DatetimeIndex")
    if not series.index.is_monotonic_increasing:
        raise DataAlignmentError(f"{name} must be sorted by date")
    if not series.index.is_unique:
        raise DataAlignmentError(f"{name} must have a unique date index")


def _aligned_to(series: pd.Series, target: pd.DatetimeIndex, name: str) -> pd.Series:
    """Forward-fill `series` onto `target`, refusing to extrapolate backwards."""
    union = series.index.union(target).sort_values()
    aligned = series.reindex(union).ffill().reindex(target)

    missing = aligned.index[aligned.isna()]
    if len(missing) > 0:
        raise DataAlignmentError(
            f"{name} has no value known on {missing[0].date()} "
            f"({len(missing)} date(s) unfillable); trim the price series to start on or "
            f"after the first {name} quote"
        )
    return aligned


def build_market_frame(
    price: pd.Series,
    fx: pd.Series,
    cpi: pd.Series | None = None,
) -> pd.DataFrame:
    """Build the frame the ledger consumes: one row per price date.

    Columns are price in USD, CLP per USD, and optionally a CPI index level.
    The index is exactly the price index; nothing is added or dropped.
    """
    _validate(price, PRICE)
    if price.isna().any():
        raise DataAlignmentError(f"{PRICE} contains missing values")

    frame = pd.DataFrame({PRICE: price.to_numpy(dtype="float64")}, index=price.index)

    if not isinstance(fx.index, pd.DatetimeIndex):
        raise DataAlignmentError(f"{FX} must use a DatetimeIndex")
    if not fx.index.is_unique:
        raise DataAlignmentError(f"{FX} must have a unique date index")
    frame[FX] = _aligned_to(fx.sort_index(), price.index, FX).to_numpy(dtype="float64")

    if cpi is not None:
        _validate(cpi, CPI)
        frame[CPI] = _aligned_to(cpi, price.index, CPI).to_numpy(dtype="float64")

    return frame
