"""The Chilean anchor: what a peso does at a bank, and what tax does to it.

The claim this file has to keep honest is a modest one: a deposit does roughly nothing
in real terms. It is modest, it is checkable, and it is the baseline every strategy in
the tour must beat.
"""

from __future__ import annotations

import pytest

from kx.chile import (
    break_even_tax_rate,
    deposit_table,
    real_after_tax,
    real_return,
)
from kx.reference import CHILE_2026_11


def test_real_return_removes_inflation() -> None:
    assert real_return(nominal=0.046, inflation=0.045) == pytest.approx(
        (1.046 / 1.045) - 1.0, rel=1e-12
    )


def test_a_deposit_that_matches_inflation_returns_nothing_real() -> None:
    assert real_return(nominal=0.045, inflation=0.045) == pytest.approx(0.0, abs=1e-15)


def test_tax_is_charged_on_the_nominal_gain_only() -> None:
    assert real_after_tax(nominal=0.046, inflation=0.045, tax_rate=0.0) == pytest.approx(
        real_return(0.046, 0.045), rel=1e-15
    )
    assert real_after_tax(nominal=0.046, inflation=0.045, tax_rate=0.20) < 0.0


def test_break_even_tax_rate_is_where_the_deposit_stops_paying() -> None:
    rate = break_even_tax_rate(nominal=0.046, inflation=0.045)

    assert rate == pytest.approx(1.0 - 0.045 / 0.046, rel=1e-12)
    assert real_after_tax(0.046, 0.045, rate) == pytest.approx(0.0, abs=1e-12)


def test_break_even_is_zero_when_inflation_already_wins() -> None:
    assert break_even_tax_rate(nominal=0.04, inflation=0.05) == 0.0


def test_deposit_table_reports_nominal_real_and_after_tax() -> None:
    rows = deposit_table(CHILE_2026_11, tax_rate=0.20)

    assert [row.rung for row in rows] == ["30-89d", "90d-1a", "1-3a"]
    short = rows[0]
    assert short.nominal == pytest.approx(0.0417)
    assert short.real == pytest.approx(real_return(0.0417, CHILE_2026_11.ipc_12m), rel=1e-12)
    assert short.real_after_tax < short.real

    # The middle rung is the one the dashboard shows first: best rate you can get
    # without locking money up for a year.
    middle = rows[1]
    assert middle.nominal == pytest.approx(0.046)
    assert middle.real == pytest.approx(0.00096, abs=1e-5)
    assert middle.real_after_tax < 0.0


def test_deposit_table_carries_its_source_and_date() -> None:
    rows = deposit_table(CHILE_2026_11, tax_rate=0.0)

    for row in rows:
        assert row.as_of == CHILE_2026_11.as_of
        assert "Banco Central" in row.source
