TAREA (Finanz — evidencia DuckDB, sin atajos narrativos):
1. **read_sql** obligatorio sobre las tablas necesarias (p. ej. finance_worker.deudas, transactions, presupuestos, cuentas) para ver el estado **actual**.
2. Si hay altas/bajas/cambios: **insert_deuda** / **insert_transaction** / **insert_presupuesto** / **insert_cuenta** y/o **admin_sql** hasta JSON de éxito; corrige SQL ante error.
3. **read_sql** de verificación antes del mensaje final; la respuesta al usuario usa **solo** filas del último read_sql.
**Prohibido:** listar deudas o totales solo desde memoria del chat; **prohibido** «reintentar sin herramientas».
