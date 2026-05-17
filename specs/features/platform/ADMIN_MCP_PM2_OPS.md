# Admin UI — arranque MCP vía PM2 (ops allowlist)

## Objetivo

Permitir **iniciar y reiniciar** el servidor MCP streamable HTTP (`duckclaw_mcp`, puerto `DUCKCLAW_MCP_PORT` / 8001) desde la pestaña **MCP** del admin y desde **Operaciones**, sin shell manual.

## Alcance

- Ecosystem PM2 canónico: `config/ecosystem.mcp.config.cjs` → proceso `DuckClaw-MCP`.
- Nuevos `op_id` en allowlist admin (gateway + fallback local Next):
  - `pm2_start_mcp` → `pm2 start config/ecosystem.mcp.config.cjs`
  - `pm2_restart_mcp` → `pm2 restart DuckClaw-MCP --update-env`
  - `pm2_logs_mcp` → últimas líneas de log
- UI: botones en `/mcp` (rol `admin`), re-probe de health tras ejecutar op.

## Fuera de alcance

- Arranque stdio de servidores en `mcp_servers.yaml`.
- Exposición Tailscale Funnel (sigue siendo ops de red).

## Seguridad

- Misma política que `/admin/ops/run`: solo `X-Admin-Key` + rol admin en UI.
- Sin ejecución arbitraria; argv fijos en allowlist.
- Auditoría `_admin_audit("ops.run", ...)`.

## Criterios de aceptación

1. Con MCP caído, admin pulsa **Iniciar MCP (PM2)** y en ≤30s el banner pasa a «MCP en línea» (si PM2 y venv están OK).
2. Con proceso ya en PM2, **Reiniciar MCP** recarga el servicio.
3. `GET /api/v1/admin/ops/commands` incluye los tres `op_id` nuevos.
