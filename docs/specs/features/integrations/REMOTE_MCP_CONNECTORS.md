# Remote MCP Connectors — spec v1

Entrada: [`docs/README.md`](../../../README.md). Protocolo: [MCP Architecture](https://modelcontextprotocol.io/docs/learn/architecture).

## Objetivo

Registry DB-first de conectores MCP (stdio + Streamable HTTP) con grants por worker, auth centralizado y política de tools. Primer perfil: **Higgsfield** (`https://mcp.higgsfield.ai/mcp`).

## Fuera de alcance v1

- OAuth redirect completo en UI Admin (v1: conectar OAuth en Claude Desktop/Code; sesión opcional en Admin para workers servidor)
- Catálogo npm auto-install desde admin (presets documentados; stdio manual)
- Sampling / roots MCP client features

## Tablas

- `main.admin_mcp_connectors` — conector lógico
- `main.admin_worker_mcp_grants` — worker_uid ↔ connector_id

Secrets: `admin_runtime_settings` domain `mcp_connector`, key `{connector_id}.bearer`, `secret=true`.

## Presets empaquetados (YAML)

Definición en [`packages/shared/src/duckclaw/seeds/mcp_connector_presets.yaml`](../../../../packages/shared/src/duckclaw/seeds/mcp_connector_presets.yaml). Loader: `duckclaw.mcp_connector_presets`.

| Prioridad | Origen |
|-----------|--------|
| 1 | `DUCKCLAW_MCP_PRESETS_PATH` — override explícito (forks, repos de extensión) |
| 2 | `{DUCKCLAW_REPO_ROOT}/config/mcp_connector_presets.yaml` — edición en monorepo |
| 3 | `duckclaw/seeds/mcp_connector_presets.yaml` — bundled en `duckclaw-shared` |

Perfiles reutilizables (`profiles.stdio_npx_ro`) evitan duplicar stdio/npx. API Python:

```python
from duckclaw.mcp_connector_presets import list_mcp_connector_presets, preset_payload
```

## API (gateway, admin key)

Prefix: `/api/v1/admin/mcp/connectors`

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/` | Lista conectores del tenant |
| GET | `/presets` | Perfiles empaquetados (Higgsfield, Notion, Google*, Tavily, Fetch, Time) |
| POST | `/` | Crear desde body o `preset_id` |
| PATCH | `/{connector_id}` | Metadata, allowlist, enabled |
| POST | `/{connector_id}/auth` | Guardar Bearer (secret) |
| POST | `/{connector_id}/test` | `list_tools` (health) |
| POST | `/{connector_id}/grants` | `{ worker_id }` |
| DELETE | `/{connector_id}/grants/{worker_id}` | Revocar grant |
| DELETE | `/{connector_id}` | Desactivar conector |

## Runtime

- `mcp_connector_bridge.register_worker_mcp_connector_tools(tools, db, worker_id, tenant_id)`
- Transports: `stdio`, `streamable_http`
- Tool names expuestos: `mcp__{connector_id}__{tool_name}`

## Política de tools

| Regla | Default |
|-------|---------|
| Sin grant worker | 0 tools |
| `tool_allowlist` vacío | Ninguna tool (admin debe allowlist o `*`) |
| `tool_allowlist` = `["*"]` | Todas salvo denylist |
| `read_only=true` | Omite tools con prefijos mutantes (`create_`, `delete_`, …) |
| Egress HTTP | Host debe estar en `egress_hosts` |

## Acceptance criteria

1. Admin crea conector preset `higgsfield`, pega Bearer, test lista tools.
2. Grant a un worker → Playground muestra tools `mcp__…`.
3. Conector deshabilitado → tools no aparecen.
4. Secret nunca en GET list (solo `has_auth: true`).

## Admin UI — inventario de conectores (N cards)

Patrones: **Progressive Disclosure** + **Table Filter** (`docs/architecture/UIUX-PATTERNS.md`). Objetivo: escanear salud de N conectores sin formularios inline de ~300px.

| Capa | Contenido |
|------|-----------|
| Lista densa | Nombre, `connector_id`, chips (`habilitado` / auth / grants), URL truncada |
| CTA primaria en fila | OAuth faltante → **Conectar OAuth** (sin drawer). Bearer faltante → **Configurar**. Auth OK sin grants → **Dar grant** (abre drawer). Resto → **Detalle** |
| Drawer lateral | Auth (OAuth/Bearer), grants, `list_tools`, desactivar |

Click en la fila abre el drawer. ConfirmModal sigue para grant. No meter OAuth PKCE solo detrás de modal: el salto de contexto ya es el redirect.

## Guía clic a clic (operativa)

### 0. Desplegar cambios

1. En la Mac/VPS del stack, desde la raíz del repo:
   ```bash
   pm2 restart DuckClaw-Gateway --update-env
   pm2 restart DuckClaw-DB-Writer --update-env
   cd apps/duckclaw-admin && npm run build && pm2 restart duckclaw-admin
   ```
2. Abre Admin → **MCP** → **Conectores MCP** (`/mcp/connectors`).

### 1. Prueba local sin token (recomendado primero)

1. En **Nuevo desde plantilla**, elige preset **MCP Time (local stdio)**.
2. Clic **Crear conector** → aparece en la lista densa (`mcp_mcp_time`).
3. Abre **Detalle** (o la fila) → **Probar list_tools** → debe listar tools de hora (requiere `npx` en el host del gateway).
4. En el drawer, elige un worker de prueba → **Grant worker**.
5. **Playground** → selecciona ese worker → pregunta: *«¿Qué hora es en UTC?»*.
6. Verifica en logs que aparece una tool `mcp__mcp_mcp_time__…`.

### 2. Higgsfield (imagen/video, OAuth en Admin)

1. Admin → **MCP** → pestaña **Conectores** → `mcp_higgsfield` (preset Higgsfield).
2. Clic **Conectar Higgsfield** → login OAuth en Higgsfield → vuelves a DuckClaw con sesión guardada.
3. **Probar list_tools** → tools de generación.
4. **Grant worker** (p. ej. un agente con skill `higgsfield`).
5. Playground: *«Genera una imagen…»*.

Variables opcionales en `.env`:
- `DUCKCLAW_ADMIN_URL` — URL pública del Admin (redirect post-OAuth).
- `DUCKCLAW_MCP_OAUTH_REDIRECT_URI` — callback exacto si difiere del default Admin BFF.

**Nota:** sesión OAuth caduca; usa **Reconectar Higgsfield** si test devuelve 401.

### 3. MCP Fetch (stdio, red externa)

Igual que Time, preset **MCP Fetch**. Grant + Playground con una URL pública. Requiere egress del gateway hacia internet.

### 4. Troubleshooting

| Síntoma | Causa probable | Acción |
|---------|----------------|--------|
| Test 502 / timeout stdio | `npx` no disponible en host gateway | Instala Node 20+ en la máquina del gateway |
| Test 401 Higgsfield | Sesión OAuth expirada o no guardada en Admin | Repite OAuth; guarda sesión en Admin |
| Playground sin tools MCP | Falta grant o conector deshabilitado | Grant worker + verifica `enabled` |
| Tool bloqueada | `read_only` + nombre mutante | Desactiva read_only o ajusta allowlist |

