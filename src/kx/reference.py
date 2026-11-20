"""Chilean reference numbers, with the date and the source attached.

Hard-coded on purpose: a beginner's dashboard must not break because a government API is
down. The staleness is visible instead of hidden — every row carries `as_of` and
`source`, and the UI prints them next to the number.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChileSnapshot:
    """One dated reading of the Chilean rates a beginner actually faces."""

    as_of: str
    tpm: float
    ipc_12m: float
    uf_clp: float
    dpf: tuple[tuple[str, float], ...]
    source: str


# Banco Central de Chile, Informe Mensual de Estadísticas Monetarias y Financieras,
# captaciones en pesos, promedio del sistema (octubre 2026). CPI 12m: INE (octubre 2026).
CHILE_2026_11 = ChileSnapshot(
    as_of="2026-11",
    tpm=0.0450,
    ipc_12m=0.0450,
    uf_clp=41_330.0,
    dpf=(("30-89d", 0.0417), ("90d-1a", 0.0460), ("1-3a", 0.0540)),
    source="Banco Central de Chile (BDE) e INE; promedio del sistema, octubre 2026",
)
