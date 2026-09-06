# Smoke report — DuckClaw Full Docker

Date: 2026-09-04T20:14:45-05:00  
Host: DESKTOP-6NCBEF1

## CLI smoke (`scripts/smoke_docker_full.ps1 -SkipRebuild`)

| Check | Result |
|-------|--------|
| Docker Desktop | OK |
| Image build (wall) | 0s (images prebuilt) |
| First `compose up` → health | **92s** |
| Second `compose up` → health | **79s** |
| gateway `/health` | OK |
| admin `/login` | OK |
| Containers (gateway, db-writer, redis, knowledge-indexer, admin) | OK |
| Login credentials in `.env` | OK (`admin@duckclaw.local`) |
| No `quant_core` / quant tables in base DB | OK |
| Manual `.env` / console edits | None required |

Cold image build (earlier this session, approximate wall clock): gateway ~uv sync + layers ~15–20 min first time; admin Next build ~20 min; sandbox full Playwright ~25 min (default stack uses **Dockerfile.slim**).

## Launcher / .exe smoke

| Check | Result |
|-------|--------|
| NSIS built | OK — `dist/docker-full/DuckClaw Full_0.1.0_x64-setup.exe` |
| `cargo check` / `tauri build` | OK |
| Release compose (image-only) in installer resources | OK |
| Simulated friend path: images already tagged locally + release compose `up -d` | Same stack as CLI (PASS) |

Friend PC still needs either:
1. `docker load -i duckclaw-full-images.tar` (produce with `scripts/build_desktop_docker.ps1 -ExportTar -SkipTauri`), or  
2. Build images on that machine from the repo once.

Launcher does **not** install Docker Desktop silently; shows download link if `docker info` fails.

## Verdict

**PASS** for CLI + packaging artifacts. Ready to install on friend’s PC after shipping the image tar alongside the `.exe`.
