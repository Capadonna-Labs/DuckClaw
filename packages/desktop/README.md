# DuckClaw Desktop (Tauri)

Tauri shell that spawns the PyInstaller sidecar (`duckclaw_backend`) and opens the gateway UI.

## Prerequisites

1. Build sidecar: `scripts/build_desktop_sidecar.ps1`
2. Copy `dist/duckclaw_backend.exe` → `packages/desktop/src-tauri/bin/duckclaw_backend-x86_64-pc-windows-msvc.exe` (Tauri externalBin naming)

## Dev

```bash
cd packages/desktop
npm install
npm run tauri dev
```

## Lifecycle

- **Start**: Tauri `setup` spawns `duckclaw_backend` sidecar (LITE_MODE inline gateway).
- **Stop**: window destroy kills sidecar child (no admin services).
- **UI**: `src/index.html` polls `http://127.0.0.1:8000/health` then redirects to gateway.

Spec: `docs/specs/features/platform/DESKTOP_LITE_SIDECAR.md`
