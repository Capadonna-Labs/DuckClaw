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
- **CRM**: https://github.com/ManePeqsiCoda/retoPWRSomegahack, https://inputs-rely-speakers-humor.trycloudflare.com/dashboard

---

## Developer quick start

```bash
uv sync
uv run duckops init # interactive wizard
uv run duckops serve --gateway
```

Operational detail (Redis, Telegram, PM2, VLM env vars, trace flags): see [`docs/COMANDOS.md`](docs/COMANDOS.md) and [`docs/Installation.md`](docs/Installation.md). VLM architecture hub: [`docs/specs/vlm_integration.md`](docs/specs/vlm_integration.md).

---

## Herramientas de Desarrollo

### Vibe Kanban (Planning Board)

Planning board con soporte para agentes de código. Requiere **Node.js ≥ 20**. Ejecutar solo en el Mac mini local (no en el VPS); no publicar por túnel por defecto (acceso vía localhost o Tailscale).

```bash
npm run kanban
# o directamente:
npx vibe-kanban --port 3333
```

Acceso: http://localhost:3333

PM2 (opcional): `pm2 start config/ecosystem.vibe-kanban.cjs`

**GitHub MCP en Vibe Kanban:** si la app no admite archivo de proyecto, configura MCP en **Settings → MCP Servers** (documentación en [Connecting MCP Servers](https://www.vibekanban.com/docs/settings-beta/mcp-servers)). Usa la misma imagen Docker oficial `ghcr.io/github/github-mcp-server` con `GITHUB_PERSONAL_ACCESS_TOKEN` y toolsets como `repos,issues,pull_requests` (omitir `projects`).

### CFD Dashboard

Dashboard de trading cuantitativo:

```bash
streamlit run scripts/humans/cfd_dashboard.py
```

Acceso: http://localhost:8501

### Diagnóstico rápido (Doctor)

```bash
uv run python scripts/doctor.py
```

### GitHub MCP Docker (protocolo MCP real)

El Doctor valida PAT + imagen, pero **no** abre una sesión stdio completa. Si pruebas a mano con un solo mensaje JSON hacia Docker, típico error del servidor oficial:

```text
method invalid during initialization  method=tools/list
```

Eso aparece porque el transporte MCP exige el handshake (**`initialize`**, luego **`notifications/initialized`**) antes de **`tools/list`**. DuckClaw y el siguiente script usan el cliente Python **`mcp`**, que ya hace ese orden al listar herramientas.

```bash
uv run python scripts/smoke_github_mcp_stdio.py
```

No pongas el PAT en la línea de `docker run` (sale en histórico de shell); usa solo `GITHUB_TOKEN` en `.env` o variables de entorno.

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
