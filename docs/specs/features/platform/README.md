# Specs — plataforma (`docs/specs/features/platform/`)

Índice de las specs de plataforma. **Arquitectura canónica:** [`DB_FIRST_CORE_REFACTOR.md`](DB_FIRST_CORE_REFACTOR.md). Entrada general: [`docs/README.md`](../../../README.md).

**Estados:** `canonical` = normativa vigente · `operational` = runbook/spec de feature acotada · `stale` = conservada con aviso, no refleja el código al 100% · `archived` = histórico en [`docs/archive/platform/`](../../../archive/platform/)

| Archivo | Estado | Léelo si… |
|---------|--------|-----------|
| [`DB_FIRST_CORE_REFACTOR.md`](DB_FIRST_CORE_REFACTOR.md) | **canonical** | Necesitas la verdad de arquitectura DB-first, purges y roadmap |
| [`DUCKCLAW_ADMIN_UI.md`](DUCKCLAW_ADMIN_UI.md) | **canonical** | Trabajas en `apps/duckclaw-admin` |
| [`ADMIN_IDENTITY_RBAC_ERD.md`](ADMIN_IDENTITY_RBAC_ERD.md) | **canonical** | Auth, sesiones y RBAC de la consola |
| [`ADMIN_ACCESS_MANAGEMENT.md`](ADMIN_ACCESS_MANAGEMENT.md) | **canonical** | Usuarios consola, whitelist Telegram, shared grants |
| [`ADMIN_RUNTIME_SETTINGS.md`](ADMIN_RUNTIME_SETTINGS.md) | **canonical** | Pantalla y API de runtime settings |
| [`RAG_TRANSVERSAL_DB_FIRST.md`](RAG_TRANSVERSAL_DB_FIRST.md) | **canonical** | Knowledge sources, ingest y RAG transversal |
| [`MULTI_VAULT_SYSTEM.md`](MULTI_VAULT_SYSTEM.md) | **canonical** | `/vault`, bóvedas por chat y ATTACH |
| [`HOMEOSTASIS_HEARTBEAT.md`](HOMEOSTASIS_HEARTBEAT.md) | operational | Servicio heartbeat y homeostasis proactiva |
| [`SPAWN_GENERIC_DEPLOY.md`](SPAWN_GENERIC_DEPLOY.md) | operational | Despliegue VM con spawn / bootstrap core-only |
| [`COMFYUI_VISUAL_BRIDGE.md`](COMFYUI_VISUAL_BRIDGE.md) | operational | Bridge ComfyUI local |
| [`COMFYUI_IMAGE_EDIT.md`](COMFYUI_IMAGE_EDIT.md) | operational | Edición de imagen vía ComfyUI |
| [`ADMIN_COMFYUI_GEN.md`](ADMIN_COMFYUI_GEN.md) | operational | Generación ComfyUI desde admin |
| [`FAL_MEDIA_BRIDGE.md`](FAL_MEDIA_BRIDGE.md) | operational | Media vía FAL |
| [`SFT_DATASET_FORMAT.md`](SFT_DATASET_FORMAT.md) | operational | Formato JSONL SFT |
| [`SFT_TRACE_SANITIZER_GEMMA4.md`](SFT_TRACE_SANITIZER_GEMMA4.md) | operational | Sanitizado de trazas Gemma4 |
| [`ADMIN_TRAIN_UI.md`](ADMIN_TRAIN_UI.md) | **stale** | Solo contexto histórico — usar `duckops train` y `packages/agents/train/` |
| [`VLM_INTEGRATION.md`](VLM_INTEGRATION.md) | **stale** | Contexto VLM parcial; ejemplos War Room legacy |
| [`API_GATEWAY_HARDENING.md`](API_GATEWAY_HARDENING.md) | **stale** | Plan de hardening OSS, no estado actual del gateway |
| [`WORKER_FACTORY_VERTICAL_PURGE_FIRST_CUT.md`](WORKER_FACTORY_VERTICAL_PURGE_FIRST_CUT.md) | **archived** | Primer corte factory → [`archive`](../../../archive/platform/WORKER_FACTORY_VERTICAL_PURGE_FIRST_CUT.md) |
| [`META_COGNITIVE_PGQ_VSS.md`](META_COGNITIVE_PGQ_VSS.md) | **archived** | Diseño PGQ/VFS no implementado → [`archive`](../../../archive/platform/META_COGNITIVE_PGQ_VSS.md) |
| [`ADMIN_PROJECT_DETAIL_AND_PLAYGROUND_FIXES.md`](ADMIN_PROJECT_DETAIL_AND_PLAYGROUND_FIXES.md) | **archived** | Fixes cerrados → [`archive`](../../../archive/platform/ADMIN_PROJECT_DETAIL_AND_PLAYGROUND_FIXES.md) |
| [`INFRA_BOOTSTRAP_VERTICAL_PURGE_SDD.md`](INFRA_BOOTSTRAP_VERTICAL_PURGE_SDD.md) | **archived** | Hito 1–2 infra (resumen en DB_FIRST) → [`archive`](../../../archive/platform/INFRA_BOOTSTRAP_VERTICAL_PURGE_SDD.md) |

## Telegram y otros dominios

- Gateway Telegram: [`../telegram-gateway/`](../telegram-gateway/)
- Patrones UI admin: [`docs/architecture/UIUX-PATTERNS.md`](../../../architecture/UIUX-PATTERNS.md)
