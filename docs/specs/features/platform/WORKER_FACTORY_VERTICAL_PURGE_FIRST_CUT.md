# Worker Factory Vertical Purge - First Cut

Fecha: 2026-06-14

## Objetivo

Reducir la responsabilidad vertical de `packages/agents/src/duckclaw/workers/factory.py` sin hacer un refactor masivo del grafo de workers. El factory core debe construir el runtime transversal; las herramientas de broker, trading o ledger no deben registrarse desde ramas Python hardcodeadas en el factory.

## Corte Aplicado

- `factory.py` no registra bridges verticales IBKR, Quant Market, Quant Trade, Quant CFD ni Quant Trader.
- `factory.py` no importa `quant_trader_bridge` para inyectar prompt de sesión trading.
- Se elimina el helper lake/Finanz no usado del factory.
- Se elimina la reconciliación de egress Finanz importada desde `quant_market_bridge`.

## Supuestos

- Las capacidades transversales siguen siendo DB-first mediante runtime policies y helpers como `worker_has_runtime_capability`.
- Las herramientas verticales que aún deban existir deben cargarse fuera del factory core, por catálogo/capability/policy específica.
- La orquestación cuant determinista residual se mantiene temporalmente para preservar compatibilidad de tests existentes; debe salir en un corte posterior hacia un módulo de policy/capability o quedar deshabilitada.

## Guardrail

`tests/test_worker_factory_modular_boundaries.py::test_factory_does_not_register_broker_or_quant_vertical_bridges` bloquea reintroducir imports y registros directos de bridges verticales en el factory.

## Siguiente Corte

Extraer o eliminar del factory las ramas de ejecución determinista que todavía nombran `quant_trading`, `get_ibkr_portfolio`, `fetch_ib_gateway_ohlcv`, señales de trading y `finance_ledger`. Ese corte debe mover decisiones a runtime policy DB-first o deshabilitar comportamiento vertical sin defaults Python.
