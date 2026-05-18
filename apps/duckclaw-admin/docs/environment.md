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
| Tailscale | URL HTTPS del gateway en la tailnet (misma clave admin) |
| Docker | Host del contenedor gateway en la red compose |

**No** commitear `.env.local`. Está en `.gitignore` de la app.

## Variables legacy CRM (no usadas por rutas admin actuales)

Si reactivas el módulo GovTech PQRSD, ver [legacy-crm-module.md](legacy-crm-module.md):

- `CRM_DUCKDB_PATH`, `CRM_VAULT_USER_ID`, `DUCKCLAW_GATEWAY_USER_ID_OVERRIDE`
- `NEXT_PUBLIC_IA_HABILITADA`, `OPENROUTER_API_KEY`

## Checklist de coherencia

1. `DUCKCLAW_ADMIN_API_KEY` idéntica en raíz `.env` y `apps/duckclaw-admin/.env.local`.
2. Gateway responde: `curl -H "X-Admin-Key: …" http://127.0.0.1:8000/api/v1/admin/health`.
3. Next arranca sin `503` en la primera llamada a `/api/admin/health`.
