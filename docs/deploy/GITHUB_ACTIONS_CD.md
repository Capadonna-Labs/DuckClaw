# CD: GitHub Actions → VPS

Tras CI verde en `main`, el job **deploy-vps** en `.github/workflows/deploy.yml`:

1. Construye `apps/duckclaw-admin` (standalone) en el runner (evita OOM del VPS 2GB).
2. Sube el tarball por SSH.
3. En el VPS: `git pull --ff-only origin main`, desempaqueta `.next/standalone`, reinicia PM2 (`duckclaw-admin-ui` + Gateway / DB-Writer / Heartbeat).

## Secrets del repo

Settings → Secrets and variables → Actions:

| Secret | Ejemplo | Obligatorio |
|--------|---------|-------------|
| `VPS_HOST` | IP pública Contabo o IP Tailscale | sí |
| `VPS_SSH_KEY` | clave privada OpenSSH (PEM) con acceso al VPS | sí |
| `VPS_USER` | `root` | no (default `root`) |
| `VPS_PATH` | `/root/duckclaw` | no |

Si faltan `VPS_HOST` o `VPS_SSH_KEY`, el job de deploy se **salta** con warning (el CI de tests sigue siendo obligatorio).

## Arranque admin en VPS

El proceso PM2 debe apuntar a standalone, p. ej. `scripts/pm2-start-admin-ui.sh` → `apps/duckclaw-admin/.next/standalone/server.js`. El CD **no** pisa `.env*` dentro de `standalone/`.

## Probar a mano

```bash
pnpm --dir apps/duckclaw-admin build
bash scripts/ci/package-admin-standalone.sh
VPS_HOST=… VPS_SSH_KEY_FILE=~/.ssh/… bash scripts/ci/deploy-vps.sh
```
