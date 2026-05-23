#!/usr/bin/env bash
# spawn-install.sh — Instalador de producción desatendido y genérico para DuckClaw
# Spec: specs/features/platform/SPAWN_GENERIC_DEPLOY.md
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

if [[ -n "${DUCKCLAW_REPO_ROOT:-}" ]]; then
  REPO_ROOT="$(cd "${DUCKCLAW_REPO_ROOT}" && pwd)"
  cd "${REPO_ROOT}"
fi

log() { echo "🦆 [DuckClaw Install] $*"; }

# --- Preflight: SWAP si RAM < 4GB ---
log "Detectando recursos del sistema..."
TOTAL_RAM="$(free -m 2>/dev/null | awk '/^Mem:/{print $2}' || echo 9999)"
if [[ "${TOTAL_RAM}" -lt 4000 ]]; then
  log "Memoria física baja (${TOTAL_RAM} MB). Creando SWAP 2GB para compilar Next.js..."
  if [[ ! -f /swapfile ]]; then
    sudo fallocate -l 2G /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=2048
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    if ! grep -q '^/swapfile ' /etc/fstab 2>/dev/null; then
      echo "/swapfile none swap sw 0 0" | sudo tee -a /etc/fstab >/dev/null
    fi
    log "SWAP de 2GB activada."
  else
    log "Archivo SWAP existente detectado."
  fi
fi

# --- Dependencias OS ---
log "Instalando dependencias de infraestructura..."
sudo apt-get update -y
sudo apt-get install -y \
  curl git build-essential python3-pip python3-venv \
  redis-server

if ! command -v redis-cli &>/dev/null || ! redis-cli ping 2>/dev/null | grep -q PONG; then
  sudo systemctl enable redis-server 2>/dev/null || true
  sudo systemctl start redis-server 2>/dev/null || true
fi

if ! command -v node &>/dev/null; then
  log "Instalando Node.js v20 LTS..."
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
  sudo apt-get install -y nodejs
fi

if ! command -v pm2 &>/dev/null; then
  log "Instalando PM2 global..."
  sudo npm install -g pm2
fi

if ! command -v uv &>/dev/null; then
  log "Instalando Astral uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
# shellcheck source=/dev/null
[[ -f "${HOME}/.local/bin/env" ]] && source "${HOME}/.local/bin/env"
export PATH="${HOME}/.local/bin:${PATH}"

# --- .env raíz (Spawn debe haber inyectado secretos; completar defaults) ---
ENV_FILE="${REPO_ROOT}/.env"
DB_DEFAULT="${DUCKDB_PATH:-${DUCKCLAW_DB_PATH:-db/private/default/duckclaw.duckdb}}"
if [[ ! -f "${ENV_FILE}" ]]; then
  log "Creando .env desde plantilla spawn..."
  cat >"${ENV_FILE}" <<EOF
# Generado por spawn-install.sh — perfil genérico
OPENROUTER_API_KEY=${OPENROUTER_API_KEY:-}
DUCKCLAW_ADMIN_API_KEY=${DUCKCLAW_ADMIN_API_KEY:-change-me-spawn-install}
DUCKDB_PATH=${DB_DEFAULT}
DUCKCLAW_DB_PATH=${DB_DEFAULT}
REDIS_URL=${REDIS_URL:-redis://127.0.0.1:6379/0}
DUCKCLAW_REPO_ROOT=${REPO_ROOT}
DUCKCLAW_SPAWN_PROFILE=1
DUCKCLAW_LLM_PROVIDER=openrouter
DUCKCLAW_LLM_BASE_URL=https://openrouter.ai/api/v1
EOF
else
  grep -q '^DUCKCLAW_SPAWN_PROFILE=' "${ENV_FILE}" 2>/dev/null || echo 'DUCKCLAW_SPAWN_PROFILE=1' >>"${ENV_FILE}"
  grep -q '^REDIS_URL=' "${ENV_FILE}" 2>/dev/null || echo 'REDIS_URL=redis://127.0.0.1:6379/0' >>"${ENV_FILE}"
  grep -q '^DUCKDB_PATH=' "${ENV_FILE}" 2>/dev/null || echo "DUCKDB_PATH=${DB_DEFAULT}" >>"${ENV_FILE}"
  grep -q '^DUCKCLAW_DB_PATH=' "${ENV_FILE}" 2>/dev/null || echo "DUCKCLAW_DB_PATH=${DB_DEFAULT}" >>"${ENV_FILE}"
  grep -q '^DUCKCLAW_REPO_ROOT=' "${ENV_FILE}" 2>/dev/null || echo "DUCKCLAW_REPO_ROOT=${REPO_ROOT}" >>"${ENV_FILE}"
fi
set -a
# shellcheck source=/dev/null
source "${ENV_FILE}" 2>/dev/null || true
set +a

# --- Python (monorepo) ---
log "Sincronizando entorno Python (uv sync)..."
cd "${REPO_ROOT}"
uv sync

# --- Bootstrap DuckDB (síncrono, antes de PM2) ---
log "Inicializando base de datos núcleo..."
export DUCKDB_PATH="${DUCKDB_PATH:-${DB_DEFAULT}}"
export DUCKCLAW_DB_PATH="${DUCKCLAW_DB_PATH:-${DUCKDB_PATH}}"
uv run python scripts/bootstrap_dbs.py --core-only --only "${DUCKDB_PATH}"

# --- Admin UI ---
log "Instalando y compilando Admin UI (Next.js)..."
ADMIN_DIR="${REPO_ROOT}/apps/duckclaw-admin"
ADMIN_KEY="${DUCKCLAW_ADMIN_API_KEY:-change-me-spawn-install}"
if command -v corepack &>/dev/null; then
  corepack enable 2>/dev/null || true
fi
cd "${ADMIN_DIR}"
if [[ -f pnpm-lock.yaml ]]; then
  pnpm install --frozen-lockfile 2>/dev/null || pnpm install
else
  pnpm install
fi
pnpm run build
cat >"${ADMIN_DIR}/.env.local" <<EOF
DUCKCLAW_GATEWAY_URL=http://127.0.0.1:8000
DUCKCLAW_ADMIN_API_KEY=${ADMIN_KEY}
EOF
cd "${REPO_ROOT}"

# --- PM2 ---
log "Iniciando servicios con PM2 (perfil spawn)..."
if command -v pm2 &>/dev/null; then
  pm2 delete duckclaw-gateway duckclaw-admin-ui DuckClaw-Gateway 2>/dev/null || true
  pm2 start config/ecosystem.spawn.config.cjs
  pm2 save 2>/dev/null || true
  log "PM2: gateway :8000, admin :3000"
else
  log "WARN: pm2 no encontrado; omitiendo arranque automático."
fi

log "Instalación completada exitosamente."
log "Admin UI: http://127.0.0.1:3000  |  Gateway: http://127.0.0.1:8000/health"
