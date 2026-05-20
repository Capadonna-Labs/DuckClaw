# Variables de entorno — DuckClaw Admin

Hay **dos capas** de configuración: el gateway (raíz del monorepo) y el BFF Next (esta app).

## Raíz del monorepo — `.env`

El **API Gateway** y el **db-writer** leen este archivo.

| Variable | Obligatoria | Descripción |
|----------|-------------|-------------|
| `DUCKCLAW_ADMIN_API_KEY` | **Sí** (admin) | Clave compartida con el BFF. Header `X-Admin-Key`. |
| `REDIS_URL` | Sí | Cola escritura + historial chat |
| `DUCKDB_PATH` / vars vault | Según despliegue | Hub DuckDB por defecto |
| `DUCKCLAW_REPO_ROOT` | No | Ruta absoluta al monorepo si el gateway no infiere la raíz |
| `DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES` | Para pantalla Telegram | Formato multiplex documentado en specs |
| `LANGCHAIN_API_KEY` | No | Traces LangSmith (admin API `/traces/langsmith`) |

Ejemplo mínimo para admin:

```env
DUCKCLAW_ADMIN_API_KEY=change-me-use-long-random-string
REDIS_URL=redis://127.0.0.1:6379/0
```

Tras cambiar la clave: `pm2 restart DuckClaw-Gateway --update-env`.

## App Next — `apps/duckclaw-admin/.env.local`

Solo variables **de servidor** (Next no expone secretos sin prefijo `NEXT_PUBLIC_` de forma segura; igualmente la API key no debe ir al browser).

| Variable | Obligatoria | Descripción |
|----------|-------------|-------------|
| `DUCKCLAW_GATEWAY_URL` | **Sí** | Base del gateway, p. ej. `http://127.0.0.1:8000` |
| `DUCKCLAW_ADMIN_API_KEY` | **Sí** | **Misma** valor que en `.env` raíz |
| `DUCKCLAW_REPO_ROOT` | No | Referencia documental; el gateway resuelve plantillas |
| `NEXT_PUBLIC_DUCKCLAW_GATEWAY_URL` | No | Solo si algún componente cliente necesita saber la URL |

Plantilla: [`.env.example`](../.env.example).

```bash
cp apps/duckclaw-admin/.env.example apps/duckclaw-admin/.env.local
```

### Desarrollo vs producción

| Entorno | `DUCKCLAW_GATEWAY_URL` |
|---------|------------------------|
| Local | `http://127.0.0.1:8000` o `http://localhost:8000` |
| Tailscale (celular) | **Mantén** `http://127.0.0.1:8000` — el BFF Next corre en el Mac y habla con el gateway en loopback |
| Docker | Host del contenedor gateway en la red compose |

### Admin en el celular (Tailscale Serve)

El gateway público/Telegram suele ir por Funnel en `:443`. La consola admin va aparte en **`:8443`** (solo tailnet, no sustituye el Funnel).

```bash
# Terminal 1 — admin (anota el puerto si Next usa 3001)
pnpm admin:dev

# Terminal 2 — proxy HTTPS tailnet (puerto local del paso anterior)
DUCKCLAW_ADMIN_PORT=3001 pnpm admin:serve-tailscale
```

**Importante:** si Next usa **3001** (puerto 3000 ocupado), define `DUCKCLAW_ADMIN_PORT=3001` en `.env.local` o el arranque automático puede apuntar Serve al puerto equivocado.

`tailscale funnel reset` (botón «Iniciar plataforma») **borra** toda la config Serve, incluido `:8443`. El stack vuelve a aplicar Serve al final; si falla, ejecuta:

```bash
DUCKCLAW_ADMIN_PORT=3001 uv run python scripts/restore_tailscale_admin_serve.py
```

En el iPhone/Android (app Tailscale conectada): `https://<nombre-maquina>.<tailnet>.ts.net:8443/`  
Ejemplo: `https://mac-mini-de-juan.tailc85db0.ts.net:8443/`

Login demo: `admin@duckclaw.local` / `1234` (ver `src/config/adminUsers.ts`).

Para apagar el proxy admin: `tailscale serve --https=8443 off`

**No** commitear `.env.local`. Está en `.gitignore` de la app.

## Variables legacy CRM (no usadas por rutas admin actuales)

Si reactivas el módulo GovTech PQRSD, ver [legacy-crm-module.md](legacy-crm-module.md):

- `CRM_DUCKDB_PATH`, `CRM_VAULT_USER_ID`, `DUCKCLAW_GATEWAY_USER_ID_OVERRIDE`
- `NEXT_PUBLIC_IA_HABILITADA`, `OPENROUTER_API_KEY`

## Checklist de coherencia

1. `DUCKCLAW_ADMIN_API_KEY` idéntica en raíz `.env` y `apps/duckclaw-admin/.env.local`.
2. Gateway responde: `curl -H "X-Admin-Key: …" http://127.0.0.1:8000/api/v1/admin/health`.
3. Next arranca sin `503` en la primera llamada a `/api/admin/health`.
