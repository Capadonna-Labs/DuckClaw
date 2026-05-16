# DuckClaw

**Multi-agent platform** with a zero-trust posture, **DuckDB** as the analytical state store, and a **singleton DB-Writer** path for ACID mutations (Gateway and workers enqueue; `services/db-writer` applies).

Cross-platform (Windows / Linux / macOS) · Multi-tenant vaults · Microservices-ready · Spec-driven development (`specs/`)

---

## Documentación

| Qué | Dónde |
|-----|--------|
| **Specs (normativa)** | [`specs/`](specs/) — leer antes de implementar |
| **Runbooks** | [`docs/`](docs/) — Markdown en repo, sin HTML |
| **Mapa del repo** | [`MONOREPO.md`](MONOREPO.md) — `packages/` vs `services/` |

Entrada: [`docs/index.md`](docs/index.md) · Diagrama: [`docs/architecture/system_overview.md`](docs/architecture/system_overview.md)

---

## Monorepo layout

Ver detalle en [`MONOREPO.md`](MONOREPO.md). Resumen:

```
duckclaw/
├── specs/             # SDD — fuente de verdad
├── docs/              # Runbooks (instalar, PM2, troubleshooting)
├── services/          # Procesos: api-gateway, db-writer, heartbeat, …
├── packages/          # Librerías: shared, agents, core, duckops
├── config/            # PM2, MCP (secretos en .env)
├── tests/
└── pyproject.toml     # uv workspace
```

---

## Key components

- **Singleton DB-Writer**: serializes durable DuckDB writes via Redis queues; keeps ledger-style state consistent.
- **API Gateway**: FastAPI front door (`services/api-gateway`); agent chat, DB write enqueue, Telegram webhook, VLM image ingest, health.
- **duckops**: Python CLI (`uv run duckops …`) for wizard-driven setup and local service control.
- **Training traces (optional)**: JSONL under `packages/agents/train/conversation_traces/` — [`packages/agents/train/README.md`](packages/agents/train/README.md), [`docs/agents/sft_conversation_traces.md`](docs/agents/sft_conversation_traces.md).
- **CRM**: https://github.com/ManePeqsiCoda/retoPWRSomegahack, https://inputs-rely-speakers-humor.trycloudflare.com/dashboard

---

## Developer quick start

```bash
uv sync
uv run duckops init # interactive wizard
uv run duckops serve --gateway
```

Operational detail (Redis, Telegram, PM2—including `duckops serve --pm2 --gateway`, DB-Writer—`doctor.py`, VLM env vars, trace flags): see [`docs/COMANDOS.md`](docs/COMANDOS.md) (**§8** cheat sheet) and [`docs/Installation.md`](docs/Installation.md). VLM spec: `specs/features/VLM INTEGRATION.md`.

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
