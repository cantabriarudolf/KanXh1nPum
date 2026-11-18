# KanXh1nPum

A cost-aware simulation lab and a guided tour through trading timeframes, built for someone
who has never invested and lives in Chile.

**What this is not:** a signal service, a profitable bot, financial advice, or a promise.
It is a lab that shows what actually lands in your account after spread, commission,
slippage, currency and inflation — and a tour that explains why the timeframes you choose
change the game you are playing.

## The thesis

The shorter the timeframe, the less the market pays you for patience and the more you have
to earn through skill. Over years, an index hands you the risk premium for free. Over
minutes, you are competing with machines that pay for colocation and you are paying worse
fees than they are.

Every screen in the tour exists to make that sentence visible with numbers instead of prose.

## The Chilean anchor

Returns are meaningless without a benchmark. As of October 2026 (Banco Central de Chile,
INE), the thing your money does at a bank is:

| Instrument | Nominal annual | Real (vs 4.5% CPI) |
| --- | --- | --- |
| DPF 30-89 days (system average) | 4.17% | -0.3% before tax |
| DPF 90 days - 1 year (system average) | 4.60% | +0.1% before tax |
| DPF 1-3 years (system average) | 5.40% | +0.9% before tax |
| Policy rate (TPM) | 4.50% | 0.0% |

Interest income is taxed, so the real return after tax can be negative. That is the honest
baseline any strategy has to beat, and the dashboard never hides it.

## Status

Early. The v1 plan and its specs live in [`odd/tasks/v1-guided-tour.md`](odd/tasks/v1-guided-tour.md).
Reuse decisions and rejected alternatives live in [`docs/decisions.md`](docs/decisions.md).

## Development

```bash
uv sync --extra dev
uv run pytest
uv run ruff check
```

## Disclaimer

Educational and experimental software. Nothing here is investment advice, nor a
recommendation to buy or sell any instrument. Past performance is not indicative of future
results. Simulated results are not real trading results. If you cannot afford to lose the
money, do not put it at risk.

## License

MIT.
