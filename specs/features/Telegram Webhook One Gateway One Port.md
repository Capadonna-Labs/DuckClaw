# Telegram Webhook: un gateway, un puerto, un webhook (modo recomendado)

## Objetivo

Aislar cada bot de Telegram en **su** proceso API Gateway (PM2): mismos logs, misma `DUCKCLAW_DB_PATH`, mismo `TELEGRAM_WEBHOOK_SECRET` y tokens de respuesta, sin multiplexar varios bots en un solo uvicorn salvo necesidad operativa.

## Contrato

1. **Un bot** → **un** `setWebhook` → **una** URL HTTPS cuyo destino final es el **puerto** del gateway definido para ese agente (ver [`config/api_gateways_pm2.json`](../../config/api_gateways_pm2.json)).
2. Path del handler: `POST /api/v1/telegram/webhook` (sin sufijos por bot cuando el aislamiento es por puerto/hostname).
3. `secret_token` en Bot API debe coincidir con `TELEGRAM_WEBHOOK_SECRET` (u otra variable documentada para ese proceso) en el **mismo** proceso PM2 que recibe el POST.

## Ingress

Telegram exige HTTPS. El monorepo no impone un proveedor: cada despliegue debe asegurar que la URL pública del bot termine en el `127.0.0.1:<puerto>` correcto. Opciones típicas:

- **Cloudflare Tunnel** (u otro túnel): varios `hostname` → varios puertos locales.
- **Tailscale Funnel / Serve**: ver [KB Funnel](https://tailscale.com/kb/1223/funnel/); un funnel “clásico” mapea un puerto; para N gateways usar varias entradas según política del tailnet o un proxy frontal.
- **Reverse proxy** (Caddy/nginx): TLS único; reglas por host o path → `8000`, `8283`, etc.

## Verificación

- `getWebhookInfo` por bot: la `url` refleja el ingress que enruta solo al gateway esperado.
- `pm2 logs <Gateway-Name>` muestra el `POST` al webhook al usar ese bot; los demás gateways no deben registrar ese tráfico.

## Relación con otros modos

- **Multiplex** (`DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES`, varios bots, un solo proceso/puerto): [Telegram Webhook Multiplex (multi-bot).md](Telegram%20Webhook%20Multiplex%20(multi-bot).md).
- Rutas `…/webhook/finanz` y `…/webhook/trabajo`: compatibilidad **legado** cuando un solo funnel recibe todo el tráfico; no sustituyen el modo recomendado si ya tienes N URLs → N puertos.

Operación: [docs/COMANDOS.md](../../docs/COMANDOS.md) § 2.0.
