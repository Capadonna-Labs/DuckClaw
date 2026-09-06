# DuckClaw Full (Docker launcher)

Tauri shell that starts the **full** Docker Compose stack (Gateway, Redis, DB-Writer, Knowledge-Indexer, Admin). Not Desktop Lite.

See [docs/deploy/DOCKER_FULL_WINDOWS.md](../../docs/deploy/DOCKER_FULL_WINDOWS.md).

```powershell
# From repo root — build images + NSIS installer
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_desktop_docker.ps1

# Dev UI only (needs Docker + images already built)
cd packages/desktop-docker
npm install
npm run dev
```
