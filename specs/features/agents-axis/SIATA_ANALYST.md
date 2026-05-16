# Trabajador Virtual — SIATA Analyst (Geo-Spatial & Weather)

## 1. Objetivo
Implementar un agente científico especializado en datos meteorológicos, calidad del aire y geolocalización del Valle de Aburrá. Este agente tendrá permisos de red explícitos para consumir la API pública del SIATA en tiempo real mediante DuckDB (`httpfs`) y procesar los JSONs en el Strix Sandbox para generar mapas o gráficas ambientales.

## 2. Perfil de Seguridad (Aislamiento)
- **Red:** `network_access: true` (A diferencia del BI Analyst, este contenedor sí tiene salida a internet).
- **Datos Internos:** Acceso de lectura restringido. No necesita ver `leila_orders` a menos que el `Manager` le pase un dataset específico para cruzar variables (ej. Clima vs Ventas).
- **Mutación:** Estrictamente bloqueada.

## 3. Fuentes de Datos (SIATA API)
El agente debe conocer los endpoints clave del SIATA para no tener que adivinarlos.

- **Radar (HTTPS, listado público):** skill `scrape_siata_radar_realtime`: GET `https://siata.gov.co/data/radar/`, regex de carpetas `YYYYMMDD` (y recorrido de subcarpetas de producto cuando no hay fechas en la raíz), segunda petición al día más reciente (prioriza hoy en America/Bogota), elección del último archivo por patrón de nombre (`_YYYYMMDD_HHMM_`), devuelve `url` directa y `extracted_timestamp` legible; `requests`, timeout 10s, errores controlados.
- **Series EntregaData1 (HTTPS):** lectura vía DuckDB `read_sql` + `read_json_auto` y `LIMIT`:
  - Calidad del Aire (PM2.5): `https://siata.gov.co/EntregaData1/Datos_SIATA_Aire_pm25.json`
  - Nivel de Quebradas: `https://siata.gov.co/EntregaData1/Datos_SIATA_Nivel_Quebradas.json`
  - Lluvia/Pluviómetros: `https://siata.gov.co/EntregaData1/Datos_SIATA_Pluviometros.json`

## 4. Contratos del Manifiesto (`manifest.yaml`)

```yaml
name: siata_analyst
version: 1.0.0
type: sovereign_worker
metadata:
  domain: environmental_science
  description: "Especialista en meteorología y calidad del aire del Valle de Aburrá (SIATA)."

cognition:
  soul: ./soul.md
  system_prompt: ./system_prompt.md
  domain_closure: ./domain_closure.md

execution:
  engine: langgraph
  entrypoint: environmental_pipeline
  policies:
    timeout_ms: 45000 # Considerar latencia de red al llamar a la API del SIATA

skills:
  - name: scrape_siata_radar_realtime
    type: read_only
    description: "Scraping HTTPS /data/radar/; última carpeta y archivo con timestamp en nombre."
  - name: read_sql / run_sql
    type: read_only
    description: "DuckDB + httpfs para JSON EntregaData1."
  - name: run_sandbox
    type: sandbox_execution
    description: "Strix: procesa JSON ya obtenido (gráficos, pandas)."

memory:
  sql:
    required_schemas: [main] # Solo usa DuckDB como motor de cómputo en memoria
    extensions: [httpfs, json] # Extensiones críticas para leer APIs

security:
  sandbox: siata_policy.yaml
  network_access: true # ⚠️ Habilitado explícitamente para este worker
```