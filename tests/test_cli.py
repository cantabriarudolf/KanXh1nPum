"""CLI surface: file naming, defaults, and failure reporting."""

from __future__ import annotations

from pathlib import Path

import pytest

from kx.cli import app_path, build_parser, main, slug


def test_slug_maps_provider_symbols_to_filenames() -> None:
    assert slug("SPY") == "SPY"
    assert slug("CLP=X") == "CLP_X"
    assert slug("^GSPC") == "GSPC"
    assert slug("brk-b") == "BRK_B"


def test_slug_rejects_symbols_without_usable_characters() -> None:
    with pytest.raises(ValueError, match="no usable characters"):
        slug("===")


def test_data_fetch_defaults_are_the_safe_ones() -> None:
    args = build_parser().parse_args(["data", "fetch", "--symbol", "SPY"])

    assert (args.command, args.data_command) == ("data", "fetch")
    assert args.start == "2005-01-01"
    assert args.out == "data/cache"
    assert args.fx == "CLP=X"
    assert args.skip_cpi is False


def test_missing_cache_exits_nonzero_and_says_what_to_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["data", "show", "--file", str(tmp_path / "nope.csv")])

    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert "kx data fetch" in captured.err


def test_app_path_points_at_the_real_entry_point() -> None:
    path = app_path()

    assert path.name == "streamlit_app.py"
    assert path.exists()


def test_app_command_accepts_headless() -> None:
    args = build_parser().parse_args(["app", "--headless"])

    assert args.command == "app"
    assert args.headless is True
