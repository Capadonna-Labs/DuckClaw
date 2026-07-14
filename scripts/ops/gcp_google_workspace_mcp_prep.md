# Google Workspace MCP — GCP prep

Endpoint: `https://workspacemcp.googleapis.com/mcp/v1`  
Conector DuckClaw: `mcp_google_workspace` (preset `google_workspace`)

## APIs

```bash
gcloud services enable \
  gmail.googleapis.com drive.googleapis.com calendar-json.googleapis.com \
  chat.googleapis.com workspacemcp.googleapis.com calendarmcp.googleapis.com \
  mapstools.googleapis.com \
  --project=PROJECT_ID
```

## OAuth consent screen (obligatorio)

### 1. Test users (fix 403 access_denied)

Si la app está en **Testing** (External), solo entran usuarios de prueba:

1. Google Cloud Console → **Google Auth Platform** → **Audience** (Público)
2. **Test users** → **Add users**
3. Añadir: `juanjoarevalo57@gmail.com` (y cualquier cuenta que use OAuth)

Sin esto Google responde: `Error 403: access_denied` — app no verificada.

### 2. Scopes en consent screen

Añadir en **Data Access** (solo readonly recomendado):

- `https://www.googleapis.com/auth/gmail.readonly`
- `https://www.googleapis.com/auth/drive.readonly`
- `https://www.googleapis.com/auth/calendar.readonly`
- `https://www.googleapis.com/auth/chat.messages.readonly`

DuckClaw filtra scopes del PRM a `*.readonly` cuando el conector es `read_only: true`.

### Calendar: listar + crear eventos

Universal Search (`mcp_google_workspace`) solo expone **`search_corpus`** — no `create_event`.

Para listar/crear eventos usa conector aparte:

- Endpoint: `https://calendarmcp.googleapis.com/mcp/v1`
- Preset: `google_calendar` → `mcp_google_calendar`
- APIs GCP: `calendarmcp.googleapis.com` **y** `calendar-json.googleapis.com`
- OAuth scopes (Data Access + preset):
  - `https://www.googleapis.com/auth/calendar.calendarlist.readonly`
  - `https://www.googleapis.com/auth/calendar.events.freebusy`
  - `https://www.googleapis.com/auth/calendar.events.readonly`
  - `https://www.googleapis.com/auth/calendar.events` (create/update/delete)
- Tras deploy: **Reconectar OAuth** (necesita consent fresco; access token dura ~1h)
- DuckClaw guarda `refresh_token` y renueva el access token automáticamente

**Nota:** Calendar MCP está en **Developer Preview**. Si Calendar REST API funciona pero MCP responde `The caller does not have permission`, confirma que `calendarmcp.googleapis.com` esté habilitada en el mismo proyecto del OAuth client. Si sigue, el proyecto puede requerir enrollment en Google Workspace Developer Preview.

Override opcional en VPS `.env`:

```
GOOGLE_OAUTH_SCOPES=openid,https://www.googleapis.com/auth/gmail.readonly,https://www.googleapis.com/auth/calendar.readonly
```

## OAuth Web client — redirect URI

Registrar **exactamente** (sin puerto `:8443` si el callback es gateway):

```
https://ubuntu-2gb-ash-1.tailc85db0.ts.net/api/v1/oauth/callback
```

Opcional (Admin BFF directo):

```
https://{admin-host}/api/admin/mcp/connectors/oauth/callback
```

## VPS `.env`

```
GOOGLE_OAUTH_CLIENT_ID=....apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=...
GOOGLE_OAUTH_REDIRECT_URI=https://ubuntu-2gb-ash-1.tailc85db0.ts.net/api/v1/oauth/callback
```

DuckClaw usa `GOOGLE_OAUTH_REDIRECT_URI` para Google (ignora `window.location.origin` del Admin).

## Tailscale Serve (VPS)

`tailscale serve` en **:443** debe apuntar al **gateway PM2** (puerto **8000**), no a un uvicorn viejo en 8002:

```bash
tailscale serve --bg --https=443 http://127.0.0.1:8000
tailscale serve --bg --https=8443 http://127.0.0.1:3000
```

Si `:443` apunta a proceso sin `/api/v1/oauth/callback`, Google devuelve `{"detail":"Not Found"}` tras el consent.

## Google Maps (conector aparte)

Maps **no** entra en el consent de Workspace (`workspacemcp.googleapis.com`). Es otro MCP:

- Endpoint: `https://mapstools.googleapis.com/mcp`
- Preset: `google_maps` → conector `mcp_google_maps`
- Scope OAuth: `https://www.googleapis.com/auth/maps-platform.mapstools`
- Alternativa: API key en header `X-Goog-Api-Key` (no implementado en DuckClaw aún)

Añadir scope en consent screen y conectar `mcp_google_maps` por separado en Admin.

## Validate

```bash
set -a && . ./.env && set +a && .venv/bin/python scripts/ops/validate_google_oauth_env.py
```
