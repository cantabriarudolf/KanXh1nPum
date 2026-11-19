# v1-guided-tour

**Feature:** KanXh1nPum v1 — simulación con costos reales para un principiante chileno, con un recorrido guiado por las temporalidades de trading y el ancla de la banca tradicional.
**Scope:** Rebanada vertical: mercado EE.UU. (ETF/acciones) + cuenta demo Alpaca paper + 1 estrategia punta a punta (buy & hold indexado), luego se ensancha a swing para probar que el motor generaliza.
**Convención de idioma:** código, tests, docs técnicos y commits en inglés; copy del producto y contenido educativo en español (Chile).

## Specs

- **S1.** El proyecto incluye "un bot que maneje una cuenta demo y probar estrategias".
- **S2.** El dashboard aborda "lo minimo que alguien va a empezar en esto", sintetizado y "que asuma tu nivel cero".
- **S3.** La experiencia "te quite igual las rueditas chicas de la bicicleta": el recorrido hace el setup, no exige jerga previa.
- **S4.** Con "segun rango etario y otros parametros que estimes le sugieras estrategias conservadoras o de medio o bajo riesgo" — implementado como perfiles de horizonte/tolerancia que devuelven carteras ilustrativas estresadas, nunca consejo personalizado (encuadre CMF).
- **S5.** Debe quedar claro "que en chile esa cuenta demo generaria en la banca tradicional con suerte lo necesario para que no se devalue": benchmark DPF vs IPC (y después de impuesto), como ancla de todo rendimiento mostrado.
- **S6.** "no quiero que reinventes la rueda, puedes perfectamente investigar si ya hay algo opensource que aborde parte del motor": reutilizar librerías vivas; poseer solo la capa diferenciadora (costos + FX + inflación).
- **S7.** El dashboard hace "un paseo por las diferentes temporalidades de trading" que "guie" y "despeje mejor sus dudas", con progreso visible.
- **S8.** "no quiero un super quant de agente, quiero guia para quien empieza que entienda de estrategias": sin ML, sin hyperopt, sin LLM en el loop.
- **S9.** Todo con "su disclaimer y no vende humo": "sp500 a 10 años es probable que me genere rentabilidad" se muestra como rango con escenarios, no como promesa.
- **S10.** El repo funciona como pieza de portafolio: README, documento de arquitectura con tradeoffs y tests que prueban que el motor no puede hacer trampa.

## Tasks

| ID | Spec | Task | Route | Commit |
| --- | --- | --- | --- | --- |
| T1 | S6, S10 | Scaffold: uv project, layout `kx`, pytest + ruff, README, decisiones de reutilización documentadas | inline | committed |
| T2 | S2, S6 | Data layer: fetch + cache determinista de precio, USD/CLP, IPC/UF; fixtures versionadas; tests sin red | inline | committed |
| T3 | S5, S6 | Ledger con costos reales: spread + comisión + slippage, conversión USD→CLP, nominal→real por IPC | inline | committed |
| T4 | S9 | Métricas: CAGR, vol, Sharpe, Sortino, maxDD, tiempo de recuperación, USD vs CLP, nominal vs real | inline | committed |
| T5 | S9 | Vistas honestas: cascada de costos, mejores días perdidos, contrafáctico de pánico, episodios de drawdown | inline | committed |
| T6 | S4, S5 | Benchmark Chile: escalera DPF vs UF vs IPC, mordida de impuesto; perfiles por horizonte y tolerancia | inline | committed |
| T7 | S2, S3, S7 | App Streamlit: parada 1 del recorrido (buy & hold) con progreso y navegación guiada | inline | e5dee81 |
| T8 | S1 | Cableado Alpaca paper para la estrategia de buy & hold, runner en modo seguro por defecto | inline | 4e5dd21 |
| T9 | S7 | Parada 2 (swing) para probar que el motor generaliza sin reescribir la capa de costos | inline | 07b341f |

## Log

**L1** (request, verbatim):

> quiero hacer un bot que maneje una cuenta demo y probar estrategias. me gustaria un proyecto que me permitiera tener un dashboard que aborde lo minimo que alguien va a empezar en esto pudiera sintetizar, que asuma tu nivel cero, pero que te quite igual las rueditas chicas de la bicicleta, que te haga la tipica de segun rango etario y otros parametros que estimes le sugieras estrategias conservadoras o de medio o bajo riesgo. que le dejes claro que en chile esa cuenta demo generaria en la banca tradicional con suerte lo necesario para que no se devalue. tampoco quiero que reinventes la rueda, puedes perfectamente investigar si ya hay algo opensource que aborde parte del motor o un extra segun tu vision fuera de la caja y aportando soluciones en otras dimensiones que no son consideradas. quiero que el proyecto pueda servirme de portafolio indirectamente pero directamente apoyando a quien recien empieza la idea que de la cuenta demo le haga un paseo por las diferentes temporalidades de trading señalandole o guiandolo para que tenga un paseo y despeje mejor sus dudas, no quiero un super quant de agente, quiero guia para quien empieza que entienda de estrategias y lo orientes con apoyo a las cartas probadas que le puedas ofrecer(claramente con su disclaimer y no vende humo blabla, pero por ejemplo sp500 a 10 años es probable que me genere rentabilidad. eso es ya mejor que una recomendacion de la banca chilena con undeposito a plazo), me explico? que opinas?

**L2** (decisions, 2026-11-18): v1 = vertical slice; primary market = US ETF/equities; demo = real Alpaca paper account.

**L3** (evidence, 2026-11-18): TPM 4.50% desde inicios de 2026; DPF promedio del sistema (BCCh, oct-2026) 4.17% a 30-89d, 4.60% a 90d-1a, 5.40% a 1-3a; IPC 4.5% 12m (INE oct-2026); UF ~$41.330. S&P 500 CAGR 1928-2025 = 9.92% (Shiller); ~15.5% a 10 años; Goldman proyectó 3% para 2024-2034. Consecuencia de diseño: el ancla real de un DPF a 90d-1a es ≈ +0.1% antes de impuesto y negativo después de impuesto.

**L4** (design, 2026-11-18): motor de reutilización verificado — `backtesting.py` 0.6.6 (jul-2026, AGPL) vivo; `backtrader` muerto (ago-2024); `vectorbt` OSS en mantenimiento y empuja a PRO pago; `freqtrade` vivo pero crypto-only y secuestra identidad; Alpaca paper gratis, global, sin residencia en EE.UU., USD 100k simulados, host separado. Decisión: no adoptar un backtester completo como núcleo; poseer el *ledger* de costos (que es la tesis del producto) y reutilizar datos, indicadores y reportes.

**L5** (resume, 2026-11-19): la máquina se reinició con T8 y T9 en vuelo y sin commitear (suite 107 verde). Al reconciliar contra S1 y S7 aparecen cuatro brechas, y se cierran acá:

- **S1** — la regla del swing no llegaba a la cuenta demo: el bot solo expresaba buy & hold con un peso fijo. Se agrega `--strategy sma-cross`, que toma el peso de `kx.strategies.sma_crossover` con la misma aritmética del ledger.
- **S7** — "progreso visible" no existía: la posición en el recorrido solo se infería de las etiquetas del radio. Ahora hay barra de progreso y "Parada N de 3".
- **S1/S3** — el recorrido nunca mencionaba la cuenta demo, que es el setup que S3 pide hacer. El sidebar nombra los tres comandos, sin campo para claves.
- **S10** — el README declaraba 65 tests con 119 reales y anunciaba el swing como futuro después de haberlo shippeado.

Se agrega además `kx.presets`: los presets de costos estaban duplicados en la app y en el bot mientras `docs/bot.md` afirmaba que se reflejaban entre sí. Commits: `56afe14` (costura compartida), `4e5dd21` (T8), `07b341f` (T9). Ruta: se ejecutó inline y no por worker — las dos unidades comparten `kx.presets`, así que ninguna entrega era independiente.

**L6** (límites declarados, 2026-11-19): no se declara hecho, y queda fuera de v1:

- La tercera parada (intradía y por qué el scalping no es para vos) sigue siendo un aviso de "próximamente": el recorrido cubre dos temporalidades, no "las diferentes".
- El comportamiento real del host paper de Alpaca no está verificado (requiere claves). Lo que sí se pinea es la invariante que importa: `paper=True` en la construcción del cliente.
- El test de la parada 2 sigue acoplado a un conteo exacto de operaciones (`[1, 5]`) sobre un fixture sintético.
