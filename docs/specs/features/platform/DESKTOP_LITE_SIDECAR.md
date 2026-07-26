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

Admin UI v1: embedded Next.js admin (`duckclaw-admin`) on `http://127.0.0.1:3000/login`. Tauri spawns bundled `node.exe` + standalone `server.js` after backend health. Gateway stays on `:8000` for API/BFF proxy.

Desktop credentials: `%LOCALAPPDATA%\DuckClaw\desktop.env` (stable `DUCKCLAW_ADMIN_API_KEY`, seed email/password on first run).

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
| Full desktop build | `scripts/build_desktop.ps1` (sidecar + admin standalone + node + Tauri NSIS) |
| Spec | `services/desktop-sidecar/duckclaw_sidecar.spec` |
| Tauri shell | `packages/desktop/` |
| Admin UI bundle | `packages/desktop/src-tauri/resources/admin-ui/` (build artifact) |
| Node runtime | `packages/desktop/src-tauri/resources/node/node.exe` (build artifact) |

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

## Auto-updater (Tauri 2)

- Plugin: `@tauri-apps/plugin-updater` + Minisign signatures.
- Endpoint: `https://github.com/<owner>/<repo>/releases/latest/download/latest.json` (synced from `origin` at build time)
- Release: `scripts/release_desktop.ps1`; signing setup: `scripts/setup_desktop_signing.ps1`
- Production sidecar: bundled `externalBin` only (updater replaces install dir). Dev hot-reload: `DUCKCLAW_DESKTOP_DEV_SIDECAR=1`.
- User data under `%LOCALAPPDATA%\DuckClaw\` (db, desktop.env) is **not** modified by updates.

## Acceptance

1. `LITE_MODE=1` → gateway writes DuckDB without Redis/db-writer.
2. Sidecar responds on loopback `/health`.
3. PyInstaller exe passes smoke on Win10/11.
4. Tauri spawns/kills sidecar **and** admin Node without residual processes.
5. Webview opens admin login (`:3000/login`), not gateway JSON root.
6. Signed auto-update from GitHub Releases updates shell + sidecar + admin bundle; user DB/env persist.
7. No trading-vertical product code in diff.

## Related

- `SPAWN_GENERIC_DEPLOY.md`
- `GATEWAY_DB_WRITER_BOUNDARIES.md`
- `DB_WRITER_CONTRACT.md`
