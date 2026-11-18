"""Assemble the frame the app runs on, and say how fresh each piece is.

Staleness is data. A dashboard that silently deflates 2026 returns with a 2025 inflation
index is lying by omission, so the loader reports the last date of every input it used
and the UI prints it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from kx.cli import slug
from kx.data import FX, PRICE, build_market_frame, load_series

DEFAULT_DATA_DIR = "data/cache"
DEFAULT_SYMBOL = "SPY"
DEFAULT_FX = "CLP=X"
DEFAULT_COUNTRY = "CHL"


@dataclass(frozen=True)
class MarketData:
    frame: pd.DataFrame
    symbol: str
    fx_symbol: str
    cpi_last: pd.Timestamp | None
    data_dir: Path

    @property
    def first(self) -> pd.Timestamp:
        return pd.Timestamp(self.frame.index[0])

    @property
    def last(self) -> pd.Timestamp:
        return pd.Timestamp(self.frame.index[-1])

    @property
    def cpi_is_stale(self) -> bool:
        """True when the inflation index lags the prices by more than a year."""
        if self.cpi_last is None:
            return False
        return (self.last - self.cpi_last).days > 400


def resolve_data_dir(explicit: str | Path | None = None) -> Path:
    if explicit is not None:
        return Path(explicit)
    return Path(os.environ.get("KX_DATA_DIR", DEFAULT_DATA_DIR))


def load_market(
    data_dir: str | Path | None = None,
    symbol: str = DEFAULT_SYMBOL,
    fx_symbol: str = DEFAULT_FX,
    country: str = DEFAULT_COUNTRY,
) -> MarketData:
    """Read the cached series and build the market frame.

    Raises DataNotCached with the exact command to run when the cache is empty.
    """
    directory = resolve_data_dir(data_dir)

    price = load_series(directory / f"{slug(symbol)}.csv")
    fx = load_series(directory / f"{slug(fx_symbol)}.csv")

    cpi_path = directory / f"CPI_{country.upper()}.csv"
    cpi = load_series(cpi_path) if cpi_path.exists() else None

    frame = build_market_frame(price, fx, cpi)
    return MarketData(
        frame=frame,
        symbol=symbol,
        fx_symbol=fx_symbol,
        cpi_last=pd.Timestamp(cpi.index[-1]) if cpi is not None else None,
        data_dir=directory,
    )


def frame_for(series: dict[str, pd.Series], cpi: pd.Series | None = None) -> pd.DataFrame:
    """Build a frame from in-memory series; used by tests and notebooks."""
    if PRICE not in series or FX not in series:
        raise ValueError(f"need {PRICE!r} and {FX!r} series")
    return build_market_frame(series[PRICE], series[FX], cpi)
