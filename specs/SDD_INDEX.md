# Índice SDD (`specs/SDD_INDEX.md`)

## Capa consolidada (`specs/core/`)

Principios transversales — leer antes de cambios grandes:

| Archivo | Contenido |
|---------|-----------|
| **00_Flujo de Vida del Dato (Wizard).md** | Onboarding, bóvedas, deploy |
| **01_System_Infrastructure.md** | Monorepo, Tailscale, API Gateway, PM2/Docker, CI/CD |
| **02_Analytical_Memory_Architecture.md** | DuckDB, PGQ, VSS, CRM, persistencia |
| **03_Skills_and_Tooling_Framework.md** | Tavily, Strix, MCP, sandbox, ingesta |
| **04_Cognitive_Agent_Logic.md** | Workers, homeostasis, HITL, SFT, singleton writer (Gateway → Redis → db-writer) |

## Features de producto (`specs/features/`)

Specs **vivas** referenciadas por código y manifests. Organizadas por dominio; índice completo:

→ **[`specs/features/FEATURES_INDEX.md`](features/FEATURES_INDEX.md)**

## Otros

| Ruta | Uso |
|------|-----|
| [`05_ADF_AGENT_DEFINITION_FRAMEWORK.md`](05_ADF_AGENT_DEFINITION_FRAMEWORK.md) | Plantillas AXIS (ADF) |
| [`features/platform/AGENTS_SHARED_PACKAGE_REORG.md`](features/platform/AGENTS_SHARED_PACKAGE_REORG.md) | Límites de paquetes shared/agents y mapa de imports |
| [`specs/meta/`](meta/PLAN_FORMAT_STANDARD.md) | Formato obligatorio de planes |
| [`specs/archive/`](archive/ARCHIVE_INDEX.md) | Migraciones y planes ya ejecutados |

## Runbooks

No duplicar procedimientos en specs: [`docs/operations/`](../docs/operations/index.md) enlaza operación; las specs de feature apuntan al runbook cuando aplica (p. ej. Homeostasis, Multi-Vault).
