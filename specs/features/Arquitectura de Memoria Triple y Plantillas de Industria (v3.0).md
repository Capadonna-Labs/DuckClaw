# Arquitectura de Memoria Triple y Plantillas de Industria (v3.0)

## 1. Objetivo Arquitectónico
Estandarizar el despliegue de DuckClaw mediante **Plantillas de Industria (Industry Templates)** que implementan una **Memoria Triple Unificada** en un único archivo DuckDB. Esta arquitectura fusiona el rigor transaccional de **SQL**, la inteligencia relacional de **PGQ (Grafos)** y la intuición semántica de **VSS (Vectores)**, permitiendo que los agentes operen sobre un sistema empresarial completo (ERP + CRM + Workflow) de forma soberana y escalable.

## 2. Estructura del Sistema de Plantillas (`The Forge`)

**Fuente de verdad del DDL:** el archivo `schema.sql` de cada plantilla (no mantener un segundo DDL solo en esta spec).

Ruta en el monorepo:

```text
packages/agents/src/duckclaw/forge/templates/industries/
└── business_standard/
    ├── schema.sql       # DDL triple canónico (SQL + duckpgq + VSS)
    ├── seed_data.sql    # Datos maestros iniciales
    └── manifest.yaml    # Metadatos, extensiones, defaults de agent_config
```

## 3. Diseño del Esquema Triple (DDL Business Standard)

Resumen conceptual; **sintaxis y políticas efectivas:** `business_standard/schema.sql`.

1. **SQL:** esquemas `core`, `rbac`, `org`, `flow`. Auditoría con `created_by` / `updated_by` donde aplica. Las FK entre esquemas y `ON DELETE CASCADE` dependen de la versión de DuckDB; el SQL del repo y sus comentarios son la referencia.
2. **Grafos:** extensión **`duckpgq`**, grafo de propiedad `enterprise_kg` (`VERTEX TABLES` / `EDGE TABLES`). No usar el ejemplo histórico `INSTALL pgq` de borradores antiguos.
3. **VSS:** extensión `vss` e índices HNSW sobre `*_embedding` cuando esté disponible.

## 4. Especificación de Skill: `UnifiedMemoryOrchestrator`

Este nodo en LangGraph decide qué capa de memoria consultar según la intención.

*   **Lógica de Decisión:**
    1.  **¿Es contable/exacto?** -> Ejecutar **SQL** (ej. "Saldos", "Conteo de usuarios").
    2.  **¿Es relacional/jerárquico?** -> Ejecutar **PGQ** (ej. "¿Quién aprueba esto?", "¿A qué equipo pertenece X?").
    3.  **¿Es conceptual/difuso?** -> Ejecutar **VSS** (ej. "Busca expertos en...", "Casos similares a...").
*   **Contrato:** El agente recibe un contexto unificado: `{"sql_data": [...], "graph_relations": [...], "semantic_matches": [...]}`.

## 5. Protocolo de Aprovisionamiento (`duckops init`)

El comando de inicialización automatiza la creación del entorno:

1.  **Tenant Isolation (Multi-Vault):** bóveda por defecto `db/private/{tenant_id}/default.duckdb` (misma ruta que `DUCKCLAW_DB_PATH` cuando se usa `--industry`; ver wizard).
2.  **Schema Injection:** Ejecuta el `schema.sql` de la plantilla seleccionada.
3.  **Master Data Seeding:** Carga `seed_data.sql` (ej. inserta los roles `admin`, `manager`, `viewer`).
4.  **Worker Activation:** Registra los agentes base en la tabla `main.agent_config`.

## 6. Garantías de Soberanía y Habeas Data (Colombia)

*   **Aislamiento Físico:** Cada empresa tiene su propio archivo DuckDB. No hay riesgo de cruce de datos a nivel de motor.
*   **Auditoría Nativa:** Las tablas de plantilla incluyen `created_by` y `updated_by` (referencia lógica a `core.profiles`; en DuckDB la forma exacta de FK la define el DDL en `schema.sql`).
*   **Derecho al Olvido:** Objetivo de diseño con `ON DELETE CASCADE` donde el motor lo permita; si una versión de DuckDB no soporta ciertas FK/CASCADE, la política debe aplicarse vía jobs o triggers documentados en el repo.

---

## 7. Nota de implementación (monorepo DuckClaw)

Alineación con el código y rutas reales:

| Tema | Implementación en repo |
| :--- | :--- |
| **Ruta de plantillas** | `packages/agents/src/duckclaw/forge/templates/industries/<id>/` (no `duckclaw/templates/industries/`). |
| **Extensión de grafos** | **duckpgq** (`INSTALL duckpgq FROM community;` / `LOAD duckpgq;`), no el nombre genérico `pgq` de documentación antigua. |
| **Aislamiento por tenant (Multi-Vault)** | Archivo `db/private/{tenant_id}/default.duckdb` (función `ensure_tenant_industry_db` en `duckclaw.vaults`). El `duckops init --industry <id>` exporta `DUCKCLAW_TENANT_ID` y `DUCKCLAW_INDUSTRY_TEMPLATE` al wizard, que aplica `schema.sql` + `seed_data.sql` y semillas en `main.agent_config`. |
| **Skill en LangGraph** | Herramienta `unified_memory` inyectada en `general_graph` si `DUCKCLAW_INDUSTRY_TEMPLATE` está definido o si `unified_memory` figura en `tools_spec`. El campo `skills` en `manifest.yaml` es documentación / contrato; **no** sustituye esa lógica de inyección (evitar duplicar fuentes de verdad). |