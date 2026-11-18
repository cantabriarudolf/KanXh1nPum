"""The honest views: what a beginner is rarely shown.

Four answers, each one a single number or a single curve:

* the cost ladder — same strategy, four different truths about what you keep;
* missing the best days — the price of one bad decision repeated;
* the panic path — selling at the drawdown you swore you could tolerate;
* drawdown episodes — how long "long term" actually felt.
"""

from __future__ import annotations

import pandas as pd
import pytest

from kx.data import CPI, FX, PRICE
from kx.honest import (
    Scenario,
    cost_ladder,
    drawdown_episodes,
    missing_best_days,
    panic_path,
)
from kx.ledger import Costs, buy_and_hold

DATES = pd.bdate_range("2024-01-01", periods=7)


def curve(values: list[float]) -> pd.Series:
    return pd.Series(values, index=DATES[: len(values)], dtype="float64")


def zero_costs() -> Costs:
    return Costs(commission_bps=0.0, half_spread_bps=0.0, slippage_bps=0.0)


def test_missing_best_days_turns_a_gain_into_a_loss() -> None:
    # One +60% day carries the whole decade; it happens, and it is the point.
    equity = curve([100.0, 100.0, 100.0, 160.0, 100.0])

    untouched = missing_best_days(equity, 0)
    missing_one = missing_best_days(equity, 1)

    assert untouched.multiple == pytest.approx(1.0)
    assert missing_one.multiple < 1.0


def test_missing_best_days_reports_cagr_over_the_original_span() -> None:
    equity = curve([100.0, 100.0, 100.0, 160.0, 100.0])

    scenario = missing_best_days(equity, 1)

    # The span is still the original six days; the person simply was not there.
    years = (DATES[4] - DATES[0]).total_seconds() / 86_400 / 365.25
    assert scenario.cagr == pytest.approx(scenario.multiple ** (1 / years) - 1.0, rel=1e-9)


def test_missing_best_days_refuses_to_remove_everything() -> None:
    with pytest.raises(ValueError, match="remove"):
        missing_best_days(curve([100.0, 101.0, 102.0]), 3)


def test_panic_path_freezes_the_curve_at_the_breach() -> None:
    equity = curve([100.0, 120.0, 80.0, 90.0, 130.0])

    frozen, sell_date = panic_path(equity, threshold=0.30)

    assert sell_date == DATES[2]
    assert frozen.iloc[2:].tolist() == [80.0] * 3
    assert frozen.iloc[-1] < equity.iloc[-1]


def test_panic_threshold_never_reached_leaves_the_curve_alone() -> None:
    equity = curve([100.0, 110.0, 105.0])

    frozen, sell_date = panic_path(equity, threshold=0.50)

    assert sell_date is None
    assert frozen.equals(equity)


def test_drawdown_episodes_are_ordered_by_depth_and_name_their_dates() -> None:
    equity = curve([100.0, 120.0, 90.0, 130.0, 80.0, 60.0, 100.0])

    episodes = drawdown_episodes(equity)

    assert len(episodes) == 2
    worst, milder = episodes
    assert worst.depth == pytest.approx(-0.5385, abs=1e-4)
    assert worst.trough == DATES[5]
    assert worst.recovery is None
    assert milder.depth == pytest.approx(-0.25)
    assert milder.recovery == DATES[3]


def test_cost_ladder_closes_with_the_deposit_and_never_improves_on_the_way_down() -> None:
    frame = pd.DataFrame(
        {
            PRICE: pd.Series([100.0, 110.0, 120.0, 130.0], index=DATES[:4]),
            FX: pd.Series([900.0] * 4, index=DATES[:4]),
            CPI: pd.Series([100.0, 101.0, 102.0, 103.0], index=DATES[:4]),
        }
    )
    costs = Costs(commission_bps=30.0, half_spread_bps=10.0, slippage_bps=10.0)

    ladder = cost_ladder(
        frame,
        target=buy_and_hold(frame.index),
        costs=costs,
        initial_cash_clp=1_000_000.0,
        risk_free_annual=0.046,
    )

    labels = [step.label for step in ladder]
    assert labels == ["sin_costos", "con_costos", "real", "deposito"]
    assert all(isinstance(step, Scenario) for step in ladder)
    assert ladder[0].multiple > ladder[1].multiple > ladder[2].multiple
    assert ladder[3].cagr == pytest.approx(0.046)


def test_cost_ladder_without_inflation_data_stops_at_two_steps() -> None:
    frame = pd.DataFrame(
        {
            PRICE: pd.Series([100.0, 110.0, 120.0], index=DATES[:3]),
            FX: pd.Series([900.0] * 3, index=DATES[:3]),
        }
    )

    ladder = cost_ladder(
        frame,
        target=buy_and_hold(frame.index),
        costs=zero_costs(),
        initial_cash_clp=1_000_000.0,
        risk_free_annual=0.046,
    )

    assert [step.label for step in ladder] == ["sin_costos", "con_costos", "deposito"]
    assert ladder[0].multiple == pytest.approx(ladder[1].multiple)
