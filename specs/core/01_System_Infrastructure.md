# Layer 0: Infraestructura y Orquestación del Sistema

Esta especificación consolida la conectividad, seguridad, despliegue y estructura del ecosistema DuckClaw. Incluye: arquitectura monorepo, API Gateway, red Tailscale Mesh, CI/CD y Docker.

---

## 1. Arquitectura Monorepo

DuckClaw está organizado como monorepo para escalabilidad y despliegues independientes.

### Mapeo de componentes (legacy → monorepo)

| Origen (Legacy) | Destino (Monorepo) | Responsabilidad |
|:---|:---|:---|
| `src/`, `include/` | `packages/core/` | Núcleo nativo C++ y bindings DuckDB. |
| `duckclaw/graphs/` | `packages/agents/src/duckclaw/graphs/` | Grafos LangGraph y flujos de decisión. |
| `duckclaw/workers/` | `packages/agents/src/duckclaw/workers/` | Plantillas de trabajadores virtuales. |
| `duckclaw/utils/` | `packages/shared/src/duckclaw/utils/` | Formateo y funciones comunes. |
| `duckclaw/integrations/` | `packages/shared/src/duckclaw/integrations/` | Telegram, build_llm, proveedores LLM. |
| `duckclaw/ops/` | `packages/shared/src/duckclaw/ops/` | CLI `duckops` y gestores de despliegue. |
| `scripts/` | `packages/shared/scripts/` | Automatización y setup. |

### Organización de la raíz

- **`packages/`**: Lógica de negocio (core, agents → duckclaw.graphs, shared); cada subpaquete tiene su `pyproject.toml`.
- **`services/`**: Puntos de despliegue (API Gateway, DB Writer).
- **`config/`**: Archivos `.json`, `.ini`, `.cjs` centralizados.
- **`data/`**: Datalake y snapshots locales.
- **`docker/`**: Imágenes multi-etapa para K8s y Docker Compose.

Principios: configuración desde `config/` o env; aislamiento de dependencias por paquete; cross-platform sin rutas hardcodeadas.

---

## 2. Conectividad: Tailscale Mesh

DuckClaw utiliza **Tailscale (WireGuard)** para una red privada E2EE entre Mac Mini y VPS.

- **Seguridad**: Zero-Trust con ACLs (p. ej. `tag:vps` → `tag:mac-mini:8000`).
- **Autenticación**: `X-Tailscale-Auth-Key` en endpoints de invocación.
- **Skill `TailscaleBridge`**: health check (`tailscale status`), resolución de IP privada, proxy con cabeceras de auth.
- **Protocolo**: n8n (VPS) ↔ DuckClaw (Mac Mini) por IP Tailscale; tráfico no sale a internet pública (Habeas Data).
- **Despliegue**: `tailscale up` en ambos nodos; firewall `ufw allow in on tailscale0`; verificación con `curl http://100.x.y.z:8000/health`.

---

## 3. API Gateway (FastAPI)

Único punto de entrada para Angular, n8n y servicios externos.

### Topología

- Angular/n8n → FastAPI Gateway → Auth Middleware → Agent Stream / Homeostasis Status / System Health.
- **Telegram (recomendado):** varios procesos gateway (puertos distintos en PM2); cada bot `setWebhook` a una URL HTTPS que termina en el puerto de *ese* proceso (`POST /api/v1/telegram/webhook`). Detalle: `specs/features/Telegram Webhook One Gateway One Port.md`. Alternativa un solo ingress: multiplex en `specs/features/Telegram Webhook Multiplex (multi-bot).md`.

### Endpoints (contrato API)

**Agentes (streaming)**

- `POST /api/v1/agent/{worker_id}/chat`: Body `message`, `session_id`, `history`, `stream` (default true). Respuesta: SSE token a token o JSON `{"response", "session_id"}` (n8n).
- `GET /api/v1/agent/{worker_id}/history`: Historial truncado (K=6).
- `GET /api/v1/agent/subagents/stream?session_id=...`: SSE de eventos de subagentes (subagents_started, subagents_updated, subagents_finished) para Angular.
- `POST /api/v1/agent/subagents/event`: Publicación de eventos de subagentes desde backend.

**Homeostasis**

- `GET /api/v1/homeostasis/status`: Estado de workers (beliefs, status).
- `POST /api/v1/homeostasis/{worker_id}/action`: Acción de restauración manual (HITL).

**Sistema**

- `GET /api/v1/system/health`: Tailscale, DuckDB, MLX.
- `GET /api/v1/system/logs`: Stream de logs (pm2).

### Middleware

- **Auth**: `X-Tailscale-Auth-Key` (interno) o `Authorization: Bearer <JWT>` (Angular).
- **Audit**: Registro en LangSmith; anonimización de datos sensibles (Habeas Data).
- **Rate limiting** (slowapi); **data masking** en salida.

Integración Angular: EventSource a SSE de chat y subagentes; polling a `/homeostasis/status` (p. ej. cada 30 s). Zero-Trust: validación de permisos en nodos del grafo, no en el Gateway.

---

## 4. Despliegue y persistencia (PM2 / Docker)

- **Local/Híbrido**: PM2 para `DuckClaw-Brain` (bot), `DuckClaw-Gateway` (API para n8n/Telegram) y `MLX-Inference` (MLX). Config generado por `duckops serve --pm2 --gateway` → `ecosystem.api.config.cjs`.
- **DuckClaw-Gateway**: Usa `services/api-gateway/main.py` (microservicio unificado: agente, db/write, homeostasis). Requiere variables de entorno para el LLM (`DUCKCLAW_LLM_PROVIDER`, `DUCKCLAW_LLM_MODEL`, `DUCKCLAW_LLM_BASE_URL`; claves según proveedor: `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, **`GROQ_API_KEY`** si `DUCKCLAW_LLM_PROVIDER=groq` con base `https://api.groq.com/openai/v1`, etc.) y para la BD (`DUCKCLAW_DB_PATH`, normalizada a `db/<nombre>.duckdb` por el wizard). Si el `.env` solo define `LLM_PROVIDER` / `LLM_MODEL` / `LLM_BASE_URL`, `build_llm` en `duckclaw.integrations.llm_providers` las refleja en `DUCKCLAW_LLM_*` cuando estas están vacías. El manager carga `.env` de la raíz al generar el config para propagarlas a PM2.
- **Contenerización**: Docker multi-etapa (`docker/base/`, `docker/api/`) para aislamiento y K8s.

---

## 5. CI/CD distribuido

Pipeline unificado: tests → despliegue Mac Mini y VPS.

- **CI**: pytest (`tests/`), mypy, validación SQL (sqlglot) para SQLValidator.
- **CD Mac Mini**: Self-hosted runner, `git pull`, `uv sync`, `pm2 reload`; health check post-despliegue; rollback automático si falla.
- **CD VPS**: SSH/rsync, `docker compose`, `systemctl restart n8n` si aplica.
- **Secretos**: GitHub Secrets (VPS_SSH_KEY, TAILSCALE_AUTH_KEY); sin tokens en repo.
- **Observabilidad**: Notificación Telegram del resultado del despliegue; registro en LangSmith.

---

## 6. Inferencia elástica (Hardware-Aware)

- **HardwareDetector** (al arranque): detecta Metal (Apple Silicon), CUDA (NVIDIA) o fallback API-Only; salida `InferenceConfig` (provider, device, model_path).
- **InferenceRouter**: en tiempo real enruta a MLX, Torch/CUDA o API según config. Core C++ con llama.cpp (Metal/CUDA/CPU); Dockerfile multi-etapa con `USE_CUDA` para Linux.

## 7. Resiliencia y recuperación

- **Singleton Writer Bridge** (ver Layer 1): escrituras vía Redis para evitar locks en DuckDB.
- **Disaster recovery**: cronjob de snapshot de `duckclaw.db` y `models/active/`; cifrado (Restic/SOPS); sync a R2/S3 con Object Lock.

---

*Consolidado desde: API_Gateway_(FastAPI), Tailscale_Mesh, CI/CD, Monorepo_Architecture_Mapping, Inferencia_Elastica, Auditoria_Arquitectura_y_Mejoras_Prioridad_Alta.*
