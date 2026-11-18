"""The honest views.

Every function here exists to answer a question a beginner is usually spared. None of
them produce advice; they produce the arithmetic of a decision already made.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from kx.data import CPI
from kx.ledger import Costs, simulate
from kx.metrics import DAYS_PER_YEAR, drawdown


@dataclass(frozen=True)
class Scenario:
    """One row of a comparison: what a peso became, and at what yearly rate."""

    label: str
    multiple: float
    cagr: float


@dataclass(frozen=True)
class Episode:
    """One stretch of time the account spent below a previous high."""

    peak: pd.Timestamp
    trough: pd.Timestamp
    recovery: pd.Timestamp | None
    depth: float


def _years(index: pd.DatetimeIndex) -> float:
    days = (index[-1] - index[0]).total_seconds() / 86_400.0
    return max(days, 1.0) / DAYS_PER_YEAR


def _scenario(label: str, curve: pd.Series) -> Scenario:
    multiple = float(curve.iloc[-1] / curve.iloc[0])
    years = _years(curve.index)
    cagr = float(multiple ** (1.0 / years) - 1.0) if years > 0 else 0.0
    return Scenario(label=label, multiple=multiple, cagr=cagr)


def missing_best_days(equity: pd.Series, days: int) -> Scenario:
    """What the same holding period returns if the best `days` days never happened.

    The holding period does not shrink. You were there for the whole decade; you just
    happened to be out those days. That asymmetry is the lesson, not the arithmetic.
    """
    if days < 0:
        raise ValueError("cannot remove a negative number of days")
    if len(equity) < 2:
        raise ValueError("equity curve needs at least two bars")

    returns = equity.pct_change().dropna()
    if days >= len(returns):
        raise ValueError(f"cannot remove {days} of {len(returns)} trading days")

    if days == 0:
        kept = returns
    else:
        kept = returns.drop(returns.nlargest(days).index)

    multiple = float(np.prod(1.0 + kept.to_numpy()))
    years = _years(equity.index)
    cagr = float(multiple ** (1.0 / years) - 1.0) if years > 0 else 0.0
    label = "sin_perder_dias" if days == 0 else "sin_los_mejores"
    return Scenario(label=label, multiple=multiple, cagr=cagr)


def panic_path(equity: pd.Series, threshold: float) -> tuple[pd.Series, pd.Timestamp | None]:
    """Sell the first time the drawdown breaches `threshold`, and never come back.

    The money does not vanish: it sits in cash while the market recovers. That is the
    honest shape of a panic, and usually the most expensive decision in the file.
    """
    if not 0.0 < threshold <= 1.0:
        raise ValueError("threshold must be between 0 and 1")

    depth = drawdown(equity)
    breach = depth[depth <= -threshold]
    if breach.empty:
        return equity.copy(), None

    sell_date = pd.Timestamp(breach.index[0])
    frozen = equity.copy()
    frozen.loc[sell_date:] = float(equity.loc[sell_date])
    return frozen, sell_date


def drawdown_episodes(equity: pd.Series) -> list[Episode]:
    """Every stretch below a previous high, worst first."""
    depth = drawdown(equity)
    underwater = depth < 0.0
    grouped = (underwater != underwater.shift()).cumsum()
    episodes: list[Episode] = []

    for _, block in depth[underwater].groupby(grouped[underwater]):
        start = pd.Timestamp(block.index[0])
        trough = pd.Timestamp(block.idxmin())
        peak = pd.Timestamp(equity.loc[:start].idxmax())
        peak_value = float(equity.loc[peak])

        after = equity.loc[trough:]
        back = after[after >= peak_value]
        recovery = pd.Timestamp(back.index[0]) if len(back) > 0 else None

        episodes.append(
            Episode(peak=peak, trough=trough, recovery=recovery, depth=float(block.min()))
        )

    return sorted(episodes, key=lambda episode: episode.depth)


def cost_ladder(
    frame: pd.DataFrame,
    *,
    target: pd.Series,
    costs: Costs,
    initial_cash_clp: float,
    risk_free_annual: float,
    cashflows: pd.Series | None = None,
) -> list[Scenario]:
    """Same strategy, four truths: gross, net, net of inflation, and the deposit.

    The deposit step is last on purpose. It is the number that has to be beaten for any
    of the three above to matter to somebody in Chile.
    """
    gross = simulate(
        frame,
        target=target,
        costs=Costs(),
        initial_cash_clp=initial_cash_clp,
        cashflows=cashflows,
    )
    net = simulate(
        frame,
        target=target,
        costs=costs,
        initial_cash_clp=initial_cash_clp,
        cashflows=cashflows,
    )

    ladder = [
        _scenario("sin_costos", gross.equity_clp),
        _scenario("con_costos", net.equity_clp),
    ]

    if CPI in frame.columns and net.equity_real_clp is not None:
        ladder.append(_scenario("real", net.equity_real_clp))

    years = _years(frame.index)
    ladder.append(
        Scenario(
            label="deposito",
            multiple=float((1.0 + risk_free_annual) ** years),
            cagr=float(risk_free_annual),
        )
    )
    return ladder
