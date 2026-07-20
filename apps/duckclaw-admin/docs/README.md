# Documentación — DuckClaw Admin

Guías operativas de esta app. Arquitectura del monorepo: [`docs/architecture/`](../../../docs/architecture/) · patrones UI: [`UIUX-PATTERNS.md`](../../../docs/architecture/UIUX-PATTERNS.md).

Punto de entrada rápido: [`../README.md`](../README.md).

## Guías

| Archivo | Para quién | Tema |
|---------|------------|------|
| [architecture.md](architecture.md) | Arquitectos / backend | BFF, catálogo DB-first, contrato admin API |
| [environment.md](environment.md) | DevOps / local | Variables `.env` raíz vs `.env.local` |
| [development.md](development.md) | Frontend | Pantallas, herramientas del manifest, lint, tests |
| [voice-realtime.md](voice-realtime.md) | Frontend / voz | Pipecat WebRTC en playground y burbuja |

## Enlaces del monorepo

- Arranque: [`docs/GETTING_STARTED.md`](../../../docs/GETTING_STARTED.md)
- Gateway admin router: [`services/api-gateway/routers/admin.py`](../../../services/api-gateway/routers/admin.py)
- Catálogo workers (runtime): [`packages/shared/src/duckclaw/catalog_worker.py`](../../../packages/shared/src/duckclaw/catalog_worker.py)
- Catálogo skills (UI picker): [`packages/shared/src/duckclaw/skill_catalog.py`](../../../packages/shared/src/duckclaw/skill_catalog.py)
- Plantilla filesystem `default`: [`packages/agents/src/duckclaw/forge/seed/default/`](../../../packages/agents/src/duckclaw/forge/seed/default/)
