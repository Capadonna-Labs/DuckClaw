# MOC Macro PGQ + Perfil VSS (Quant Trader)

## Objetivo

Enriquecer el pipeline MOC Core-Satellite antes de la válvula CFD con:

1. **Grafo macro** en `quant_core.macro_nodes` / `quant_core.macro_edges` (consultas por JOIN; PGQ `MATCH` opcional en el futuro).
2. **Perfil de inversor** desde VSS (`main.semantic_memory`) con búsqueda por embedding (mismo patrón que `search_semantic_context`).
3. **Régimen detectado** (VIX + contexto VSS + coherencia PGQ), con **override manual** en `quant_core.macro_manual_state`.

## Convención de aristas (PGQ lógico)

- Los **activos** son nodos `node_type = 'ACTIVO'` (p. ej. `SPY`, `SHY`).
- Los **régimenes** son nodos `node_type = 'REGIMEN'` (p. ej. `REGIMEN_RISK_OFF`).
- Arista **ACTIVO → RÉGIMEN**: `src` = activo, `dst` = régimen.
- Consultas “activos coherentes con el régimen R”: aristas donde `dst.name = R` y `edge_type` en la lista permitida; se devuelve **`src.name`**.
- Idem **contraindicados** con `edge_type` de presión/contraindicación.

## Variables de entorno

| Variable | Default | Uso |
|----------|---------|-----|
| `DUCKCLAW_MOC_MACRO_VSS` | `1` | Si `1`, MOC calc usa `calculate_target_allocation_v2` (macro + perfil). |
| `DUCKCLAW_MOC_VSS_TIMEOUT_SEC` | `3` | Presupuesto máximo (s) para bloque VSS perfil + macro en un ciclo. |
| `DUCKCLAW_MOC_PROFILE_LLM` | `0` | Si `1`, intenta estructurar perfil vía LLM (no obligatorio en v1). |

## Comandos Telegram

- `/profile` — Muestra perfil inferido (VSS + heurística).
- `/macro --update REGIMEN_* confidence=0.8 evidence="..."` — Solo **admin** del tenant u **owner**; escribe `macro_manual_state` vía cola Singleton Writer.

## Singleton Writer

Mutaciones desde jobs y fly hacia la bóveda: `enqueue_duckdb_write_sync` / `enqueue_vault_sql` / `_vault_apply_sql_statements`. No abrir DuckDB escritura directa en el proceso del job salvo tests `:memory:`.

## Referencias de código

- Pipeline: [`scripts/quant/moc_pipeline.py`](../../../scripts/quant/moc_pipeline.py)
- Válvula v2: [`packages/agents/src/duckclaw/forge/atoms/moc_allocation_v2.py`](../../../packages/agents/src/duckclaw/forge/atoms/moc_allocation_v2.py)
- Régimen: [`packages/agents/src/duckclaw/forge/atoms/macro_regime_detector.py`](../../../packages/agents/src/duckclaw/forge/atoms/macro_regime_detector.py)
- Perfil VSS: [`packages/agents/src/duckclaw/forge/atoms/investor_profile_vss.py`](../../../packages/agents/src/duckclaw/forge/atoms/investor_profile_vss.py)
- DDL template: [`packages/agents/src/duckclaw/forge/templates/Quant-Trader/schema.sql`](../../../packages/agents/src/duckclaw/forge/templates/Quant-Trader/schema.sql)

## Documentación relacionada

- [Core-Satellite HRP Weekly + MOC CFD.md](./Core-Satellite%20HRP%20Weekly%20+%20MOC%20CFD.md)
