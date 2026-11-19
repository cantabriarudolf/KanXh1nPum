"""The paper bot: safe by default, and it borrows the ledger's cost arithmetic.

Every test here exists because the bot can reach an account. A runner that submits an
order by accident, or that can touch real money, is worse than no runner at all — so the
defaults, the refusals and the exact error messages are all pinned below.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import pytest

from kx import bot as bot_module
from kx.bot import (
    KEY_ENV,
    LIVE_REFUSED,
    SECRET_ENV,
    AlpacaPaperBroker,
    BotConfig,
    BotError,
    DryRunBroker,
    OrderIntent,
    describe,
    paper_broker,
    plan,
    run,
    strategy_weight,
)
from kx.cli import build_parser, main
from kx.data import FX, PRICE, load_series, write_series
from kx.ledger import buy_and_hold, simulate

FIXTURES = Path(__file__).parent / "fixtures"
DATES = pd.bdate_range("2024-01-02", periods=5)

MISSING_KEYS = (
    "KX_ALPACA_KEY and KX_ALPACA_SECRET are not set: export KX_ALPACA_KEY and "
    "KX_ALPACA_SECRET with your Alpaca paper keys (docs/bot.md says where to click), "
    "then retry. Nothing is sent without them."
)


def make_frame(prices: Sequence[float] | None = None, fx: float = 1000.0) -> pd.DataFrame:
    values = [100.0] * 5 if prices is None else list(prices)
    index = DATES[: len(values)]
    return pd.DataFrame(
        {
            PRICE: pd.Series(values, index=index, dtype="float64"),
            FX: pd.Series([fx] * len(values), index=index, dtype="float64"),
        }
    )


@dataclass
class FakeBroker:
    """An account that records what it was asked to do and never talks to anyone."""

    equity_clp: float = 1_000_000.0
    qty: float = 0.0
    sent: list[OrderIntent] = field(default_factory=list)

    def account_value_clp(self, fx: float) -> float:
        return self.equity_clp

    def position_qty(self, symbol: str) -> float:
        return self.qty

    def submit(self, order: OrderIntent) -> str:
        self.sent.append(order)
        return f"fake-{len(self.sent)}"


def write_cache(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    write_series(load_series(FIXTURES / "price_tiny.csv"), directory / "SPY.csv")
    write_series(load_series(FIXTURES / "fx_tiny.csv"), directory / "CLP_X.csv")
    return directory


class FakePositionClient:
    """An account client that answers one position call, or raises what it was given."""

    def __init__(self, position: object = None, raises: BaseException | None = None) -> None:
        self._position = position
        self._raises = raises

    def get_open_position(self, symbol: str) -> object:
        if self._raises is not None:
            raise self._raises
        return self._position


def fake_alpaca_errors(monkeypatch: pytest.MonkeyPatch) -> type[Exception]:
    """Stand in for alpaca.common.exceptions so APIError is testable without the extra."""

    class APIError(Exception):
        def __init__(self, message: str, status_code: int | None = None) -> None:
            super().__init__(message)
            self.status_code = status_code

    module = types.ModuleType("alpaca.common.exceptions")
    module.APIError = APIError  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "alpaca", types.ModuleType("alpaca"))
    monkeypatch.setitem(sys.modules, "alpaca.common", types.ModuleType("alpaca.common"))
    monkeypatch.setitem(sys.modules, "alpaca.common.exceptions", module)
    return APIError


def test_plan_returns_the_intent_and_sends_nothing() -> None:
    frame = make_frame()
    broker = FakeBroker()

    result = plan(BotConfig(), frame.iloc[-1], 1.0, broker)

    assert broker.sent == []
    assert result.sent is False
    assert result.order_ids == ()
    assert len(result.intents) == 1
    assert (result.intents[0].symbol, result.intents[0].side) == ("SPY", "buy")
    assert result.intents[0].qty > 0.0


def test_run_without_send_is_plan_only() -> None:
    broker = FakeBroker()

    result = run(BotConfig(), make_frame().iloc[-1], 1.0, broker)

    assert broker.sent == []
    assert result.sent is False


def test_send_true_is_the_only_path_that_reaches_the_broker() -> None:
    broker = FakeBroker()

    result = run(BotConfig(), make_frame().iloc[-1], 1.0, broker, send=True)

    assert len(broker.sent) == 1
    assert broker.sent[0] == result.intents[0]
    assert result.sent is True
    assert result.order_ids == ("fake-1",)


def test_live_mode_is_refused_with_the_reason() -> None:
    broker = FakeBroker()

    with pytest.raises(NotImplementedError) as planned:
        plan(BotConfig(), make_frame().iloc[-1], 1.0, broker, live=True)
    assert str(planned.value) == LIVE_REFUSED
    assert "never trades real money" in str(planned.value)

    with pytest.raises(NotImplementedError):
        run(BotConfig(), make_frame().iloc[-1], 1.0, broker, live=True, send=True)

    assert broker.sent == []


def test_missing_credentials_name_the_env_vars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(KEY_ENV, raising=False)
    monkeypatch.delenv(SECRET_ENV, raising=False)

    with pytest.raises(BotError) as raised:
        bot_module.paper_broker()

    assert str(raised.value) == MISSING_KEYS


def test_credentials_error_never_echoes_a_value(monkeypatch: pytest.MonkeyPatch) -> None:
    marker = "do-not-print-this-key-1234"
    monkeypatch.setenv(KEY_ENV, marker)
    monkeypatch.delenv(SECRET_ENV, raising=False)

    with pytest.raises(BotError) as raised:
        bot_module.paper_broker()

    message = str(raised.value)
    assert marker not in message
    assert SECRET_ENV in message


def test_a_missing_alpaca_extra_names_the_command(monkeypatch: pytest.MonkeyPatch) -> None:
    if importlib.util.find_spec("alpaca") is not None:
        pytest.skip("alpaca-py is installed, so the missing-extra path cannot be observed")
    monkeypatch.setenv(KEY_ENV, "key-placeholder")
    monkeypatch.setenv(SECRET_ENV, "secret-placeholder")

    with pytest.raises(BotError, match=r"uv sync --extra bot"):
        bot_module.paper_broker()


def test_planned_quantity_matches_the_ledger_cost_model() -> None:
    frame = make_frame()
    config = BotConfig(initial_cash_clp=1_000_000.0)
    broker = FakeBroker(equity_clp=config.initial_cash_clp)

    intended = plan(config, frame.iloc[1], 1.0, broker).intents[0]

    ledger = simulate(
        frame,
        target=buy_and_hold(frame.index),
        costs=config.costs,
        initial_cash_clp=config.initial_cash_clp,
    )
    first = ledger.trades[0]
    assert first.date == DATES[1]
    assert intended.qty == pytest.approx(first.qty)
    assert intended.exec_price_usd == pytest.approx(config.costs.buy_price(100.0))
    commission_clp = intended.qty * intended.exec_price_usd * 1000.0 * config.costs.commission_rate
    assert intended.commission_clp == pytest.approx(commission_clp)
    # The budget pays the friction too, so the position cannot eat the whole balance.
    assert intended.qty < config.initial_cash_clp / 1000.0 / 100.0


def test_zero_weight_plans_the_sell_the_ledger_would_do() -> None:
    config = BotConfig()
    broker = FakeBroker(qty=5.0)

    intended = plan(config, make_frame().iloc[-1], 0.0, broker).intents[0]

    assert intended.side == "sell"
    assert intended.qty == pytest.approx(5.0)
    assert intended.exec_price_usd == pytest.approx(config.costs.sell_price(100.0))


def test_unknown_cost_preset_names_the_choices() -> None:
    with pytest.raises(BotError, match="alpaca, chile"):
        BotConfig(cost_preset="vibes")


def test_target_weight_outside_zero_and_one_is_refused() -> None:
    with pytest.raises(BotError, match="between 0 and 1"):
        plan(BotConfig(), make_frame().iloc[-1], 1.5, FakeBroker())


def test_market_row_without_columns_names_the_fix() -> None:
    row = pd.Series({PRICE: 100.0}, name=DATES[0])

    with pytest.raises(ValueError, match="build_market_frame"):
        plan(BotConfig(), row, 1.0, FakeBroker())


def test_dry_run_broker_refuses_to_submit() -> None:
    order = OrderIntent(
        symbol="SPY",
        side="buy",
        qty=1.0,
        ref_price_usd=100.0,
        exec_price_usd=100.05,
        notional_clp=100_050.0,
        commission_clp=0.0,
    )

    with pytest.raises(BotError, match="dry run"):
        DryRunBroker().submit(order)


def test_bot_plan_defaults_are_the_safe_ones() -> None:
    args = build_parser().parse_args(["bot", "plan"])

    assert (args.command, args.bot_command) == ("bot", "plan")
    assert args.weight == 1.0
    assert args.live is False
    assert args.symbol == "SPY"
    assert args.cost_preset == "alpaca"
    assert args.whole_shares is False


def test_bot_run_defaults_to_plan_only() -> None:
    args = build_parser().parse_args(["bot", "run"])

    assert (args.command, args.bot_command) == ("bot", "run")
    assert args.send is False
    assert args.live is False


def test_bot_command_is_discoverable_in_help() -> None:
    help_text = build_parser().format_help()

    assert "bot" in help_text
    assert "paper-trade" in help_text


def test_adding_the_bot_keeps_the_existing_commands_parseable() -> None:
    parser = build_parser()

    assert parser.parse_args(["app", "--headless"]).headless is True
    fetch = parser.parse_args(["data", "fetch", "--symbol", "SPY"])
    assert (fetch.data_command, fetch.start, fetch.fx) == ("fetch", "2005-01-01", "CLP=X")


def test_cli_plan_exits_zero_without_network_or_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("KX_DATA_DIR", str(write_cache(tmp_path)))
    monkeypatch.delenv(KEY_ENV, raising=False)
    monkeypatch.delenv(SECRET_ENV, raising=False)
    imported_before = {name for name in sys.modules if name.startswith("alpaca")}

    code = main(["bot", "plan"])

    captured = capsys.readouterr()
    assert code == 0
    assert captured.err == ""
    assert "BUY" in captured.out
    assert "SPY" in captured.out
    assert "nothing was sent" in captured.out
    assert {name for name in sys.modules if name.startswith("alpaca")} == imported_before


def test_cli_run_plans_without_sending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("KX_DATA_DIR", str(write_cache(tmp_path)))
    broker = FakeBroker()
    monkeypatch.setattr(bot_module, "paper_broker", lambda: broker)

    code = main(["bot", "run"])

    captured = capsys.readouterr()
    assert code == 0
    assert captured.err == ""
    assert broker.sent == []
    assert "nothing was sent" in captured.out


def test_cli_run_send_reaches_the_broker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("KX_DATA_DIR", str(write_cache(tmp_path)))
    broker = FakeBroker()
    monkeypatch.setattr(bot_module, "paper_broker", lambda: broker)

    code = main(["bot", "run", "--send"])

    captured = capsys.readouterr()
    assert code == 0
    assert captured.err == ""
    assert len(broker.sent) == 1
    assert "sent to the paper account: fake-1" in captured.out


def test_cli_run_without_keys_names_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("KX_DATA_DIR", str(write_cache(tmp_path)))
    monkeypatch.delenv(KEY_ENV, raising=False)
    monkeypatch.delenv(SECRET_ENV, raising=False)

    code = main(["bot", "run"])

    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert captured.err == f"kx: {MISSING_KEYS}\n"


def test_cli_bad_cost_preset_is_reported_not_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("KX_DATA_DIR", str(tmp_path / "empty"))

    code = main(["bot", "plan", "--cost-preset", "vibes"])

    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert captured.err == "kx: unknown cost preset 'vibes'; choose one of alpaca, chile\n"


def test_cli_live_is_refused_before_any_broker_or_cache_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("KX_DATA_DIR", str(tmp_path / "empty"))
    monkeypatch.delenv(KEY_ENV, raising=False)
    monkeypatch.delenv(SECRET_ENV, raising=False)

    code = main(["bot", "run", "--live"])

    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert captured.err == f"kx: {LIVE_REFUSED}\n"


def test_importing_the_bot_does_not_need_alpaca_py() -> None:
    assert "alpaca" not in sys.modules
    assert "paper only" in describe(plan(BotConfig(), make_frame().iloc[-1], 1.0, FakeBroker()))


def test_describe_names_the_rule_that_set_the_weight() -> None:
    """Two rules, two plans: the printout has to say which one produced the number."""
    held = plan(BotConfig(), make_frame().iloc[-1], 1.0, FakeBroker())
    crossed = plan(
        BotConfig(strategy="sma-cross", fast=2, slow=3),
        make_frame([100.0, 101.0, 102.0, 103.0, 104.0]).iloc[-1],
        1.0,
        FakeBroker(),
    )

    assert "sma-cross" not in describe(held)
    assert "sma-cross 2/3" in describe(crossed)


def test_position_qty_reads_a_missing_position_as_flat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = fake_alpaca_errors(monkeypatch)
    broker = AlpacaPaperBroker(FakePositionClient(raises=error("position does not exist", 404)))

    assert broker.position_qty("SPY") == 0.0


def test_position_qty_never_masks_a_real_api_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A rate limit read as flat would size a full order against a position never read."""
    error = fake_alpaca_errors(monkeypatch)
    broker = AlpacaPaperBroker(FakePositionClient(raises=error("rate limit exceeded", 429)))

    with pytest.raises(error, match="rate limit exceeded"):
        broker.position_qty("SPY")


def test_paper_broker_is_built_with_paper_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The only guard between a demo account and real money is this keyword."""
    captured: dict[str, object] = {}

    class FakeTradingClient:
        def __init__(self, key: str, secret: str, paper: bool) -> None:
            captured.update(key=key, secret=secret, paper=paper)

    client_module = types.ModuleType("alpaca.trading.client")
    client_module.TradingClient = FakeTradingClient  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "alpaca", types.ModuleType("alpaca"))
    monkeypatch.setitem(sys.modules, "alpaca.trading", types.ModuleType("alpaca.trading"))
    monkeypatch.setitem(sys.modules, "alpaca.trading.client", client_module)

    broker = paper_broker({KEY_ENV: "paper-key", SECRET_ENV: "paper-secret"})

    assert captured["paper"] is True
    assert captured["key"] == "paper-key"
    assert isinstance(broker, AlpacaPaperBroker)


def test_send_with_nothing_to_do_reports_nothing_was_sent() -> None:
    """`sent` means an order reached the account, not that send was requested."""
    broker = FakeBroker(qty=0.0)

    result = run(BotConfig(), make_frame().iloc[-1], 0.0, broker, send=True)

    assert result.intents == ()
    assert result.sent is False
    assert result.order_ids == ()
    assert broker.sent == []
    rendered = describe(result)
    assert "no order" in rendered
    assert "sent to the paper account" not in rendered


def test_sma_cross_strategy_takes_the_weight_from_the_cached_history() -> None:
    config = BotConfig(strategy="sma-cross", fast=2, slow=3)
    rising = make_frame([100.0, 101.0, 102.0, 103.0, 104.0])
    falling = make_frame([104.0, 103.0, 102.0, 101.0, 100.0])

    assert strategy_weight(config, rising, 1.0) == 1.0
    assert strategy_weight(config, falling, 1.0) == 0.0


def test_hold_strategy_ignores_the_history_and_keeps_the_weight() -> None:
    config = BotConfig()

    assert config.strategy == "hold"
    assert strategy_weight(config, make_frame([100.0] * 5), 0.4) == 0.4


def test_sma_cross_refuses_a_cache_shorter_than_its_slow_window() -> None:
    """Going flat because history is missing would silently liquidate the account."""
    config = BotConfig(strategy="sma-cross", fast=2, slow=50)

    with pytest.raises(BotError, match="at least 50"):
        strategy_weight(config, make_frame(), 1.0)


def test_unknown_strategy_names_the_choices() -> None:
    with pytest.raises(BotError, match="unknown strategy"):
        BotConfig(strategy="moon")


def test_whole_shares_plan_buys_whole_shares() -> None:
    result = plan(BotConfig(fractional=False), make_frame().iloc[-1], 1.0, FakeBroker())

    assert len(result.intents) == 1
    assert result.intents[0].qty == int(result.intents[0].qty)
    assert result.intents[0].qty > 0


def test_cli_strategy_plans_from_the_cached_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("KX_DATA_DIR", str(write_cache(tmp_path)))

    code = main(["bot", "plan", "--strategy", "sma-cross", "--fast", "2", "--slow", "3"])

    captured = capsys.readouterr()
    assert code == 0
    assert "target" in captured.out
    assert captured.err == ""


def test_cli_strategy_that_cannot_fit_the_cache_is_reported_not_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("KX_DATA_DIR", str(write_cache(tmp_path)))

    code = main(["bot", "plan", "--strategy", "sma-cross", "--fast", "2", "--slow", "9999"])

    captured = capsys.readouterr()
    assert code == 1
    assert "at least 9999" in captured.err
    assert captured.out == ""
