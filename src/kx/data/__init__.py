"""Data layer public API."""

from __future__ import annotations

from kx.data.errors import (
    DataAlignmentError,
    DataError,
    DataNotCached,
    DataSourceError,
    KxError,
)
from kx.data.frame import CPI, FX, PRICE, build_market_frame
from kx.data.store import load_series, write_series

__all__ = [
    "CPI",
    "FX",
    "PRICE",
    "DataAlignmentError",
    "DataError",
    "DataNotCached",
    "DataSourceError",
    "KxError",
    "build_market_frame",
    "load_series",
    "write_series",
]
