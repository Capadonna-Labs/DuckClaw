# IBKR Bracket Orders — Setup & Configuration

**Status**: Fase 1 (Core Infrastructure) ✅  
**Fecha**: 2026-09-11  
**Versión mínima**: Python 3.10  
**Dependencias**: `ib-insync >= 0.9.86`

---

## 📦 Instalación

### Opción 1: Instalar con uv (recomendado)

```bash
# Instalar dependencias de trading (incluye ib-insync)
uv sync --extra trading

# O instalar solo ib-insync
uv pip install ib-insync
```

### Opción 2: pip tradicional

```bash
pip install ib-insync
```

---

## 🔧 Configuración IBKR Gateway/TWS

### Requisitos Previos

1. **IBKR Account** (paper o live)
2. **TWS (Trader Workstation)** o **IB Gateway** instalado
3. **API Access** habilitado en IBKR

### Configurar TWS/Gateway

#### 1. Descargar IB Gateway (recomendado para producción)

```bash
# Linux
wget https://download2.interactivebrokers.com/installers/ibgateway/latest-standalone/ibgateway-latest-standalone-linux-x64.sh
chmod +x ibgateway-latest-standalone-linux-x64.sh
./ibgateway-latest-standalone-linux-x64.sh

# macOS
# Descargar desde: https://www.interactivebrokers.com/en/trading/ibgateway-stable.php
```

#### 2. Habilitar API Access

1. Abrir TWS/Gateway
2. **File → Global Configuration → API → Settings**
3. Configurar:
   - ✅ Enable ActiveX and Socket Clients
   - ✅ Allow connections from localhost
   - ✅ Read-Only API (para testing inicial)
   - Socket port: **4002** (paper) o **4001** (live)
   - Master API client ID: **0** (opcional)

4. **Trusted IP Addresses**:
   - Añadir `127.0.0.1` (localhost)
   - Para VPS: añadir IP del servidor

5. **Apply** y **Restart** TWS/Gateway

---

## 🌍 Variables de Entorno

Configurar en `.env`:

```bash
# IBKR Connection
IBKR_HOST=127.0.0.1           # IP del Gateway/TWS
IBKR_PORT=4002                 # 4002 = paper, 4001 = live
IBKR_CLIENT_ID=1               # Client ID único (1-32)

# Optional: Trading Account ID
IBKR_ACCOUNT_ID=DU1234567      # Para multi-account setups
```

### Puertos por Tipo de Cuenta

| Ambiente | Puerto | Uso |
|----------|--------|-----|
| Paper Trading | 4002 | Testing y desarrollo |
| Live Trading | 4001 | Producción (real money) |
| TWS API | 7496 | TWS legacy API |

---

## ✅ Verificación de Setup

### 1. Test de Conexión

```python
import asyncio
from duckclaw.ibkr_bracket_orders import connect_ibkr

async def test_connection():
    try:
        ib = await connect_ibkr()
        print(f"✅ Conectado a IBKR Gateway")
        print(f"   Host: {ib.client.host}")
        print(f"   Port: {ib.client.port}")
        print(f"   Client ID: {ib.client.clientId}")
        await ib.disconnect()
    except Exception as e:
        print(f"❌ Error de conexión: {e}")

asyncio.run(test_connection())
```

### 2. Test de Bracket Order (Dry Run)

```python
from duckclaw.ibkr_bracket_orders import create_bracket_order

main, tp, sl = create_bracket_order("SPY", "BUY", 10, 600.0, 550.0)

print(f"Main: {main.action} {main.totalQuantity} @ {main.orderType}")
print(f"TP: {tp.action} {tp.totalQuantity} @ limit {tp.lmtPrice}")
print(f"SL: {sl.action} {sl.totalQuantity} @ stop {sl.auxPrice}")
```

### 3. Unit Tests

```bash
# Correr tests unitarios (sin conexión real)
uv run pytest tests/test_ibkr_bracket_orders.py -v

# Correr integration tests (requiere Gateway corriendo)
uv run pytest tests/test_ibkr_bracket_orders.py -v -m integration
```

---

## 🚀 Uso Básico

### Enviar Bracket Order

```python
import asyncio
from duckclaw.ibkr_bracket_orders import connect_ibkr, submit_bracket_order

async def example_bracket_order():
    # Conectar
    ib = await connect_ibkr()
    
    # Enviar bracket order: BUY 10 SPY @ market, TP=$600, SL=$550
    result = await submit_bracket_order(
        ib,
        ticker="SPY",
        side="BUY",
        quantity=10,
        tp_price=600.0,
        sl_price=550.0,
    )
    
    print(f"✅ Bracket order enviado:")
    print(f"   Main Order ID: {result['main_order_id']}")
    print(f"   TP Order ID: {result['tp_order_id']}")
    print(f"   SL Order ID: {result['sl_order_id']}")
    print(f"   Status: {result['status']}")
    
    # Desconectar
    await ib.disconnect()

asyncio.run(example_bracket_order())
```

### Consultar Estado de Orden

```python
from duckclaw.ibkr_bracket_orders import get_order_status

status = await get_order_status(ib, order_id=12345)
print(f"Status: {status['status']}")
print(f"Filled: {status['filled_qty']} @ ${status['filled_price']:.2f}")
```

---

## 🔍 Troubleshooting

### Error: `ConnectionError: No se pudo conectar a IBKR Gateway`

**Causas comunes**:
1. Gateway/TWS no está corriendo → Iniciar Gateway
2. Puerto incorrecto → Verificar `IBKR_PORT` (4002 paper, 4001 live)
3. API no habilitado → Revisar **Global Configuration → API → Settings**
4. Firewall bloqueando → Permitir puerto en firewall

**Verificar Gateway está corriendo**:
```bash
# Linux/macOS
netstat -an | grep 4002

# Debería mostrar:
# tcp4  0  0  127.0.0.1.4002  *.*  LISTEN
```

---

### Error: `Socket closed` o `Timeout`

**Solución**:
1. Aumentar timeout en `connect_ibkr`:
   ```python
   ib = await connect_ibkr()
   ib.client.setTimeout(30)  # 30 segundos
   ```

2. Reiniciar Gateway/TWS

3. Verificar que no hay otro cliente conectado con mismo `client_id`

---

### Error: `Order rejected: ...`

**Causas comunes**:
1. **Ticker inválido** → Verificar símbolo correcto
2. **Precio fuera de rango** → Verificar que TP > entry (BUY), SL < entry
3. **Insufficient margin** → Verificar buying power en paper account
4. **Market closed** → Usar `outsideRth=True` (ya configurado)

---

### Warning: `ib_insync no disponible`

**Solución**:
```bash
uv sync --extra trading
# o
uv pip install ib-insync
```

---

## 📊 Migración de Base de Datos

La migración `39_ibkr_orders_v1` crea:
- Schema `quant_core` (si no existe)
- Tabla `quant_core.ibkr_orders`
- Índices para queries eficientes

**Correr migración**:
```bash
uv run duckclaw-migrate
```

**Verificar tabla creada**:
```python
import duckdb

con = duckdb.connect("db/private/default/duckclaw.duckdb", read_only=True)
result = con.execute("""
    SELECT * FROM quant_core.ibkr_orders LIMIT 1
""").fetchall()
con.close()
```

---

## 🔗 Referencias

- [ib_insync Documentation](https://ib-insync.readthedocs.io/)
- [IBKR TWS API Guide](https://interactivebrokers.github.io/tws-api/)
- [Bracket Orders Tutorial](https://ib-insync.readthedocs.io/recipes.html#bracket-orders)
- Propuesta completa: [`docs/proposals/2026-09-11-ibkr-bracket-orders.md`](../proposals/2026-09-11-ibkr-bracket-orders.md)

---

## 📝 Próximos Pasos

- [ ] **Fase 2**: Signal Execution Bridge (link TP/SL levels → bracket orders)
- [ ] **Fase 3**: Order Monitor (sync estado desde IBKR cada 1min)
- [ ] **Production**: Deploy a VPS + setup cron jobs

---

**Status**: ✅ Core Infrastructure completada (Fase 1)  
**Ready for**: Integration testing con paper account
