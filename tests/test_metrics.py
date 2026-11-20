"""Curve metrics: the numbers a beginner is shown, and the ones that hurt.

Undefined ratios return None instead of infinity. A Sharpe of inf because the strategy
never lost money is not a good number, it is a sample too small to say anything.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from kx.metrics import drawdown, summarize

YEARS_IN_DAYS = 365.25


def curve(values: list[float], start: str = "2024-01-01", freq: str = "D") -> pd.Series:
    dates = pd.date_range(start, periods=len(values), freq=freq)
    return pd.Series(values, index=dates, dtype="float64")


def test_drawdown_of_a_straight_line_is_zero() -> None:
    dd = drawdown(curve([100.0, 110.0, 120.0]))

    assert dd.tolist() == [0.0, 0.0, 0.0]


def test_max_drawdown_is_the_worst_peak_to_trough() -> None:
    stats = summarize(curve([100.0, 120.0, 90.0, 130.0]))

    assert stats.max_drawdown == pytest.approx(-0.25)
    assert stats.drawdown_peak == pd.Timestamp("2024-01-02")
    assert stats.drawdown_trough == pd.Timestamp("2024-01-03")
    assert stats.recovery == pd.Timestamp("2024-01-04")


def test_recovery_is_none_when_the_old_peak_is_never_recovered() -> None:
    stats = summarize(curve([100.0, 120.0, 90.0, 110.0]))

    assert stats.max_drawdown == pytest.approx(-0.25)
    assert stats.recovery is None


def test_cagr_needs_one_year_to_double() -> None:
    equity = pd.Series([100.0, 200.0], index=pd.DatetimeIndex(["2024-01-01", "2025-01-01"]))

    stats = summarize(equity)

    # Exact under the documented convention: 366 calendar days, 365.25 days per year.
    assert stats.cagr == pytest.approx(2.0 ** (365.25 / 366.0) - 1.0, rel=1e-12)
    assert stats.years == pytest.approx(366.0 / YEARS_IN_DAYS)


def test_flat_curve_has_zero_growth_and_zero_volatility() -> None:
    stats = summarize(curve([100.0] * 10))

    assert stats.cagr == pytest.approx(0.0)
    assert stats.volatility == pytest.approx(0.0)
    assert stats.sharpe is None
    assert stats.sortino is None


def test_risk_free_rate_lowers_the_sharpe_ratio() -> None:
    equity = curve([100.0, 102.0, 101.0, 104.0, 103.0, 106.0])

    free = summarize(equity, risk_free_annual=0.0, periods_per_year=6)
    costly = summarize(equity, risk_free_annual=0.50, periods_per_year=6)

    assert free.sharpe is not None and costly.sharpe is not None
    assert costly.sharpe < free.sharpe


def test_sortino_only_punishes_the_downside() -> None:
    same_std_up = curve([100.0, 110.0, 121.0, 133.1])
    same_std_down = curve([100.0, 90.0, 81.0, 72.9])

    assert summarize(same_std_up).sortino is None  # no downside at all
    downside = summarize(same_std_down).sortino
    assert downside is not None and downside < 0


def test_total_return_includes_the_last_bar() -> None:
    stats = summarize(curve([100.0, 100.0, 110.0]))

    assert stats.total_return == pytest.approx(0.10)


def test_single_bar_curve_is_refused() -> None:
    with pytest.raises(ValueError, match="at least two"):
        summarize(curve([100.0]))


def test_drawdown_never_goes_positive() -> None:
    dd = drawdown(curve([100.0, 50.0, 75.0, 25.0]))

    assert (dd <= 0).all()
    assert dd.min() == pytest.approx(-0.75)


def test_years_uses_calendar_days_not_row_counts() -> None:
    weekdays = summarize(
        pd.Series([100.0, 110.0], index=[pd.Timestamp("2024-01-01"), pd.Timestamp("2024-12-31")])
    )

    assert math.isclose(weekdays.years, 365.0 / YEARS_IN_DAYS, rel_tol=1e-12)
