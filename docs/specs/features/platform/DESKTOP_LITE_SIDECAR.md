# Desktop Lite Sidecar (LITE_MODE)

Windows desktop stack: one process, no Redis writer, no admin rights. Tauri shell (phase 4) manages a PyInstaller sidecar that runs the API gateway with Spawn inline writes.

## LITE_MODE alias

`LITE_MODE=1` is an **alias** for the existing Spawn profile — not a parallel runtime.

| Env | Effect |
|-----|--------|
| `LITE_MODE=1` | Sets `DUCKCLAW_SPAWN_PROFILE=1`, clears `DUCKCLAW_SPAWN_USE_DB_WRITER` |
| `DUCKCLAW_SPAWN_PROFILE=1` | Same lite semantics when `DUCKCLAW_SPAWN_USE_DB_WRITER` is unset |
| `DUCKCLAW_SPAWN_USE_DB_WRITER=1` | Escape hatch: re-enable Redis queue + db-writer (not desktop v1) |

Implementation: `duckclaw.spawn_profile.apply_lite_mode_env()` (call before gateway bootstrap).

## Invariant (v1)

One OS process = API gateway + DuckDB writes inline.

- Writes go through `enqueue_typed_command` → in-process `dispatch_command` (see `SPAWN_GENERIC_DEPLOY.md`, `GATEWAY_DB_WRITER_BOUNDARIES.md`).
- `task_status:{id}` confirmations use an in-process store when Spawn inline is active (no Redis poll).
- State deltas (visual, reports, context) apply via `spawn_inline_delta` handlers, same bodies as db-writer.

## Composition root

Entry: `services/desktop-sidecar/run.py`

- Applies lite/spawn env and `%LOCALAPPDATA%\DuckClaw\` data dir (no admin).
- Bootstraps DuckDB schema on first run.
- Binds `127.0.0.1`; health at `GET /health`.
- Does **not** start db-writer, heartbeat PM2, knowledge-indexer, or separate MCP HTTP.

Admin UI v1: point webview at `http://127.0.0.1:8000` (gateway). Embedded Next admin is out of scope for sidecar v1.

## Out of scope (v1)

- Redis (writer queue, task_status broker)
- db-writer PM2 process
- SQLite queue (`duckclaw/core/queue/` — **do not create**)
- Separate MCP HTTP server
- Knowledge indexer consumer
- Trading / vertical product strings or Capadonna-specific paths

## Packaging

| Artifact | Path |
|----------|------|
| Sidecar entry | `services/desktop-sidecar/run.py` |
| PyInstaller build | `scripts/build_desktop_sidecar.ps1` |
| Spec | `services/desktop-sidecar/duckclaw_sidecar.spec` |
| Tauri shell | `packages/desktop/` |

Build ships **with console first** (`console=True`). Switch to `--noconsole` only after smoke is stable.

### Smoke (documented in build script)

1. Start sidecar exe or `python services/desktop-sidecar/main.py`
2. `GET http://127.0.0.1:8000/health` → 200
3. One typed inline write (or legacy enqueue path under lite)
4. Clean shutdown (no orphan process)

### PyInstaller exclusions

Do not bundle: mlx, comfyui, edge integrations, full MCP prefetch trees, knowledge-indexer. Sidecar needs gateway + shared + agents core only.

**Prereq:** `uv sync --group dev` (PyInstaller in dev group; `.venv` has no pip — use `uv`, not `pip install`).

## SQLite queue (deferred)

Introduce a local queue **only if** lite bypass stops being enough (e.g. sidecar + child worker without Redis). If added later:

- Contract aligned to `services/db-writer/db_writer_ops.py` (lease, ACK, DLQ) — not toy `push`/`pop`.
- DB file: `%LOCALAPPDATA%\DuckClaw\queue.db` (WAL).
- Location: `packages/shared/src/duckclaw/queue/` (not `duckclaw/core/queue/`).

Until then: YAGNI; Spawn inline is the queue bypass.

## Acceptance

1. `LITE_MODE=1` → gateway writes DuckDB without Redis/db-writer.
2. Sidecar responds on loopback `/health`.
3. PyInstaller exe passes smoke on Win10/11.
4. Tauri spawns/kills sidecar without residual processes.
5. No trading-vertical product code in diff.

## Related

- `SPAWN_GENERIC_DEPLOY.md`
- `GATEWAY_DB_WRITER_BOUNDARIES.md`
- `DB_WRITER_CONTRACT.md`
