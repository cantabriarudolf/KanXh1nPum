"""The ledger: what actually lands in the account.

These tests are the project's alibi. If the ledger can quietly cheat — fill on the
signal bar, forget the sell side, ignore that pesos became worth less — every number
the dashboard shows is fiction. So each rule below gets one test that fails loudly.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from kx.data import CPI, FX, PRICE
from kx.ledger import Costs, buy_and_hold, simulate

DATES = pd.bdate_range("2024-01-02", periods=5)


def make_frame(prices: list[float], fx: float = 900.0, cpi: list[float] | None = None):
    frame = pd.DataFrame(
        {
            PRICE: pd.Series(prices, index=DATES[: len(prices)], dtype="float64"),
            FX: pd.Series([fx] * len(prices), index=DATES[: len(prices)], dtype="float64"),
        }
    )
    if cpi is not None:
        frame[CPI] = pd.Series(cpi, index=DATES[: len(prices)], dtype="float64")
    return frame


def zeros(length: int) -> Costs:
    return Costs(commission_bps=0.0, half_spread_bps=0.0, slippage_bps=0.0)


def test_buy_and_hold_fills_on_the_next_bar_not_the_signal_bar() -> None:
    """The first bar is a decision, not a fill. Anything else uses a price you could not trade."""
    frame = make_frame([100.0, 102.0, 101.0, 105.0, 106.0])

    result = simulate(
        frame,
        target=buy_and_hold(frame.index),
        costs=zeros(5),
        initial_cash_clp=900_000.0,
    )

    assert result.equity_clp.iloc[0] == pytest.approx(900_000.0)  # still in cash
    assert result.trades[0].date == DATES[1]
    assert result.trades[0].price_usd == pytest.approx(102.0)
    assert result.equity_clp.iloc[2] == pytest.approx(900_000.0 * 101.0 / 102.0)


def test_a_jump_on_the_signal_bar_is_not_captured() -> None:
    frame = make_frame([100.0, 200.0, 100.0])

    result = simulate(
        frame, target=buy_and_hold(frame.index), costs=zeros(3), initial_cash_clp=1_000_000.0
    )

    assert result.trades[0].price_usd == pytest.approx(200.0)
    assert result.equity_clp.iloc[-1] == pytest.approx(500_000.0)


def test_buy_side_charges_spread_slippage_and_commission() -> None:
    frame = make_frame([100.0, 100.0, 100.0], fx=1000.0)
    costs = Costs(commission_bps=10.0, half_spread_bps=5.0, slippage_bps=5.0)

    result = simulate(frame, target=buy_and_hold(frame.index), costs=costs, initial_cash_clp=1e6)

    # Effective price drifts 10 bps against the buyer; commission is charged on top.
    assert result.trades[0].exec_price_usd == pytest.approx(100.1)

    # Sizing must divide out the commission too, otherwise the last trade cannot pay for itself.
    executor = 100.0 * (1 + 10.0 / 10_000)
    commission_rate = 10.0 / 10_000
    qty = (1e6 / 1000.0) / (executor * (1 + commission_rate))
    expected_left = 1e6 * (1 - 100.0 / (executor * (1 + commission_rate)))

    assert result.equity_clp.iloc[-1] == pytest.approx(qty * 100.0 * 1000.0)
    assert 1e6 - result.equity_clp.iloc[-1] == pytest.approx(expected_left, rel=1e-9)
    assert result.costs_clp == pytest.approx(1e6 - result.equity_clp.iloc[-1], rel=1e-9)


def test_sell_side_pays_costs_too() -> None:
    frame = make_frame([100.0, 100.0, 100.0, 100.0, 100.0], fx=1000.0)
    costs = Costs(commission_bps=10.0, half_spread_bps=5.0, slippage_bps=5.0)
    target = pd.Series([1.0, 1.0, 0.0, 0.0, 0.0], index=frame.index)

    result = simulate(frame, target=target, costs=costs, initial_cash_clp=1e6)

    _, sell = result.trades
    assert sell.side == "sell"
    assert sell.exec_price_usd == pytest.approx(99.9)

    gross = sell.qty * 99.9 * 1000.0
    assert result.equity_clp.iloc[-1] == pytest.approx(gross * (1 - 0.001))
    assert result.qty.iloc[-1] == 0.0


def test_cash_injections_are_invested_on_the_following_bar() -> None:
    frame = make_frame([100.0, 100.0, 100.0, 100.0, 100.0], fx=1000.0)
    cashflows = pd.Series([0.0, 1e6, 0.0, 0.0, 0.0], index=frame.index)

    result = simulate(
        frame,
        target=buy_and_hold(frame.index),
        costs=zeros(5),
        initial_cash_clp=1e6,
        cashflows=cashflows,
    )

    assert len(result.trades) == 2
    assert result.cash_clp.iloc[1] == pytest.approx(1e6)  # arrived, not yet invested
    assert result.qty.iloc[2] == pytest.approx(20.0)  # 2e6 CLP at 100 USD * 1000 CLP


def test_whole_shares_leave_the_rest_in_cash() -> None:
    frame = make_frame([730.0, 730.0, 730.0], fx=1000.0)

    fractional = simulate(
        frame, target=buy_and_hold(frame.index), costs=zeros(3), initial_cash_clp=500_000.0
    )
    whole = simulate(
        frame,
        target=buy_and_hold(frame.index),
        costs=zeros(3),
        initial_cash_clp=500_000.0,
        fractional=False,
    )

    assert fractional.qty.iloc[-1] == pytest.approx(500_000.0 / 730_000.0)
    assert whole.qty.iloc[-1] == 0.0
    assert whole.cash_clp.iloc[-1] == pytest.approx(500_000.0)
    assert math.floor(500_000.0 / 730_000.0) == 0


def test_real_equity_deflates_by_the_cpi_index() -> None:
    frame = make_frame([100.0] * 3, fx=1000.0, cpi=[100.0, 150.0, 200.0])

    result = simulate(
        frame, target=buy_and_hold(frame.index), costs=zeros(3), initial_cash_clp=1e6
    )

    # Expressing everything in the last bar's pesos: the first peso was worth double.
    assert result.equity_real_clp.iloc[0] == pytest.approx(2 * result.equity_clp.iloc[0])
    assert result.equity_real_clp.iloc[-1] == pytest.approx(result.equity_clp.iloc[-1])


def test_target_outside_zero_and_one_is_refused() -> None:
    frame = make_frame([100.0] * 3)
    target = pd.Series([0.0, 1.5, 1.0], index=frame.index)

    with pytest.raises(ValueError, match="between 0 and 1"):
        simulate(frame, target=target, costs=zeros(3), initial_cash_clp=1e6)


def test_target_must_share_the_frame_index() -> None:
    frame = make_frame([100.0] * 3)
    target = pd.Series([1.0, 1.0], index=frame.index[:2])

    with pytest.raises(ValueError, match="index"):
        simulate(frame, target=target, costs=zeros(3), initial_cash_clp=1e6)
