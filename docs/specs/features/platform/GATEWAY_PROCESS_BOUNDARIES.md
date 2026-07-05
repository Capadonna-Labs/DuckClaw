# Gateway Process Boundaries

## Principio

**DuckClaw-Gateway** es HTTP I/O-bound: auth, routing, SSE, encolado Redis, lecturas DuckDB ligeras vía `run_heavy_work`. **Nunca indexa** PDFs, embeddings ni auto-sync.

| Proceso PM2 | Rol | Responsabilidad |
|-------------|-----|-----------------|
| `DuckClaw-Gateway` | `gateway` | HTTP, enqueue, búsqueda read-only |
| `DuckClaw-DB-Writer` | `db-writer` | Escrituras DuckDB ACID |
| `DuckClaw-Knowledge-Indexer` | `knowledge-indexer` | Cola Redis + ingest/sync/auto-sync |
| `DuckClaw-Heartbeat` | `heartbeat` | Crons, méditate, homeostasis |

## Cola unificada (`duckclaw:knowledge_sync_jobs`)

| Job kind | Gateway | Indexer |
|----------|---------|---------|
| `folder_ingest` | Encola tras crear fuente | Escanea carpeta, indexa |
| `folder_sync` | Encola en POST `/sync` | Sync incremental |
| `browser_upload` | Staging disco + encola | Parse, embed, db-writer |
| `single_file_sync` | Encola tras write sandbox/vault | Re-indexa un archivo |

Estado: `duckclaw:knowledge_sync_status:{job_id}`

## Variables Gateway

```bash
DUCKCLAW_PROCESS_ROLE=gateway
DUCKCLAW_EMBED_GOALS_TICKER=false
DUCKCLAW_GATEWAY_EMBED_KNOWLEDGE_SYNC=false
DUCKCLAW_KNOWLEDGE_AUTO_SYNC=false
DUCKCLAW_GATEWAY_EMBEDDING_POLICY=remote_only
DUCKCLAW_MLX_EMBEDDINGS_URL=http://127.0.0.1:8080/v1/embeddings
```

## Guard de código

`knowledge_indexer_guard.assert_indexer_process_for_mutation()` — lanza si el Gateway intenta indexar.

## Stack local

```bash
uv run duckops stack deploy
```

Procesos PM2: DB-Writer → Knowledge-Indexer → Heartbeat → Gateway.

Admin **Reiniciar stack** incluye Knowledge-Indexer y Heartbeat.

## Pendiente (otros subsistemas)

- Telegram inbound → cola Redis (fase 2 — fuera de scope)
- UI Admin: poll genérico write-tasks tras CRUD

Ver también: `GATEWAY_DB_WRITER_BOUNDARIES.md`
