# Knowledge dual-lane Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Separate “en disco” vs “en el chat”, fix `source_not_found` race, reuse existing sources on re-import.

**Architecture:** Indexer retries missing source rows; gateway creates DB row before enqueueing ingest; admin Knowledge UI uses dual-lane copy and sync-if-exists.

**Tech Stack:** Python (gateway + `knowledge_sync_queue`), Next.js admin (`KnowledgeControlPanel`, `knowledge` page).

---

### Task 1: Indexer retry on `source_not_found`

**Files:**
- Modify: `packages/shared/src/duckclaw/knowledge_sync_queue.py`
- Modify: `tests/test_knowledge_sync_queue.py`

**Steps:**
1. When `get_knowledge_source` returns None, if `metadata.source_wait_attempts` < 20, sleep briefly, requeue job with incremented attempt, status `queued` detail `waiting_for_source`.
2. Else fail with `source_not_found`.
3. Unit test with FakeRedis covering requeue then eventual fail/pass.

### Task 2: Create source before enqueue ingest/upload

**Files:**
- Modify: `services/api-gateway/routers/admin_domains/knowledge.py`

**Steps:**
1. In `create_knowledge_source` and `upload_knowledge_files`, enqueue `CreateKnowledgeSourceCommand` first, then sync/upload job (metadata may be updated on a follow-up status write if needed).
2. Keep response shape stable.

### Task 3: Admin copy + sync-if-exists

**Files:**
- Modify: `apps/duckclaw-admin/src/components/knowledge/KnowledgeControlPanel.tsx`
- Modify: `apps/duckclaw-admin/src/components/knowledge/knowledgeErrorMessage.ts`
- Modify: `apps/duckclaw-admin/src/components/knowledge/KnowledgeFolderBrowser.tsx`
- Modify: `apps/duckclaw-admin/src/app/(admin)/knowledge/page.tsx`

**Steps:**
1. Dual-lane headings/copy; rename Usar → Elegir; CTA Añadir al chat / Actualizar.
2. `formatKnowledgeError` + preview line.
3. `importServerPath`: if matching `source_uri` in `sources`, call sync.

### Task 4: Verify

**Steps:**
1. Run `tests/test_knowledge_sync_queue.py` and any admin static tests that touch KnowledgeControlPanel.
2. Manual: Knowledge page shows dual lanes; re-index existing MacMiniVault syncs.
