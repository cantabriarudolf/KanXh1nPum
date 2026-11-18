"""Reading and writing cached series.

The on-disk format is CSV on purpose: a beginner can open it, diff it, and commit it.
Floats are written with round-trip precision so a cache cycle never changes a number.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from kx.data.errors import DataError, DataNotCached

_DATE_COLUMN = "date"
_VALUE_COLUMN = "close"


def _require_index(series: pd.Series, path: Path) -> None:
    if not isinstance(series.index, pd.DatetimeIndex):
        raise DataError(f"{path}: expected a DatetimeIndex, got {type(series.index).__name__}")
    if series.index.hasnans:
        raise DataError(f"{path}: index contains NaT")


def load_series(path: str | Path, column: str = _VALUE_COLUMN) -> pd.Series:
    """Read a cached series from `path`.

    Raises DataNotCached instead of FileNotFoundError so the callers can tell a user
    what to run, not just which file is missing.
    """
    path = Path(path)
    if not path.exists():
        raise DataNotCached(
            f"no cached series at {path}; run `kx data fetch` to create it, "
            "or point --fixtures at a committed snapshot"
        )

    # pandas >= 3 parses floats losslessly by default; test_csv_cache_roundtrip_is_lossless
    # is what keeps that promise honest if the default ever changes.
    frame = pd.read_csv(path)
    if _DATE_COLUMN not in frame.columns or column not in frame.columns:
        raise DataError(
            f"{path}: expected columns {_DATE_COLUMN!r} and {column!r}, "
            f"found {list(frame.columns)}"
        )

    index = pd.DatetimeIndex(pd.to_datetime(frame[_DATE_COLUMN]), name=_DATE_COLUMN)
    series = pd.Series(frame[column].to_numpy(dtype="float64"), index=index, name=column)
    _require_index(series, path)
    return series.sort_index()


def write_series(series: pd.Series, path: str | Path) -> None:
    """Write `series` to `path` with round-trip float precision."""
    path = Path(path)
    _require_index(series, path)
    path.parent.mkdir(parents=True, exist_ok=True)

    frame = pd.DataFrame(
        {
            _DATE_COLUMN: series.index.strftime("%Y-%m-%d"),
            _VALUE_COLUMN: series.to_numpy(dtype="float64"),
        }
    )
    frame.to_csv(path, index=False, float_format="%.17g")
