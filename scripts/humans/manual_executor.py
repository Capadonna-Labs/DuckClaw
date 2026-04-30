import os
import sys
import json
import duckdb
import urllib.request
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

# 1. Cargar entorno
env_path = Path(__file__).resolve().parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

def execute_order_at_broker(ticker, action, qty, signal_id):
    """Envía la orden con el contrato completo requerido por el broker."""
    url = os.environ.get("IBKR_EXECUTE_ORDER_URL") or "http://100.97.151.69:8002/api/broker/execute"
    api_key = os.environ.get("IBKR_PORTFOLIO_API_KEY")
    mode = os.environ.get("IBKR_ACCOUNT_MODE", "paper")

    # EL CONTRATO CORRECTO (Incluyendo signal_id)
    payload = {
        "signal_id": str(signal_id),
        "ticker": ticker.upper(),
        "action": action.upper(),
        "quantity": float(qty),
        "paper": (mode == "paper")
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-Duckclaw-IBKR-Account-Mode": mode
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8")), True
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.reason}"}, False
    except Exception as e:
        return {"error": str(e)}, False

def main():
    db_path = os.environ.get("DUCKCLAW_QUANT_SCRIPT_DB")
    con = duckdb.connect(db_path, read_only=False)

    # 2. Leer señales PENDING_HITL (Filtrando NaNs y duplicados por ticker)
    # Solo tomamos la ÚLTIMA señal de cada ticker para no sobre-operar
    query = """
        SELECT signal_id, ticker, action, order_qty, rationale 
        FROM quant_core.trade_signals 
        WHERE status = 'PENDING_HITL' 
          AND order_qty IS NOT NULL 
          AND order_qty > 0
        ORDER BY updated_at DESC
    """
    try:
        pending = con.execute(query).df()
    except Exception as e:
        print(f"❌ Error DB: {e}")
        return

    if pending.empty:
        print("✅ No hay señales válidas para ejecutar.")
        return

    # Limpieza: Solo la más reciente por ticker
    pending = pending.drop_duplicates(subset=['ticker'])

    print(f"\n🚀 SEÑALES FILTRADAS PARA EJECUCIÓN ({len(pending)}):")
    print(pending[['ticker', 'action', 'order_qty', 'rationale']])
    
    confirm = input("\n¿Ejecutar estas órdenes ÚNICAS en IBKR? (s/n): ").lower()
    
    if confirm == 's':
        for _, row in pending.iterrows():
            print(f"执行 {row['action']} {row['order_qty']} {row['ticker']}...")
            res, success = execute_order_at_broker(row['ticker'], row['action'], row['order_qty'], row['signal_id'])
            
            if success:
                con.execute("UPDATE quant_core.trade_signals SET status = 'EXECUTED', updated_at = now() WHERE signal_id = ?", (row['signal_id'],))
                print(f"   ✅ Éxito.")
            else:
                print(f"   ❌ Fallo: {res.get('error')}")
    
    # Limpiar las señales viejas que no vamos a usar para que no estorben
    con.execute("UPDATE quant_core.trade_signals SET status = 'CANCELLED' WHERE status = 'PENDING_HITL'")
    print("\n🧹 Ledger limpiado (señales restantes marcadas como CANCELLED).")
    con.close()

if __name__ == "__main__":
    main()