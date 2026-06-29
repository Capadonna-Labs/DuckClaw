# Remote MCP Connectors — spec v1

Entrada: [`docs/README.md`](../../../README.md). Protocolo: [MCP Architecture](https://modelcontextprotocol.io/docs/learn/architecture).

## Objetivo

Registry DB-first de conectores MCP (stdio + Streamable HTTP) con grants por worker, auth centralizado y política de tools. Primer perfil: **Higgsfield** (`https://mcp.higgsfield.ai/mcp`).

## Fuera de alcance v1

- OAuth redirect completo en UI (v1: pegar Bearer manual post-login Higgsfield/Claude)
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
| 1 | `DUCKCLAW_MCP_PRESETS_PATH` — override explícito (forks, Capadonna-Driller) |
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
| GET | `/presets` | Perfiles empaquetados (Higgsfield, Fetch, Time) |
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

1. En **Nuevo conector**, elige preset **MCP Time (local stdio)**.
2. Clic **Crear conector** → aparece `mcp_mcp_time`.
3. Clic **Probar list_tools** → debe listar tools de hora (requiere `npx` en el host del gateway).
4. En el desplegable de workers, elige un worker de prueba → **Grant worker**.
5. **Playground** → selecciona ese worker → pregunta: *«¿Qué hora es en UTC?»*.
6. Verifica en logs que aparece una tool `mcp__mcp_mcp_time__…`.

### 2. Higgsfield (imagen/video, requiere Bearer v1)

Higgsfield no expone API key estática: usa OAuth en clientes nativos. DuckClaw v1 pide pegar el Bearer manualmente.

1. Crea cuenta en [higgsfield.ai](https://higgsfield.ai) (plan con créditos).
2. En **Claude Desktop** o **Cursor**: Settings → Connectors → Add custom connector.
   - Nombre: `Higgsfield`
   - URL: `https://mcp.higgsfield.ai/mcp`
3. Completa el login OAuth en el navegador.
4. Captura el Bearer (workaround v1):
   - Abre DevTools → pestaña **Network**.
   - Dispara una acción MCP en el cliente (p. ej. listar modelos).
   - Busca una petición a `mcp.higgsfield.ai` y copia el valor del header `Authorization: Bearer …` (sin la palabra Bearer).
5. Admin → **Conectores MCP** → preset **Higgsfield** → **Crear conector** (`mcp_higgsfield`).
6. Pega el token en **Token Bearer** → **Guardar token**.
7. **Probar list_tools** → debe devolver tools de generación.
8. **Grant worker** al agente que usarás en Playground/Telegram.
9. Playground: *«Genera una imagen de un pato en estilo minimalista»*.

**Nota:** el Bearer de OAuth caduca; si el test falla con 401, repite pasos 3–6.

### 3. MCP Fetch (stdio, red externa)

Igual que Time, preset **MCP Fetch**. Grant + Playground con una URL pública. Requiere egress del gateway hacia internet.

### 4. Troubleshooting

| Síntoma | Causa probable | Acción |
|---------|----------------|--------|
| Test 502 / timeout stdio | `npx` no disponible en host gateway | Instala Node 20+ en la máquina del gateway |
| Test 401 Higgsfield | Bearer expirado o mal pegado | Renueva OAuth y vuelve a guardar token |
| Playground sin tools MCP | Falta grant o conector deshabilitado | Grant worker + verifica `enabled` |
| Tool bloqueada | `read_only` + nombre mutante | Desactiva read_only o ajusta allowlist |

