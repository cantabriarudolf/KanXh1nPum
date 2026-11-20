"""Remote sources. Thin, defensive, and never imported by the core package.

Every function returns a plain `pd.Series` indexed by date, so the rest of the code
never learns which provider produced the number.
"""

from __future__ import annotations

import json
import urllib.request

import pandas as pd

from kx.data.errors import DataSourceError

_TIMEOUT_SECONDS = 30
_WORLD_BANK_URL = (
    "https://api.worldbank.org/v2/country/{country}/indicator/FP.CPI.TOTL"
    "?format=json&per_page=500"
)


def _clean(series: pd.Series, source: str) -> pd.Series:
    if series.empty:
        raise DataSourceError(f"{source} returned no rows")

    index = series.index
    if getattr(index, "tz", None) is not None:
        index = index.tz_localize(None)
    series = pd.Series(series.to_numpy(dtype="float64"), index=index.normalize())
    series = series[~series.index.duplicated(keep="last")].sort_index()

    if series.isna().any():
        raise DataSourceError(f"{source} returned missing values")
    return series


def fetch_prices(symbol: str, start: str, end: str | None = None) -> pd.Series:
    """Adjusted daily closes for `symbol`.

    Adjusted on purpose: the tour compares total returns, so dividends belong in the
    price. The dashboard labels this, because an adjusted chart is not what a broker
    statement shows.
    """
    try:
        import yfinance as yf
    except ModuleNotFoundError as exc:  # pragma: no cover - optional extra
        raise DataSourceError("install the data extra: `uv sync --extra data`") from exc

    history = yf.Ticker(symbol).history(start=start, end=end, interval="1d", auto_adjust=True)
    if history is None or history.empty:
        raise DataSourceError(f"no price history for {symbol!r} between {start} and {end}")
    return _clean(history["Close"], f"prices({symbol})")


def fetch_fx(start: str, end: str | None = None, pair: str = "CLP=X") -> pd.Series:
    """CLP per USD, from the provider's daily close."""
    series = fetch_prices(pair, start=start, end=end)
    series.name = "fx_clp_per_usd"
    return series


def fetch_cpi(country: str = "CHL") -> pd.Series:
    """Annual consumer price index from the World Bank.

    Annual resolution is coarse and we say so in the dashboard. It is the price of
    having a source that needs no API key, no registration, and no scraping.
    """
    request = urllib.request.Request(
        _WORLD_BANK_URL.format(country=country),
        headers={"User-Agent": "kan-xhin-pum/0.1 (+https://github.com/)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except OSError as exc:
        raise DataSourceError(f"world bank request failed: {exc}") from exc

    if not isinstance(payload, list) or len(payload) < 2 or not payload[1]:
        raise DataSourceError(f"world bank returned an unexpected payload for {country}")

    rows = {row["date"]: row["value"] for row in payload[1] if row.get("value") is not None}
    if not rows:
        raise DataSourceError(f"world bank returned no CPI values for {country}")

    series = pd.Series(
        {pd.Timestamp(f"{year}-01-01"): float(value) for year, value in rows.items()},
        dtype="float64",
    ).sort_index()
    series.name = "cpi"
    return series
