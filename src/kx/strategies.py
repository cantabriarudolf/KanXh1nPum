"""Strategy rules: signals the ledger can execute without being rewritten.

One rule lives here, and it exists to prove the point of the second stop in the tour:
the cost layer does not care what produced a weight. Change the rule, keep the
arithmetic.

The convention that keeps the engine honest is stated once, here:

* `sma_crossover` returns a target weight for bar *t* using prices up to **and
  including** bar *t*. That is a decision made at the close, not a fill.
* The ledger already fills a decision on bar *t* on bar *t+1*. So the series is
  returned unshifted. Shifting it here would fill on *t+2* in disguise, and shifting
  it the other way would let the rule trade a price it had not seen yet.

Long only: the weight is either 1.0 (fully invested) or 0.0 (in cash). The rule never
goes short, so the worst it can do is watch from the sideline.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _validate(prices: pd.Series, fast: int, slow: int) -> None:
    for name, value in (("fast", fast), ("slow", slow)):
        if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
            raise ValueError(f"{name} must be a whole number of bars, got {value!r}")
        if value < 1:
            raise ValueError(f"{name} must be at least 1, got {value}")
    if fast >= slow:
        raise ValueError(f"fast ({fast}) must be smaller than slow ({slow})")

    if not prices.index.is_monotonic_increasing:
        raise ValueError("prices index must be sorted by date")
    if not prices.index.is_unique:
        raise ValueError("prices index must have unique dates")

    gaps = int(prices.isna().sum())
    if gaps:
        raise ValueError(
            f"prices has {gaps} missing prices; fill or drop the gaps before asking the "
            "rule, because a gap is a data bug and not a flat position"
        )


def sma_crossover(prices: pd.Series, fast: int = 20, slow: int = 100) -> pd.Series:
    """Long while the `fast` simple average is above the `slow` one, flat otherwise.

    Bars before the `slow` window is full are 0.0: the rule does not guess. The result
    is a target-weight series ready to feed `kx.ledger.simulate`, with no shift applied
    (see the module docstring for why).
    """
    _validate(prices, fast, slow)

    values = prices.astype("float64")
    fast_average = values.rolling(window=fast, min_periods=fast).mean()
    slow_average = values.rolling(window=slow, min_periods=slow).mean()

    weights = (fast_average > slow_average).astype("float64")
    return weights.rename("target_weight")
