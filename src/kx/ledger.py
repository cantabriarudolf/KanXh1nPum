"""The ledger: mark-to-market accounting with friction applied for real.

This is deliberately not a backtester. It answers one narrow question — what lands in
the account of someone who pays spread, commission, slippage, a currency conversion,
and then watches inflation eat the rest — and it answers it with arithmetic that can be
read line by line.

Two rules carry the honesty:

1. A decision taken on bar *t* fills on bar *t+1*. Both bars are in the source data, so
   nothing needs to be guessed, and no test can accidentally reward a lookahead.
2. Costs are charged on both sides, on the executed notional, in the currency the
   person actually spends.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from kx.data import CPI, FX, PRICE

_BPS = 10_000.0
_CASH_DUST_CLP = 1e-6
_MIN_TRADE_CLP = 1.0


@dataclass(frozen=True)
class Costs:
    """What a trade costs, in basis points of traded notional."""

    commission_bps: float = 0.0
    half_spread_bps: float = 0.0
    slippage_bps: float = 0.0

    @property
    def _drift(self) -> float:
        return (self.half_spread_bps + self.slippage_bps) / _BPS

    @property
    def commission_rate(self) -> float:
        return self.commission_bps / _BPS

    def buy_price(self, price: float) -> float:
        return price * (1.0 + self._drift)

    def sell_price(self, price: float) -> float:
        return price * (1.0 - self._drift)


@dataclass(frozen=True)
class Trade:
    date: pd.Timestamp
    side: str
    qty: float
    price_usd: float
    exec_price_usd: float
    commission_clp: float
    cash_after_clp: float


@dataclass(frozen=True)
class Result:
    equity_clp: pd.Series
    cash_clp: pd.Series
    qty: pd.Series
    trades: tuple[Trade, ...]
    costs_clp: float
    initial_cash_clp: float
    invested_clp: float
    equity_real_clp: pd.Series | None = field(default=None)

    @property
    def final_equity_clp(self) -> float:
        return float(self.equity_clp.iloc[-1])


def buy_and_hold(index: pd.DatetimeIndex) -> pd.Series:
    """Always fully invested, from the first bar to the last."""
    return pd.Series(1.0, index=index)


def _validate(
    frame: pd.DataFrame,
    target: pd.Series,
    cashflows: pd.Series | None,
    initial_cash_clp: float,
) -> None:
    for column in (PRICE, FX):
        if column not in frame.columns:
            raise ValueError(f"frame is missing the {column!r} column")
    if not frame.index.equals(target.index):
        raise ValueError("target index must match the frame index")
    if target.isna().any():
        raise ValueError("target contains missing weights")
    if target.min() < 0.0 or target.max() > 1.0:
        raise ValueError("target weights must be between 0 and 1")
    if initial_cash_clp < 0:
        raise ValueError("initial_cash_clp cannot be negative")
    if cashflows is not None:
        if not frame.index.equals(cashflows.index):
            raise ValueError("cashflows index must match the frame index")
        if (cashflows < 0).any():
            raise ValueError("cashflows cannot be negative")


def _rebalance(
    *,
    cash_clp: float,
    qty: float,
    target_weight: float,
    price_usd: float,
    fx: float,
    date: pd.Timestamp,
    costs: Costs,
    fractional: bool,
) -> tuple[float, float, float, Trade | None]:
    """Move the position to `target_weight` of current equity. Returns cash, qty, cost, trade."""
    equity_clp = cash_clp + qty * price_usd * fx

    if target_weight <= 0.0:
        if qty <= 0.0:
            return cash_clp, 0.0, 0.0, None
        exec_price = costs.sell_price(price_usd)
        proceeds_clp = qty * exec_price * fx
        commission_clp = proceeds_clp * costs.commission_rate
        cash_clp += proceeds_clp - commission_clp
        friction_clp = qty * (price_usd - exec_price) * fx + commission_clp
        trade = Trade(date, "sell", qty, price_usd, exec_price, commission_clp, cash_clp)
        return cash_clp, 0.0, friction_clp, trade

    exec_price = costs.buy_price(price_usd)
    budget_usd = target_weight * equity_clp / fx
    affordable_qty = budget_usd / (exec_price * (1.0 + costs.commission_rate))
    delta = affordable_qty - qty
    if not fractional:
        delta = float(math.floor(delta))

    notional_clp = delta * exec_price * fx
    if delta <= 0.0 or notional_clp < _MIN_TRADE_CLP:
        return cash_clp, qty, 0.0, None

    spend_clp = notional_clp * (1.0 + costs.commission_rate)
    if spend_clp > cash_clp:
        delta *= cash_clp / spend_clp
        if not fractional:
            delta = float(math.floor(delta))
        notional_clp = delta * exec_price * fx
        if delta <= 0.0 or notional_clp < _MIN_TRADE_CLP:
            return cash_clp, qty, 0.0, None
        spend_clp = notional_clp * (1.0 + costs.commission_rate)

    commission_clp = notional_clp * costs.commission_rate
    friction_clp = delta * (exec_price - price_usd) * fx + commission_clp
    cash_clp = max(0.0, cash_clp - spend_clp)
    if cash_clp < _CASH_DUST_CLP:
        cash_clp = 0.0
    trade = Trade(date, "buy", delta, price_usd, exec_price, commission_clp, cash_clp)
    return cash_clp, qty + delta, friction_clp, trade


def simulate(
    frame: pd.DataFrame,
    target: pd.Series,
    costs: Costs,
    initial_cash_clp: float,
    cashflows: pd.Series | None = None,
    fractional: bool = True,
) -> Result:
    """Run the ledger over `frame`, following `target` weights.

    `cashflows` are CLP added on the given dates (monthly savings, for instance). They
    are invested on the following bar like any other decision.
    """
    _validate(frame, target, cashflows, initial_cash_clp)

    prices = frame[PRICE].to_numpy(dtype="float64")
    rates = frame[FX].to_numpy(dtype="float64")
    weights = target.to_numpy(dtype="float64")
    flows = (
        cashflows.to_numpy(dtype="float64")
        if cashflows is not None
        else np.zeros(len(frame), dtype="float64")
    )

    n = len(frame)
    equity = np.zeros(n, dtype="float64")
    cash_series = np.zeros(n, dtype="float64")
    qty_series = np.zeros(n, dtype="float64")

    cash = float(initial_cash_clp)
    qty = 0.0
    friction_total = 0.0
    pending: float | None = None
    effective: float | None = None
    trades: list[Trade] = []

    for i in range(n):
        date = frame.index[i]
        price = prices[i]
        fx = rates[i]

        if pending is not None:
            cash, qty, friction, trade = _rebalance(
                cash_clp=cash,
                qty=qty,
                target_weight=pending,
                price_usd=price,
                fx=fx,
                date=date,
                costs=costs,
                fractional=fractional,
            )
            friction_total += friction
            if trade is not None:
                trades.append(trade)
            effective = pending
            pending = None

        cash += flows[i]

        wanted = weights[i]
        needs_work = wanted != effective or (flows[i] > 0.0 and wanted > 0.0)
        if needs_work and i + 1 < n:
            pending = wanted

        cash_series[i] = cash
        qty_series[i] = qty
        equity[i] = cash + qty * price * fx

    equity_real = None
    if CPI in frame.columns:
        levels = frame[CPI].to_numpy(dtype="float64")
        equity_real = pd.Series(
            equity * (levels[-1] / levels), index=frame.index, name="equity_real_clp"
        )

    return Result(
        equity_clp=pd.Series(equity, index=frame.index, name="equity_clp"),
        cash_clp=pd.Series(cash_series, index=frame.index, name="cash_clp"),
        qty=pd.Series(qty_series, index=frame.index, name="qty"),
        trades=tuple(trades),
        costs_clp=friction_total,
        initial_cash_clp=float(initial_cash_clp),
        invested_clp=float(initial_cash_clp + flows.sum()),
        equity_real_clp=equity_real,
    )
