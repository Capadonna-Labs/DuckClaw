# The Mind — deprecación

**Estado:** deprecated (2026-05)  
**Código:** `packages/agents/src/duckclaw/deprecated/the_mind/`  
**Runtime:** sin registro en gateway, manager ni fly commands activos.

## Resumen

The Mind era un mini-juego cooperativo por Telegram (partidas, cartas, DMs). No existía como template ADF en `forge/templates/`; vivía en fly commands y skills. Se retira del stack activo; los agentes propios nuevos usan el template **`default`** (`topology: general`).

## Comportamiento actual

| Antes | Ahora |
|-------|--------|
| `/new_mind`, `/play`, `/game`, … | No registrados → `handle_command` devuelve `None` (ignorado en silencio) |
| Manager intent «última partida» → `the_mind_latest_game` | Flujo normal del worker activo (`default`, `finanz`, …) |
| Tools `broadcast_message` / `deal_cards` en grafo general | No se registran |
| `TheMind-Gateway` PM2 (8080) | Fuera de código; eliminar proceso manualmente si existe |

## Datos

- Tablas `the_mind_games`, `the_mind_players`, `the_mind_moves` en DuckDB: **no se eliminan** (histórico).
- Sin migración automática.

## Reactivación (solo desarrollo)

Importar desde `duckclaw.deprecated.the_mind` en un branch o fork; no soportado en producción.

## Referencias

- Worker base: [`default/manifest.yaml`](../../../packages/agents/src/duckclaw/forge/templates/default/manifest.yaml)
- Admin UI: [`DUCKCLAW_ADMIN_UI.md`](DUCKCLAW_ADMIN_UI.md)
- Gateway único: [`config/api_gateways_pm2.json.example`](../../../config/api_gateways_pm2.json.example)
