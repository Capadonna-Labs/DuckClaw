# Finanz — presupuesto «disponible» en Telegram

## Comportamiento

Cuando el usuario registra un gasto o pide resumen mensual con presupuestos, la respuesta debe mostrar **cuánto queda del cupo** por categoría (`disponible` = presupuesto del mes − gasto del mes en esa categoría), **no** rotular el gasto ya incurrid como «acumulado» en la misma viñeta (eso confunde con el cupo restante).

## Implementación

- La tool `get_presupuesto_vs_real` expone columnas incluyendo **`disponible`** (mismo valor que presupuestado − gastado del mes).
- `system_prompt.md` (Finanz) y, si aplica, reglas de síntesis NL obligan a usar texto del tipo «Categoría disponible: …» cuando `presupuestado > 0`.

## Total de gastos del mes

La línea «Total gastos» del mes puede seguir mostrando la suma de gastos (p. ej. vía `get_monthly_summary`); solo cambia el criterio de la viñeta **por categoría con presupuesto**.
