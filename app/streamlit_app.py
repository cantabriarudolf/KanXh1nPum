"""KanXh1nPum — laboratorio de costos y recorrido guiado por las temporalidades.

Cada pantalla responde una pregunta que un principiante suele recibir en forma de
promesa: qué te queda después de costos, de inflación y de impuesto; cuánto cuesta
perderte los mejores días; qué pasó cuando el mercado cayó y la gente vendió.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from kx.chile import break_even_tax_rate, deposit_table
from kx.data import PRICE, DataAlignmentError, DataNotCached
from kx.honest import cost_ladder, drawdown_episodes, missing_best_days, panic_path
from kx.ledger import Costs, Result, buy_and_hold, simulate
from kx.loader import MarketData, load_market
from kx.metrics import drawdown, summarize
from kx.presets import PRESETS_BY_LABEL
from kx.profiles import suggest_profile
from kx.reference import CHILE_2026_11
from kx.strategies import sma_crossover

DPF_MIDDLE = dict(CHILE_2026_11.dpf)["90d-1a"]


def clp(value: float) -> str:
    return f"${value:,.0f}".replace(",", ".")


def pct(value: float, digits: int = 1, *, signed: bool = True) -> str:
    spec = f"+.{digits}f" if signed else f".{digits}f"
    return f"{value * 100:{spec}}%".replace(".", ",")


def monthly_cashflows(index: pd.DatetimeIndex, amount: float) -> pd.Series:
    """One contribution on the first trading day of each month, starting next month."""
    flows = pd.Series(0.0, index=index)
    if amount <= 0:
        return flows
    first_of_month = ~index.to_period("M").duplicated(keep="first")
    first_of_month[0] = False
    flows[first_of_month] = amount
    return flows


def deposit_future_value(flows: pd.Series, annual_rate: float) -> float:
    """The same money in a deposit, each contribution compounding from its own date."""
    final = flows.index[-1]
    years = np.array([(final - date).days / 365.25 for date in flows.index])
    return float((flows.to_numpy() * (1.0 + annual_rate) ** years).sum())


def render_reality_check(tax_rate: float) -> None:
    st.header("0 · La realidad chilena primero")
    st.markdown(
        "Antes de cualquier estrategia, el dato incómodo: tu plata quieta en el banco **cada "
        "día puede comprar menos cosas**. No es mala suerte ni un ciclo raro — es el IPC "
        "trabajando de fondo. Lo que sigue es el número que todo lo demás tiene que superar, "
        "medido con las tasas del Banco Central, no con opiniones."
    )

    rows = deposit_table(CHILE_2026_11, tax_rate=tax_rate)
    st.dataframe(
        pd.DataFrame(
            {
                "Plazo": [row.rung for row in rows],
                "Tasa nominal": [pct(row.nominal, signed=False) for row in rows],
                "Real (descontando inflación)": [pct(row.real, 2, signed=False) for row in rows],
                "Real después de impuesto": [
                    pct(row.real_after_tax, 2, signed=False) for row in rows
                ],
            }
        ),
        hide_index=True,
        width="stretch",
    )
    st.caption(
        f"Inflación 12 meses: {pct(CHILE_2026_11.ipc_12m)} · TPM: {pct(CHILE_2026_11.tpm)} · "
        f"UF: {clp(CHILE_2026_11.uf_clp)} · Fuente: {CHILE_2026_11.source}."
    )

    middle = rows[1]
    break_even = break_even_tax_rate(middle.nominal, CHILE_2026_11.ipc_12m)
    izquierda, centro, derecha = st.columns(3)
    izquierda.metric("Depósito a 90 días-1 año", pct(middle.nominal))
    centro.metric("Lo que sobrevive a la inflación", pct(middle.real, 2, signed=False))
    derecha.metric("Impuesto que lo deja en cero", pct(break_even, 2))

    st.info(
        f"Con una tasa marginal sobre {pct(break_even, 1)} el depósito **crece en pesos y "
        "pierde poder de compra al mismo tiempo**. La forma más rata de guardar plata — "
        "dejarla a plazo — alcanza justo para que no se te apolille en el colchón. No para "
        "hacerte más rico. Y los intereses, encima, tributan."
    )


def result_return_years(frame: pd.DataFrame) -> float:
    return (frame.index[-1] - frame.index[0]).total_seconds() / 86_400 / 365.25


def render_cost_expander(
    frame: pd.DataFrame,
    *,
    target: pd.Series,
    costs: Costs,
    initial: float,
    costs_clp: float,
    invested_clp: float,
    costs_name: str,
    note: str | None = None,
) -> None:
    costas = st.expander("¿Cuánto te cuesta operar?", expanded=False)
    with costas:
        ladder = cost_ladder(
            frame,
            target=target,
            costs=costs,
            initial_cash_clp=initial,
            risk_free_annual=DPF_MIDDLE,
        )
        st.dataframe(
            pd.DataFrame(
                {
                    "Escenario": [step.label for step in ladder],
                    "Un peso se convierte en": [f"{step.multiple:.2f}" for step in ladder],
                    "Anualizado": [pct(step.cagr, 2, signed=False) for step in ladder],
                }
            ),
            hide_index=True,
            width="stretch",
        )
        st.caption(
            f"Fricción pagada: {clp(costs_clp)} sobre {clp(invested_clp)} que pusiste, con "
            f"'{costs_name}'. Eso no es volatilidad ni un mal día: es plata que se fue a otro "
            "bolsillo."
        )
        if note is not None:
            st.caption(note)


def render_best_days_expander(lump: Result) -> None:
    dias = st.expander("¿Y si te perdés los mejores días?", expanded=False)
    with dias:
        tradeable = len(lump.equity_clp) - 1
        counts = [n for n in (0, 5, 10, 20) if n < tradeable] or [0]
        scenarios = [missing_best_days(lump.equity_clp, n) for n in counts]
        st.dataframe(
            pd.DataFrame(
                {
                    "Días perdidos": ["ninguno" if n == 0 else str(n) for n in counts],
                    "Un peso se convierte en": [f"{s.multiple:.2f}" for s in scenarios],
                    "Anualizado": [pct(s.cagr, 2, signed=False) for s in scenarios],
                }
            ),
            hide_index=True,
            width="stretch",
        )
        st.caption(
            "Mismo período, misma plata: seguiste aportando, solo que esos días no estabas. "
            "Los mejores días se pegan a los peores, y no avisan."
        )


def render_panic_expander(lump: Result) -> None:
    panico = st.expander("¿Y si vendías en pánico?", expanded=False)
    with panico:
        threshold = st.slider(
            "Venderías si la caída llega a", min_value=5, max_value=60, value=20, step=5,
            format="-%d%%",
        ) / 100.0
        frozen, sell_date = panic_path(lump.equity_clp, threshold)
        comparacion = pd.DataFrame(
            {
                "Aguantaste": lump.equity_clp / lump.equity_clp.iloc[0],
                "Vendiste y no volviste": frozen / frozen.iloc[0],
            }
        )
        st.line_chart(comparacion)
        if sell_date is None:
            st.caption(f"Con -{threshold:.0%} nunca habrías vendido en este período.")
        else:
            diferencia = frozen.iloc[-1] / lump.equity_clp.iloc[-1] - 1.0
            st.caption(
                f"Habrías vendido el {sell_date.date()}. Al final te quedaría "
                f"{pct(diferencia)} de lo que tendrías por no hacer nada."
            )


def render_drawdown_expander(lump: Result) -> None:
    caidas = st.expander("Las caídas que vas a vivir", expanded=False)
    with caidas:
        episodes = drawdown_episodes(lump.equity_clp)[:5]
        st.dataframe(
            pd.DataFrame(
                {
                    "Máximo previo": [episode.peak.date().isoformat() for episode in episodes],
                    "Fondo": [episode.trough.date().isoformat() for episode in episodes],
                    "Caída": [pct(episode.depth, signed=False) for episode in episodes],
                    "Recuperado": [
                        episode.recovery.date().isoformat() if episode.recovery else "todavía no"
                        for episode in episodes
                    ],
                }
            ),
            hide_index=True,
            width="stretch",
        )
        deepest = episodes[0] if episodes else None
        if deepest is not None:
            st.caption(
                f"La peor: {pct(deepest.depth)} desde {deepest.peak.date()} hasta "
                f"{deepest.trough.date()}. Eso es el precio de entrada, no un accidente."
            )
        st.line_chart(drawdown(lump.equity_clp).rename("caída desde el máximo"))


def render_buy_and_hold(data: MarketData, initial: float, monthly: float, costs_name: str) -> None:
    costs = PRESETS_BY_LABEL[costs_name]
    frame = data.frame
    target = buy_and_hold(frame.index)
    flows = monthly_cashflows(frame.index, monthly)

    result = simulate(
        frame, target=target, costs=costs, initial_cash_clp=initial, cashflows=flows
    )
    lump = simulate(frame, target=target, costs=costs, initial_cash_clp=initial)

    st.header("1 · Comprar y aguantar: el piso honesto")
    st.markdown(
        "Comprar el índice entero y no tocarlo. Sin señal, sin destreza, sin acierto: cobrás "
        "la prima de riesgo por aguantar, que es lo único que nadie te puede vender. Si una "
        "regla activa no le gana a esto, no vale el tiempo ni la comisión."
    )

    izquierda, centro, derecha = st.columns(3)
    izquierda.metric("Aportaste en total", clp(result.invested_clp))
    centro.metric("Tu cuenta hoy", clp(result.final_equity_clp))
    derecha.metric(
        "La misma plata en DPF",
        clp(
            deposit_future_value(flows, DPF_MIDDLE)
            + initial * (1 + DPF_MIDDLE) ** result_return_years(frame)
        ),
    )

    nominal = result.equity_clp / result.equity_clp.iloc[0]
    deposit_line = (1 + DPF_MIDDLE) ** np.array(
        [(date - frame.index[0]).days / 365.25 for date in frame.index]
    )
    lines = pd.DataFrame({"Tu cuenta (nominal)": nominal, "Depósito a plazo": deposit_line})
    if result.equity_real_clp is not None:
        lines["Tu cuenta (pesos de hoy)"] = result.equity_real_clp / result.equity_real_clp.iloc[0]
    st.line_chart(lines)
    st.caption(
        "Cada línea arranca en 1: es un índice, no plata. La de pesos de hoy ya descuenta la "
        "inflación; la del depósito usa la tasa a 90 días-1 año y **no** descuenta impuesto "
        "— o sea que el depósito está dibujado mejor de lo que es."
    )

    if result.equity_real_clp is not None:
        real_stats = summarize(result.equity_real_clp, risk_free_annual=DPF_MIDDLE)
        st.caption(
            f"Rendimiento real anualizado: {pct(real_stats.cagr, 2)} · "
            f"peor caída: {pct(real_stats.max_drawdown)}"
        )

    render_cost_expander(
        frame,
        target=target,
        costs=costs,
        initial=initial,
        costs_clp=result.costs_clp,
        invested_clp=result.invested_clp,
        costs_name=costs_name,
    )
    render_best_days_expander(lump)
    render_panic_expander(lump)
    render_drawdown_expander(lump)


def render_swing(data: MarketData, initial: float, monthly: float, costs_name: str) -> None:
    costs = PRESETS_BY_LABEL[costs_name]
    frame = data.frame
    flows = monthly_cashflows(frame.index, monthly)

    st.header("2 · Cruzar medias: el mismo motor, otra regla")
    st.markdown(
        "Cambia la regla, no el motor. Estás adentro cuando el promedio corto le gana al "
        "largo, y afuera cuando se da vuelta. Es la parte que suena a que uno sabe algo — y "
        "por eso la plata y los costos son los mismos que en la parada anterior: para que "
        "compares contra eso y no contra tu entusiasmo."
    )
    st.caption("Cruzar medias no es un descubrimiento: es una regla, y las reglas se pagan.")

    izquierda, derecha = st.columns(2)
    rapida = izquierda.slider("Media corta (ruedas)", min_value=2, max_value=60, value=20)
    lenta = derecha.slider("Media larga (ruedas)", min_value=5, max_value=250, value=100)
    if rapida >= lenta:
        st.warning(
            "La media corta tiene que ser menor que la larga. Mientras tanto uso 20 y 100."
        )
        rapida, lenta = 20, 100

    target = sma_crossover(frame[PRICE], fast=rapida, slow=lenta)
    result = simulate(
        frame, target=target, costs=costs, initial_cash_clp=initial, cashflows=flows
    )
    hold = simulate(
        frame,
        target=buy_and_hold(frame.index),
        costs=costs,
        initial_cash_clp=initial,
        cashflows=flows,
    )
    lump_swing = simulate(frame, target=target, costs=costs, initial_cash_clp=initial)
    lump_hold = simulate(
        frame, target=buy_and_hold(frame.index), costs=costs, initial_cash_clp=initial
    )

    izquierda, centro, derecha = st.columns(3)
    izquierda.metric("Aportaste en total", clp(result.invested_clp))
    centro.metric("Tu cuenta cruzando medias", clp(result.final_equity_clp))
    derecha.metric("Aguantando, la misma plata", clp(hold.final_equity_clp))

    st.dataframe(
        pd.DataFrame(
            {
                "Regla": ["Comprar y aguantar", "Cruzar medias"],
                "Tu cuenta hoy": [clp(hold.final_equity_clp), clp(result.final_equity_clp)],
                "Fricción pagada": [clp(lump_hold.costs_clp), clp(lump_swing.costs_clp)],
                "Operaciones": [len(lump_hold.trades), len(lump_swing.trades)],
            }
        ),
        hide_index=True,
        width="stretch",
    )
    st.line_chart(
        pd.DataFrame(
            {
                "Cruzar medias": result.equity_clp / result.equity_clp.iloc[0],
                "Comprar y aguantar": hold.equity_clp / hold.equity_clp.iloc[0],
            }
        )
    )
    st.caption(
        "Las dos líneas arrancan en 1: es un índice, no pesos. Lo único que cambia entre "
        "ellas es la regla que decidió cuándo estar adentro."
    )

    if lenta > len(frame):
        st.info(
            "La muestra es más corta que la media larga: la regla se queda en efectivo todo "
            "el período. No es prudencia; es que no hay con qué decidir."
        )

    render_cost_expander(
        frame,
        target=target,
        costs=costs,
        initial=initial,
        costs_clp=result.costs_clp,
        invested_clp=result.invested_clp,
        costs_name=costs_name,
        note=(
            f"El cruce pagó {clp(lump_swing.costs_clp)} de fricción y aguantar "
            f"{clp(lump_hold.costs_clp)}, con la misma plata. Cada entrada y cada salida se "
            "cobran: la regla se paga sola, gane o pierda."
        ),
    )
    render_best_days_expander(lump_swing)
    render_panic_expander(lump_swing)
    render_drawdown_expander(lump_swing)


FREQUENCY_WINDOWS: tuple[tuple[int, int], ...] = ((5, 20), (10, 50), (20, 100), (50, 200))


def render_frequency(data: MarketData, initial: float, monthly: float, costs_name: str) -> None:
    costs = PRESETS_BY_LABEL[costs_name]
    frame = data.frame
    flows = monthly_cashflows(frame.index, monthly)

    st.header("3 · Cada cuánto mover: el precio de la frecuencia")
    st.markdown(
        "Acá se cae el mito: **la gracia no es comprar y vender**. Mirar más seguido te da "
        "más señales y más comisiones, y el motor de costos no distingue una señal buena de "
        "una mala — cobra las dos. Misma regla que la parada anterior, ventanas distintas: "
        "la única diferencia es cuánto pagaste por moverte."
    )
    st.caption(
        "Intradía y scalping no están porque el caché es de ruedas diarias: no hay dato que "
        "represente operar varias veces por día, y preferimos no inventarlo. Lo que sí se "
        "puede medir es la cuenta de movernos más seguido."
    )

    windows = [(fast, slow) for fast, slow in FREQUENCY_WINDOWS if slow <= len(frame)]
    if not windows:
        st.info(
            f"La muestra tiene {len(frame)} ruedas y la ventana más corta de esta parada "
            "necesita 20. Traé más historia con "
            "`kx data fetch --symbol SPY --start 2005-01-01`."
        )
        return

    # One simulation per window, and every number in the row comes from that same run:
    # pairing friction from one hypothetical with contributions from another is how a
    # table starts lying without anyone noticing.
    measured = []
    for fast, slow in windows:
        target = sma_crossover(frame[PRICE], fast=fast, slow=slow)
        result = simulate(
            frame, target=target, costs=costs, initial_cash_clp=initial, cashflows=flows
        )
        measured.append(
            {
                "label": f"{fast} / {slow}",
                "trades": len(result.trades),
                "friction": result.costs_clp,
                "equity": result.final_equity_clp,
                "invested": result.invested_clp,
            }
        )

    st.dataframe(
        pd.DataFrame(
            {
                "Ventanas": [row["label"] for row in measured],
                "Operaciones": [row["trades"] for row in measured],
                "Fricción pagada": [clp(row["friction"]) for row in measured],
                "Tu cuenta hoy": [clp(row["equity"]) for row in measured],
                "Aportaste": [clp(row["invested"]) for row in measured],
            }
        ),
        hide_index=True,
        width="stretch",
    )
    st.bar_chart(
        pd.DataFrame(
            {"Fricción pagada": [row["friction"] for row in measured]},
            index=[row["label"] for row in measured],
        )
    )

    most = max(measured, key=lambda row: row["trades"])
    least = min(measured, key=lambda row: row["trades"])
    st.caption(
        f"La ventana {most['label']} operó {most['trades']} veces y pagó "
        f"{clp(most['friction'])}; la {least['label']} operó {least['trades']} y pagó "
        f"{clp(least['friction'])}. Que moverse más cuesta más es seguro. Que además "
        "convenga no lo es, y por eso acá nadie te vende la ventana ganadora."
    )


def _house_style() -> str:
    """The few rules the theme cannot express, taken from `assets/band.svg`.

    Colours are the band's: `#0a0a0b` ground, `#c0a062` and `#8a6d3f` brass for structure,
    `#f095c8` pink for cost only, `#c9ccd1` ink. The theme in `.streamlit/config.toml`
    carries the palette; this carries the geometry.
    """
    return (
        "<style>"
        ".block-container{padding-top:1.1rem;max-width:1180px}"
        ".kx-band{margin:0 0 1.2rem 0}"
        ".kx-band svg{width:100%;height:auto;display:block}"
        "[data-testid='stHeader']{background:transparent}"
        "[data-testid='stDivider'] hr{border-color:#8a6d3f}"
        "</style>"
    )


def _band() -> str:
    """The repo's masthead plate, so the tour opens with the project's own mark.

    Returns an empty string when the asset is missing: a missing mark must not take the
    whole page down, and nothing here invents a replacement.
    """
    path = Path(__file__).resolve().parents[1] / "assets" / "band.svg"
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def main() -> None:
    st.set_page_config(page_title="KanXh1nPum", page_icon="🧭", layout="wide")
    st.markdown(_house_style(), unsafe_allow_html=True)
    band = _band()
    if band:
        st.markdown(f'<div class="kx-band">{band}</div>', unsafe_allow_html=True)
    st.title("KanXh1nPum")
    st.caption(
        "Esto no es un curso ni una forma académica de mirarlo. Es un simulador para ver, "
        "con números y no con fe, qué le pasa a tu plata cuando la movés. Podés creerle o "
        "no — pero acá no hay humo."
    )

    with st.sidebar:
        st.subheader("El recorrido")
        stops = [
            "0 · La realidad chilena",
            "1 · Comprar y aguantar",
            "2 · Cruzar medias",
            "3 · Cada cuánto mover",
        ]
        stop = st.radio(
            "Parada",
            stops,
            index=0,
            label_visibility="collapsed",
        )
        position = stops.index(stop) + 1
        st.progress(position / len(stops))
        st.caption(f"Parada {position} de {len(stops)}.")

        with st.expander("Tu cuenta demo, en tres comandos"):
            st.caption(
                "El recorrido simula. Para operar de verdad —sobre una cuenta demo, sin "
                "plata real en ningún paso— corrés el bot en tu terminal:"
            )
            st.code(
                "kx bot plan       # qué haría, sin red y sin claves\n"
                "kx bot run        # lee la cuenta demo, no envía nada\n"
                "kx bot run --send # envía la orden a la cuenta demo",
                language="bash",
            )
            st.caption(
                "Las claves viven en tu terminal, nunca en esta página: export "
                "KX_ALPACA_KEY y KX_ALPACA_SECRET. `docs/bot.md` dice dónde hacer clic."
            )

        st.divider()
        st.subheader("Tu perfil")
        st.caption(
            "La edad sola no dice nada. Lo que manda es cuándo necesitás la plata y cuánto "
            "aguantás mirando el saldo sin vender."
        )
        horizon = st.slider("¿En cuántos años la necesitás?", 1, 30, 10)
        tolerance = st.select_slider(
            "¿Cuánta caída aguantarías sin vender?",
            options=[0.10, 0.20, 0.30, 0.40, 0.50],
            value=0.30,
            format_func=lambda value: f"-{value:.0%}",
        )
        emergency = st.slider("Meses de gastos en tu colchón", 0, 12, 6)

        st.divider()
        st.subheader("Tu plata")
        initial = st.number_input(
            "Aporte inicial (CLP)",
            min_value=10_000,
            max_value=100_000_000,
            value=500_000,
            step=50_000,
        )
        monthly = st.number_input(
            "Aporte mensual (CLP)", min_value=0, max_value=10_000_000, value=50_000, step=10_000
        )
        costs_name = st.selectbox("Costos de operar", list(PRESETS_BY_LABEL), index=1)
        tax_rate = st.slider("Tu tasa marginal de impuesto", 0.0, 0.40, 0.08, step=0.01,
                             format="%.2f")

    try:
        data = load_market()
    except DataNotCached:
        st.error(
            "No hay datos en el caché. Corré `kx data fetch --symbol SPY --start 2010-01-01` "
            "en el proyecto y recargá: sin datos esto no simula nada."
        )
        st.stop()
    except DataAlignmentError as exc:
        st.error(
            "El caché no se puede alinear: el tipo de cambio o el IPC no tienen valor para "
            "las primeras fechas de precios, y rellenar hacia atrás sería inventar datos. "
            "Volvé a bajarlos con `kx data fetch --symbol SPY --start 2005-01-01` para que "
            "cubran el mismo período."
        )
        st.caption(f"Detalle: {exc}")
        st.stop()

    profile = suggest_profile(
        horizon_years=float(horizon),
        drawdown_tolerance=float(tolerance),
        emergency_fund_months=float(emergency),
    )

    izquierda, derecha = st.columns([2, 1])
    with izquierda:
        st.subheader(f"Perfil sugerido: {profile.name}")
        st.markdown(
            f"Con **{horizon} años** de horizonte y tolerancia a **-{tolerance:.0%}**, "
            f"la categoría a explorar es **{profile.equity_weight:.0%} renta variable / "
            f"{profile.fixed_income_weight:.0%} renta fija**."
        )
        st.caption(profile.stress_hint)
    with derecha:
        st.warning(profile.not_advice)

    st.caption(
        f"Datos: {data.symbol} desde {data.first.date()} hasta {data.last.date()} "
        f"(precios ajustados por dividendos), tipo de cambio y CPI desde el Banco Mundial."
    )
    if data.cpi_is_stale:
        st.warning(
            "El índice de inflación está desactualizado respecto de los precios: la serie "
            "'en pesos de hoy' se queda corta y te muestra la inflación más benigna de lo "
            "que fue."
        )

    if len(data.frame) < 250:
        st.warning(
            f"La muestra tiene solo {len(data.frame)} ruedas: alcanza para ver que la máquina "
            "anda, no para concluir nada. Traé más historia con "
            "`kx data fetch --symbol SPY --start 2005-01-01`."
        )

    st.divider()
    if stop.startswith("0"):
        render_reality_check(tax_rate)
    elif stop.startswith("1"):
        render_buy_and_hold(data, float(initial), float(monthly), costs_name)
    elif stop.startswith("2"):
        render_swing(data, float(initial), float(monthly), costs_name)
    else:
        render_frequency(data, float(initial), float(monthly), costs_name)

    st.divider()
    st.caption(
        "Nada de esto es asesoría financiera ni una recomendación de compra o venta: es un "
        "simulador con costos y datos históricos, y el pasado no anticipa nada. Si no podés "
        "perder esta plata, no la arriesgues — ni acá ni en ninguna parte."
    )


main()
