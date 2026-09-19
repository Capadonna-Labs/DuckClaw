# DuckClaw Full on Windows (Docker + launcher)

Generic **full** stack (not Desktop Lite). No Quant-Trader / `quant_core` — those arrive later via worker `.zip` import.

## What you get

| Piece | Role |
|-------|------|
| Gateway `:8000` | API + chat |
| DB-Writer | Redis → DuckDB writes |
| Knowledge-Indexer | RAG ingest outside Gateway |
| Heartbeat | Crons, homeostasis and proactive ticks while every UI is closed |
| Redis | Queue / cache |
| Admin `:3001` | Next.js console |
| Sandbox image | `duckclaw/sandbox:latest` — default build uses `Dockerfile.slim`; full Playwright image via `docker/sandbox/Dockerfile` |
| Tailscale | Optional (`--profile tailscale`) |

## Requirements

1. [Docker Desktop](https://www.docker.com/products/docker-desktop/) for Windows (WSL2 backend recommended).
2. Images `duckclaw/gateway`, `duckclaw/admin`, `duckclaw/sandbox` (build from this repo or `docker load` a tar).
3. Optional: **DuckClaw Full** launcher `.exe` (Tauri) — does not replace Docker.

## Quick start (CLI)

```powershell
cd deploy\docker
copy .env.example .env
# edit admin password/API key once if you want
docker compose up -d --build
# wait until healthy
curl http://127.0.0.1:8000/health
start http://127.0.0.1:3001/login
```

Login: `DUCKCLAW_ADMIN_EMAIL` / `DUCKCLAW_ADMIN_PASSWORD` from `.env`.

## Build images + launcher

```powershell
pwsh scripts/build_desktop_docker.ps1 -ExportTar
# or: powershell -File scripts/build_desktop_docker.ps1 -ExportTar
# artifacts: dist\docker-full\
```

- `docker-compose.yml` (release, image-only)
- `.env.example`
- `duckclaw-full-images.tar` (if `-ExportTar`)
- NSIS `DuckClaw Full_…_x64-setup.exe` (unless `-SkipTauri`)

## Launcher behaviour

1. Checks `docker info`. If missing → message + Docker Desktop download link (no silent install).
2. Copies compose + `.env` to `%LOCALAPPDATA%\DuckClaw\full\` (generates random admin secrets on first run).
3. Optionally `docker load` if `duckclaw-full-images.tar` is present there.
4. `docker compose up -d` (no console window).
5. Polls Gateway `/health` and Admin `/login` (up to ~20 min on first pull).
6. Opens the system browser at `http://127.0.0.1:3001/login`.

## Smoke test

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/smoke_docker_full.ps1
```

Report: [`SMOKE_DOCKER_FULL_REPORT.md`](SMOKE_DOCKER_FULL_REPORT.md) (generated). Criteria:

- Clean DB volume (no worker schemas)
- Gateway + DB-Writer + Redis + Knowledge-Indexer + Heartbeat + Admin up
- Admin login page reachable without hand-editing console
- Document first vs second `compose up` times

## Paso 2 (out of scope here)

Import Quant-Trader worker `.zip` (includes its own `schema.sql`). Do **not** bake `quant_core` into this base image.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| “Esperando Gateway” / health fail | `docker compose -f deploy/docker/docker-compose.yml ps` + `logs gateway` |
| Missing images | Re-run build script or `docker load -i duckclaw-full-images.tar` |
| Sandbox tools fail | Ensure Docker socket mounted; rebuild `duckclaw/sandbox` |
| Port 8000/3001 busy | Stop local PM2 / Desktop Lite; or change host ports in compose |
| Tailscale | `docker compose --profile tailscale up -d` after setting `TS_AUTHKEY` |

## Persistent VPS runtime

The Docker Full stack is also the production runtime for a VPS. The launcher
and browser are clients; closing either one must not stop the containers. Use
`restart: unless-stopped`, keep state in Docker volumes or explicit host
mounts, and stop the stack only with an explicit `docker compose stop/down`.

For a PM2 → Docker Full VPS migration, use a short controlled cutover (the
actual cutover script is VPS/vertical-specific and lives in the ops repo that
owns that VPS, not in this generic repo):

1. Back up the current DuckDB vaults and `.env`.
2. Generate Web Push VAPID keys for phone/watch notifications:
   `uv run python scripts/generate_web_push_vapid.py --subject mailto:admin@example.com`.
3. Put `WEB_PUSH_VAPID_PUBLIC_KEY`, `WEB_PUSH_VAPID_PRIVATE_KEY`, and
   `WEB_PUSH_SUBJECT` in the VPS Docker Full `.env`.
4. Serve Admin over HTTPS or Tailscale HTTPS. Browser Push only works on secure
   origins, except `localhost` during development.
5. Stop the PM2 core processes.
6. Start Docker Full from a stable directory such as `/opt/duckclaw-full`.
7. Validate Gateway `/health`, Admin `/login`, DB-Writer, Knowledge-Indexer,
   Heartbeat, and the migrated worker state.
8. From the installed PWA/browser, allow notifications and call
   `/api/admin/notifications/web-push/test` through the admin BFF.
9. Roll back by stopping Compose and restarting PM2 if validation fails.
