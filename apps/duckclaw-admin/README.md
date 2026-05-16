# DuckClaw Admin UI

Consola web (Next.js 14). Spec: `specs/features/platform/DUCKCLAW_ADMIN_UI.md`.

## Requisitos

- Node 20+
- [pnpm](https://pnpm.io) 9+
- API Gateway en marcha con `DUCKCLAW_ADMIN_API_KEY` en `.env` raíz

## Variables (solo en esta carpeta)

Crea `apps/duckclaw-admin/.env.local` (no commitear):

```env
DUCKCLAW_GATEWAY_URL=http://127.0.0.1:8000
DUCKCLAW_ADMIN_API_KEY=<misma clave que en .env raíz del monorepo>
```

El BFF Next lee estas variables en servidor; el navegador nunca ve la admin key.

## Comandos (pnpm)

```bash
pnpm install          # desde apps/duckclaw-admin
pnpm dev              # http://localhost:3000

# o desde la raíz del monorepo:
pnpm admin:dev
pnpm admin:build
```

Login demo: `admin@duckclaw.local` / `DuckAdmin2026!` · viewer solo lectura.
