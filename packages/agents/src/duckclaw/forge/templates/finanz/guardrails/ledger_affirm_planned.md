TAREA: Ejecutar las mutaciones ledger pendientes del mensaje assistant anterior usando **admin_sql** (INSERT/UPDATE/DELETE sobre tablas permitidas). No emitir otro resumen de deudas ni solo read_sql.

Pasos obligatorios:
1. Relee el plan del assistant previo (acciones concretas: montos, acreedores, meses).
2. Invoca **admin_sql** por cada mutación acordada hasta JSON de éxito.
3. Verifica con **read_sql** sobre las mismas tablas antes del mensaje final al usuario.
4. Responde en español con ✅ y cifras alineadas al último read_sql.

Contexto del assistant previo (si aplica):
{context}
