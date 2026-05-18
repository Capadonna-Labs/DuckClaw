# Catálogo MCP oficial (Admin UI)

**Objetivo:** Priorizar integraciones vía **MCP** (paquetes empaquetados) frente a skills Python sueltas en `forge/skills/`. La consola admin expone servidores de referencia del repositorio [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) como guía de instalación, sin scrapear el README en runtime.

---

## 1. Navegación

- Sidebar: orden **Workers → MCP → Skills** (fuente: `apps/duckclaw-admin/src/config/adminNav.ts`).
- Overview: QuickLinks MCP antes de Skills.

## 2. Fuente de datos

| Artefacto | Rol |
|-----------|-----|
| [`config/mcp_official_reference.yaml`](../../../config/mcp_official_reference.yaml) | Lista curada (7 reference servers activos del README oficial) |
| `services/api-gateway/core/mcp_official_catalog.py` | Loader YAML → dict tipado |
| `GET /api/v1/admin/catalog/mcp` | Campo `official_reference` junto a `duckclaw_mcp` y `stdio_servers` |

Actualización del catálogo: **manual** al cambiar upstream (no sync automático con GitHub).

## 3. Contrato `official_reference`

```json
{
  "source_repo": "https://github.com/modelcontextprotocol/servers",
  "source_label": "modelcontextprotocol/servers",
  "registry_url": "https://registry.modelcontextprotocol.io/",
  "servers": [
    {
      "id": "memory",
      "name": "Memory",
      "description": "...",
      "runtime": "npx",
      "install": "npx -y @modelcontextprotocol/server-memory",
      "repo_path": "src/memory"
    }
  ]
}
```

## 4. UI `/mcp`

1. Copy: MCP recomendado (stdio en `config/mcp_servers.yaml`, DuckClaw HTTP, bridges Docker/npm).
2. Sección **Servidores de referencia (oficial)** — tabla con install copiable y enlace al repo.
3. Pie: enlace al repo + MCP Registry; CTA secundario a `/skills`.

## 5. UI `/skills`

Banner informativo: integraciones empaquetadas → usar **MCP** primero; catálogo `forge/skills` sin cambios.

## 6. Fuera de alcance v1

- Instalar o editar `mcp_servers.yaml` desde la UI.
- Listar servidores *archived* del repo oficial.
- Sincronización automática con GitHub.

## 7. Verificación

- `pytest tests/test_admin_router.py -k catalog_mcp`
- Manual: sidebar, `/mcp` (7 filas oficiales), `/skills` (banner).
