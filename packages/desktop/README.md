# DuckClaw Desktop (Tauri)



Tauri shell that spawns the PyInstaller sidecar (`duckclaw_backend` on `:8000`) and the embedded Next.js admin UI (`node.exe` + standalone `server.js` on `:3000`).



## Prerequisites



- `uv`, `pnpm`, `npm`, Rust/cargo

- Network for Node LTS download during build



## Build (full installer)



```powershell

.\scripts\build_desktop.ps1

```



Output: `packages/desktop/src-tauri/target/release/bundle/nsis/DuckClaw_*_x64-setup.exe`



Stages under `packages/desktop/src-tauri/resources/` (gitignored):



- `admin-ui/` — Next standalone from `apps/duckclaw-admin`

- `node/node.exe` — portable Node win-x64



Sidecar only: `scripts/build_desktop_sidecar.ps1`, then copy to `src-tauri/bin/duckclaw_backend-x86_64-pc-windows-msvc.exe`.



## Auto-updater (Tauri 2 + Minisign)



Signed updates via `@tauri-apps/plugin-updater`. Manifest: GitHub Releases `latest.json`.



### One-time signing setup



```powershell

.\scripts\setup_desktop_signing.ps1

```



Creates `packages/desktop/.tauri/duckclaw.key` (gitignored) and `duckclaw.key.pub` (committed). Injects pubkey into `tauri.conf.json`.



CI/release: set `TAURI_SIGNING_PRIVATE_KEY` (contents of private key) and optional password secret. Never commit the private key.



### Release



```powershell

.\scripts\release_desktop.ps1 -Version 0.2.0 -Notes "Release notes"

# Preview manifest only:

.\scripts\release_desktop.ps1 -Version 0.2.0 -DryRun -SkipBuild

```



Uploads NSIS setup + `latest.json` to this repo's GitHub Releases (slug from `origin` remote).



### User data (never touched by updater)



| Path | Content |

|------|---------|

| `%LOCALAPPDATA%\DuckClaw\db\` | DuckDB hub + vaults |

| `%LOCALAPPDATA%\DuckClaw\desktop.env` | API key + admin credentials |

| `%LOCALAPPDATA%\DuckClaw\gateway.log` | Gateway logs |



Updater replaces install-dir binaries (Tauri shell, bundled sidecar, admin-ui, node). Session lite is in-memory — user re-logs in after update.



### Dev sidecar hot-reload



Set `DUCKCLAW_DESKTOP_DEV_SIDECAR=1` to spawn `%LOCALAPPDATA%\DuckClaw\duckclaw_backend.exe` instead of bundled sidecar. **Do not use in production** (breaks updater sidecar path).



## Dev



```bash

cd packages/desktop

npm install

npm run tauri dev

```



Debug builds skip sidecar/admin spawn; run gateway and admin manually if needed. Updater is inactive in debug builds.



## Lifecycle



- **Start**: Tauri spawns bundled `duckclaw_backend`, waits for `:8000`, reads `%LOCALAPPDATA%\DuckClaw\desktop.env`, spawns admin Node on `:3000`.

- **Stop**: window destroy kills backend + admin (no orphan processes).

- **Update**: admin banner → `prepare_for_update` (kill processes) → download/install → relaunch.

- **UI**: `src/index.html` polls backend `/health` and admin `/login`, redirects to `http://127.0.0.1:3000/login`.



## Desktop login



First run creates `%LOCALAPPDATA%\DuckClaw\desktop.env` with stable `DUCKCLAW_ADMIN_API_KEY` and seed credentials. Default email: `admin@duckclaw.local`. Password is in `desktop.env` (`DUCKCLAW_DESKTOP_ADMIN_PASSWORD`).



## Verification checklist



| Case | Expected |

|------|----------|

| v0.1.0, no GitHub release | No update banner |

| Publish v0.2.0 + latest.json | Banner «Actualizar y reiniciar» |

| Install update | Sidecar/admin stop → install → relaunch; chat works after re-login |

| Post-update | `db/` + `desktop.env` unchanged |

| Invalid signature | Update rejected, error in banner |



Spec: `docs/specs/features/platform/DESKTOP_LITE_SIDECAR.md`

