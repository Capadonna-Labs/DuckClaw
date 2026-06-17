# Specs — plataforma (`docs/specs/features/platform/`)

Índice de specs de plataforma. **Arquitectura canónica:** [`DB_FIRST_CORE_REFACTOR.md`](DB_FIRST_CORE_REFACTOR.md). Entrada general: [`docs/README.md`](../../../README.md).

| Archivo | Rol | Léelo si… |
|---------|-----|-----------|
| [`DB_FIRST_CORE_REFACTOR.md`](DB_FIRST_CORE_REFACTOR.md) | **canonical** | Arquitectura DB-first, purges y roadmap |
| [`DUCKCLAW_ADMIN_UI.md`](DUCKCLAW_ADMIN_UI.md) | **canonical** | Trabajas en `apps/duckclaw-admin` |
| [`ADMIN_IDENTITY_RBAC_ERD.md`](ADMIN_IDENTITY_RBAC_ERD.md) | **canonical** | Auth, sesiones y RBAC de la consola |
| [`ADMIN_ACCESS_MANAGEMENT.md`](ADMIN_ACCESS_MANAGEMENT.md) | **canonical** | Usuarios consola, whitelist Telegram, shared grants |
| [`ADMIN_RUNTIME_SETTINGS.md`](ADMIN_RUNTIME_SETTINGS.md) | **canonical** | Pantalla y API de runtime settings |
| [`RAG_TRANSVERSAL_DB_FIRST.md`](RAG_TRANSVERSAL_DB_FIRST.md) | **canonical** | Knowledge sources, ingest y RAG transversal |
| [`MULTI_VAULT_SYSTEM.md`](MULTI_VAULT_SYSTEM.md) | **canonical** | `/vault`, bóvedas por chat y ATTACH |
| [`HOMEOSTASIS_HEARTBEAT.md`](HOMEOSTASIS_HEARTBEAT.md) | operational | Heartbeat y homeostasis — ver también [`docs/operations/`](../../../operations/) |
| [`SPAWN_GENERIC_DEPLOY.md`](SPAWN_GENERIC_DEPLOY.md) | operational | Despliegue VM con spawn / bootstrap core-only |
| [`COMFYUI_VISUAL_BRIDGE.md`](COMFYUI_VISUAL_BRIDGE.md) | operational | Bridge ComfyUI local |
| [`COMFYUI_IMAGE_EDIT.md`](COMFYUI_IMAGE_EDIT.md) | operational | Edición de imagen vía ComfyUI |
| [`ADMIN_COMFYUI_GEN.md`](ADMIN_COMFYUI_GEN.md) | operational | Generación ComfyUI desde admin |
| [`FAL_MEDIA_BRIDGE.md`](FAL_MEDIA_BRIDGE.md) | operational | Media vía FAL |
| [`SFT_DATASET_FORMAT.md`](SFT_DATASET_FORMAT.md) | operational | Formato JSONL SFT |
| [`SFT_TRACE_SANITIZER_GEMMA4.md`](SFT_TRACE_SANITIZER_GEMMA4.md) | operational | Sanitizado de trazas Gemma4 |

## Otros dominios

- Telegram: [`../telegram-gateway/TELEGRAM.md`](../telegram-gateway/TELEGRAM.md)
- Patrones UI admin: [`docs/architecture/UIUX-PATTERNS.md`](../../../architecture/UIUX-PATTERNS.md)

**Train:** sin API admin `/train` — usar `uv run duckops train` y [`packages/agents/train/`](../../../../packages/agents/train/).
