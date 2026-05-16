Soy **Finanz** (finanzas personales + broker). Puedo:
• **Cuentas en DuckDB:** saldos por cuenta (Bancolombia, Nequi, efectivo…), resumen con **totales por moneda**, gastos, presupuestos y deudas.
• **IBKR:** consultar saldo y portafolio en vivo con la API del gateway cuando lo pidas (o en resúmenes amplios junto a tus cuentas locales).
• **Datos y cambios:** consultas `read_sql`, registro con las tools de finanzas, y actualizaciones de saldo vía `admin_sql` (cola db-writer).
• **Mercado / cuant:** OHLCV, CFD y contexto web cuando el manifest lo tenga activo.

Ejemplos: «Dame un resumen de mis cuentas», «¿Cuánto tengo en Nequi?», «Consulta el saldo de IBKR», «gastos del mes».
