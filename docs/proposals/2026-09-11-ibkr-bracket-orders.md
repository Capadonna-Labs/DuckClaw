# Propuesta: Bracket Orders con TP/SL en IBKR

**Fecha**: 2026-09-11  
**Autor**: Cursor Cloud Agent  
**Status**: Propuesta  
**Prioridad**: Alta

---

## 🎯 Problema

### Caso Real: CEG - Pérdida de $32,400

| Dato | Valor |
|------|-------|
| Entrada | 994 shares @ $267.37 (julio) |
| TP configurado | $300.00 (ACTIVE desde 6-ago) |
| **Precio alcanzado** | **$305.80** el 8-sep |
| **Resultado** | ❌ Posición **NO se cerró** |
| **Ganancia perdida** | ~**$32,400** (12.2% sobre posición) |

### Root Cause

El sistema actual:
1. ✅ Calcula niveles TP/SL (`calculate_tp_sl_distance`)
2. ✅ Los almacena en `tp_sl_levels` (estado ACTIVE)
3. ✅ Los monitorea en ciclos `/loop`
4. ❌ **NO ejecuta automáticamente** cuando se alcanza el nivel
5. ❌ **NO envía órdenes** TP/SL al broker

**Consecuencia**: Los TP/SL son solo "monitore human-in-the-loop", no órdenes ejecutables.

---

## ✨ Solución Propuesta

### Bracket Orders en IBKR

Cuando se ejecuta una señal BUY/SELL, enviar **3 órdenes simultáneas**:

```python
# Orden principal
main_order = MarketOrder("BUY", 994)

# Take Profit (venta limit)
tp_order = LimitOrder("SELL", 994, limit_price=300.00)
tp_order.parentId = main_order.orderId
tp_order.transmit = False  # OCA group

# Stop Loss (venta stop)
sl_order = StopOrder("SELL", 994, stop_price=245.00)
sl_order.parentId = main_order.orderId
sl_order.transmit = True  # Envía todo el grupo

# Resultado: 
# - Si precio alcanza $300 → ejecuta TP, cancela SL
# - Si precio cae a $245 → ejecuta SL, cancela TP
# - Automático, sin monitoreo local
```

### Arquitectura

```
┌─────────────────────────────────────────────────┐
│ Quant Trader                                    │
│ propose_trade_signal(ticker, side, qty)         │
└────────────────┬────────────────────────────────┘
                 │ HITL Approval
                 ▼
┌─────────────────────────────────────────────────┐
│ Signal Execution Bridge (NUEVO)                 │
│                                                  │
│ 1. Lee tp_sl_levels para el ticker             │
│ 2. Crea bracket order (main + TP + SL)         │
│ 3. Envía a IBKR vía ib_insync                  │
│ 4. Registra order_ids en DB                    │
└────────────────┬────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────┐
│ IBKR                                            │
│                                                  │
│ - Ejecuta main order → posición abierta         │
│ - Activa TP/SL orders (GTC, OCA group)         │
│ - Monitorea precio 24/7                         │
│ - Ejecuta TP o SL automáticamente               │
└─────────────────────────────────────────────────┘
```

---

## 📋 Implementación

### Fase 1: Infraestructura IBKR (Core)

#### 1.1 Módulo de Bracket Orders

**Archivo**: `workers/duckclaw/lib/ibkr_bracket_orders.py`

```python
from ib_insync import IB, MarketOrder, LimitOrder, StopOrder
from typing import Optional

def create_bracket_order(
    ticker: str,
    side: str,  # "BUY" o "SELL"
    quantity: int,
    tp_price: Optional[float] = None,
    sl_price: Optional[float] = None,
) -> tuple[MarketOrder, Optional[LimitOrder], Optional[StopOrder]]:
    """
    Crea bracket order (entrada + TP + SL).
    
    Returns:
        (main_order, tp_order, sl_order)
    """
    # Main order
    main = MarketOrder(side, quantity)
    main.outsideRth = True  # Permite ejecución fuera de horario
    
    if not (tp_price or sl_price):
        return (main, None, None)
    
    # Determinar acción opuesta (para cerrar)
    close_action = "SELL" if side == "BUY" else "BUY"
    
    # Take Profit (limit)
    tp_order = None
    if tp_price:
        tp_order = LimitOrder(close_action, quantity, tp_price)
        tp_order.parentId = main.orderId
        tp_order.transmit = False
        tp_order.tif = "GTC"  # Good Till Canceled
    
    # Stop Loss (stop)
    sl_order = None
    if sl_price:
        sl_order = StopOrder(close_action, quantity, sl_price)
        sl_order.parentId = main.orderId
        sl_order.transmit = True  # Envía todo el grupo
        sl_order.tif = "GTC"
    
    return (main, tp_order, sl_order)


async def submit_bracket_order(
    ib: IB,
    ticker: str,
    side: str,
    quantity: int,
    tp_price: Optional[float] = None,
    sl_price: Optional[float] = None,
) -> dict:
    """
    Envía bracket order a IBKR.
    
    Returns:
        {
            "main_order_id": int,
            "tp_order_id": Optional[int],
            "sl_order_id": Optional[int],
            "status": "submitted"
        }
    """
    from ib_insync import Stock
    
    contract = Stock(ticker, "SMART", "USD")
    main, tp, sl = create_bracket_order(ticker, side, quantity, tp_price, sl_price)
    
    # Enviar al broker
    trades = []
    main_trade = ib.placeOrder(contract, main)
    trades.append(main_trade)
    
    if tp:
        tp.parentId = main_trade.order.orderId
        tp_trade = ib.placeOrder(contract, tp)
        trades.append(tp_trade)
    
    if sl:
        sl.parentId = main_trade.order.orderId
        sl_trade = ib.placeOrder(contract, sl)
        trades.append(sl_trade)
    
    # Esperar confirmación
    await ib.sleep(1)
    
    return {
        "main_order_id": main_trade.order.orderId,
        "tp_order_id": tp_trade.order.orderId if tp else None,
        "sl_order_id": sl_trade.order.orderId if sl else None,
        "status": "submitted",
        "timestamp": datetime.now(timezone.utc),
    }
```

#### 1.2 Tabla de Órdenes

**Migración**: `schema_migrations.py` (nueva versión)

```sql
CREATE TABLE IF NOT EXISTS quant_core.ibkr_orders (
    order_id INTEGER PRIMARY KEY,
    ticker VARCHAR NOT NULL,
    side VARCHAR NOT NULL,  -- 'BUY', 'SELL'
    quantity INTEGER NOT NULL,
    order_type VARCHAR NOT NULL,  -- 'MARKET', 'LIMIT', 'STOP'
    limit_price DOUBLE,
    stop_price DOUBLE,
    parent_order_id INTEGER,  -- Para TP/SL
    status VARCHAR NOT NULL,  -- 'submitted', 'filled', 'cancelled'
    filled_qty INTEGER DEFAULT 0,
    filled_price DOUBLE,
    submitted_at TIMESTAMP NOT NULL,
    filled_at TIMESTAMP,
    cancelled_at TIMESTAMP,
    trade_signal_id VARCHAR,  -- Link a trade_signals
    notes TEXT
);

CREATE INDEX idx_ibkr_orders_ticker ON quant_core.ibkr_orders(ticker);
CREATE INDEX idx_ibkr_orders_status ON quant_core.ibkr_orders(status);
CREATE INDEX idx_ibkr_orders_parent ON quant_core.ibkr_orders(parent_order_id);
```

### Fase 2: Integración con Signals

#### 2.1 Signal Execution Bridge

**Archivo**: `workers/duckclaw/lib/signal_execution_bridge.py`

```python
async def execute_signal_with_bracket(
    signal_id: str,
    ticker: str,
    side: str,
    quantity: int,
    vault_db_path: str,
) -> dict:
    """
    Ejecuta señal con bracket order (TP/SL incluidos).
    
    Workflow:
    1. Lee tp_sl_levels para el ticker
    2. Crea bracket order
    3. Envía a IBKR
    4. Registra en ibkr_orders
    5. Actualiza trade_signals.executed_at
    """
    con = duckdb.connect(vault_db_path)
    
    # 1. Leer niveles TP/SL
    tp_sl = con.execute("""
        SELECT tp, sl
        FROM quant_core.tp_sl_levels
        WHERE ticker = ? AND status = 'ACTIVE'
        ORDER BY created_at DESC
        LIMIT 1
    """, [ticker]).fetchone()
    
    tp_price = tp_sl[0] if tp_sl else None
    sl_price = tp_sl[1] if tp_sl else None
    
    # 2. Conectar a IBKR
    ib = await connect_ibkr()
    
    # 3. Enviar bracket order
    result = await submit_bracket_order(
        ib, ticker, side, quantity, tp_price, sl_price
    )
    
    # 4. Registrar órdenes
    orders = [
        {
            "order_id": result["main_order_id"],
            "ticker": ticker,
            "side": side,
            "quantity": quantity,
            "order_type": "MARKET",
            "trade_signal_id": signal_id,
        }
    ]
    
    if result["tp_order_id"]:
        orders.append({
            "order_id": result["tp_order_id"],
            "ticker": ticker,
            "side": "SELL" if side == "BUY" else "BUY",
            "quantity": quantity,
            "order_type": "LIMIT",
            "limit_price": tp_price,
            "parent_order_id": result["main_order_id"],
            "trade_signal_id": signal_id,
        })
    
    if result["sl_order_id"]:
        orders.append({
            "order_id": result["sl_order_id"],
            "ticker": ticker,
            "side": "SELL" if side == "BUY" else "BUY",
            "quantity": quantity,
            "order_type": "STOP",
            "stop_price": sl_price,
            "parent_order_id": result["main_order_id"],
            "trade_signal_id": signal_id,
        })
    
    # INSERT via write command queue
    for order in orders:
        enqueue_write_command("insert_ibkr_order", order)
    
    # 5. Marcar señal como ejecutada
    enqueue_write_command("update_trade_signal_executed", {
        "signal_id": signal_id,
        "executed_at": result["timestamp"],
    })
    
    await ib.disconnect()
    con.close()
    
    return result
```

#### 2.2 Skill de Ejecución

**Archivo**: `workers/duckclaw/templates/Quant-Trader/skills/execute_signal_with_bracket.py`

```python
@skill_function(
    name="execute_signal_with_bracket",
    description="Ejecuta señal de trading con TP/SL en IBKR (bracket order)",
    vault_binding_required=True,
)
async def execute_signal_with_bracket_skill(
    signal_id: str,
    vault_context: VaultContext,
) -> dict:
    """
    Ejecuta una señal de trading enviando bracket order (entrada + TP + SL) a IBKR.
    
    Args:
        signal_id: ID de la señal en trade_signals
    
    Returns:
        {
            "status": "submitted",
            "main_order_id": 12345,
            "tp_order_id": 12346,
            "sl_order_id": 12347,
            "ticker": "CEG",
            "message": "Bracket order submitted: BUY 994 CEG @ market, TP=$300, SL=$245"
        }
    """
    # ... implementación usando execute_signal_with_bracket()
```

### Fase 3: Monitoreo de Órdenes

#### 3.1 Order Status Sync

**Archivo**: `workers/duckclaw/lib/ibkr_order_monitor.py`

```python
async def sync_order_status(vault_db_path: str):
    """
    Sincroniza estado de órdenes activas desde IBKR.
    
    Actualiza ibkr_orders con:
    - Status (filled, cancelled, partially_filled)
    - Filled quantity / price
    - Timestamps
    """
    ib = await connect_ibkr()
    
    con = duckdb.connect(vault_db_path, read_only=True)
    pending = con.execute("""
        SELECT order_id, ticker
        FROM quant_core.ibkr_orders
        WHERE status IN ('submitted', 'partial')
    """).fetchall()
    con.close()
    
    for order_id, ticker in pending:
        trade = ib.trade(order_id)
        if not trade:
            continue
        
        status_map = {
            "Filled": "filled",
            "Cancelled": "cancelled",
            "PendingSubmit": "submitted",
            "PreSubmitted": "submitted",
            "Submitted": "submitted",
        }
        
        enqueue_write_command("update_ibkr_order_status", {
            "order_id": order_id,
            "status": status_map.get(trade.orderStatus.status, "unknown"),
            "filled_qty": trade.orderStatus.filled,
            "filled_price": trade.orderStatus.avgFillPrice,
        })
    
    await ib.disconnect()
```

**Cron Job**: Correr cada 1 minuto (PM2 o systemd timer)

---

## 🚀 Deployment Plan

### Pre-requisitos

1. **IBKR Gateway/TWS running** en el VPS
2. **ib_insync** instalado:
   ```bash
   uv pip install ib-insync
   ```
3. **Credenciales IBKR** en `.env`:
   ```bash
   IBKR_HOST=127.0.0.1
   IBKR_PORT=4002  # Paper trading: 4002, Live: 4001
   IBKR_CLIENT_ID=1
   ```

### Rollout (3 fases)

#### Fase 1: Core Infrastructure (1-2 días)
- [ ] Crear `ibkr_bracket_orders.py`
- [ ] Migración: tabla `ibkr_orders`
- [ ] Unit tests bracket order creation
- [ ] Integration test con IBKR paper account

#### Fase 2: Signal Execution (1 día)
- [ ] Crear `signal_execution_bridge.py`
- [ ] Skill `execute_signal_with_bracket`
- [ ] Agregar a manifest de Quant-Trader
- [ ] Test end-to-end: signal → bracket order → IBKR

#### Fase 3: Monitoring & Prod (1 día)
- [ ] `ibkr_order_monitor.py` + cron job
- [ ] Dashboard en admin UI (tabla de órdenes activas)
- [ ] Producción: CEG signal re-execution con bracket
- [ ] Documentación operativa

---

## 📊 Beneficios

| Métrica | Antes | Después |
|---------|-------|---------|
| **TP ejecutado automáticamente** | ❌ No | ✅ Sí (GTC en broker) |
| **SL ejecutado automáticamente** | ❌ No | ✅ Sí (GTC en broker) |
| **Monitoreo 24/7** | ❌ Solo ciclos `/loop` | ✅ IBKR monitorea |
| **Latencia de ejecución** | Manual | ~1-2 segundos |
| **Pérdida por no-ejecución** | $32,400 (CEG) | **$0** |

---

## ⚠️ Riesgos & Mitigaciones

### Riesgo 1: Double Execution

**Problema**: Orden enviada 2 veces (bug en código).

**Mitigación**:
- ✅ Unique constraint en `ibkr_orders.order_id`
- ✅ Idempotency check: si `trade_signals.executed_at` != NULL, skip
- ✅ Logs detallados en cada paso

### Riesgo 2: TP/SL Incorrectos

**Problema**: Precio TP/SL mal calculado.

**Mitigación**:
- ✅ Validación pre-submit: TP debe ser > entry (BUY), SL < entry
- ✅ Dry-run mode: log órdenes sin enviar a IBKR
- ✅ HITL review: mostrar TP/SL en UI antes de ejecutar

### Riesgo 3: IBKR Disconnect

**Problema**: Gateway caído, órden no se envía.

**Mitigación**:
- ✅ Retry logic (3 intentos, backoff exponencial)
- ✅ Alert en Slack/log si falla después de retries
- ✅ Fallback: marcar señal como "pending_execution" para retry manual

---

## 📝 Testing Strategy

### Unit Tests

```python
def test_create_bracket_order_buy():
    main, tp, sl = create_bracket_order("CEG", "BUY", 994, 300.0, 245.0)
    
    assert main.action == "BUY"
    assert main.totalQuantity == 994
    
    assert tp.action == "SELL"
    assert tp.lmtPrice == 300.0
    assert tp.tif == "GTC"
    
    assert sl.action == "SELL"
    assert sl.auxPrice == 245.0

def test_tp_sl_from_levels():
    # Mock tp_sl_levels query
    # Verify correct prices extracted
```

### Integration Tests (Paper Account)

```python
@pytest.mark.integration
async def test_submit_bracket_order_ibkr_paper():
    ib = await connect_ibkr()  # Paper account
    
    result = await submit_bracket_order(
        ib, "SPY", "BUY", 10, tp_price=600.0, sl_price=550.0
    )
    
    assert result["main_order_id"] > 0
    assert result["tp_order_id"] > 0
    assert result["sl_order_id"] > 0
    
    # Verificar en IBKR que las 3 órdenes existen
    trades = ib.trades()
    assert len([t for t in trades if t.order.orderId == result["main_order_id"]]) == 1
```

---

## 📚 References

- [ib_insync Bracket Orders](https://ib-insync.readthedocs.io/recipes.html#bracket-orders)
- [IBKR TWS API - Bracket Orders](https://interactivebrokers.github.io/tws-api/bracket_order.html)
- Código existente: `packages/shared/src/duckclaw/position_metrics.py`

---

## ✅ Acceptance Criteria

Una señal de trading se considera **correctamente ejecutada** cuando:

1. ✅ Se envían 3 órdenes a IBKR: main + TP + SL
2. ✅ Las 3 órdenes tienen `status = 'submitted'` en `ibkr_orders`
3. ✅ TP y SL tienen `parent_order_id = main.order_id`
4. ✅ IBKR confirma que las órdenes están activas (GTC)
5. ✅ Cuando precio toca TP → orden se ejecuta automáticamente
6. ✅ Cuando precio toca SL → orden se ejecuta automáticamente
7. ✅ Al ejecutar TP → SL se cancela (OCA group)
8. ✅ Al ejecutar SL → TP se cancela (OCA group)

**Caso de Validación**: Re-ejecutar CEG con TP=$300, SL=$245 y verificar que si precio > $300, posición se cierra automáticamente.

---

**Próximo Paso**: ¿Aprobamos esta propuesta y comenzamos con Fase 1 (Core Infrastructure)?
