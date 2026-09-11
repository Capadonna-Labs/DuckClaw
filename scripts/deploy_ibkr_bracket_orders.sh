#!/usr/bin/env bash
# IBKR Bracket Orders — Deployment Script for VPS
#
# Este script despliega la funcionalidad de bracket orders en el VPS de producción.
# 
# Usage:
#   bash scripts/deploy_ibkr_bracket_orders.sh [--dry-run]
#
# Requisitos previos:
#   - SSH access a root@100.75.4.17 (Tailscale)
#   - Git configurado en VPS
#   - Python 3.10+ con uv
#   - IBKR Gateway/TWS instalado y configurado

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Config
VPS_HOST="${VPS_HOST:-root@100.75.4.17}"
REPO_PATH="${REPO_PATH:-/root/duckclaw}"
VAULT_DB="${VAULT_DB:-/root/Capadonna-Driller/db/private/1726618406/quant_traderdb1.duckdb}"
DRY_RUN=false

# Parse args
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
    echo -e "${YELLOW}[DRY RUN MODE]${NC}"
fi

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

run_remote() {
    local cmd="$1"
    if $DRY_RUN; then
        echo -e "${YELLOW}[DRY RUN]${NC} Would run on VPS: $cmd"
    else
        ssh "$VPS_HOST" "$cmd"
    fi
}

# =============================================================================
# 1. Pre-flight checks
# =============================================================================

log_info "Verificando conectividad VPS..."
if ! $DRY_RUN; then
    if ! ssh -o ConnectTimeout=5 "$VPS_HOST" "echo 'SSH OK'"; then
        log_error "No se puede conectar a $VPS_HOST"
        exit 1
    fi
    log_info "✓ SSH OK"
fi

# =============================================================================
# 2. Git pull
# =============================================================================

log_info "Actualizando código en VPS..."
run_remote "cd $REPO_PATH && git fetch origin && git pull origin main"

# =============================================================================
# 3. Instalar dependencias
# =============================================================================

log_info "Instalando dependencias (ib-insync)..."
run_remote "cd $REPO_PATH && uv sync --extra trading"

# =============================================================================
# 4. Correr migraciones
# =============================================================================

log_info "Corriendo migraciones DuckDB (v39: ibkr_orders)..."
run_remote "cd $REPO_PATH && uv run duckclaw-migrate"

# Verificar que tabla se creó
log_info "Verificando tabla quant_core.ibkr_orders..."
if ! $DRY_RUN; then
    TABLE_EXISTS=$(ssh "$VPS_HOST" "cd $REPO_PATH && uv run python -c \"
import duckdb
con = duckdb.connect('$VAULT_DB', read_only=True)
try:
    result = con.execute('SELECT COUNT(*) FROM quant_core.ibkr_orders').fetchone()
    print('EXISTS')
except Exception:
    print('NOT_FOUND')
finally:
    con.close()
\"")

    if [[ "$TABLE_EXISTS" == "EXISTS" ]]; then
        log_info "✓ Tabla quant_core.ibkr_orders verificada"
    else
        log_error "Tabla quant_core.ibkr_orders no encontrada"
        exit 1
    fi
fi

# =============================================================================
# 5. Verificar IBKR Gateway
# =============================================================================

log_info "Verificando configuración IBKR Gateway..."

if ! $DRY_RUN; then
    # Check .env variables
    ENV_CHECK=$(ssh "$VPS_HOST" "cd $REPO_PATH && grep -E 'IBKR_(HOST|PORT|CLIENT_ID)' .env || echo 'NOT_FOUND'")
    
    if [[ "$ENV_CHECK" == "NOT_FOUND" ]]; then
        log_warn "Variables IBKR_* no encontradas en .env"
        log_warn "Por favor configurar:"
        echo ""
        echo "IBKR_HOST=127.0.0.1"
        echo "IBKR_PORT=4002  # 4002=paper, 4001=live"
        echo "IBKR_CLIENT_ID=1"
        echo ""
        log_warn "Agregar a $REPO_PATH/.env antes de continuar"
    else
        log_info "✓ Variables IBKR_* configuradas"
    fi

    # Check if Gateway is running
    GATEWAY_RUNNING=$(ssh "$VPS_HOST" "netstat -an 2>/dev/null | grep -E ':(4001|4002).*LISTEN' || echo 'NOT_RUNNING'")
    
    if [[ "$GATEWAY_RUNNING" == "NOT_RUNNING" ]]; then
        log_warn "IBKR Gateway/TWS no parece estar corriendo"
        log_warn "Puerto 4001 o 4002 no está en LISTEN"
        log_warn "Iniciar Gateway antes de usar bracket orders"
    else
        log_info "✓ IBKR Gateway detectado en puerto 4001 o 4002"
    fi
fi

# =============================================================================
# 6. Setup Order Monitor (cron job)
# =============================================================================

log_info "Configurando Order Monitor (cron job)..."

CRON_CMD="* * * * * cd $REPO_PATH && uv run python -m duckclaw.ibkr_order_monitor --vault-db $VAULT_DB >> /var/log/ibkr_order_monitor.log 2>&1"

if ! $DRY_RUN; then
    # Check if cron job already exists
    CRON_EXISTS=$(ssh "$VPS_HOST" "crontab -l 2>/dev/null | grep -F 'ibkr_order_monitor' || echo 'NOT_FOUND'")
    
    if [[ "$CRON_EXISTS" == "NOT_FOUND" ]]; then
        log_info "Agregando cron job para Order Monitor..."
        ssh "$VPS_HOST" "(crontab -l 2>/dev/null; echo '$CRON_CMD') | crontab -"
        log_info "✓ Cron job agregado (cada 1 minuto)"
    else
        log_info "✓ Cron job ya existe"
    fi
else
    log_info "[DRY RUN] Would add cron job: $CRON_CMD"
fi

# =============================================================================
# 7. Test de conexión
# =============================================================================

log_info "Testeando conexión IBKR (opcional, requiere Gateway corriendo)..."

if ! $DRY_RUN; then
    TEST_RESULT=$(ssh "$VPS_HOST" "cd $REPO_PATH && timeout 10 uv run python -c \"
import asyncio
import os
import sys

# Set env vars from .env
with open('.env') as f:
    for line in f:
        if '=' in line and not line.strip().startswith('#'):
            key, val = line.strip().split('=', 1)
            os.environ[key] = val

try:
    from duckclaw.ibkr_bracket_orders import connect_ibkr
    
    async def test():
        try:
            ib = await connect_ibkr()
            print('CONNECTION_OK')
            await ib.disconnect()
        except Exception as e:
            print(f'CONNECTION_FAILED: {e}')
    
    asyncio.run(test())
except Exception as e:
    print(f'IMPORT_ERROR: {e}')
\" 2>&1 || echo 'TIMEOUT'")

    if [[ "$TEST_RESULT" == *"CONNECTION_OK"* ]]; then
        log_info "✓ Conexión IBKR Gateway OK"
    elif [[ "$TEST_RESULT" == *"IMPORT_ERROR"* ]]; then
        log_warn "Error importando ib_insync — verificar instalación"
        log_warn "Correr: ssh $VPS_HOST 'cd $REPO_PATH && uv sync --extra trading'"
    elif [[ "$TEST_RESULT" == *"CONNECTION_FAILED"* ]] || [[ "$TEST_RESULT" == "TIMEOUT" ]]; then
        log_warn "No se pudo conectar a IBKR Gateway"
        log_warn "Esto es normal si Gateway no está corriendo"
        log_warn "El deployment está completo, pero necesitas iniciar Gateway para usar bracket orders"
    fi
fi

# =============================================================================
# 8. Summary
# =============================================================================

echo ""
log_info "=========================================="
log_info "Deployment completado ✓"
log_info "=========================================="
echo ""
echo "Próximos pasos:"
echo ""
echo "1. Iniciar IBKR Gateway/TWS en VPS (si no está corriendo)"
echo "   - Conectar a VPS via VNC o X11 forwarding"
echo "   - Ejecutar IB Gateway"
echo "   - Configurar API (puerto 4002 paper, 4001 live)"
echo ""
echo "2. Verificar Order Monitor está corriendo:"
echo "   ssh $VPS_HOST 'tail -f /var/log/ibkr_order_monitor.log'"
echo ""
echo "3. Test manual de bracket order:"
echo "   ssh $VPS_HOST"
echo "   cd $REPO_PATH"
echo "   uv run python"
echo "   >>> from duckclaw.signal_execution_bridge import execute_signal_with_bracket"
echo "   >>> import asyncio"
echo "   >>> result = asyncio.run(execute_signal_with_bracket("
echo "   ...     signal_id='test_001',"
echo "   ...     ticker='SPY',"
echo "   ...     side='BUY',"
echo "   ...     quantity=10,"
echo "   ...     vault_db_path='$VAULT_DB'"
echo "   ... ))"
echo "   >>> print(result)"
echo ""
echo "4. Habilitar skill en Quant-Trader manifest:"
echo "   - Agregar 'ibkr_bracket_orders' a skills list"
echo "   - Reimportar worker template"
echo ""
log_info "Deployment script completado."
