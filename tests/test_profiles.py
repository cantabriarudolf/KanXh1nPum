"""Risk profiles: a category to explore, never a recommendation.

The distinction is not cosmetic. In Chile, telling a specific person what to do with
their money is regulated advice. Telling them what a category of portfolio has done,
and how badly it can hurt, is education. The tests below pin the wording too, because
copy drifts silently and the disclaimer is the part that must not.
"""

from __future__ import annotations

import pytest

from kx.profiles import Profile, suggest_profile


def test_no_emergency_fund_comes_before_any_investing() -> None:
    result = suggest_profile(horizon_years=10, drawdown_tolerance=0.4, emergency_fund_months=1)

    assert result.key == "primero_colchon"
    assert result.equity_weight == 0.0


def test_short_horizon_stays_conservative() -> None:
    result = suggest_profile(horizon_years=2, drawdown_tolerance=0.5, emergency_fund_months=6)

    assert result.key == "conservador"
    assert result.equity_weight <= 0.30


def test_long_horizon_with_tolerance_reaches_growth() -> None:
    result = suggest_profile(horizon_years=15, drawdown_tolerance=0.40, emergency_fund_months=6)

    assert result.key == "crecimiento"
    assert result.equity_weight >= 0.70


def test_low_tolerance_downgrades_one_step() -> None:
    bold = suggest_profile(horizon_years=15, drawdown_tolerance=0.40, emergency_fund_months=6)
    timid = suggest_profile(horizon_years=15, drawdown_tolerance=0.10, emergency_fund_months=6)

    assert timid.equity_weight < bold.equity_weight
    assert timid.key == "equilibrado"


def test_every_profile_refuses_to_be_advice() -> None:
    for horizon, tolerance in ((2, 0.5), (5, 0.3), (15, 0.4), (15, 0.05)):
        profile = suggest_profile(
            horizon_years=horizon, drawdown_tolerance=tolerance, emergency_fund_months=6
        )
        assert isinstance(profile, Profile)
        assert "no es una recomendación" in profile.not_advice.lower()
        assert profile.disclaimer


def test_negative_inputs_are_refused() -> None:
    with pytest.raises(ValueError, match="horizon"):
        suggest_profile(horizon_years=0, drawdown_tolerance=0.3, emergency_fund_months=6)
    with pytest.raises(ValueError, match="tolerance"):
        suggest_profile(horizon_years=5, drawdown_tolerance=1.5, emergency_fund_months=6)
