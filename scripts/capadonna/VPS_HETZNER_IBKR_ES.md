# Hetzner VPS — IB Gateway + API :8002 + RealVNC

VPS: **ubuntu-2gb-ash-1** · Tailscale `100.75.4.17` · público `87.99.156.231`  
SSH: `root` con clave `~/.ssh/id_ed25519`  
IB Gateway (Docker): paper **:4002** · API DuckClaw: **:8002**

---

## 1. Desplegar API desde tu PC (Windows PowerShell)

```powershell
cd C:\Users\DELL\Desktop\duckclaw
$env:SSH_TARGET = "root@100.75.4.17"
$env:IBKR_API_KEY = "a0d76e5e046b6fcd42c0d7294558a7376830cb8185ce7d7b2a803da93c7ab508"
bash scripts/capadonna/vps_deploy_ibkr_ohlcv_hetzner.sh
```

Si no tienes `bash` en PATH, usa Git Bash o WSL para el script. Alternativa: copia manual + pasos del §3.

---

## 2. Probar desde Windows (PowerShell)

**No uses** `curl -H` en PowerShell (es alias de `Invoke-WebRequest` con otra sintaxis).

### Health (sin auth)

```powershell
Invoke-RestMethod -Uri "http://100.75.4.17:8002/health"
```

### OHLCV (con Bearer)

```powershell
$headers = @{ Authorization = "Bearer a0d76e5e046b6fcd42c0d7294558a7376830cb8185ce7d7b2a803da93c7ab508" }
Invoke-RestMethod -Uri "http://100.75.4.17:8002/api/market/ohlcv?ticker=SPY&timeframe=1d&lookback_days=5" -Headers $headers
```

### Comprobar puerto TCP

```powershell
Test-NetConnection -ComputerName 100.75.4.17 -Port 8002
Test-NetConnection -ComputerName 100.75.4.17 -Port 4002
```

---

## 3. Comandos en el VPS (después de `ssh root@100.75.4.17`)

### Estado IB Gateway y API

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
ss -tlnp | grep -E ':4002|:8002'
systemctl status capadonna-observability --no-pager
curl -sS http://127.0.0.1:8002/health
```

### Ver puerto VNC del contenedor IB Gateway

```bash
# Nombre del contenedor (ajusta si difiere)
GW=$(docker ps --format '{{.Names}}' | grep -iE 'ib|gateway' | head -1)
echo "Contenedor: $GW"
docker port "$GW" 2>/dev/null || true
docker inspect "$GW" --format '{{json .NetworkSettings.Ports}}' | python3 -m json.tool
```

Patrones habituales en imágenes IB Gateway Docker:

| Publicación en host | Puerto VNC interno |
|---------------------|-------------------|
| `0.0.0.0:5900->5900/tcp` | 5900 |
| Sin publicar (solo red Docker) | 5900 dentro del contenedor |

Si **5900 está publicado en el host**:

```bash
ss -tlnp | grep 5900
```

### Arrancar / reiniciar API

```bash
sudo systemctl restart capadonna-observability
journalctl -u capadonna-observability -n 40 --no-pager
curl -sS "http://127.0.0.1:8002/api/market/ohlcv?ticker=SPY&timeframe=1d&lookback_days=3" | head -c 500
```

### Instalación manual (si no usaste el script)

```bash
apt-get update && apt-get install -y python3 python3-venv curl
cd /root/duckclaw && python3 -m venv .venv
.venv/bin/pip install -r services/ibkr-ohlcv-api/requirements.txt ib_async
bash /root/duckclaw/scripts/capadonna/vps_deploy_ibkr_ohlcv_hetzner.sh --local
```

---

## 4. RealVNC — túnel SSH desde Windows

RealVNC Viewer se conecta a **`127.0.0.1:5905`** en tu PC. El túnel reenvía al VNC del Gateway en el VPS.

### Paso A — averiguar destino VNC en el VPS

En el VPS:

```bash
GW=$(docker ps --format '{{.Names}}' | grep -iE 'ib|gateway' | head -1)
docker port "$GW" 5900 2>/dev/null | awk -F: '{print $NF}'
# Si no hay salida, VNC solo está dentro del contenedor:
docker inspect "$GW" --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'
```

- Si el primer comando imprime **`5900`**: el túnel apunta a `127.0.0.1:5900` en el VPS.
- Si solo tienes IP Docker (p. ej. `172.17.0.2`): usa esa IP y puerto **5900**.

### Paso B — one-liner PowerShell (VNC publicado en host :5900)

Deja esta ventana abierta mientras usas RealVNC:

```powershell
ssh -i $env:USERPROFILE\.ssh\id_ed25519 -L 5905:127.0.0.1:5900 -N root@100.75.4.17
```

Vía Tailscale (recomendado):

```powershell
ssh -i $env:USERPROFILE\.ssh\id_ed25519 -L 5905:127.0.0.1:5900 -N root@100.75.4.17
```

### Paso C — si VNC no está publicado (IP Docker 172.17.0.x)

Sustituye `172.17.0.2` por la IP que devolvió `docker inspect`:

```powershell
ssh -i $env:USERPROFILE\.ssh\id_ed25519 -L 5905:172.17.0.2:5900 -N root@100.75.4.17
```

### Paso D — RealVNC Viewer

1. Abre RealVNC Viewer.
2. Conecta a **`127.0.0.1:5905`** (o `localhost:5905`).
3. Contraseña: la de la imagen Docker (p. ej. variable `VNC_PASSWORD` del compose; muchas imágenes usan `123456` por defecto — revisa tu `docker-compose`).

---

## 5. Variables de entorno en el VPS (`/etc/duckclaw/ibkr-ohlcv.env`)

| Variable | Valor típico |
|----------|----------------|
| `IB_ENV` | `paper` |
| `IB_PORT` | `4002` |
| `IB_HOST` | `127.0.0.1` |
| `OHLCV_IB_CLIENT_ID` | `42` (cambiar si Error 326) |
| `OHLCV_API_KEY` | misma clave que `IBKR_PORTFOLIO_API_KEY` en DuckClaw |

Editar y reiniciar:

```bash
sudo nano /etc/duckclaw/ibkr-ohlcv.env
sudo systemctl restart capadonna-observability
```

---

## Notas

- Este despliegue mínimo expone **`/health`**, **`/api/market/ohlcv`**, **`/api/market/ibkr/historical`** y **`/api/broker/execute`** (501 sin hook de órdenes).
- **`/api/portfolio/summary`** requiere `observability_api` completo (Capadonna-Driller); no está en el standalone `ibkr-ohlcv-api`.
- Sin lake Parquet en el VPS, `/api/market/ohlcv` usa fallback IB vía `ibkr_historical_bars.py` → Gateway `:4002`.
