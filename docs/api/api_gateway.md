# API Gateway Reference

This page has two parts: **HTTP surface** (for integrators) and **Python API reference** (auto-generated from docstrings via mkdocstrings).

## HTTP surface (FastAPI)

Implementation: `services/api-gateway/main.py` (FastAPI app).

| Area | Typical routes | Notes |
|------|----------------|--------|
| Agent chat | `POST /api/v1/agent/chat` | Main JSON chat ingress; resolves vault path per `user_id` when multi-vault is enabled. |
| DB write (enqueue) | `POST /api/v1/db/write` | Queues writes for the singleton DB-Writer; do not bypass for production mutations. |
| Telegram | `POST /api/v1/telegram/webhook` (+ optional path variants) | Native webhook; see [Telegram Webhook Multiplex](../specs/telegram_webhook_multiplex.md). |
| Health | `GET /health` | Liveness check (exact path may vary by deployment). |

**Auth / headers:** Some deployments use `X-Tailscale-Auth-Key` or similar; public Telegram webhook routes are documented in ops guides. See [Commands (COMANDOS)](../COMANDOS.md) and [Troubleshooting Gateway PM2](../Troubleshooting-Gateway-PM2.md).

**OpenAPI:** When the gateway is running locally, FastAPI typically exposes interactive docs at `/docs` (dev only unless explicitly enabled in production).

## Related documentation

- [Multi Vault System](../Multi-Vault-System.md) — `/vault` and `vault_db_path` behavior.
- [Observability and Identity](../Observability-2.1-Identidad.md) — log prefixes, LangSmith, fly commands.
- [Singleton Writer](../architecture/singleton_writer.md) — why writes go through the queue/Writer.
- [Specs hub](../specs/index.md) — canonical feature specs.

## Python API reference (mkdocstrings)

The blocks below document selected Python modules used by the gateway and vault layer.

## Manager Graph API Server

::: duckclaw.vaults

## Telegram Webhook Multiplex Core

::: duckclaw.integrations.telegram.telegram_webhook_multiplex
