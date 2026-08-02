# Knowledge dual-lane UX — Design

**Date:** 2026-08-02  
**Status:** Approved for implementation  
**Scope:** Transversal (any agent / task). Default binding: platform.

## Problem

Users confuse three layers:

1. `DUCKCLAW_KNOWLEDGE_ALLOWED_ROOTS` (disk allowlist)
2. Registered RAG sources (`admin_knowledge_sources`)
3. What the agent can retrieve in chat

UI actions like “Usar” only select a path; preview counts feel like “already in chat”. Indexing can fail with `source_not_found` when the sync job runs before db-writer creates the source row.

## Goals

- One mental model for technical and non-technical admins.
- Clear split: **En el chat** (indexed) vs **En disco** (readable under allowlist, not semantic search until promoted).
- Default new sources → platform scope (`project_id` / `worker_uid` empty unless user narrows).
- Existing URI → update/sync, not duplicate create.
- No raw `source_not_found` in the UI; indexer waits/retries for source row.

## Non-goals

- Embedding LibreOffice / full filesystem explorer as primary RAG.
- Per-Alcaldía copy or task-specific taxonomies.
- Changing ALLOWED_ROOTS semantics (still security allowlist).

## UX

### Carril A — En el chat

- List of registered sources with status (listo / indexando / falló).
- Primary CTA on a selected folder: **Añadir al chat** (create+ingest) or **Actualizar** if URI already registered.
- Progress and human errors.

### Carril B — En disco

- Browser over allowed roots.
- Copy: agent may read here if skills allow; **not** in semantic search until added to chat.
- “Elegir carpeta” (rename from “Usar”) only selects path + preview.
- Preview line: “N candidatos · aún no están en el chat”.

### Run settings (later / light touch)

- Chip “Conocimiento: N fuentes listas” linking to `/knowledge` (optional follow-up).

## Backend

1. Enqueue `CreateKnowledgeSourceCommand` **before** sync/ingest job.
2. On `source_not_found`, requeue with backoff/attempts (cap), then fail with clear detail.
3. Map `source_not_found` in admin error formatter to Spanish actionable copy.

## Success criteria

- Selecting an allowed root never implies it is searchable until status is listo.
- Re-adding MacMiniVault (or any existing URI) triggers sync, not a new orphaned job.
- Race create↔indexer does not surface as a stuck failure under normal db-writer latency.
