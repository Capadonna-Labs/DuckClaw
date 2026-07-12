# Specs — plataforma (`docs/specs/features/platform/`)

Índice de specs de plataforma. **Arquitectura canónica:** [`DB_FIRST_CORE_REFACTOR.md`](DB_FIRST_CORE_REFACTOR.md). Entrada general: [`docs/README.md`](../../../README.md).

| Archivo | Rol | Léelo si… |
|---------|-----|-----------|
| [`DB_FIRST_CORE_REFACTOR.md`](DB_FIRST_CORE_REFACTOR.md) | **canonical** | Arquitectura DB-first, purges y roadmap |
| [`PLUG_AND_PLAY_ONBOARDING.md`](PLUG_AND_PLAY_ONBOARDING.md) | **canonical** | Onboarding dev: doctor → init → serve → admin |
| [`DUCKCLAW_ADMIN_UI.md`](DUCKCLAW_ADMIN_UI.md) | **canonical** | Trabajas en `apps/duckclaw-admin` |
| [`apps/duckclaw-admin/README.md`](../../../../apps/duckclaw-admin/README.md) | operational | Runbook UI: manifest, herramientas, GitHub MCP, troubleshooting |
| [`ADMIN_IDENTITY_RBAC_ERD.md`](ADMIN_IDENTITY_RBAC_ERD.md) | **canonical** | Auth, sesiones y RBAC de la consola |
| [`ADMIN_ACCESS_MANAGEMENT.md`](ADMIN_ACCESS_MANAGEMENT.md) | **canonical** | Usuarios consola, whitelist Telegram, shared grants |
| [`ADMIN_RUNTIME_SETTINGS.md`](ADMIN_RUNTIME_SETTINGS.md) | **canonical** | Pantalla y API de runtime settings |
| [`INTEGRATION_SECRETS.md`](INTEGRATION_SECRETS.md) | **canonical** | API keys de integraciones (DB-first) |
| [`RAG_TRANSVERSAL_DB_FIRST.md`](RAG_TRANSVERSAL_DB_FIRST.md) | **canonical** | Knowledge sources, ingest y RAG transversal |
| [`MULTI_VAULT_SYSTEM.md`](MULTI_VAULT_SYSTEM.md) | **canonical** | `/vault`, bóvedas por chat y ATTACH |
| [`SPAWN_GENERIC_DEPLOY.md`](SPAWN_GENERIC_DEPLOY.md) | operational | Despliegue VM con spawn / bootstrap core-only |
| [`PIPECAT_VOICE_REALTIME.md`](PIPECAT_VOICE_REALTIME.md) | **canonical** | Voz realtime WebRTC (Pipecat) — core genérico, catálogo de workers después |

## Otros dominios

- Telegram: [`../telegram-gateway/TELEGRAM.md`](../telegram-gateway/TELEGRAM.md)
- Patrones UI admin: [`docs/architecture/UIUX-PATTERNS.md`](../../../architecture/UIUX-PATTERNS.md)
- Operaciones (heartbeat, loop, multi-vault): [`docs/operations/`](../../../operations/)

**Train:** sin API admin `/train` — usar `uv run duckops train` y [`packages/agents/train/`](../../../../packages/agents/train/).
