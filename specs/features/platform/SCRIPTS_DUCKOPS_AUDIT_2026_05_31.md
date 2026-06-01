# Scripts DuckOps Audit — 2026-05-31

**Estado:** auditoría aplicada. No borrar `scripts/SCRIPTS-DEPRECATED/` hasta revisión dedicada.

## Decisiones

- Shell activo migrado a `duckops` con wrappers compatibles:
  - `scripts/tailscale_serve_admin.sh` → `uv run duckops ingress serve-admin`
  - `scripts/prefetch_mcp_reddit.sh` → `uv run duckops mcp prefetch reddit`
  - `scripts/start_comfyui.sh` → `uv run duckops comfyui start`
- `scripts/deploy/spawn-install.sh` se conserva como shell de bajo nivel por bootstrap de sistema; DuckOps lo expone como `uv run duckops deploy spawn-install`.
- One-offs eliminados del árbol activo:
  - `scripts/crm_origin_check.py`
  - `scripts/openweather_city.py`
  - `scripts/experimental/remap_weights.py`
  - `scripts/experimental/LOCAL_EXPERIMENTAL_SCRIPTS.md`

## Specs Revisadas

- `DUCKCLAW_ADMIN_UI.md`: legacy parcial; apunta al contrato DB-first de `ADMIN_IDENTITY_RBAC_ERD.md`.
- `FORGE_PROJECTS.md`: legacy filesystem; el contrato canónico es `/workspace/projects*`.
- `SPAWN_GENERIC_DEPLOY.md`: actualizado a `duckops db bootstrap`.
- `TELEGRAM_WEBHOOK_MULTIPLEX.md`: actualizado a `duckops ingress telegram-register-webhooks`.
- `TELEGRAM_MCP_INTEGRATION.md`: actualizado a `duckops init`.
- `TELEGRAM_WEBHOOK_ONE_PORT.md`: se mantiene como modo recomendado.
