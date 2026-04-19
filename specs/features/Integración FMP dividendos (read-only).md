# Integración FMP — dividendos (solo lectura)

## Objetivo

Exponer datos de dividendos vía [Financial Modeling Prep](https://financialmodelingprep.com) como herramientas LangGraph del worker **Quant-Trader**, sin persistencia ni órdenes.

## Variables de entorno

| Variable | Obligatoria | Descripción |
|----------|-------------|-------------|
| `FMP_API_KEY` | Sí (para usar las tools) | Clave API FMP. |
| `FMP_API_BASE` | No | Origen HTTP (default `https://financialmodelingprep.com`). |

**Seguridad:** no registrar la clave en logs, trazas LangSmith ni respuestas al usuario. En logs solo códigos HTTP, símbolo o rango de fechas (sin query completa con `apikey`).

## Herramientas

### 1. `get_fmp_stock_dividends`

- **HTTP:** `GET {FMP_API_BASE}/stable/dividends?symbol={SYMBOL}&apikey=***`
- **Args:** `symbol` (ticker, normalizado mayúsculas); `limit` opcional (1–80, default 40) — recorta tras ordenar por fecha de pago descendente.
- **Salida:** texto compacto (markdown/tabular) o mensaje de error legible.

### 2. `get_fmp_dividends_calendar`

- **HTTP:** `GET {FMP_API_BASE}/stable/dividends-calendar?from={YYYY-MM-DD}&to={YYYY-MM-DD}&apikey=***`
- **Args:** `from_date`, `to_date` (ISO); `limit` opcional (1–200, default 200).
- **Validación:** `from_date <= to_date`; ventana máxima **90 días** (si se excede, error claro sin llamar al API).
- **Salida:** texto compacto truncado al `limit` (orden cronológico por fecha de pago o `date` según campos disponibles).

## Errores

- Sin `FMP_API_KEY`: mensaje indicando configurar la variable.
- HTTP no 2xx: mensaje con status, sin cuerpo crudo extenso.
- JSON inválido o lista vacía inesperada: mensaje breve.

## Manifest

Skill compuesta `fmp: {}` en `manifest.yaml`; `enabled: false` desactiva el registro de ambas tools.

## Fuera de alcance

Otros endpoints FMP (earnings, splits, fundamentals) no forman parte de esta spec.
