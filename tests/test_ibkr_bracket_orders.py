"""Unit tests for IBKR bracket orders module."""

from __future__ import annotations

import pytest

# Mock ib_insync para tests sin conexión real
pytest.importorskip("ib_insync", reason="ib_insync required for bracket order tests")

from duckclaw.ibkr_bracket_orders import (
    create_bracket_order,
)


def test_create_bracket_order_buy_with_tp_sl():
    """Bracket order BUY con TP y SL debe crear 3 órdenes."""
    main, tp, sl = create_bracket_order("CEG", "BUY", 994, 300.0, 245.0)

    # Main order
    assert main.action == "BUY"
    assert main.totalQuantity == 994
    assert main.orderType == "MKT"
    assert main.outsideRth is True

    # TP order
    assert tp is not None
    assert tp.action == "SELL"  # Opuesta a BUY
    assert tp.totalQuantity == 994
    assert tp.orderType == "LMT"
    assert tp.lmtPrice == 300.0
    assert tp.tif == "GTC"
    assert tp.outsideRth is True

    # SL order
    assert sl is not None
    assert sl.action == "SELL"
    assert sl.totalQuantity == 994
    assert sl.orderType == "STP"
    assert sl.auxPrice == 245.0
    assert sl.tif == "GTC"
    assert sl.outsideRth is True


def test_create_bracket_order_sell_with_tp_sl():
    """Bracket order SELL invierte las acciones de TP/SL."""
    main, tp, sl = create_bracket_order("SPY", "SELL", 100, 550.0, 600.0)

    assert main.action == "SELL"
    assert main.totalQuantity == 100

    # Para SELL, TP y SL son BUY (cerrar short)
    assert tp.action == "BUY"
    assert tp.lmtPrice == 550.0

    assert sl.action == "BUY"
    assert sl.auxPrice == 600.0


def test_create_bracket_order_only_tp():
    """Bracket order solo con TP (sin SL)."""
    main, tp, sl = create_bracket_order("AAPL", "BUY", 50, tp_price=200.0, sl_price=None)

    assert main.action == "BUY"
    assert main.totalQuantity == 50

    assert tp is not None
    assert tp.lmtPrice == 200.0
    assert tp.transmit is True  # Último en el grupo

    assert sl is None


def test_create_bracket_order_only_sl():
    """Bracket order solo con SL (sin TP)."""
    main, tp, sl = create_bracket_order("MSFT", "BUY", 75, tp_price=None, sl_price=400.0)

    assert main.action == "BUY"
    assert main.totalQuantity == 75

    assert tp is None

    assert sl is not None
    assert sl.auxPrice == 400.0
    assert sl.transmit is True


def test_create_bracket_order_no_tp_sl():
    """Sin TP ni SL, solo devuelve main order."""
    main, tp, sl = create_bracket_order("TSLA", "BUY", 10, tp_price=None, sl_price=None)

    assert main.action == "BUY"
    assert main.totalQuantity == 10
    assert main.transmit is True  # Se envía directamente

    assert tp is None
    assert sl is None


def test_create_bracket_order_validates_side():
    """side debe ser 'BUY' o 'SELL'."""
    with pytest.raises(ValueError, match="side debe ser"):
        create_bracket_order("CEG", "HOLD", 100, 300.0, 245.0)

    with pytest.raises(ValueError, match="side debe ser"):
        create_bracket_order("CEG", "buy", 100, 300.0, 245.0)  # Case sensitive


def test_create_bracket_order_validates_quantity():
    """quantity debe ser > 0."""
    with pytest.raises(ValueError, match="quantity debe ser > 0"):
        create_bracket_order("CEG", "BUY", 0, 300.0, 245.0)

    with pytest.raises(ValueError, match="quantity debe ser > 0"):
        create_bracket_order("CEG", "BUY", -100, 300.0, 245.0)


def test_create_bracket_order_validates_ticker():
    """ticker no puede estar vacío."""
    with pytest.raises(ValueError, match="ticker no puede estar vacío"):
        create_bracket_order("", "BUY", 100, 300.0, 245.0)

    with pytest.raises(ValueError, match="ticker no puede estar vacío"):
        create_bracket_order("   ", "BUY", 100, 300.0, 245.0)


def test_create_bracket_order_validates_tp_price():
    """tp_price debe ser > 0 si se proporciona."""
    with pytest.raises(ValueError, match="tp_price debe ser > 0"):
        create_bracket_order("CEG", "BUY", 100, tp_price=0.0, sl_price=245.0)

    with pytest.raises(ValueError, match="tp_price debe ser > 0"):
        create_bracket_order("CEG", "BUY", 100, tp_price=-10.0, sl_price=245.0)


def test_create_bracket_order_validates_sl_price():
    """sl_price debe ser > 0 si se proporciona."""
    with pytest.raises(ValueError, match="sl_price debe ser > 0"):
        create_bracket_order("CEG", "BUY", 100, tp_price=300.0, sl_price=0.0)

    with pytest.raises(ValueError, match="sl_price debe ser > 0"):
        create_bracket_order("CEG", "BUY", 100, tp_price=300.0, sl_price=-50.0)


def test_bracket_order_transmit_flags():
    """Verificar que transmit flags están correctos para el grupo OCA."""
    # Con TP y SL, solo SL debe tener transmit=True
    main, tp, sl = create_bracket_order("CEG", "BUY", 100, 300.0, 245.0)
    assert main.transmit is False
    assert tp.transmit is False
    assert sl.transmit is True  # Último en el grupo

    # Solo TP, TP debe tener transmit=True
    main2, tp2, sl2 = create_bracket_order("SPY", "BUY", 100, tp_price=600.0, sl_price=None)
    assert main2.transmit is False
    assert tp2.transmit is True
    assert sl2 is None

    # Solo SL, SL debe tener transmit=True
    main3, tp3, sl3 = create_bracket_order("AAPL", "BUY", 100, tp_price=None, sl_price=180.0)
    assert main3.transmit is False
    assert tp3 is None
    assert sl3.transmit is True


def test_bracket_order_parent_id_set():
    """parentId debe estar configurado para TP y SL."""
    main, tp, sl = create_bracket_order("CEG", "BUY", 100, 300.0, 245.0)

    # Parent ID de TP y SL debe coincidir con main.orderId
    assert tp.parentId == main.orderId
    assert sl.parentId == main.orderId




def test_create_bracket_order_rejects_bad_buy_direction():
    """BUY exige tp_price > sl_price."""
    with pytest.raises(ValueError, match="tp_price > sl_price"):
        create_bracket_order("CEG", "BUY", 100, tp_price=200.0, sl_price=250.0)


def test_create_bracket_order_rejects_bad_sell_direction():
    """SELL exige tp_price < sl_price."""
    with pytest.raises(ValueError, match="tp_price < sl_price"):
        create_bracket_order("SPY", "SELL", 100, tp_price=600.0, sl_price=550.0)


def test_create_bracket_order_sets_oca_group_when_tp_and_sl():
    """TP y SL comparten ocaGroup/ocaType cuando ambos existen."""
    main, tp, sl = create_bracket_order("CEG", "BUY", 100, 300.0, 245.0)
    assert tp.ocaGroup == sl.ocaGroup
    assert tp.ocaGroup.startswith("BRACKET_CEG")
    assert tp.ocaType == 1
    assert sl.ocaType == 1

# ---------------------------------------------------------------------------
# Integration tests (requieren conexión a IBKR paper account)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_connect_ibkr_paper():
    """Test de conexión a IBKR paper account (requiere Gateway corriendo)."""
    pytest.skip("Requiere IBKR Gateway/TWS paper account en localhost:4002")

    from duckclaw.ibkr_bracket_orders import connect_ibkr

    ib = await connect_ibkr(host="127.0.0.1", port=4002, client_id=999)
    assert ib.isConnected()

    await ib.disconnect()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_submit_bracket_order_paper():
    """Test de envío de bracket order a paper account (requiere Gateway)."""
    pytest.skip("Requiere IBKR Gateway/TWS paper account en localhost:4002")

    from duckclaw.ibkr_bracket_orders import connect_ibkr, submit_bracket_order

    ib = await connect_ibkr(host="127.0.0.1", port=4002, client_id=999)

    result = await submit_bracket_order(
        ib,
        ticker="SPY",
        side="BUY",
        quantity=10,
        tp_price=600.0,
        sl_price=550.0,
    )

    assert result["main_order_id"] > 0
    assert result["tp_order_id"] > 0
    assert result["sl_order_id"] > 0
    assert result["status"] == "submitted"
    assert result["ticker"] == "SPY"
    assert result["side"] == "BUY"
    assert result["quantity"] == 10

    # Verificar que las órdenes están en IBKR
    trades = ib.trades()
    main_ids = [t.order.orderId for t in trades]
    assert result["main_order_id"] in main_ids
    assert result["tp_order_id"] in main_ids
    assert result["sl_order_id"] in main_ids

    # Cancelar órdenes de prueba
    for order_id in [result["main_order_id"], result["tp_order_id"], result["sl_order_id"]]:
        try:
            trade = next(t for t in trades if t.order.orderId == order_id)
            ib.cancelOrder(trade.order)
        except StopIteration:
            pass

    await ib.disconnect()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_order_status():
    """Test de consulta de estado de orden (requiere Gateway)."""
    pytest.skip("Requiere IBKR Gateway/TWS paper account en localhost:4002")

    from duckclaw.ibkr_bracket_orders import connect_ibkr, get_order_status, submit_bracket_order

    ib = await connect_ibkr(host="127.0.0.1", port=4002, client_id=999)

    # Enviar bracket order
    result = await submit_bracket_order(ib, "SPY", "BUY", 10, 600.0, 550.0)
    main_order_id = result["main_order_id"]

    # Consultar estado
    status = await get_order_status(ib, main_order_id)
    assert status is not None
    assert status["order_id"] == main_order_id
    assert status["status"] in ["Submitted", "PreSubmitted", "PendingSubmit"]

    # Cancelar y cleanup
    trades = ib.trades()
    for order_id in [result["main_order_id"], result["tp_order_id"], result["sl_order_id"]]:
        try:
            trade = next(t for t in trades if t.order.orderId == order_id)
            ib.cancelOrder(trade.order)
        except StopIteration:
            pass

    await ib.disconnect()
