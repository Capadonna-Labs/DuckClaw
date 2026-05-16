TAREA: JOB_OPPORTUNITY_TRACKING. Registra en finance_worker.job_opportunities la vacante o postulación del contexto siguiente. **No** uses tavily_search ni run_browser_sandbox salvo que no exista ninguna URL ni dato mínimo de oferta en el contexto. Usa read_sql/admin_sql: primero verifica columnas reales de finance_worker.job_opportunities y luego INSERT con apply_url (literal del mensaje si existe), title, company, location, status='applied' si el usuario indica que ya postuló, si no 'tracking'; applied_at=CURRENT_TIMESTAMP cuando aplique a aplicación ya hecha. **No asumas columnas opcionales** (ej. notes) si no existen en el esquema. Si INSERT falla por URL duplicada (índice único), lee la fila y haz UPDATE de columnas existentes.

--- Contexto ---
{context}
