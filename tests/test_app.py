"""The app must render without exploding, with data and without it.

A dashboard that only works on the author's machine is not a dashboard. AppTest runs the
real script headlessly, so a broken widget or a bad f-string fails here instead of in
front of whoever opens the link.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("streamlit")

from streamlit.testing.v1 import AppTest  # noqa: E402

from kx.data import load_series, write_series  # noqa: E402

APP = Path(__file__).parents[1] / "app" / "streamlit_app.py"
FIXTURES = Path(__file__).parent / "fixtures"


def write_cache(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    write_series(load_series(FIXTURES / "price_tiny.csv"), directory / "SPY.csv")
    write_series(load_series(FIXTURES / "fx_tiny.csv"), directory / "CLP_X.csv")
    write_series(load_series(FIXTURES / "cpi_tiny.csv"), directory / "CPI_CHL.csv")


def write_cache_with_history(directory: Path) -> None:
    """A sample long enough for the default 20/100 crossover to trade several times."""
    directory.mkdir(parents=True, exist_ok=True)
    index = pd.bdate_range("2022-01-03", periods=400)
    closes = 100.0 + 20.0 * np.sin(np.arange(len(index)) / 20.0) + np.arange(len(index)) * 0.05
    write_series(pd.Series(closes, index=index, dtype="float64"), directory / "SPY.csv")
    write_series(pd.Series(900.0, index=index, dtype="float64"), directory / "CLP_X.csv")
    write_series(
        pd.Series(np.linspace(100.0, 108.0, len(index)), index=index, dtype="float64"),
        directory / "CPI_CHL.csv",
    )


def comparison_table(at: AppTest) -> pd.DataFrame:
    return next(frame.value for frame in at.dataframe if "Regla" in frame.value.columns)


def frequency_table(at: AppTest) -> pd.DataFrame:
    return next(frame.value for frame in at.dataframe if "Ventanas" in frame.value.columns)


def money(value: str) -> int:
    return int(value.replace("$", "").replace(".", ""))


def test_app_renders_with_cached_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_cache(tmp_path)
    monkeypatch.setenv("KX_DATA_DIR", str(tmp_path))

    at = AppTest.from_file(str(APP), default_timeout=60).run()

    assert not at.exception
    assert "KanXh1nPum" in at.title[0].value
    assert "0 · La realidad chilena" in at.sidebar.radio[0].options


def test_app_explains_how_to_fetch_data_instead_of_crashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KX_DATA_DIR", str(tmp_path / "empty"))

    at = AppTest.from_file(str(APP), default_timeout=60).run()

    assert not at.exception
    assert any("kx data fetch" in error.value for error in at.error)


def test_buy_and_hold_stop_renders_and_reports_costs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_cache(tmp_path)
    monkeypatch.setenv("KX_DATA_DIR", str(tmp_path))

    at = AppTest.from_file(str(APP), default_timeout=60).run()
    at.sidebar.radio[0].set_value("1 · Comprar y aguantar").run()

    assert not at.exception
    assert any("Comprar y aguantar" in str(header.value) for header in at.header)
    labels = [metric.label for metric in at.metric]
    assert "Aportaste en total" in labels
    assert "La misma plata en DPF" in labels
    # The four honest views must be on screen, not just the chart that motivated them.
    labels = [expander.label for expander in at.expander]
    assert "¿Cuánto te cuesta operar?" in labels
    assert "¿Y si te perdés los mejores días?" in labels
    assert "¿Y si vendías en pánico?" in labels
    assert "Las caídas que vas a vivir" in labels
    assert len(at.dataframe) >= 3


def test_swing_stop_renders_beside_buy_and_hold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_cache_with_history(tmp_path)
    monkeypatch.setenv("KX_DATA_DIR", str(tmp_path))

    at = AppTest.from_file(str(APP), default_timeout=60).run()
    at.sidebar.radio[0].set_value("2 · Cruzar medias").run()

    assert not at.exception
    assert any("Cruzar medias" in str(header.value) for header in at.header)
    assert "Cruzar medias no es un descubrimiento: es una regla, y las reglas se pagan." in [
        str(caption.value) for caption in at.caption
    ]

    labels = [expander.label for expander in at.expander]
    for view in (
        "¿Cuánto te cuesta operar?",
        "¿Y si te perdés los mejores días?",
        "¿Y si vendías en pánico?",
        "Las caídas que vas a vivir",
    ):
        assert view in labels

    # The comparison has to be on screen: same money, same period, two rules.
    comparison = comparison_table(at)
    assert comparison["Regla"].tolist() == ["Comprar y aguantar", "Cruzar medias"]
    assert comparison["Operaciones"].tolist() == [1, 5]
    friction = [money(value) for value in comparison["Fricción pagada"]]
    assert friction[1] > friction[0]


def test_swing_stop_survives_a_sample_shorter_than_its_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_cache(tmp_path)
    monkeypatch.setenv("KX_DATA_DIR", str(tmp_path))

    at = AppTest.from_file(str(APP), default_timeout=60).run()
    at.sidebar.radio[0].set_value("2 · Cruzar medias").run()

    assert not at.exception
    assert any("más corta que la media larga" in str(info.value) for info in at.info)
    assert len(comparison_table(at)) == 2


def test_no_emergency_fund_changes_the_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_cache(tmp_path)
    monkeypatch.setenv("KX_DATA_DIR", str(tmp_path))

    at = AppTest.from_file(str(APP), default_timeout=60).run()
    buffer_slider = next(s for s in at.sidebar.slider if "colchón" in s.label)
    buffer_slider.set_value(0).run()

    assert not at.exception
    assert any("colchón" in str(subheader.value).lower() for subheader in at.subheader)
    assert any("recomendación" in str(warning.value) for warning in at.warning)


def test_app_opens_with_the_project_masthead(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The tour carries the repo's own plate instead of opening on a bare title."""
    write_cache(tmp_path)
    monkeypatch.setenv("KX_DATA_DIR", str(tmp_path))

    at = AppTest.from_file(str(APP), default_timeout=60).run()

    assert not at.exception
    rendered = " ".join(str(block.value) for block in at.markdown)
    assert "kx-band" in rendered
    assert "<svg" in rendered
    assert "powered by" in rendered


def test_tour_shows_where_you_are_in_the_walk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S7 asks for visible progress: the tour must say which stop you are on."""
    write_cache(tmp_path)
    monkeypatch.setenv("KX_DATA_DIR", str(tmp_path))

    at = AppTest.from_file(str(APP), default_timeout=60).run()

    assert not at.exception
    assert len(at.sidebar.progress) == 1
    assert any("Parada 1 de 4" in str(caption.value) for caption in at.sidebar.caption)

    at.sidebar.radio[0].set_value("2 · Cruzar medias").run()

    assert any("Parada 3 de 4" in str(caption.value) for caption in at.sidebar.caption)


def test_tour_names_the_demo_account_and_how_to_reach_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S1/S3: the tour is where the beginner learns a demo account exists."""
    write_cache(tmp_path)
    monkeypatch.setenv("KX_DATA_DIR", str(tmp_path))

    at = AppTest.from_file(str(APP), default_timeout=60).run()

    assert not at.exception
    commands = " ".join(str(block.value) for block in at.sidebar.code)
    assert "kx bot plan" in commands
    assert "kx bot run --send" in commands
    # No key ever enters the dashboard: the account is wired from the shell.
    assert not at.text_input


def test_frequency_stop_charges_more_when_the_rule_trades_more(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stop's whole claim: moving more often costs more, measured, not promised."""
    write_cache_with_history(tmp_path)
    monkeypatch.setenv("KX_DATA_DIR", str(tmp_path))

    at = AppTest.from_file(str(APP), default_timeout=60).run()
    at.sidebar.radio[0].set_value("3 · Cada cuánto mover").run()

    assert not at.exception
    assert any("Cada cuánto mover" in str(header.value) for header in at.header)
    table = frequency_table(at)
    assert len(table) == 4

    busiest = table.loc[table["Operaciones"].idxmax()]
    calmest = table.loc[table["Operaciones"].idxmin()]
    assert busiest["Operaciones"] > calmest["Operaciones"]
    assert money(busiest["Fricción pagada"]) > money(calmest["Fricción pagada"])


def test_frequency_stop_survives_a_sample_shorter_than_its_shortest_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_cache(tmp_path)
    monkeypatch.setenv("KX_DATA_DIR", str(tmp_path))

    at = AppTest.from_file(str(APP), default_timeout=60).run()
    at.sidebar.radio[0].set_value("3 · Cada cuánto mover").run()

    assert not at.exception
    assert any("necesita 20" in str(info.value) for info in at.info)


def test_app_explains_a_misaligned_cache_instead_of_crashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An FX series that starts after the prices must not reach the beginner raw."""
    prices = pd.bdate_range("2024-01-02", periods=10)
    late_fx = pd.bdate_range("2024-01-08", periods=5)
    write_series(pd.Series(100.0, index=prices, dtype="float64"), tmp_path / "SPY.csv")
    write_series(pd.Series(900.0, index=late_fx, dtype="float64"), tmp_path / "CLP_X.csv")
    write_series(
        pd.Series(np.linspace(100.0, 101.0, len(prices)), index=prices, dtype="float64"),
        tmp_path / "CPI_CHL.csv",
    )
    monkeypatch.setenv("KX_DATA_DIR", str(tmp_path))

    at = AppTest.from_file(str(APP), default_timeout=60).run()

    assert not at.exception
    assert any("alinear" in str(error.value) for error in at.error)


def test_fixture_frame_is_what_the_app_expects() -> None:
    price = load_series(FIXTURES / "price_tiny.csv")
    assert isinstance(price.index, pd.DatetimeIndex)
    assert price.index.is_monotonic_increasing
