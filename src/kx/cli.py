"""Command line entry point for KanXh1nPum."""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from pathlib import Path

from kx import __version__
from kx.data.errors import KxError

_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9]+")


def slug(symbol: str) -> str:
    """Turn a provider symbol into a file name: CLP=X -> CLP_X."""
    cleaned = _UNSAFE_FILENAME.sub("_", symbol).strip("_").upper()
    if not cleaned:
        raise ValueError(f"symbol {symbol!r} has no usable characters")
    return cleaned


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kx",
        description="Cost-aware simulation lab for first-time investors (Chile).",
        epilog="Every number this tool prints is a simulation with costs applied, not a forecast.",
    )
    parser.add_argument("--version", action="version", version=f"kx {__version__}")
    commands = parser.add_subparsers(dest="command", metavar="<command>")

    data = commands.add_parser("data", help="fetch and inspect the input series")
    data_commands = data.add_subparsers(dest="data_command", metavar="<data-command>")

    fetch = data_commands.add_parser("fetch", help="download series into the cache directory")
    fetch.add_argument("--symbol", action="append", required=True, help="repeatable, e.g. SPY")
    fetch.add_argument("--start", default="2005-01-01", help="first date (YYYY-MM-DD)")
    fetch.add_argument("--end", default=None, help="last date (YYYY-MM-DD), default today")
    fetch.add_argument("--out", default="data/cache", help="cache directory")
    fetch.add_argument("--fx", default="CLP=X", help="CLP per USD symbol")
    fetch.add_argument("--skip-cpi", action="store_true", help="do not download the CPI index")
    fetch.add_argument("--country", default="CHL", help="World Bank country code for CPI")

    app = commands.add_parser("app", help="open the guided tour in the browser")
    app.add_argument("--headless", action="store_true", help="do not open a browser")

    show = data_commands.add_parser("show", help="print a cached series")
    show.add_argument("--file", required=True, help="path to a cached .csv")
    show.add_argument("--rows", type=int, default=5, help="rows to print from each end")

    return parser


def _describe(path, series) -> str:
    return f"{path}  {len(series)} rows  {series.index[0].date()} -> {series.index[-1].date()}"


def _fetch(args: argparse.Namespace) -> int:
    from pathlib import Path

    from kx.data.sources import fetch_cpi, fetch_fx, fetch_prices
    from kx.data.store import write_series

    out = Path(args.out)
    written: list[str] = []

    for symbol in args.symbol:
        series = fetch_prices(symbol, start=args.start, end=args.end)
        path = out / f"{slug(symbol)}.csv"
        write_series(series, path)
        written.append(_describe(path, series))

    fx = fetch_fx(args.start, end=args.end, pair=args.fx)
    path = out / f"{slug(args.fx)}.csv"
    write_series(fx, path)
    written.append(_describe(path, fx))

    if not args.skip_cpi:
        cpi = fetch_cpi(args.country)
        path = out / f"CPI_{args.country.upper()}.csv"
        write_series(cpi, path)
        written.append(_describe(path, cpi))

    for line in written:
        print(line)
    return 0


def app_path() -> Path:
    """Locate the Streamlit entry point, whether installed or run from the repo."""
    for candidate in (
        Path(__file__).resolve().parents[2] / "app" / "streamlit_app.py",
        Path.cwd() / "app" / "streamlit_app.py",
    ):
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "app/streamlit_app.py not found; run `kx app` from the project root"
    )


def _app(args: argparse.Namespace) -> int:
    import subprocess

    command = [sys.executable, "-m", "streamlit", "run", str(app_path())]
    if args.headless:
        command += ["--server.headless", "true"]
    try:
        return subprocess.call(command)
    except FileNotFoundError as exc:
        print("kx: streamlit is not installed; run `uv sync --extra app`", file=sys.stderr)
        raise SystemExit(1) from exc


def _show(args: argparse.Namespace) -> int:
    from kx.data.store import load_series

    series = load_series(args.file)
    print(f"{args.file}: {len(series)} rows, {series.index[0].date()} -> {series.index[-1].date()}")
    print(series.head(args.rows).to_string())
    print("...")
    print(series.tail(args.rows).to_string())
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "app":
        return _app(args)

    if args.command == "data":
        if args.data_command is None:
            parser.parse_args(["data", "--help"])
            return 0

        handler = _fetch if args.data_command == "fetch" else _show
        try:
            return handler(args)
        except KxError as exc:
            print(f"kx: {exc}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
