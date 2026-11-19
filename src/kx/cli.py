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

    bot = commands.add_parser(
        "bot",
        help="paper-trade buy & hold on Alpaca's demo account, plan-only unless --send",
    )
    bot_commands = bot.add_subparsers(dest="bot_command", metavar="<bot-command>")

    bot_plan = bot_commands.add_parser(
        "plan", help="print the orders the bot would send (no network, no keys)"
    )
    _add_bot_arguments(bot_plan)

    bot_run = bot_commands.add_parser(
        "run", help="read the paper account and plan; submit only with --send"
    )
    _add_bot_arguments(bot_run)
    bot_run.add_argument(
        "--send",
        action="store_true",
        help="submit the planned orders to the paper account (needs KX_ALPACA_KEY/SECRET)",
    )

    return parser


def _add_bot_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--symbol", default="SPY", help="ticker to hold, default SPY")
    parser.add_argument(
        "--weight", type=float, default=1.0, help="fraction of account value to hold (0 to 1)"
    )
    parser.add_argument(
        "--strategy",
        default="hold",
        choices=("hold", "sma-cross"),
        help="rule that sets the weight: hold uses --weight, sma-cross reads the cache",
    )
    parser.add_argument(
        "--fast", type=int, default=20, help="sma-cross short window in bars, default 20"
    )
    parser.add_argument(
        "--slow", type=int, default=100, help="sma-cross long window in bars, default 100"
    )
    parser.add_argument(
        "--cost-preset", default="alpaca", help="cost model: alpaca or chile (docs/bot.md)"
    )
    parser.add_argument(
        "--initial-cash", type=float, default=1_000_000.0, help="CLP to plan with"
    )
    parser.add_argument(
        "--contribution", type=float, default=50_000.0, help="monthly CLP you add yourself"
    )
    parser.add_argument(
        "--whole-shares", action="store_true", help="buy whole shares instead of fractions"
    )
    parser.add_argument("--data-dir", default=None, help="cache directory, default data/cache")
    parser.add_argument(
        "--live",
        action="store_true",
        help="refused on purpose: this project never trades real money",
    )


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


def _bot_config(args: argparse.Namespace):
    from kx.bot import BotConfig

    return BotConfig(
        initial_cash_clp=args.initial_cash,
        contribution_clp=args.contribution,
        symbol=args.symbol,
        cost_preset=args.cost_preset,
        fractional=not args.whole_shares,
        strategy=args.strategy,
        fast=args.fast,
        slow=args.slow,
    )


def _bot_market(args: argparse.Namespace):
    """The cached frame: the bot decides on what is already on disk, never on a live quote."""
    from kx.loader import load_market

    return load_market(args.data_dir, symbol=args.symbol).frame


def _bot_weight(config, frame, args: argparse.Namespace) -> float:
    from kx.bot import strategy_weight

    return strategy_weight(config, frame, args.weight)


def _bot_plan(args: argparse.Namespace) -> int:
    from kx.bot import DryRunBroker, describe, plan

    config = _bot_config(args)
    frame = _bot_market(args)
    weight = _bot_weight(config, frame, args)
    broker = DryRunBroker(equity_clp=config.initial_cash_clp)
    print(describe(plan(config, frame.iloc[-1], weight, broker)))
    return 0


def _bot_run(args: argparse.Namespace) -> int:
    from kx.bot import describe, paper_broker, run

    config = _bot_config(args)
    # Ask for credentials first: it is the refusal a beginner needs to see, and it keeps
    # the plan honest — it is computed against the real paper account, not a guess.
    broker = paper_broker()
    frame = _bot_market(args)
    weight = _bot_weight(config, frame, args)
    result = run(config, frame.iloc[-1], weight, broker, send=args.send)
    print(describe(result))
    return 0


def _bot(args: argparse.Namespace) -> int:
    from kx.bot import LIVE_REFUSED

    # Refuse live trading before any credential, cache or network work happens.
    if args.live:
        print(f"kx: {LIVE_REFUSED}", file=sys.stderr)
        return 1

    try:
        return _bot_run(args) if args.bot_command == "run" else _bot_plan(args)
    except (KxError, ValueError) as exc:
        # ValueError comes from the rule and the bar validators: a corrupted cache is a
        # message the person can act on, not a traceback. docs/bot.md promises that.
        print(f"kx: {exc}", file=sys.stderr)
        return 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "app":
        return _app(args)

    if args.command == "bot":
        if args.bot_command is None:
            parser.parse_args(["bot", "--help"])
            return 0
        return _bot(args)

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
