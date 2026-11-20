"""Curve metrics.

Two conventions matter and both are stated here instead of implied:

* Years are calendar days divided by 365.25, not row counts. Ten business days are not
  half a month of returns.
* Undefined ratios are None. A Sharpe computed from zero volatility is not a good
  number, and reporting `inf` would make a flat line look like a miracle.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

DAYS_PER_YEAR = 365.25


@dataclass(frozen=True)
class Stats:
    total_return: float
    cagr: float
    volatility: float
    sharpe: float | None
    sortino: float | None
    max_drawdown: float
    drawdown_peak: pd.Timestamp
    drawdown_trough: pd.Timestamp
    recovery: pd.Timestamp | None
    years: float

    @property
    def underwater(self) -> bool:
        """True when the curve has not recovered its worst peak."""
        return self.recovery is None and self.max_drawdown < 0.0


def drawdown(equity: pd.Series) -> pd.Series:
    """Distance from the running peak, as a negative fraction."""
    peak = equity.cummax()
    return (equity / peak - 1.0).rename("drawdown")


def _years(index: pd.DatetimeIndex) -> float:
    days = (index[-1] - index[0]).total_seconds() / 86_400.0
    return max(days, 1.0) / DAYS_PER_YEAR


def summarize(
    equity: pd.Series,
    *,
    risk_free_annual: float = 0.0,
    periods_per_year: int = 252,
) -> Stats:
    """Summarize an equity curve expressed in constant units (CLP nominal or real)."""
    if len(equity) < 2:
        raise ValueError("summary needs at least two bars")
    if equity.isna().any():
        raise ValueError("equity curve contains missing values")
    if (equity <= 0).any():
        raise ValueError("equity curve must stay positive")

    years = _years(equity.index)
    total_return = float(equity.iloc[-1] / equity.iloc[0] - 1.0)
    cagr = float((1.0 + total_return) ** (1.0 / years) - 1.0) if years > 0 else 0.0

    returns = equity.pct_change().dropna()
    volatility = (
        float(returns.std(ddof=1) * math.sqrt(periods_per_year)) if len(returns) > 1 else 0.0
    )

    risk_free_per_period = (1.0 + risk_free_annual) ** (1.0 / periods_per_year) - 1.0
    excess = returns - risk_free_per_period

    sharpe: float | None = None
    if len(excess) > 1 and excess.std(ddof=1) > 0:
        sharpe = float(excess.mean() / excess.std(ddof=1) * math.sqrt(periods_per_year))

    sortino: float | None = None
    downside = excess[excess < 0.0]
    if len(downside) > 0:
        downside_deviation = math.sqrt(float((downside**2).mean()))
        if downside_deviation > 0:
            sortino = float(excess.mean() / downside_deviation * math.sqrt(periods_per_year))

    dd = drawdown(equity)
    trough = dd.idxmin()
    peak_window = equity.loc[:trough]
    peak = peak_window.idxmax()
    after_trough = equity.loc[trough:]
    recovered = after_trough[after_trough >= equity.loc[peak]]
    recovery = recovered.index[0] if len(recovered) > 0 else None

    return Stats(
        total_return=total_return,
        cagr=cagr,
        volatility=volatility,
        sharpe=sharpe,
        sortino=sortino,
        max_drawdown=float(dd.min()),
        drawdown_peak=peak,
        drawdown_trough=trough,
        recovery=recovery,
        years=years,
    )
