# Cyber-Fluid Dynamics (CFD) — marco cualitativo en Finanz / QuantClaw

**Objetivo**  
Ofrecer un **lenguaje analógico** (fluido / termodinámico) para integrar OHLCV, volatilidad y datos alternativos (Reddit, Google Trends) en un único “estado” del activo, persistido en DuckDB y usable en narrativas de riesgo. **No** es un modelo físico riguroso ni una garantía de rendimiento.

**Mapa conceptual (v1)**

| Dimensión           | Fuente típica en Duckclaw | Notas |
|--------------------|---------------------------|--------|
| Masa               | `quant_core.ohlcv_data` (precio × volumen agregado) | Sandbox o lecturas SQL. |
| Densidad           | Proxy volumen por nivel de precio desde OHLCV | Sin L2 real; o `NULL`. |
| Temperatura        | Volatilidad (p. ej. std de retornos, ATR en sandbox) | |
| Presión            | Reservado (MOC / cierre institucional) | **Fase 2**; columna puede ser `NULL`. |
| Viscosidad         | Proxy p. ej. (high−low)/close | Spread real: fase 2; o `NULL`. |
| Tensión superficial| Reddit + Trends + (opcional) VADER en sandbox | Cohesión “retail” heurística. |

**Fases discretas**  
Valores permitidos en `quant_core.fluid_state.phase`: `SOLID`, `LIQUID`, `GAS`, `PLASMA` (convención mayúsculas en la tool).

**Flujo cognitivo**  
1. **Ingesta:** `fetch_market_data`, `read_sql` sobre `quant_core.ohlcv_data`, herramientas Reddit / Google Trends / Tavily según manifest.  
2. **Reactor (Strix Sandbox):** `run_sandbox` con `data_sql` (LIMIT 5000) para masa, temperatura, proxies de densidad/viscosidad.  
3. **Fase:** Clasificación cualitativa según umbrales documentados en el prompt (no codificados como reglas duras en el motor).  
4. **Persistencia:** `record_fluid_state` inserta/actualiza una fila en `quant_core.fluid_state`.  
5. **Trading (opcional):** `propose_trade` con `strategy_name` p. ej. `cfd` — mismas reglas HITL / paper que el resto de quant.

**Esquema**  
Tabla `quant_core.fluid_state`: ver [packages/agents/src/duckclaw/forge/templates/finanz/schema.sql](packages/agents/src/duckclaw/forge/templates/finanz/schema.sql).

**Herramienta**  
`record_fluid_state` en [packages/agents/src/duckclaw/forge/skills/quant_cfd_bridge.py](packages/agents/src/duckclaw/forge/skills/quant_cfd_bridge.py). Activa con `quant.cfd: true` en [finanz/manifest.yaml](packages/agents/src/duckclaw/forge/templates/finanz/manifest.yaml).

**Limitaciones**  
- Metáforas y fases son **hipótesis narrativas**, no asesoramiento.  
- No inventar MOC, order book ni spreads si no hay fuente.  
- Paper only / HITL sin cambio respecto a la spec de trading cuantitativo.

**Fase 2 (opcional)**  
Feeds MOC, libro de órdenes, spread IBKR; reglas automáticas tipo “max entropy” en código.
