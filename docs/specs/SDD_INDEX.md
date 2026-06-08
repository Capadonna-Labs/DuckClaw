# SDD Index — DuckClaw Spec-Driven Development

## DB-First Hardening — Status

| Prioridad | Tarea | Fase | Estado |
|-----------|-------|------|--------|
| P0 | Migraciones versionadas + constraints | Phase 1 | 🔴 Pendiente |
| P0 | DB-Writer comandos tipados + idempotencia | Phase 2 | 🔴 Pendiente |
| P0 | Gateway sin RW directo productivo | Phase 3 | 🔴 Pendiente |
| P1 | Completar modelo: conversaciones, kanban, workflows, MCP | Phase 4 | 🔴 Pendiente |
| P1 | Admin UI sin fallbacks filesystem | Phase 5 | 🔴 Pendiente |
| P1 | Tests de migraciones, writer, gateway | Phase 6 | 🔴 Pendiente |
| P2 | Auditoría e idempotencia en writes | Phase 4 | 🔴 Pendiente |
| P2 | Runtime Settings DB > env | Phase 4 | 🔴 Pendiente |

## Core specs

Principios transversales — leer antes de cambios grandes:

| Archivo | Contenido |
|---------|-----------|
| `docs/core/00_Flujo de Vida del Dato (Wizard).md` | Onboarding, bóvedas, deploy |
| `docs/core/01_System_Infrastructure.md` | Monorepo, Tailscale, API Gateway, PM2/Docker, CI/CD |
| `docs/core/02_Analytical_Memory_Architecture.md` | DuckDB, PGQ, VSS, CRM, persistencia |
| `docs/core/03_Skills_and_Tooling_Framework.md` | Tavily, Strix, MCP, sandbox, ingesta |
| `docs/core/04_Cognitive_Agent_Logic.md` | Workers, homeostasis, HITL, SFT, singleton writer |
| `features/platform/LEGACY_RETIREMENT_DB_FIRST.md` | Migración DB-first — hoja de ruta |
| `features/platform/ADMIN_IDENTITY_RBAC_ERD.md` | RBAC, actores y visibilidad |
| `features/platform/ADMIN_RUNTIME_SETTINGS.md` | Precedencia env vs DB |
| `features/platform/SPAWN_GENERIC_DEPLOY.md` | Deploy automático VPS |

## Features de producto

→ **[`features/FEATURES_INDEX.md`](features/FEATURES_INDEX.md)**

## Plan de implementación

1. **Phase 1**: Migraciones versionadas + constraints DB
2. **Phase 2**: DB-Writer comandos tipados
3. **Phase 3**: Gateway sin RW directo
4. **Phase 4**: Modelo completo + auditoría
5. **Phase 5**: Admin UI sin fallbacks
6. **Phase 6**: Tests integrales
