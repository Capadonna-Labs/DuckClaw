# Agents/Shared Package Reorganization

**Estado:** implemented incremental, con fachadas de compatibilidad.

## Objetivo

Separar responsabilidades en `duckclaw-shared` y `duckclaw-agents` para que cada carpeta tenga una razón clara:

- `shared/config`: configuración runtime y política `.env`.
- `shared/storage`: DuckDB, vaults, grants, bootstrap y write queue.
- `shared/control_plane`: usuarios admin, perfiles, proyectos y catálogo de workers.
- `shared/llm`: construcción y utilidades de proveedores LLM.
- `agents/runtime`: ejecución de grafos, comandos, heartbeat, trazas y sandbox.
- `agents/manager`: superficie de orquestación del manager.
- `agents/graphs`: builders LangGraph públicos y compatibilidad.
- `agents/train`: prompts, scripts, datasets y outputs separados por intención.

## Contratos De Compatibilidad

Los imports legacy siguen disponibles durante la migración:

| Legacy | Nuevo destino |
|--------|---------------|
| `duckclaw.gateway_db` | `duckclaw.storage.gateway_db` |
| `duckclaw.vaults` | `duckclaw.storage.vaults` |
| `duckclaw.shared_db_grants` | `duckclaw.storage.shared_db_grants` |
| `duckclaw.db_write_queue` | `duckclaw.storage.db_write_queue` |
| `duckclaw.bootstrap_core` | `duckclaw.storage.bootstrap_core` |
| `duckclaw.admin_console_users` | `duckclaw.control_plane.admin_console_users` |
| `duckclaw.admin_user_profiles` | `duckclaw.control_plane.admin_user_profiles` |
| `duckclaw.admin_worker_catalog` | `duckclaw.control_plane.admin_worker_catalog` |
| `duckclaw.admin_workspace` | `duckclaw.control_plane.admin_workspace` |
| `duckclaw.integrations.llm_providers` | `duckclaw.llm.providers` |
| `duckclaw.graphs.graph_server` | `duckclaw.runtime.graph_server` |
| `duckclaw.graphs.on_the_fly_commands` | `duckclaw.runtime.commands` |
| `duckclaw.graphs.sandbox` | `duckclaw.runtime.sandbox` |
| `duckclaw.graphs.chat_heartbeat` | `duckclaw.runtime.heartbeat` |
| `duckclaw.graphs.conversation_traces` | `duckclaw.runtime.conversation_traces` |
| `duckclaw.graphs.manager_graph` | `duckclaw.manager.graph` |

## Training Layout

`packages/agents/train` queda organizado así:

- `prompts/synthetic/`: prompts generadores de datos.
- `scripts/data/`: curación y materialización.
- `scripts/serve/`: launchers locales MLX/OpenAI-compatible.
- `scripts/train/`: entrenamiento SFT/LoRA.
- `scripts/eval/`: evaluación y guardrails de modelos.
- `datasets/raw`: datos fuente no versionables.
- `datasets/curated`: datos regenerados.
- `datasets/golden`: fixtures pequeños sanitizados.
- `outputs`: adapters, modelos y reportes generados.

## Regla De Evolución

Nuevos módulos deben importar desde los destinos nuevos. Los imports legacy se mantienen sólo para compatibilidad externa y deben eliminarse cuando Gateway, DuckOps, tests y specs hayan migrado.
