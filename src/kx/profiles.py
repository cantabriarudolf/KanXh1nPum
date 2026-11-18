"""Risk profiles: a category to explore, never a recommendation.

Age is only a proxy for horizon, and a bad one: a 60-year-old who will not touch the
money for twenty years is not the same as a 30-year-old saving for a flat next year.
So the input here is horizon, tolerance and the emergency fund — and the output is a
category with a known worst case, not an instruction.
"""

from __future__ import annotations

from dataclasses import dataclass

DISCLAIMER = (
    "Esto describe cómo se comporta una categoría de cartera. No es asesoría financiera, "
    "no considera tu situación completa y no te dice qué hacer con tu plata."
)

NOT_ADVICE = (
    "No es una recomendación: es una categoría para explorar y estresar. "
    "La decisión, y el riesgo, son tuyos."
)

_MIN_EMERGENCY_MONTHS = 3
_LOW_TOLERANCE = 0.15

_LADDER: tuple[tuple[str, str, float], ...] = (
    ("conservador", "Conservador", 0.25),
    ("equilibrado", "Equilibrado", 0.55),
    ("crecimiento", "Crecimiento", 0.85),
)

_LADDER_KEYS = {key: index for index, (key, _, _) in enumerate(_LADDER)}


@dataclass(frozen=True)
class Profile:
    key: str
    name: str
    equity_weight: float
    fixed_income_weight: float
    horizon_years: float
    drawdown_tolerance: float
    stress_hint: str
    not_advice: str = NOT_ADVICE
    disclaimer: str = DISCLAIMER


def _park_first(horizon_years: float, drawdown_tolerance: float) -> Profile:
    return Profile(
        key="primero_colchon",
        name="Primero el colchón",
        equity_weight=0.0,
        fixed_income_weight=0.0,
        horizon_years=horizon_years,
        drawdown_tolerance=drawdown_tolerance,
        stress_hint=(
            "Antes de mirar rentabilidades: si un imprevisto te obliga a vender en el peor "
            "momento, ninguna estrategia te salva. Tres meses de gastos en algo líquido es "
            "el paso previo, no una alternativa."
        ),
    )


def suggest_profile(
    horizon_years: float,
    drawdown_tolerance: float,
    emergency_fund_months: float,
) -> Profile:
    """Map horizon, tolerance and cash buffer onto an exploratory category."""
    if horizon_years <= 0:
        raise ValueError("horizon must be greater than zero years")
    if not 0.0 <= drawdown_tolerance <= 1.0:
        raise ValueError("tolerance must be a fraction between 0 and 1")

    if emergency_fund_months < _MIN_EMERGENCY_MONTHS:
        return _park_first(horizon_years, drawdown_tolerance)

    if horizon_years < 3:
        level = 0
    elif horizon_years <= 7:
        level = 1
    else:
        level = 2

    if drawdown_tolerance < _LOW_TOLERANCE:
        level = max(0, level - 1)

    key, name, equity_weight = _LADDER[level]
    return Profile(
        key=key,
        name=name,
        equity_weight=equity_weight,
        fixed_income_weight=1.0 - equity_weight,
        horizon_years=horizon_years,
        drawdown_tolerance=drawdown_tolerance,
        stress_hint=(
            "El peor episodio de esta mezcla está simulado abajo, con las caídas reales del "
            "mercado. Léelo antes que el retorno: es el precio de entrada."
        ),
    )
