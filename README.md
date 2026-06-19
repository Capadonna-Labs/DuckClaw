# DuckClaw

Plataforma multi-agente con **DuckDB** como estado analítico, mutaciones ACID vía **DB-Writer** (cola Redis) y **API Gateway** como puerta de entrada.

Multi-tenant · Windows / Linux / macOS · Spec-driven (`docs/specs/`)

---

## Inicio rápido

```bash
uv sync
uv run duckops init          # wizard de configuración
uv run duckops serve --gateway
```

Diagnóstico: `uv run python scripts/doctor.py`  
Operación (Redis, PM2, Telegram, variables): [`docs/COMANDOS.md`](docs/COMANDOS.md)

**VPS (actualizar):** `bash scripts/deploy/vps-deploy.sh` · primera vez: `--install` · remoto: `--remote user@host`

---

## Estructura del repo

```
duckclaw/
├── packages/     # Librerías: agents, core, shared, duckops
├── services/     # Procesos: api-gateway, db-writer, heartbeat, …
├── apps/         # Consola admin (Next.js)
├── integrations/ # Sensory node, edge devices, …
├── docs/         # Specs, arquitectura y runbooks
└── tests/
```

---

## Componentes principales

| Pieza | Rol |
|-------|-----|
| **API Gateway** | Chat, webhooks, admin API, encola escrituras |
| **DB-Writer** | Aplica mutaciones DuckDB de forma serializada |
| **Agents** | Manager, workers LangGraph, comandos fly, RAG |
| **duckops** | CLI local: `init`, `serve`, `doctor` |
| **Admin UI** | [`apps/duckclaw-admin/`](apps/duckclaw-admin/) — plantillas, playground, políticas |

Extensiones externas (fly commands, worker skills): [`docs/extensions/fly-commands.md`](docs/extensions/fly-commands.md)

---

## Imports Python

Puntos de entrada públicos más usados (`uv sync` en la raíz):

```python
# DuckDB
from duckclaw import DuckClaw

# MLOps / SFT (filesystem-only, sin Redis)
from duckclaw.traces import TraceCollector
from duckclaw.train import MlxSFT

# Workers
from duckclaw.workers import WorkerFactory, WorkerSpec, list_workers, load_manifest

# RAG
from duckclaw.forge.rag import (
    build_knowledge_context,
    preserve_context_blocks_for_worker,
    search_knowledge,
)

# Extensiones desde repos externos (DUCKCLAW_EXTENSION_ROOT, …)
from duckclaw.extensions import (
    dispatch_extension_fly_command,
    extension_fly_read_only_command_names,
    invoke_extension_worker_skill_hooks,
)
```

Script de entrenamiento: `packages/agents/train/train_sft.py` (usa `MlxSFT` internamente).

---

## Tests

```bash
uv run pytest tests/ -m "not integration" --ignore tests/run_singleton_writer_pipeline.py --ignore tests/deprecated
```

Pipeline completo Gateway → Redis → DB-Writer: [`tests/run_singleton_writer_pipeline.py`](tests/run_singleton_writer_pipeline.py)

---

## Documentación

| Qué | Dónde |
|-----|--------|
| Índice | [`docs/README.md`](docs/README.md) |
| Primeros pasos | [`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md) |
| Arquitectura | [`docs/architecture/system_overview.md`](docs/architecture/system_overview.md) |
| Specs | [`docs/specs/`](docs/specs/) |

---

Built by [IoTCoreLabs](https://iotcorelabs.io)
