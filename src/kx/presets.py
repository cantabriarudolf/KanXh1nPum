"""The cost models the project offers, named once.

The dashboard and the bot have to charge the same friction for the same trade, or the
number on the order stops matching the number on the chart. Both import from here, so
there is one literal to change instead of two that agree by habit.

Two keys for the same objects, because the two surfaces are read differently: the CLI
wants something short enough to type (`alpaca`, `chile`), and the dashboard wants a label
a beginner can recognise. Neither is derived from the other, so a rename cannot silently
split them.

The zero-cost model exists to be compared against, never to be believed: a simulation
without friction describes a market that does not exist.
"""

from __future__ import annotations

from kx.ledger import Costs

FREE = Costs()
ALPACA = Costs(commission_bps=0.0, half_spread_bps=5.0, slippage_bps=5.0)
CHILE = Costs(commission_bps=30.0, half_spread_bps=10.0, slippage_bps=10.0)

#: What `kx bot --cost-preset` accepts. The bot validates membership against this exact
#: mapping and holds no second list, so a new key here is usable from the CLI at once.
PRESETS_BY_KEY: dict[str, Costs] = {"alpaca": ALPACA, "chile": CHILE}

#: What the dashboard's selectbox lists, in the order it should be read.
PRESETS_BY_LABEL: dict[str, Costs] = {
    "Sin costos (para comparar)": FREE,
    "Broker internacional (Alpaca)": ALPACA,
    "Banco o broker chileno": CHILE,
}
