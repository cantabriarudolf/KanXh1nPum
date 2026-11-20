"""What a peso does at a Chilean bank, stated three ways.

Nominal, real, and real after tax are three different numbers, and the gap between them
is the whole argument for looking beyond a deposit. The most useful output here is not
a return: it is the tax rate at which the deposit stops paying anything.
"""

from __future__ import annotations

from dataclasses import dataclass

from kx.reference import ChileSnapshot


@dataclass(frozen=True)
class DepositRow:
    rung: str
    nominal: float
    real: float
    real_after_tax: float
    as_of: str
    source: str


def real_return(nominal: float, inflation: float) -> float:
    """Fisher, not subtraction. Four percent against five is not minus one percent."""
    if inflation <= -1.0:
        raise ValueError("inflation must be greater than -100%")
    return (1.0 + nominal) / (1.0 + inflation) - 1.0


def after_tax(nominal: float, tax_rate: float) -> float:
    """Interest in Chile is taxed at the marginal rate; the principal is not."""
    if not 0.0 <= tax_rate < 1.0:
        raise ValueError("tax_rate must be between 0 and 1")
    return nominal * (1.0 - tax_rate)


def real_after_tax(nominal: float, inflation: float, tax_rate: float) -> float:
    return real_return(after_tax(nominal, tax_rate), inflation)


def break_even_tax_rate(nominal: float, inflation: float) -> float:
    """The marginal rate at which the deposit's real return reaches zero.

    Below it, the deposit preserves purchasing power. Above it, the deposit loses money
    while looking like it grows.
    """
    if nominal <= 0.0:
        raise ValueError("nominal rate must be positive")
    return max(0.0, 1.0 - inflation / nominal)


def deposit_table(snapshot: ChileSnapshot, tax_rate: float = 0.0) -> list[DepositRow]:
    """The deposit ladder, each rung in nominal, real and real-after-tax terms."""
    return [
        DepositRow(
            rung=rung,
            nominal=nominal,
            real=real_return(nominal, snapshot.ipc_12m),
            real_after_tax=real_after_tax(nominal, snapshot.ipc_12m, tax_rate),
            as_of=snapshot.as_of,
            source=snapshot.source,
        )
        for rung, nominal in snapshot.dpf
    ]
