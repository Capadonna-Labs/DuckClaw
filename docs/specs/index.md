# Índice de especificaciones

**Canónico:**

- Principios: [`../../specs/core/`](../../specs/core/) · [`../../specs/SDD_INDEX.md`](../../specs/SDD_INDEX.md)
- Features: [`../../specs/features/FEATURES_INDEX.md`](../../specs/features/FEATURES_INDEX.md)
- ADF / AXIS: [`../../specs/05_ADF_AGENT_DEFINITION_FRAMEWORK.md`](../../specs/05_ADF_AGENT_DEFINITION_FRAMEWORK.md)

Este índice solo enlaza; no copia el contenido de las specs.

## Core (`specs/core/`)

| Tema | Archivo |
|------|---------|
| Flujo de vida del dato | `00_Flujo de Vida del Dato (Wizard).md` |
| Infraestructura | `01_System_Infrastructure.md` |
| Memoria analítica | `02_Analytical_Memory_Architecture.md` |
| Skills y tooling | `03_Skills_and_Tooling_Framework.md` |
| Lógica cognitiva / workers | `04_Cognitive_Agent_Logic.md` |

## Features frecuentes

| Tema | Spec |
|------|------|
| Finanz + db-writer | [`finanz/FINANZ_ADMIN_SQL_DB_WRITER.md`](../../specs/features/finanz/FINANZ_ADMIN_SQL_DB_WRITER.md) |
| Context injection | [`finanz/FINANZ_CONTEXT_INJECTION_TELEGRAM.md`](../../specs/features/finanz/FINANZ_CONTEXT_INJECTION_TELEGRAM.md) |
| Webhook (recomendado) | [`telegram-gateway/TELEGRAM_WEBHOOK_ONE_PORT.md`](../../specs/features/telegram-gateway/TELEGRAM_WEBHOOK_ONE_PORT.md) |
| VLM | [`platform/VLM_INTEGRATION.md`](../../specs/features/platform/VLM_INTEGRATION.md) |
| Fly commands | [`platform/FLY_COMMANDS_UI.md`](../../specs/features/platform/FLY_COMMANDS_UI.md) |
| Guardrails | `packages/agents/src/duckclaw/guardrails/` (plan archivado en [`specs/archive/`](../../specs/archive/ARCHIVE_INDEX.md)) |
| AXIS | [`agents-axis/AXIS_TEMPLATES_001.md`](../../specs/features/agents-axis/AXIS_TEMPLATES_001.md) |

Lista completa por dominio: [`FEATURES_INDEX.md`](../../specs/features/FEATURES_INDEX.md).

## Docs relacionados

- [Arquitectura](../architecture/system_overview.md)
- [Singleton Writer](../architecture/singleton_writer.md)
- [Operaciones](../operations/index.md)
