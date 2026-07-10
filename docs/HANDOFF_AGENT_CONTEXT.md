# Handoff — contexto para nuevo agente (Jul 2026)

Copia/pega este bloque al iniciar una conversación nueva.

---

## Objetivo del proyecto

DuckClaw = plataforma multi-agente **DB-first**. Admin + Playground deben funcionar **sin Telegram** (Telegram = integración opt-in). Fresh install como usuario nuevo con una sola bóveda limpia.

## Estado actual del repo

**Rama:** `samuel_dev` (push hecho; PR manual en GitHub Capadonna-Labs/DuckClaw compare main...samuel_dev)

**Commit reciente:** `feat(platform): M033 main-only schema, progreso RAG y DDL sin ALTER`

### Hecho

- `.env` canónico: `DUCKCLAW_GATEWAY_DB_PATH=db/private/default/duckclaw.duckdb`
- **33 migraciones** (`M033`: `main.homeostasis_targets`, `main.meditate_runs`, `main.semantic_memory`; elimina schema `harness_core`)
- Bootstrap sin `ALTER TABLE ADD COLUMN`
- `db/` limpio: solo `db/private/default/duckclaw.duckdb` (~7 MB)
- Telegram opt-in (no arranque core)
- Admin fire-and-forget writes → DB-Writer
- Knowledge-Indexer proceso separado (PM2 `DuckClaw-Knowledge-Indexer`)
- Barra progreso RAG (parcial — ver bug abierto)

### Bug abierto — indexación MacMiniVault (PRIORIDAD)

**Síntoma:** Fuente `MacMiniVault` queda `INDEXANDO` con `0/49 archivos (0%)`. Banner dice "Indexación completada" pero 0 docs/chunks.

**Evidencia Redis (job `ksync_9ca0add8104f4732`):**
```json
{"status":"completed","detail":"{\"scanned\":0,\"upserted\":0,\"skipped\":0,\"removed\":0,\"chunks\":0}"}
```

**Fuente en DuckDB:**
```
source_id: ksrc_3142a8b73ed04483
status: indexing
docs: 0, chunks: 0
metadata.file_count: 49
metadata.sync_job_id: ksync_9ca0add8104f4732
source_uri: .../MacMiniVault (Google Drive)
tenant_id: user-jimenez-ochoa-samuel-feec1482b878c628
```

**Causa raíz (seguro):** El indexer marcaba jobs como `completed` aunque `skipped_reason` o `scanned=0` — la fuente nunca recibía `status=ready` ni `status=error`. UI interpretaba `completed` como éxito.

**Fix en progreso (sin commit aún):**
- `process_knowledge_sync_job`: `skipped_reason` → `failed` + `_enqueue_source_error_status`
- `folder_ingest` con scanned=0 → failed
- UI: detecta job completed con 0 archivos → mensaje error rojo
- Endpoint `GET /knowledge/sources/{id}/indexing-progress` con `error_message`

**Archivos clave:**
- `packages/shared/src/duckclaw/knowledge_sync_queue.py`
- `packages/agents/src/duckclaw/forge/rag/knowledge_auto_sync.py`
- `services/api-gateway/routers/admin_domains/knowledge.py`
- `services/knowledge-indexer/main.py`
- `apps/duckclaw-admin/src/app/(admin)/knowledge/page.tsx`
- `apps/duckclaw-admin/src/components/knowledge/KnowledgeIndexingProgress.tsx`

**Diagnóstico pendiente:** Por qué el indexer ejecutó ingest con `scanned=0` (¿race source_not_found?, ¿sync_lock?, ¿env sin `DUCKCLAW_KNOWLEDGE_ALLOWED_ROOTS` en PM2?). Con `.env` cargado el scan encuentra 49 archivos.

**Comandos:**
```bash
uv run duckops stack deploy
uv run duckclaw-migrate --verify-only
pm2 logs DuckClaw-Knowledge-Indexer --lines 50
redis-cli GET duckclaw:knowledge_sync_status:ksync_9ca0add8104f4732
cd apps/duckclaw-admin && pnpm dev
```

**Workaround usuario:** Eliminar fuente del RAG → re-importar vault → **Sincronizar** tras deploy del fix.

## Arquitectura DB-first (resumen)

Ver **README.md** sección "Arquitectura DB-first (canonical)".

- Una DB: `db/private/default/duckclaw.duckdb`, schema `main`
- Gateway/indexer/agents: read_only
- Mutaciones: `write_commands` → Redis `duckdb_write_queue` → DB-Writer
- RAG carpetas: Gateway encola → Redis `duckclaw:knowledge_sync_jobs` → Knowledge-Indexer

## Deuda / no urgente

- Squash 33 migraciones → 1
- Mover paquete Python `harness_core/` → `packages/agents` (naming)
- Rotar secretos expuestos en chat
- Admin no arranca con stack deploy (manual `pnpm dev`)
- PR GitHub: requiere `gh auth login`

## Tests relevantes

```bash
uv run pytest tests/test_knowledge_sync_queue.py tests/test_schema_migrations.py -q
```

---

*Actualizado: 2026-07-10*
