# Admin DuckDB Explorer (tabular, PGQ, vector)

**Objetivo:** Consola web en `/duckdb` para auditar bóvedas DuckDB sin conexión directa desde el navegador: explorador SQL read-only, grafo PGQ y búsqueda semántica VSS.

**Flujo:** Browser → BFF `/api/admin/duckdb/*` → Gateway `/api/v1/admin/duckdb/*` → DuckDB `read_only=True`.

---

## Endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/duckdb/tables` | Catálogo `information_schema.tables` por schema. Query: `vault_path?` |
| `POST` | `/duckdb/query` | Body `{ "query": "SELECT …", "vault_path?": "…" }` → `{ columns, rows, row_count, limit_applied? }` |
| `GET` | `/duckdb/pgq-graph` | Grafo `{ nodes, links }` para react-force-graph-2d. Query: `vault_path?` |
| `POST` | `/duckdb/vector-search` | Body `{ "query?": "", "limit?": 10, "vault_path?": "…" }` → `{ results, mode, warning? }` |

Todos protegidos con `X-Admin-Key` (`_require_admin_key`).

---

## Esquemas

### PGQ (grafos)

- Tablas: `memory_nodes` (`node_id`, `label`, `properties`), `memory_edges` (`source_id`, `target_id`, `relationship`).
- Si no existen: grafo vacío `{ nodes: [], links: [] }` (no 500).

### VSS (memoria semántica)

- Tabla: **`main.semantic_memory`** (`id`, `content`, `source`, `embedding FLOAT[384]`, `embedding_status`, `created_at`).
- Búsqueda: `array_cosine_distance(embedding, ?::FLOAT[384])` + `embed_text()` en gateway (dim 384).
- Query vacío: últimos N por `created_at DESC` (`mode: recent`).
- Con texto: vector READY primero; fallback léxico (`semantic_memory_hybrid`).
- Tabla ausente: HTTP 400 — *La memoria vectorial aún no ha sido inicializada*.

### SQL explorer

- Solo `SELECT` / `WITH` (rechazar DDL/DML).
- Si la query no incluye `LIMIT`, el gateway añade **LIMIT 500** server-side.

---

## UI (duckclaw-admin)

Pestañas en `/duckdb`:

1. **Data Explorer** — `TableExplorer` (árbol + grid + SQL).
2. **PGQ Graph** — `PGQVisualizer` (react-force-graph-2d, SSR off).
3. **Vector Memory** — `VectorExplorer` (cards + distance badge).
4. **Overview** — bóvedas y variables `.env` (vista legada).

Selector de bóveda compartido (`DuckDbVaultSelector`).

---

## Referencias

- [`02_Analytical_Memory_Architecture.md`](../../core/02_Analytical_Memory_Architecture.md)
- [`DUCKCLAW_ADMIN_UI.md`](DUCKCLAW_ADMIN_UI.md)
- Implementación: `services/api-gateway/core/admin_duckdb_readonly.py`
