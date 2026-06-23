# Sandbox Artifacts Viewer — spec v1

Entrada: [`docs/README.md`](../../../README.md). UI: [`UIUX-PATTERNS.md`](../../../architecture/UIUX-PATTERNS.md) (Module Tabs, Preview, Table Filter).

## Objetivo

Visualizar artefactos generados por `run_sandbox` / `run_browser_sandbox` **dentro del Admin Playground**, sin indexarlos en RAG ni copiarlos al vault OUTPUT.

**Explícitamente fuera de alcance v1:** botón “Promover al vault”, sync a Google Drive, filas en `admin_knowledge_*`.

## Principios

| Lane | Rol |
|------|-----|
| Sandbox scratch | Cómputo aislado; artefactos efímeros con TTL |
| Vault OUTPUT + RAG | Entregables explícitos (`write_output_document`, Report Engine) |

## Almacenamiento

```
output/sandbox/{chat_session_id}/{run_id}/
  manifest.json
  <archivos copiados desde /workspace/output>
```

- `chat_session_id` = `sanitize_chat_to_session_id(chat_id)` o `"default"`.
- `run_id` = UUID hex por ejecución exitosa (o por intento con artefactos).
- Compatibilidad: copia legacy a `output/sandbox/default/` opcional (Telegram) — no usar para el viewer.

### manifest.json

```json
{
  "run_id": "abc123",
  "chat_id": "playground-…",
  "chat_session_id": "playground_…",
  "tenant_id": "default",
  "worker_id": "informe-mensual-agent",
  "created_at": 1718650000.0,
  "expires_at": 1718918800.0,
  "exit_code": 0,
  "artifacts": [
    {
      "artifact_id": "uuid",
      "filename": "chart.png",
      "relative_path": "chart.png",
      "mime": "image/png",
      "byte_size": 12345,
      "previewable": true
    }
  ]
}
```

## TTL

- Default: `DUCKCLAW_SANDBOX_ARTIFACT_TTL_S` = 259200 (72 h).
- Limpieza: al arranque del gateway + endpoint admin opcional `POST /sandbox/artifacts/cleanup`.
- Borrar directorio `run_id` completo al expirar.

## API (gateway, admin key)

Prefix: `/api/v1/admin/sandbox/artifacts`

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/runs?chat_id=&limit=20` | Lista runs recientes del chat |
| GET | `/runs/{run_id}` | Detalle + lista artefactos |
| GET | `/{artifact_id}/preview?chat_id=` | Preview (texto/json/tabular/imagen) |
| GET | `/{artifact_id}/download?chat_id=` | Descarga binaria |
| POST | `/cleanup` | Purga runs expirados (admin) |

Autorización: misma validación que `GET /sandbox/chat-policy` (`_playground_team_context`).

## Preview por MIME

| MIME / ext | Preview |
|------------|---------|
| image/* | bytes inline |
| text/*, .md | texto UTF-8 (md renderizado en UI) |
| .csv | primeras 100 filas JSON |
| .json | pretty JSON truncado |
| .parquet | schema + 50 filas (pyarrow si disponible) |
| .docx | texto vía MarkItDown (solo preview, no escribe vault) |
| otro | 404 preview; download sí |

## SSE / Playground

Tras `run_sandbox` exitoso con artefactos, en sesión admin UI:

```json
{ "kind": "visual", "sandbox_run_id": "…", "artifact_ids": ["…"], "text": "Sandbox: N artefactos" }
```

## UI

- Ruta dedicada **`/sandbox`** (sidebar → Trabajo → Sandbox) con pestañas:
  - **Archivos** — explorador global + filtro por `chat_id`; preview; descargar; eliminar; guardar en Drive
  - **Configuración** — política red, contenedores activos, `chat_id` de referencia
  - **Navegador** — noVNC (antes `/vnc`, redirige aquí)
- Playground: enlace a `/sandbox?chat=…` (sin panel embebido).
- Copy: scratch efímero hasta «Guardar en Drive» (entonces vault OUTPUT + RAG opcional).

## API adicional (v2)

| Método | Ruta | Descripción |
|--------|------|-------------|
| DELETE | `/runs/{run_id}?chat_id=` | Borrar run completo |
| DELETE | `/{artifact_id}?chat_id=` | Borrar un archivo |
| POST | `/{artifact_id}/save-to-vault` | Copia a `KNOWLEDGE_OUTPUT_ROOTS` |
| GET | `/runs` sin `chat_id` | Lista global (admin workspace) |

## Tests

- Unit: registry paths, manifest write/read, TTL purge, path traversal blocked.
- API: list runs, preview md/png, download docx.
- Sandbox: `_collect_artifacts` escribe manifest con run_id.

## Acceptance criteria

1. Ejecutar `run_sandbox` que escriba `out.md` + `plot.png` → aparecen en panel del Playground para ese `chat_id`.
2. Preview md y png sin tocar tablas RAG.
3. Runs expirados eliminados por cleanup.
4. Guardar en Drive copia a OUTPUT sin borrar scratch; RAG solo si `sync_rag` y auto_sync activo.
