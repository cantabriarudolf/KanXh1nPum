# Decisions

Short records of what we reuse, what we own, and what we rejected on purpose. The rule that
governs all of them: **reuse where the wheel is the hard part, own where the wheel is the
point.**

## D1 — We do not adopt a full backtesting framework as the core

*Status: accepted (2026-11-18).*

A general backtester solves order-book simulation, corporate actions, multi-asset routing and
tick-level fills. That is the hard part of the domain, and it is not our problem: the tour
runs on daily bars, one instrument at a time, for someone with a few hundred dollars.

What our product actually differentiates is the cost and valuation pipeline — spread,
commission, slippage, USD/CLP, inflation to real returns, turnover tax, and the honest
comparison against a Chilean deposit. No open-source backtester models that set, because
none of them are aimed at a Chilean retail beginner.

So the core is a small, explicit ledger we own and can explain line by line. It is not a
general backtester and does not try to be.

Measured alternatives (2026-11):

| Option | Verdict |
| --- | --- |
| `backtesting.py` 0.6.6 | Alive (last commit Aug 2026) but AGPL-3.0, and its cost model stops at commission + spread. Would be a wrapper fighting us for the exact layer we care about. |
| `backtrader` | Dead. Last commit 2024-08-19. Do not build on it. |
| `vectorbt` (OSS) | In maintenance mode; active work moved to paid PRO. Documentation gaps are a real tax on a teaching codebase. |
| `freqtrade` | Very alive (2026.10) with dry-run built in, but crypto-only, GPL, and it would redefine the project's identity. Good reference to read, not to depend on. |
| `NautilusTrader` / `LEAN` | Correct when event-level execution and live trading are the job. Overkill here; revisit only if the tour ever needs intraday fills at real depth. |

Revisit trigger: if a stop in the tour needs intraday order simulation, adopt NautilusTrader
rather than growing our own.

## D2 — Alpaca paper trading as the demo account (S1)

*Status: accepted (2026-11-18).*

Free, open globally, no US residency and no brokerage account required, USD 100,000 simulated
balance, separate `paper-api` host, unlimited resets. That is exactly the "demo account" the
product needs, and it is real enough to teach order types and fills.

Rejected: MetaTrader 5 (its Python bridge is Windows-only, and this project lives on Linux),
Binance testnet as the primary venue (crypto-first is the worst classroom for a beginner).

## D3 — Barriers we keep, and barriers we remove

The product removes the small training wheels: environment setup, jargon-only explanations,
and the guessing about what a chart means. It keeps the honest barriers: costs are never
zero, draws are never smooth, and the benchmark never disappears from the screen.

## D4 — No ML, no hyperparameter search, no LLM in the loop (S8)

The tour teaches reading, not optimization. If a chart needs a model to be interpreted, the
chart is wrong.

## D5 — Language

Code, tests, technical docs and commit messages in English. Product copy and educational
content in Spanish (Chile), because that is who the tour is for.
