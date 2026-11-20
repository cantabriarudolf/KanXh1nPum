# Audit — KanXh1nPum Streamlit tour

Date: 2026-11-20 · Branch `feat/app-identity` · Base `c119340`

Snapshot before the first write:
`sha256 app/streamlit_app.py 891f67bf…`, `sha256 assets/band.svg f71d0a9e…`
Rollback: `git checkout main && git branch -D feat/app-identity`

## Audience, one line

Someone in Chile who has never invested, is deciding whether to start, and has already been
told that a deposit at 4,6% is the safe choice. They are not comparing features; they are
deciding whether to believe a number. Source: `odd/tasks/v1-guided-tour.md` L1, S2, S3, S5.

## S1 — the product does not look like its own project

| # | Evidence | Measured |
| --- | --- | --- |
| 1 | `app/streamlit_app.py:450` — `set_page_config` sets only `page_title`, `page_icon`, `layout` | 0 of 5 brand colours referenced |
| 2 | `.streamlit/config.toml` absent | theme is Streamlit's default: light ground, `#FF4B4B` accent |
| 3 | `assets/band.svg` referenced only from `README.md` | 0 references under `app/` |
| 4 | `assets/band.svg` palette, by occurrence | `#c9ccd1` ×19, `#f095c8` ×5, `#c0a062` ×4, `#8a6d3f` ×3, `#0a0a0b` ×1 |

A reader who arrives from the repo to the app sees two different products. The repo already
made the aesthetic decision; the app ignores it. This is the finding that matters: it is not
a taste gap, it is an incoherence.

## S2 — the honest views carry no visual weight

| # | Evidence | Measured |
| --- | --- | --- |
| 5 | `render_cost_expander`, `render_best_days_expander`, `render_panic_expander`, `render_drawdown_expander` | 4 expanders, identical default styling, no colour semantics |
| 6 | sidebar `st.progress` | inherits the default accent, unrelated to the brand |
| 7 | `clp()` / `pct()` | format numbers correctly; nothing distinguishes a cost from a return typographically |

The four views are the product's argument (S9, "no vende humo"). Today they look like four
accordions.

## S3 — polish

| # | Evidence | Measured |
| --- | --- | --- |
| 8 | `page_icon="🧭"` | an emoji, not the project mark |
| 9 | `assets/band.svg` | 1200×240 intrinsic, no consumer constrains it; would overflow below 1200px |

## Out of scope, named

- No backend, no data, no cost model touched. The audit found no defect there.
- No copy invented: every string stays as written.
