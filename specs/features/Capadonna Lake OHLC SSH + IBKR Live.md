# Capadonna Lake OHLC (SSH) + IBKR tiempo real

**Objetivo**

Ingerir **OHLC histórico** (y series de precio desde **`moc/`** con `timeframe=moc`) desde el data lake del VPS Capadonna (vía SSH, bajo `~/projects/Capadonna-Driller/data/lake/`: **`daily`**, **`gold`**, **`intraday`**, **`moc`**) y **barras en tiempo real** (intradía) desde el **gateway HTTP** (`IBKR_MARKET_DATA_URL`) cuando aplique, sin duplicar fuentes para el mismo uso.

**Relación**

- Continúa [Quantitative Trading Worker](Quantitative%20Trading%20Worker.md): destino único `quant_core.ohlcv_data`.
- La herramienta `fetch_market_data` enruta por `timeframe` y variables de entorno (esta spec).
- La herramienta **`fetch_lake_ohlcv`** llama siempre al lake vía SSH (misma sesión que `fetch_market_data` en rama lake), devuelve **solo JSON** con barras normalizadas y **no escribe** `quant_core.ohlcv_data`. Úsala cuando se requiera evidencia OHLCV sin persistir; para CFD con DB, tras `fetch_market_data` usar `read_sql` sobre `quant_core.ohlcv_data`.

**Errores JSON (`fetch_lake_ohlcv` y fallos de transporte en rama lake de `fetch_market_data`):**

| `error` | Significado |
|---------|-------------|
| `CAPADONNA_OFFLINE` | Sin túnel / config incompleta (`CAPADONNA_SSH_HOST` vacío, falta comando remoto, o ruta de clave declarada e inexistente). `message` suele ser `Túnel Lake cerrado`. |
| `SSH_FAILED` | `ssh` falló (rc, timeout, stdout vacío, JSON inválido, binario `ssh` ausente). `message` con detalle breve. |

## Enrutado por timeframe

| Origen | Condición |
|--------|-----------|
| **Lake (SSH)** | `timeframe` ∈ `CAPADONNA_HISTORICAL_TIMEFRAMES` (default `1d,1w,1M,moc`), lake SSH configurado (`CAPADONNA_SSH_HOST` + `CAPADONNA_REMOTE_OHLC_CMD`), y el mismo `timeframe` **no** aparece en `IBKR_REALTIME_TIMEFRAMES` (live gana si hay solapamiento). Claves **`1M`** (mes) y **`1m`** (minuto) se distinguen en el bridge. |
| **IBKR (HTTP)** | Cualquier otro caso: intradía en vivo, histórico sin lake, o solapamiento resuelto a favor de IBKR. |

## Variables de entorno

| Variable | Descripción |
|----------|-------------|
| `CAPADONNA_SSH_HOST` | Host (p. ej. IP Tailscale `100.97.151.69`). Obligatorio para rama lake. |
| `CAPADONNA_SSH_USER` | Usuario SSH (default `capadonna`). |
| `CAPADONNA_SSH_IDENTITY_FILE` | Ruta a clave privada local (`-i`); opcional si usa `ssh-agent`. |
| `CAPADONNA_SSH_TIMEOUT` | Segundos para `ssh` (default `120`). |
| `CAPADONNA_REMOTE_OHLC_CMD` | Plantilla del comando remoto con placeholders `{ticker}`, `{timeframe}`, `{lookback_days}` (sustituidos con `shlex.quote`). Debe imprimir **solo JSON** en stdout (objeto o lista compatible con el parser de `quant_market_bridge`). |
| `CAPADONNA_LAKE_DATA_ROOT` | *(Solo en el VPS, para el script de exportación)* Raíz del lake; default `~/projects/Capadonna-Driller/data/lake`. |
| `CAPADONNA_HISTORICAL_TIMEFRAMES` | Lista CSV en minúsculas (default `1d,1w,1M`). |
| `IBKR_REALTIME_TIMEFRAMES` | Lista CSV (default `1m,5m,15m,30m,1h`). Si un timeframe está aquí y también en histórico, **prevalece IBKR**. |
| `IBKR_MARKET_DATA_URL` | GET con `ticker`, `timeframe`, `lookback_days` — rama tiempo real u omólogo histórico si no hay lake. |
| `IBKR_PORTFOLIO_API_KEY` / `IBKR_MARKET_DATA_API_KEY` | Bearer opcional para el endpoint de barras. |

## Contrato JSON remoto (stdout)

La salida debe ser JSON parseable que contenga barras en uno de los formatos ya soportados: lista de objetos, o dict con claves `bars`, `data`, `ohlcv`, `candles`, `rows`, `results`, o clave del ticker / `series`. Cada objeto de barra admite campos como `timestamp`/`time`/`date`, `open`, `high`, `low`, `close`, `volume`.

**Layout `data/lake` en el VPS**

| Subcarpeta | Timeframe → carpeta (también puedes usar la palabra clave como timeframe) |
|------------|--------------------------------------------------|
| `daily/` | `1d` o `daily` |
| `intraday/` | `1m`, `5m`, `15m`, `30m`, `1h`, … o `intraday` (`1m` = minuto; **no** confundir con `1M` = mes) |
| `gold/` | `1w`, `1M` (mes, **M** mayúscula) o `gold` |
| `moc/` | `moc` (order flow; barras sintéticas o=h=l=c si solo hay un precio) |

**Particionado Hive / Delta (Parquet en el VPS):** p. ej. `daily/symbol=CCJ/year=2025/CCJ_daily.parquet` o `…/symbol=NVDA/year=2026/part-….parquet`. El script reconoce `symbol=` / `ticker=` en **cualquier** segmento del path (no solo el directorio padre), ignora rutas bajo `_delta_log`, y si no hay match por path/nombre hace un escaneo amplio de `.parquet` filtrando filas por columna `symbol`/`ticker`.

**Script en el monorepo Duckclaw** (copiar al VPS): `scripts/capadonna/export_lake_ohlcv.py` — recorre Parquet bajo la subcarpeta del `timeframe`, aplica `lookback_days`, imprime `{"bars":[...]}`.

```bash
# En el Mac (repo Duckclaw)
scp scripts/capadonna/export_lake_ohlcv.py capadonna@100.x.x.x:~/projects/Capadonna-Driller/scripts/

# En .env del gateway (plantilla SSH)
CAPADONNA_REMOTE_OHLC_CMD=/home/capadonna/projects/Capadonna-Driller/.venv/bin/python /home/capadonna/projects/Capadonna-Driller/scripts/export_lake_ohlcv.py {ticker} {timeframe} {lookback_days}
```

Requisito en el VPS: intérprete con `duckdb` (típ. el **venv del proyecto** `Capadonna-Driller/.venv`). **PEP 668:** no uses `pip install --user` en el Python del sistema.

```bash
cd ~/projects/Capadonna-Driller
./.venv/bin/pip install duckdb
```

En `.env` del **gateway (Mac)** conviene **ruta absoluta Linux** en `CAPADONNA_REMOTE_OHLC_CMD`: el proceso solo pasa la cadena a `ssh`; un `~` mal interpretado o copiar el comando en la terminal local puede resolver al home del Mac.

`CAPADONNA_REMOTE_OHLC_CMD` debe apuntar a ese `…/.venv/bin/python` y al script bajo `…/scripts/export_lake_ohlcv.py` en el VPS.

Opcional: `export CAPADONNA_LAKE_DATA_ROOT=/ruta/al/lake` si el lake no está en `~/projects/Capadonna-Driller/data/lake`.

## Creencias Finanz (`finance_worker.agent_beliefs`)

La tabla usa valores numéricos. Para el lake:

| `belief_key` | `observed_value` (después de arrancar el worker Finanz con `quant.enabled`) |
|--------------|----------------|
| `lake_host_configured` | `1.0` si la config SSH del lake es válida (`capadonna_ssh_config_ok`: host, comando, y si hay `-i` en env el archivo existe); si no, `0.0`. |
| `lake_status_online` | `1.0` si `CAPADONNA_SSH_HOST` y `CAPADONNA_REMOTE_OHLC_CMD` están definidos (misma noción que poder enrutar `fetch_market_data` al lake); si no, `0.0`. |

Se siembran desde `homeostasis.yaml` del template finanz y se **actualizan** al construir el grafo (`_sync_finanz_lake_beliefs`).

## Fly: `/lake` | `/lake status`

Comando del gateway: resume variables `CAPADONNA_*` y, si la config es válida, ejecuta `ssh … true` con conexión corta (`ConnectTimeout=5`). Ver [Interfaz de Control de Agentes (Fly Commands)](Interfaz%20de%20Control%20de%20Agentes%20(Fly%20Commands).md).

## Seguridad y operación

- Tráfico preferente por Tailscale; `ssh -o BatchMode=yes` (sin password interactivo).
- Usuario remoto con permisos **solo lectura** sobre el lake.
- No commitear claves ni valores personales en el repo; solo `.env` / PM2 en runtime.

## MOC (`lake/moc`)

La carpeta **moc** (order flow / microestructura) se lee con **`timeframe=moc`** vía `fetch_lake_ohlcv` / rama lake de `fetch_market_data` si `moc` está en `CAPADONNA_HISTORICAL_TIMEFRAMES` (por defecto en código: `1d,1w,1M,moc`). El script `export_lake_ohlcv.py` relaja OHLC: si solo existe `close`/`price`/`last`/`mid`, replica en open/high/low para cuadrar con `quant_core.ohlcv_data`. Interpretación CFD de esas series queda bajo criterio del agente y de specs CFD.

**Enrutado `1M` vs `1m`:** en `CAPADONNA_HISTORICAL_TIMEFRAMES` e `IBKR_REALTIME_TIMEFRAMES` use **`1M`** (mayúscula) para el mes y **`1m`** para el minuto; el bridge normaliza claves sin colisionar.
