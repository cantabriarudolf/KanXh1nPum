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

## Voice

The copy is part of the identity, not a coat of paint on top of it. The register is the one
the project owner speaks in: Chilean, blunt, anti-academic, and self-aware enough to say
"podés creerle o no" out loud.

What the voice does:

- Opens by refusing to be a course: *"Esto no es un curso ni una forma académica de
  mirarlo."*
- Names the eroding number before any strategy: *"tu plata quieta en el banco cada día
  puede comprar menos cosas"*.
- Calls a term deposit what it is without insulting it: *"la forma más rata de guardar
  plata"*, which reaches the colchón and no further.
- Under-cuts itself where the evidence does, and never where it does not.

What the voice is not allowed to do — these are hard limits, not preferences:

- **No number changes.** Every figure, rate and label stays exactly as computed.
- **No promise.** It may sound confident; it may not predict a return.
- **No personalized advice.** The CMF framing survives the register: the profile still
  returns an illustrative category under stress, never "you should".
- **No self-contradiction.** The brief said *"la gracia es comprar y vender"*; the project's
  own stop 3 measures that moving more often costs more. The copy states the tension instead
  of picking a side quietly: *"Acá se cae el mito: la gracia no es comprar y vender."* A
  voice that lies to stay in character is worse than an academic one.

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
