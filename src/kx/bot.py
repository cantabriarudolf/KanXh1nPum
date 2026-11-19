"""Paper trading: the tour's buy & hold strategy wired to a demo account.

The bot has one job and three refusals.

The job: turn "hold this fraction of the account in SPY" into the order the ledger would
charge for, so the cost line on the dashboard and the cost line on the order are the same
arithmetic. Sizing is delegated to :func:`kx.ledger._rebalance` on purpose — a second
opinion about what a trade costs is how a teaching project stops being honest.

The refusals are the point of the module:

* Nothing is submitted unless the caller passes ``send=True``. Planning is the default in
  the library and in the CLI, and it opens no socket.
* There is no live path. ``live=True`` raises :class:`NotImplementedError` and says why.
* Credentials are read from the environment only, and the error names the variables
  without ever echoing their values.

Alpaca's SDK is imported inside :func:`paper_broker`, so ``import kx.bot`` works without
the ``bot`` extra installed and without touching the network.
"""

from __future__ import annotations

import math
import os
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Protocol

import pandas as pd

from kx.data import FX, PRICE
from kx.data.errors import KxError
from kx.ledger import Costs, _rebalance
from kx.presets import PRESETS_BY_KEY
from kx.strategies import sma_crossover

KEY_ENV = "KX_ALPACA_KEY"
SECRET_ENV = "KX_ALPACA_SECRET"

#: The rules a beginner can run against the demo account.
STRATEGIES = ("hold", "sma-cross")

LIVE_REFUSED = (
    "live trading is refused: this project never trades real money. A paper account is "
    "the demo; there is no code path here that can send a real order (see docs/bot.md)"
)

_PAPER_ONLY = "paper only: nothing was sent"
_NO_ORDER = "no order: the target is already met or the difference is below the minimum"

# Estimates, not quotes. They come from kx.presets, which the dashboard also imports, so
# a plan printed here costs the same as the same plan simulated there.
COST_PRESETS = PRESETS_BY_KEY


class BotError(KxError):
    """Something the person running the bot can fix without reading the source."""


class MissingCredentials(BotError):
    """The environment has no Alpaca paper keys."""


@dataclass(frozen=True)
class BotConfig:
    """What the runner needs before it can size anything."""

    initial_cash_clp: float = 1_000_000.0
    contribution_clp: float = 50_000.0
    symbol: str = "SPY"
    cost_preset: str = "alpaca"
    fractional: bool = True
    strategy: str = "hold"
    fast: int = 20
    slow: int = 100

    def __post_init__(self) -> None:
        if self.cost_preset not in COST_PRESETS:
            raise BotError(
                f"unknown cost preset {self.cost_preset!r}; choose one of "
                f"{', '.join(sorted(COST_PRESETS))}"
            )
        if self.strategy not in STRATEGIES:
            raise BotError(
                f"unknown strategy {self.strategy!r}; choose one of {', '.join(STRATEGIES)}"
            )
        if self.strategy == "sma-cross" and self.fast >= self.slow:
            raise BotError(
                f"fast ({self.fast}) must be smaller than slow ({self.slow}): a crossover "
                "needs a short average to cross a long one"
            )
        if self.initial_cash_clp < 0.0:
            raise BotError("initial_cash_clp cannot be negative")
        if self.contribution_clp < 0.0:
            raise BotError("contribution_clp cannot be negative")
        if not self.symbol.strip():
            raise BotError("symbol cannot be empty")

    @property
    def costs(self) -> Costs:
        return COST_PRESETS[self.cost_preset]


@dataclass(frozen=True)
class OrderIntent:
    """One order, with the price the ledger would charge and the one the chart shows."""

    symbol: str
    side: str
    qty: float
    ref_price_usd: float
    exec_price_usd: float
    notional_clp: float
    commission_clp: float


@dataclass(frozen=True)
class Plan:
    """What the bot would do on this bar. Nothing here has happened yet."""

    symbol: str
    as_of: pd.Timestamp
    target_weight: float
    equity_clp: float
    contribution_clp: float
    current_qty: float
    target_qty: float
    intents: tuple[OrderIntent, ...]
    reason: str
    rule: str = "hold"
    sent: bool = False
    order_ids: tuple[str, ...] = ()


class Broker(Protocol):
    """The only three things the bot asks an account."""

    def account_value_clp(self, fx: float) -> float:
        """Total account value in CLP, converted at `fx` (CLP per USD)."""

    def position_qty(self, symbol: str) -> float:
        """Shares held right now; 0.0 when flat."""

    def submit(self, order: OrderIntent) -> str:
        """Send `order` and return the broker's order id."""


@dataclass(frozen=True)
class DryRunBroker:
    """An account made of numbers: good for a plan, incapable of an order.

    `kx bot plan` uses it, which is how that command stays free of credentials and network.
    """

    equity_clp: float = 0.0
    qty: float = 0.0

    def account_value_clp(self, fx: float) -> float:
        return self.equity_clp

    def position_qty(self, symbol: str) -> float:
        return self.qty

    def submit(self, order: OrderIntent) -> str:
        raise BotError(
            "dry run: this broker cannot submit. Nothing was sent; run against the paper "
            "account with `kx bot run --send`"
        )


class AlpacaPaperBroker:
    """Alpaca's paper host, and only that host.

    The client arrives as an opaque object so this module never imports alpaca-py at
    import time; :func:`paper_broker` builds it, with ``paper=True`` hard-coded.
    """

    def __init__(self, client: object) -> None:
        self._client = client

    def account_value_clp(self, fx: float) -> float:
        account = self._client.get_account()
        return float(account.equity) * fx

    def position_qty(self, symbol: str) -> float:
        from alpaca.common.exceptions import APIError

        try:
            position = self._client.get_open_position(symbol)
        except APIError:
            return 0.0
        return float(position.qty)

    def submit(self, order: OrderIntent) -> str:
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import MarketOrderRequest

        request = MarketOrderRequest(
            symbol=order.symbol,
            qty=order.qty,
            side=OrderSide.BUY if order.side == "buy" else OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        )
        return str(self._client.submit_order(request).id)


def _credentials(environ: Mapping[str, str] | None = None) -> tuple[str, str]:
    """Read the paper keys from the environment, or say which variables are missing."""
    env = os.environ if environ is None else environ
    values = {name: (env.get(name) or "").strip() for name in (KEY_ENV, SECRET_ENV)}
    missing = [name for name in (KEY_ENV, SECRET_ENV) if not values[name]]
    if missing:
        subject = " and ".join(missing)
        verb = "are" if len(missing) > 1 else "is"
        raise MissingCredentials(
            f"{subject} {verb} not set: export {KEY_ENV} and {SECRET_ENV} with your Alpaca "
            f"paper keys (docs/bot.md says where to click), then retry. Nothing is sent "
            f"without them."
        )
    return values[KEY_ENV], values[SECRET_ENV]


def paper_broker(environ: Mapping[str, str] | None = None) -> Broker:
    """Build the broker for the demo account.

    The import lives here, not at module level, so the rest of the project keeps working
    without the optional ``bot`` extra.
    """
    key, secret = _credentials(environ)
    try:
        from alpaca.trading.client import TradingClient
    except ImportError as exc:
        raise BotError(
            "alpaca-py is not installed; run `uv sync --extra bot`, then `kx bot run`"
        ) from exc
    return AlpacaPaperBroker(TradingClient(key, secret, paper=True))


def refuse_live(live: bool) -> None:
    """Fail loudly instead of pretending this project trades real money."""
    if live:
        raise NotImplementedError(LIVE_REFUSED)


def strategy_weight(config: BotConfig, history: pd.DataFrame, weight: float) -> float:
    """The target weight the configured rule wants on the last bar of `history`.

    `hold` keeps whatever the caller passed. `sma-cross` asks :func:`kx.strategies.
    sma_crossover`, which reads prices up to and including the last bar: the decision is
    taken at that close, and the paper account fills it on the next session. The series
    is not shifted here, for the reason the strategy module states once.

    A cache shorter than the slow window is refused rather than answered with 0.0. The
    rule is genuinely flat while it warms up, but on a real account that reads as
    "liquidate because I have no history", which is the wrong lesson to teach silently.
    """
    if config.strategy == "hold":
        return weight

    if PRICE not in history.columns:
        raise BotError(
            f"the cached frame has no {PRICE!r} column; build it with "
            "kx.loader.load_market or pass a frame from kx.data.build_market_frame"
        )
    if len(history) < config.slow:
        raise BotError(
            f"the cached series has {len(history)} bars but the rule needs at least "
            f"{config.slow}; fetch more history with "
            f"`kx data fetch --symbol {config.symbol} --start 2005-01-01`"
        )
    return float(sma_crossover(history[PRICE], fast=config.fast, slow=config.slow).iloc[-1])


def _rule_label(config: BotConfig) -> str:
    """The provenance of the weight, short enough to print on the plan's first line."""
    if config.strategy == "hold":
        return "hold"
    return f"sma-cross {config.fast}/{config.slow}"


def _as_of(market_row: pd.Series) -> pd.Timestamp:
    label = market_row.name
    if label is None:
        raise ValueError("market_row needs a date index label; pass a row of a dated frame")
    return pd.Timestamp(label)


def _column(market_row: pd.Series, name: str) -> float:
    if name not in market_row.index:
        raise ValueError(
            f"market_row is missing {name!r}; build it with kx.data.build_market_frame or "
            f"pass the last row of a loaded frame"
        )
    value = float(market_row[name])
    if not math.isfinite(value):
        raise ValueError(f"market_row has no finite {name!r}; check the cached series")
    return value


def plan(
    config: BotConfig,
    market_row: pd.Series,
    target_weight: float,
    broker: Broker,
    *,
    live: bool = False,
) -> Plan:
    """What the bot would do on this bar, using the ledger's own sizing.

    Reads the account and the bar; sends nothing, opens no socket, needs no credentials.
    """
    refuse_live(live)
    if not 0.0 <= target_weight <= 1.0:
        raise BotError(f"target_weight must be between 0 and 1, got {target_weight!r}")

    as_of = _as_of(market_row)
    price_usd = _column(market_row, PRICE)
    fx = _column(market_row, FX)

    equity_clp = float(broker.account_value_clp(fx))
    current_qty = float(broker.position_qty(config.symbol))
    cash_clp = equity_clp - current_qty * price_usd * fx

    _cash_after, target_qty, _friction, trade = _rebalance(
        cash_clp=cash_clp,
        qty=current_qty,
        target_weight=target_weight,
        price_usd=price_usd,
        fx=fx,
        date=as_of,
        costs=config.costs,
        fractional=config.fractional,
    )

    intents: tuple[OrderIntent, ...] = ()
    reason = _NO_ORDER
    if trade is not None:
        intents = (
            OrderIntent(
                symbol=config.symbol,
                side=trade.side,
                qty=trade.qty,
                ref_price_usd=trade.price_usd,
                exec_price_usd=trade.exec_price_usd,
                notional_clp=trade.qty * trade.exec_price_usd * fx,
                commission_clp=trade.commission_clp,
            ),
        )
        reason = (
            f"one {trade.side} at the ledger's cost model "
            f"({config.cost_preset} preset, both sides charged)"
        )

    return Plan(
        symbol=config.symbol,
        as_of=as_of,
        target_weight=target_weight,
        equity_clp=equity_clp,
        contribution_clp=config.contribution_clp,
        current_qty=current_qty,
        target_qty=target_qty,
        intents=intents,
        reason=reason,
        rule=_rule_label(config),
    )


def run(
    config: BotConfig,
    market_row: pd.Series,
    target_weight: float,
    broker: Broker,
    *,
    send: bool = False,
    live: bool = False,
) -> Plan:
    """Plan, and submit only when the caller says `send=True`.

    The default is a rehearsal: same arithmetic, no order.
    """
    planned = plan(config, market_row, target_weight, broker, live=live)
    if not send:
        return planned
    order_ids = tuple(broker.submit(intent) for intent in planned.intents)
    # `sent` answers "did an order reach the account", not "was send requested".
    return replace(planned, sent=bool(order_ids), order_ids=order_ids)


def describe(result: Plan) -> str:
    """Render a plan the way a broker statement would, one line per fact."""
    target = f"target {result.target_weight:.0%}"
    if result.rule != "hold":
        target += f" ({result.rule})"
    lines = [
        f"{result.symbol} on {result.as_of:%Y-%m-%d}  {target}  "
        f"equity {result.equity_clp:.0f} CLP  contribution "
        f"{result.contribution_clp:.0f} CLP/month",
        f"position {result.current_qty:.4f} -> {result.target_qty:.4f} {result.symbol}",
    ]
    for intent in result.intents:
        lines.append(
            f"  {intent.side.upper()} {intent.qty:.4f} {intent.symbol}  "
            f"ref {intent.ref_price_usd:.2f} USD  exec {intent.exec_price_usd:.2f} USD  "
            f"notional {intent.notional_clp:.0f} CLP  commission {intent.commission_clp:.0f} CLP"
        )
    if not result.intents:
        lines.append(f"  {result.reason}")
    elif result.sent:
        lines.append(f"sent to the paper account: {', '.join(result.order_ids)}")
    else:
        lines.append(_PAPER_ONLY)
    return "\n".join(lines)
