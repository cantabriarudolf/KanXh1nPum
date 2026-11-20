"""The swing rule: one crossover, and the arithmetic that proves it cannot cheat.

If a weight can be computed from a bar it could not have traded, every comparison the
dashboard shows becomes fiction. So the crossover gets one test per promise: long in an
uptrend, flat in a downtrend, flat while warming up, untouched by bars that had not
happened yet, and more expensive to operate than simply holding.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from kx.data import FX, PRICE
from kx.ledger import Costs, Trade, buy_and_hold, simulate
from kx.strategies import sma_crossover

COSTS = Costs(commission_bps=10.0, half_spread_bps=5.0, slippage_bps=5.0)
FX_CLP = 1000.0

# Rises, sprints, then falls back through the averages: one full round trip.
ROUND_TRIP = [100.0, 100.0, 100.0, 100.0, 100.0, 110.0, 120.0, 130.0, 120.0, 110.0, 100.0, 100.0]


def prices(values: list[float], start: str = "2024-01-02") -> pd.Series:
    return pd.Series(
        values, index=pd.bdate_range(start, periods=len(values)), dtype="float64"
    )


def frame_for(series: pd.Series, fx: float = FX_CLP) -> pd.DataFrame:
    return pd.DataFrame(
        {
            PRICE: series,
            FX: pd.Series([fx] * len(series), index=series.index, dtype="float64"),
        }
    )


def friction_of(trade: Trade, fx: float = FX_CLP) -> float:
    """Friction on one fill, recomputed from the trade the ledger reports."""
    drift_clp = trade.qty * abs(trade.price_usd - trade.exec_price_usd) * fx
    return drift_clp + trade.commission_clp


def test_uptrend_stays_long() -> None:
    series = prices([100.0 + 2.0 * i for i in range(30)])

    weights = sma_crossover(series, fast=3, slow=5)

    assert weights.index.equals(series.index)
    assert weights.tolist() == [0.0] * 4 + [1.0] * 26
    assert weights.min() == 0.0
    assert weights.max() == 1.0


def test_downtrend_stays_flat() -> None:
    series = prices([200.0 - 2.0 * i for i in range(30)])

    weights = sma_crossover(series, fast=3, slow=5)

    assert weights.tolist() == [0.0] * 30


def test_warmup_bars_are_flat() -> None:
    series = prices(
        [100.0, 101.0, 99.0, 103.0, 98.0, 104.0, 97.0, 105.0, 96.0, 106.0, 95.0, 107.0, 94.0]
    )

    weights = sma_crossover(series, fast=3, slow=6)

    assert weights.iloc[:5].tolist() == [0.0] * 5
    assert not weights.isna().any()
    assert weights.tolist() == [0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0]


def test_signal_bar_carries_the_weight_and_the_ledger_fills_the_next_bar() -> None:
    """No shift here: bar t decides with bar t's close, and the ledger fills on t+1."""
    series = prices(ROUND_TRIP)

    weights = sma_crossover(series, fast=2, slow=4)
    assert weights.tolist() == [0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0]

    result = simulate(
        frame_for(series), target=weights, costs=COSTS, initial_cash_clp=1_000_000.0
    )

    assert [trade.side for trade in result.trades] == ["buy", "sell"]
    assert [trade.date for trade in result.trades] == [series.index[6], series.index[10]]
    assert result.trades[0].price_usd == 120.0
    assert result.trades[1].price_usd == 100.0
    # The exit is real: the rule is flat at the end, so the position is closed.
    assert result.qty.iloc[-1] == 0.0


def test_weight_at_bar_t_is_unchanged_when_future_bars_are_appended() -> None:
    """The lookahead proof. Tomorrow cannot change what today's rule decided."""
    index = pd.bdate_range("2024-01-02", periods=200)
    series = pd.Series(
        100.0 + 10.0 * np.sin(np.arange(len(index)) / 5.0), index=index, dtype="float64"
    )

    full = sma_crossover(series, fast=3, slow=8)

    for cut in (20, 30, 55, 90, 140, 199):
        truncated = sma_crossover(series.iloc[:cut], fast=3, slow=8)

        pd.testing.assert_series_equal(truncated, full.iloc[:cut])
        # The prefixes are not trivially flat: both states show up before the cut.
        assert set(full.iloc[:cut].unique()) == {0.0, 1.0}

        # Rewriting the future is just as harmless as appending it.
        mutated = series.copy()
        mutated.iloc[cut:] *= 2.0
        pd.testing.assert_series_equal(
            sma_crossover(mutated, fast=3, slow=8).iloc[:cut], full.iloc[:cut]
        )


def test_round_trip_pays_strictly_more_friction_than_buy_and_hold() -> None:
    series = prices(ROUND_TRIP)
    frame = frame_for(series)

    swing = simulate(
        frame, target=sma_crossover(series, fast=2, slow=4), costs=COSTS,
        initial_cash_clp=1_000_000.0,
    )
    hold = simulate(
        frame, target=buy_and_hold(frame.index), costs=COSTS, initial_cash_clp=1_000_000.0
    )

    # Buying and holding pays one entry: 998.0029999999997 drift + 999.000999000999 commission.
    assert hold.costs_clp == pytest.approx(1997.0039950059368)
    # The round trip pays the same entry, then the exit: 831.6691633374951 + 830.8374941740871.
    assert swing.costs_clp == pytest.approx(3659.510652517519)
    assert swing.costs_clp > hold.costs_clp

    # Both sides are charged, and the totals above are exactly the fills the ledger reports.
    assert swing.costs_clp == pytest.approx(sum(friction_of(trade) for trade in swing.trades))
    assert hold.costs_clp == pytest.approx(sum(friction_of(trade) for trade in hold.trades))
    assert [trade.side for trade in swing.trades] == ["buy", "sell"]
    assert [trade.side for trade in hold.trades] == ["buy"]

    # The exit is a real sale, not a weight change: the account ends in cash.
    assert swing.qty.iloc[-1] == 0.0
    assert hold.qty.iloc[-1] == pytest.approx(9.980029960049942)


@pytest.mark.parametrize(
    ("fast", "slow", "message"),
    [
        (20, 20, "fast .* must be smaller than slow"),
        (30, 10, "fast .* must be smaller than slow"),
        (0, 10, "fast must be at least 1"),
        (-5, 10, "fast must be at least 1"),
        (5, 0, "slow must be at least 1"),
        (5, -1, "slow must be at least 1"),
        (2.5, 10, "fast must be a whole number of bars"),
    ],
)
def test_rejects_window_lengths_that_cannot_cross(
    fast: float, slow: float, message: str
) -> None:
    series = prices([100.0, 101.0, 102.0])

    with pytest.raises(ValueError, match=message):
        sma_crossover(series, fast=fast, slow=slow)


def test_rejects_an_index_that_is_not_sorted() -> None:
    series = prices([100.0, 101.0, 102.0, 103.0])
    shuffled = series.iloc[[2, 0, 3, 1]]

    with pytest.raises(ValueError, match="sorted"):
        sma_crossover(shuffled, fast=1, slow=2)


def test_rejects_a_duplicated_index() -> None:
    series = prices([100.0, 101.0, 102.0])
    duplicated = pd.concat([series, series.iloc[[-1]]])

    with pytest.raises(ValueError, match="unique"):
        sma_crossover(duplicated, fast=1, slow=2)


def test_rejects_prices_with_gaps_instead_of_quietly_going_flat() -> None:
    """A missing price is a data bug; answering 0.0 would read as a trading decision."""
    gapped = prices([100.0, 101.0, 102.0, 103.0, 104.0])
    gapped.iloc[2] = np.nan

    with pytest.raises(ValueError, match="missing prices"):
        sma_crossover(gapped, fast=2, slow=3)


def test_default_windows_warm_up_in_ruedas_not_in_rows_of_something_else() -> None:
    series = prices([100.0 + i for i in range(130)])

    weights = sma_crossover(series)

    assert weights.iloc[:99].tolist() == [0.0] * 99
    assert weights.iloc[99:].tolist() == [1.0] * 31
