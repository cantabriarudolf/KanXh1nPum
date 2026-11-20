# Proposal — one identity for the tour

Status: **implemented on `feat/app-identity`, awaiting a human look.**
Evidence behind it: [`audit.md`](audit.md).

## Governing idea

The tour is an instrument panel, not a dashboard: dark ground, brass rules that separate
measurements, and one pink accent reserved for the number that hurts — the money you paid to
someone else.

## Three anchor decisions

1. **Adopt the band's ground instead of Streamlit's light default.**
   `base=dark`, `backgroundColor=#0a0a0b`.
   *Tradeoff:* long prose is harder to read on dark. Mitigated by keeping body text at
   `#c9ccd1` — the band's dominant colour, 19 occurrences — and putting surfaces at `#141416`
   rather than on pure black.
2. **Brass is structure only.**
   `primaryColor=#c0a062` drives headings, focus and the tour's progress bar; `#8a6d3f` draws
   the dividers.
   *Tradeoff:* brass on dark reads "luxury fintech" the moment it touches data, so it never
   marks a series.
3. **Pink is semantic.**
   `#f095c8` means cost, and nothing else.
   *Tradeoff:* with one accent the charts cannot use it for a second line, so equity stays
   ink. This is the decision that makes the styling *mean* something instead of decorating:
   if it is pink, it is friction.

## Tokens

| Token | Value | Source |
| --- | --- | --- |
| ground | `#0a0a0b` | band background |
| surface | `#141416` | derived, lifted ground |
| brass | `#c0a062` | band rules |
| brass dim | `#8a6d3f` | band rules |
| accent (cost) | `#f095c8` | band |
| ink | `#c9ccd1` | band, dominant colour |

## Rejected, and why

- **A generic "fintech dark mode" with gradients and glow.** No source for it in the band;
  this is the anti-generic gate, not a preference.
- **New fonts from a CDN.** Adds a network dependency to a project whose tests run offline.
- **Swapping the chart library.** The audit found no data-visualisation defect, and the
  skill forbids rebuilding.
- **Restructuring the sidebar.** The tour navigation works and S7 is already satisfied.
- **A wordmark inside the band.** The asset is a plate carrying "powered by", not a title, so
  the `h1` stays and the plate sits above it.

## Files

- Changed: `app/streamlit_app.py` (style block + masthead), `tests/test_app.py` (one test).
- New: `.streamlit/config.toml`.
- Untouched: every `src/kx/` module, `assets/band.svg`, all tour copy and content.

## Validation

- `uv run pytest` → 137 passed. `uv run ruff check` → clean.
- Streamlit reads the theme: `theme.base=dark`, `primaryColor=#c0a062`,
  `backgroundColor=#0a0a0b`, `textColor=#c9ccd1`.
- **No visual check has run.** No screenshot was taken and none is claimed: the visual
  judgement belongs to a human opening `http://localhost:8501`.
