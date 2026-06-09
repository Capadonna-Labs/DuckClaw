# Ops Quant / IBKR (Capadonna-Driller)

Los scripts de producto **quant**, **ibkr** y **capadonna** ya no viven en el monorepo DuckClaw. Están en el repo **Capadonna-Driller** (despliegue VPS, hooks subprocess, jobs batch).

## Ubicación

| Qué | Ruta en Capadonna-Driller |
|-----|---------------------------|
| Hooks IBKR (portfolio, historical, broker execute) | `scripts/capadonna/` |
| Lake export | `scripts/data/export_lake_ohlcv.py` |
| Jobs batch ML4T / MOC / HRP | `scripts/quant/` |
| API HTTP `:8002` | `services/ibkr-ohlcv-api/` |
| Deploy VPS | `scripts/deployment/ibkr/` |
| Workers Quant-Trader / finanz | `workers/duckclaw/templates/` |

## Despliegue rápido (VPS)

```bash
cd ~/Desktop/Capadonna-Driller   # o /root/Capadonna-Driller en VPS
export SSH_TARGET=root@100.75.4.17
export IBKR_API_KEY='tu-bearer'
bash scripts/deployment/ibkr/vps_deploy_ibkr_ohlcv_hetzner.sh
bash scripts/deployment/ibkr/verify_execute_hook_vps.sh
```

Variables del servicio: `/etc/duckclaw/ibkr-ohlcv.env`. Documentación: `workers/duckclaw/README.md` y `scripts/deployment/ibkr/README.md`.

## DuckClaw (gateway)

El gateway solo necesita URLs HTTP en `.env` (`IBKR_PORTFOLIO_API_URL`, `IBKR_EXECUTE_ORDER_URL`, `CAPADONNA_REMOTE_OHLC_CMD`). No requiere scripts locales de IBKR.
