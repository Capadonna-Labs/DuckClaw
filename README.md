# DuckClaw

**Multi-agent platform** with a zero-trust posture, **DuckDB** as the analytical state store, and a **singleton DB-Writer** path for ACID mutations (Gateway and workers enqueue; `services/db-writer` applies).

Cross-platform (Windows / Linux / macOS) · Multi-tenant vaults · Microservices-ready · Spec-driven development (`specs/`)

---

## Documentation (MkDocs)

Human-oriented docs (architecture, operations, API overview, curated specs) live under [`docs/`](docs/).

```bash
uv run mkdocs serve
uv run mkdocs build --strict
```

Start here: [`docs/index.md`](docs/index.md) (published site home when built).

---

## Monorepo layout

```
duckclaw/
├── packages/
│   ├── core/          # Native layer & bindings (performance-critical paths)
│   ├── agents/        # LangGraph, workers, forge templates
│   │   └── train/     # Conversation traces (JSONL), SFT Gemma/MLX pipeline — see train/README.md
│   ├── shared/        # Shared Python utilities
│   └── duckops/       # CLI (wizard, serve, etc.)
├── services/
│   ├── api-gateway/   # FastAPI ingress
│   ├── db-writer/     # Singleton writer (Redis → DuckDB)
│   └── heartbeat/     # Optional proactive / homeostasis daemon
├── docs/              # MkDocs source (Material theme)
├── specs/             # Canonical specifications (features + core)
├── config/            # Gateway, PM2, MCP, etc.
├── db/                # Local DuckDB vaults (gitignored data)
├── docker/            # Dockerfiles
├── tests/             # Pytest suites
├── mkdocs.yml
└── pyproject.toml     # Root workspace (uv)
```

---

## Key components

- **Singleton DB-Writer**: serializes durable DuckDB writes via Redis queues; keeps ledger-style state consistent.
- **API Gateway**: FastAPI front door (`services/api-gateway`); agent chat, DB write enqueue, Telegram webhook, VLM image ingest, health.
- **duckops**: Python CLI (`uv run duckops …`) for wizard-driven setup and local service control.
- **Training traces (optional)**: successful chat turns can be written to JSONL under `packages/agents/train/conversation_traces/` for SFT datasets (`DUCKCLAW_SAVE_CONVERSATION_TRACES`, etc.). Site docs: [`docs/agents/sft_conversation_traces.md`](docs/agents/sft_conversation_traces.md) (published under **Agents → SFT & conversation traces** when you run MkDocs); repo README: [`packages/agents/train/README.md`](packages/agents/train/README.md).

---

## Developer quick start

```bash
uv sync
uv run duckops init # interactive wizard
uv run duckops serve --gateway
```

Operational detail (Redis, Telegram, PM2, VLM env vars, trace flags): see [`docs/COMANDOS.md`](docs/COMANDOS.md) and [`docs/Installation.md`](docs/Installation.md). VLM architecture hub: [`docs/specs/vlm_integration.md`](docs/specs/vlm_integration.md).

---

## Testing the singleton-writer pipeline

End-to-end **API Gateway → Redis → DB Writer → DuckDB** is covered by [`tests/run_singleton_writer_pipeline.py`](tests/run_singleton_writer_pipeline.py). Architecture context: [`docs/architecture/singleton_writer.md`](docs/architecture/singleton_writer.md); infrastructure narrative: `specs/core/01_System_Infrastructure.md` and `specs/core/00_Flujo de Vida del Dato (Wizard).md`.

**Unit tests** (no live Redis):

```bash
uv run pytest tests/run_singleton_writer_pipeline.py -v -m "not integration"
```

**Integration** (Redis on `localhost:6379`, e.g. `docker run -d --name duckclaw-redis -p 6379:6379 redis:7-alpine`):

```bash
RUN_SINGLETON_PIPELINE_INTEGRATION=1 uv run pytest tests/run_singleton_writer_pipeline.py -v -m integration
```

---

## Docker

```bash
docker build -t duckclaw-base -f docker/base/Dockerfile .
docker build -t duckclaw-api -f docker/api/Dockerfile .
```

---

## Spec-driven development

No substantial feature without an approved spec under [`specs/`](specs/). Index and conventions: [`specs/README.md`](specs/README.md).

---

Built by [IoTCoreLabs](https://iotcorelabs.io)
