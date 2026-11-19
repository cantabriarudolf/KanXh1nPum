# The paper bot (Alpaca demo account)

`kx bot` wires the tour's trading stops — buy & hold, and crossing averages — to a real
demo account at Alpaca. It sizes orders with the same ledger the dashboard uses, prints
what it *would* do, and submits nothing unless you ask it to.

It is a plumbing exercise for a beginner, not a signal generator. No ML, no
hyperparameter search, no LLM in the loop.

## 1. Create the paper account

1. Sign up at [app.alpaca.markets](https://app.alpaca.markets) — free, open from Chile,
   no US residency and no brokerage account required.
2. In the dashboard, switch the account selector to **Paper Trading**. Alpaca keeps a
   separate paper host (`paper-api.alpaca.markets`) with USD 100,000 of simulated money
   and unlimited resets. Your paper keys do not work on the live host, and `kx` never
   talks to the live host either.
3. Open **API Keys** inside the paper account and generate a key pair. The secret is
   shown once; copy it somewhere safe (a password manager, not a file in this repo).

## 2. Where the keys go

The bot reads credentials from the environment, and only from the environment:

```bash
export KX_ALPACA_KEY="your-paper-key-id"
export KX_ALPACA_SECRET="your-paper-secret"
```

Then run the commands below in that same shell.

* There is no config file and no `.env` loader: this project has no dependency to read
  one, so anything you write to disk stays out of the picture.
* Never commit the keys, and never paste them into the Streamlit dashboard. Both
  variables must be exported in the shell that runs `kx bot`.
* On failure the error names the missing variable and nothing else; no value is ever
  echoed by the bot, the CLI, or the tests.

## 3. Commands

The bot decides on the **last cached bar**, never on a live quote, so the data comes
first:

```bash
uv run kx data fetch --symbol SPY     # prices, USD/CLP and CPI into data/cache
```

```bash
uv run kx bot plan                    # offline: no keys, no socket, exit 0
uv run kx bot run                     # reads the paper account, plans only
uv run kx bot run --send              # submits the planned order to the paper host
```

`plan` uses the numbers in the flags as the account state:

```bash
uv run kx bot plan --weight 0.5 --cost-preset chile --whole-shares
```

`--strategy` picks the rule that sets the target weight:

```bash
uv run kx bot plan --strategy sma-cross --fast 20 --slow 100
```

`hold` (the default) uses `--weight` as written. `sma-cross` ignores `--weight` and asks
the rule the second stop teaches: fully invested while the short average is above the
long one, in cash otherwise. The decision is taken at the last cached close, so the paper
account fills it on the next session — the same convention the dashboard simulates.

If the cache is shorter than `--slow`, the bot refuses instead of answering `0%`: the
rule is genuinely flat while it warms up, but on a real account that reads as "liquidate
because I have no history".

Useful flags: `--symbol` (default `SPY`), `--weight` (fraction of account value, 0 to 1,
default `1.0`), `--strategy` (`hold` or `sma-cross`), `--fast` and `--slow` (crossover
windows in bars, default 20 and 100), `--cost-preset` (`alpaca` or `chile`),
`--initial-cash`, `--contribution`, `--whole-shares`, `--data-dir`, and `--live`
(accepted so it can be refused with a reason).

Exit codes: `0` when a plan was printed, `1` when the command refused or failed, with the
reason on stderr as `kx: <reason>`. `kx bot` with no subcommand prints the bot's help and
exits `0`; an invalid `--strategy` or `--cost-preset` value is caught by the argument
parser and exits `2`. Scripts can rely on the first two.

## 4. What it will and will not do

It will:

* read the paper account's equity and current position;
* size one market order toward the target weight, using the ledger's commission and
  spread arithmetic — the same numbers the dashboard charges;
* take that target weight either from `--weight` or from the crossover rule
  (`--strategy sma-cross`), so the second stop is not dashboard-only;
* print the order with the price on the chart (`ref`) and the price the ledger assumes
  you get (`exec`), plus the commission and the CLP notional;
* with `--send`, submit that order to the paper host only.

It will not:

* trade real money. `live=True` raises `NotImplementedError` and the CLI exits 1 with
  that message. There is no code path to the live host.
* submit anything by default. `send` defaults to `False` in the library and in the CLI.
* move money for you. `--contribution` is informational: funding the account is a
  transfer you make yourself, and the bot invests whatever the account already holds.
* sell down to a target. The ledger's rebalance buys toward the target and liquidates
  completely at weight `0`; it does not trim an overweight position. That is the
  buy & hold rule, not an omission.
* place limit orders, shorts, margin, options or crypto. One market order, day duration,
  fractional shares by default (`--whole-shares` turns that off).
* model Chilean tax or inflation on the order. Both are in the dashboard comparison, not
  in the order path.

## 5. Costs

Two presets, shared with the dashboard so a plan and a simulation agree. Both read from
`PRESETS_BY_KEY` in `src/kx/presets.py`; the dashboard's labels live beside it in
`PRESETS_BY_LABEL`, so there is one literal to change and no second copy to drift:

| Preset | Commission | Half spread | Slippage |
| --- | --- | --- | --- |
| `alpaca` (default) | 0 bps | 5 bps | 5 bps |
| `chile` | 30 bps | 10 bps | 10 bps |

They are estimates, not a quote. Edit `src/kx/presets.py` to match your own broker, then
re-read the plan: the difference between `ref` and `exec` on the printout is the friction
you are paying for the round trip.

## 6. Why a paper account proves plumbing, not edge

A paper account proves the plumbing — keys, order types, fills, position accounting — and
proves nothing about edge: paper fills are simulated against live quotes but never move
the book, so they systematically understate the friction you would actually pay. A single
decision has no edge to test, only a horizon, and two averages crossing is a rule with a
cost, not an edge.

## 7. Troubleshooting

| Message | Fix |
| --- | --- |
| `KX_ALPACA_KEY and KX_ALPACA_SECRET are not set` | Export both variables in this shell (section 2). |
| `alpaca-py is not installed` | `uv sync --extra bot` |
| `no cached series at ...` | `uv run kx data fetch --symbol SPY` |
| `the cached series has N bars but the rule needs at least 100` | Fetch more history: `kx data fetch --start 2005-01-01`, or lower `--slow`. |
| `live trading is refused` | Drop `--live`. This project has no live path. |

Nothing here is investment advice: it is a cost model with an order button that only
works on simulated money.
