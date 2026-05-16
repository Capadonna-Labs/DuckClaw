# API Gateway (HTTP)

Implementación: `services/api-gateway/main.py`.

## Rutas principales

| Área | Ruta típica | Notas |
|------|-------------|--------|
| Chat agente | `POST /api/v1/agent/chat` | Ingress JSON; bóveda por `user_id` si multi-vault |
| Escritura (cola) | `POST /api/v1/db/write` | Encola para **db-writer**; no mutar DuckDB directo en prod |
| Telegram | `POST /api/v1/telegram/webhook` | Webhook nativo |
| Health | `GET /health` | Liveness |

**OpenAPI:** en local, FastAPI suele exponer `/docs` (solo dev).

## Python (paquetes)

- Vaults: `duckclaw.vaults` en **duckclaw-shared**
- Telegram multiplex: `duckclaw.integrations.telegram` en **shared**
- Grafos/workers: **duckclaw-agents** (`duckclaw.graphs`, `duckclaw.workers`)

## Ver también

- [Multi Vault](../operations/Multi-Vault-System.md)
- [Observabilidad](../operations/Observability-2.1-Identidad.md)
- [Singleton Writer](../architecture/singleton_writer.md)
- [COMANDOS](../COMANDOS.md)
- Spec: `specs/features/Telegram Webhook Multiplex (multi-bot).md`
