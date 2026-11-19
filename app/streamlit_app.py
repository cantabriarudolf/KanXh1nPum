"""KanXh1nPum — laboratorio de costos y recorrido guiado por las temporalidades.

Cada pantalla responde una pregunta que un principiante suele recibir en forma de
promesa: qué te queda después de costos, de inflación y de impuesto; cuánto cuesta
perderte los mejores días; qué pasó cuando el mercado cayó y la gente vendió.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from kx.chile import break_even_tax_rate, deposit_table
from kx.data import PRICE, DataNotCached
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
        "Antes de mirar cualquier estrategia, conviene saber qué hace tu plata si no hacés "
        "nada. Este es el número que todo lo demás tiene que superar."
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
        f"Con una tasa marginal sobre {pct(break_even, 1)} el depósito crece en pesos y "
        "pierde poder de compra al mismo tiempo. Eso no es una opinión: sale de las tasas "
        "del Banco Central y del IPC. Los intereses, además, tributan."
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
            f"Total pagado en fricción: {clp(costs_clp)} sobre {clp(invested_clp)} "
            f"aportados. Con '{costs_name}'."
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
            "El período es el mismo: seguiste invirtiendo todo el tiempo, solo que esos días "
            "no estabas. Los mejores días se concentran cerca de los peores."
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
                f"{pct(diferencia)} de lo que tendrías aguantando."
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
        "Comprar el índice completo y no tocarlo. No hay señal, no hay destreza, no hay "
        "acierto: cobrás la prima de riesgo por aguantar. Si una estrategia activa no le "
        "gana a esto, no vale el tiempo."
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
        "Cada línea arranca en 1: es un índice, no pesos. La línea de pesos de hoy descuenta "
        "la inflación; la del depósito usa la tasa a 90 días-1 año y no descuenta impuesto."
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
        "Acá cambia la regla, no el motor: estás adentro cuando el promedio de las últimas "
        "ruedas cortas supera al de las largas, y te salís cuando el cruce se da al revés. "
        "Misma plata, mismo período y los mismos costos que en la parada anterior."
    )
    st.caption("Cruzar medias es una regla con un costo, no un descubrimiento.")

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
            "el período."
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
            f"El cruce pagó {clp(lump_swing.costs_clp)} en fricción y comprar y aguantar "
            f"{clp(lump_hold.costs_clp)}, con la misma plata. Cada entrada y cada salida se "
            "cobran."
        ),
    )
    render_best_days_expander(lump_swing)
    render_panic_expander(lump_swing)
    render_drawdown_expander(lump_swing)


def main() -> None:
    st.set_page_config(page_title="KanXh1nPum", page_icon="🧭", layout="wide")
    st.title("KanXh1nPum")
    st.caption(
        "Un laboratorio para entender qué pasa con tu plata antes de arriesgarla. "
        "Nivel cero, con costos reales y sin humo."
    )

    with st.sidebar:
        st.subheader("El recorrido")
        stops = ["0 · La realidad chilena", "1 · Comprar y aguantar", "2 · Cruzar medias"]
        stop = st.radio(
            "Parada",
            stops,
            index=0,
            label_visibility="collapsed",
        )
        position = stops.index(stop) + 1
        st.progress(position / len(stops))
        st.caption(
            f"Parada {position} de {len(stops)}. Próximamente: intradía y por qué el "
            "scalping no es para vos."
        )

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
        st.caption("La edad sola no sirve: lo que manda es cuándo necesitás la plata.")
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
            "No hay datos en caché. Corré `kx data fetch --symbol SPY --start 2010-01-01` "
            "en el proyecto y volvé a cargar esta página."
        )
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
            "'en pesos de hoy' subestima cuánto se comió la inflación al final."
        )

    if len(data.frame) < 250:
        st.warning(
            f"La muestra tiene solo {len(data.frame)} ruedas: alcanza para probar que todo "
            "funciona, no para concluir nada. Traé más historia con "
            "`kx data fetch --symbol SPY --start 2005-01-01`."
        )

    st.divider()
    if stop.startswith("0"):
        render_reality_check(tax_rate)
    elif stop.startswith("1"):
        render_buy_and_hold(data, float(initial), float(monthly), costs_name)
    else:
        render_swing(data, float(initial), float(monthly), costs_name)

    st.divider()
    st.caption(
        "Nada de esto es asesoría financiera ni una recomendación de compra o venta. Son "
        "simulaciones con costos y datos históricos; el pasado no anticipa el futuro. Si no "
        "podés perder esta plata, no la arriesgues."
    )


main()
