# Telegram Webhook Multiplex (multi-bot)

## Modo recomendado (fuera de este documento)

Cuando cada bot tiene **su propio** proceso gateway y **su propia** URL HTTPS que termina en el puerto PM2 correcto, **no** hace falta multiplex ni `DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES`. Ver [Telegram Webhook One Gateway One Port.md](Telegram%20Webhook%20One%20Gateway%20One%20Port.md) y [docs/COMANDOS.md](../../docs/COMANDOS.md) § 2.0.

Este documento describe el **Modo B**: varios bots compartiendo **una** URL pública y **un** proceso receptor.

## Problema

Una sola URL HTTPS (p. ej. Tailscale Funnel) no puede ejecutar varios procesos Puerto-distintos a la vez. Si **todos** los bots registran el mismo `setWebhook` URL contra **un** gateway, ese gateway debe enrutar cada `Update` al worker y al `TELEGRAM_BOT_TOKEN` correcto.

Hoy el handler usa `DUCKCLAW_TELEGRAM_DEFAULT_WORKER` → por defecto `finanz`, y un solo token de salida, por lo que cualquier bot que comparta la URL se comporta como Finanz.

## Solución

Telegram envía el `secret_token` definido en `setWebhook` en la cabecera `X-Telegram-Bot-Api-Secret-Token`.  

Variable opcional: `DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES` — JSON lista de objetos:

- `secret` (string, obligatorio): mismo valor que `secret_token` en `setWebhook` de ese bot.
- `worker_id` (string, obligatorio): id del grafo (p. ej. `finanz`, `bi_analyst`, `siata_analyst`).
- `tenant_id` (string, opcional): por defecto `default`.
- `bot_token_env` (string, obligatorio): nombre de variable con el token Bot API para **respuestas** de ese bot (convención estándar: `TELEGRAM_<ID_MANIFEST_EN_MAYÚSCULAS>_TOKEN`, p. ej. `TELEGRAM_BI_ANALYST_TOKEN`; los nombres `TELEGRAM_BOT_TOKEN_*` siguen funcionando como legado).

Reglas de autorización:

1. Si **no** hay rutas parseables: se mantiene el comportamiento previo (`TELEGRAM_WEBHOOK_SECRET` único o sin secreto en dev).
2. Si hay rutas: se acepta la petición si la cabecera coincide con **alguna** ruta (compare_digest) **o** con `TELEGRAM_WEBHOOK_SECRET` legacy (modo “default” del proceso: worker/tenant/token del propio gateway).

Cada bot debe usar un `secret_token` distinto en `setWebhook`. La deduplicación Redis de updates incluye un fingerprint del secreto para evitar colisiones de `update_id` entre bots.
