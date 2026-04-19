# Asistente PQRSD (Alcaldía de Medellín)

## Objetivo

Proveer un worker Forge que **orienta** al ciudadano sobre el uso del portal de **Peticiones, Quejas, Reclamos, Sugerencias y Denuncias (PQRSD)** y la **correspondencia** ante la Alcaldía de Medellín, usando información obtenida mediante herramientas de lectura (HTTP acotado y búsqueda Tavily), alineada con el portal oficial.

### Interacción Telegram (system prompt)

El `system_prompt` del template prioriza **mensajes cortos** (orientación máxima ~**6 líneas** por turno), tono conversacional, **consentimiento Ley 1581 antes** de pedir los cuatro datos (nombre, cédula, dirección, correo), **relato mínimo de hechos** del caso antes del mensaje de confirmación para registrar (no rellenar “Tema” con la definición genérica del portal ni inventar contexto), **clasificación interna** del tipo PQRSD sin preguntar “¿petición o queja?” **solo cuando ya hay hechos**, confirmación explícita antes de persistir y cierre **sin números de radicado inventados**. Tras un **INSERT** exitoso en `radicacion_crm` o respuesta exitosa de `pqrsd_registrar_radicacion_crm`, el mensaje al ciudadano **debe incluir obligatoriamente** el radicado interno real (`Radicado interno: MDE-…`) devuelto por la tool o insertado en SQL. Herramientas nombradas en el prompt: `pqrsd_fetch_canonical`, `pqrsd_entity_routing`, `tavily_search`, `read_sql`, `admin_sql` (el gateway puede seguir exponiendo skills adicionales de perfil/CRM/sandbox según el manifest).

## Alcance

- Explicar conceptos (PQRSD vs correspondencia), plazos orientativos publicados por la entidad, enlaces oficiales y desvío a otras entidades cuando el tema **no** es competencia de la Alcaldía.
- **Interacción con la página (sandbox):** con `/sandbox on`, el worker puede usar **`run_browser_sandbox`** (Playwright en imagen Strix) para navegar y extraer texto del portal **oficial** (`medellin.gov.co`), según `security_policy.yaml` del template. **No** se usa el nodo **mercenario** (Caged Beast / stub) del Manager para este flujo: el Manager debe delegar al worker PQRSD-Assistant.
- **HITL (human-in-the-loop):** la verificación por **correo** (código OTP) y, cuando el portal lo exija, la lectura del mensaje institucional siguen siendo responsabilidad del ciudadano en el navegador o en su cliente de correo. El asistente **no** solicita el OTP en el chat para automatizar su ingreso en el portal.
- **Automatización opcional (solo con consentimiento):** si el usuario pide explícitamente completar el **primer paso** de identificación en el sandbox y **consiente** que los datos que él mismo proporciona en el chat se escriban **solo** en el navegador del sandbox (sesión efímera), el worker puede invocar la herramienta dedicada **`pqrsd_run_identificacion_step1`**, que ejecuta un script Playwright versionado en el repo (no código inventado por el modelo). El resultado útil es el estado de la página y la URL en noVNC.
- **Perfil para radicar (bóveda DuckDB, opcional):** si el usuario **consiente explícitamente** guardar en la bóveda del tenant los datos mínimos para reutilizarlos al radicar (modo identificada/anónima, documento si aplica, correo), el worker debe **persistir y verificar** en la misma DuckDB (`DUCKCLAW_PQRSD_ASSISTANT_DB_PATH`, tabla `pqrsd_assistant.radicacion_perfil`) **antes** de priorizar tutoriales al portal o automatización sandbox: **`admin_sql`** + **`read_sql`**, o **`pqrsd_upsert_radicacion_perfil`** + **`read_sql`**. Con manifest `read_only: false`, las escrituras de perfil/CRM vía skills usan el **mismo handle RW del gateway** (`db.execute`) para evitar lock con el proceso **db-writer** mientras el archivo está abierto en el proceso del gateway. No sustituye el portal ni el OTP; sirve para no volver a pedir cédula/correo en la misma sesión de chat cuando proceda.
- **CRM interno (radicado simulado):** con consentimiento y datos del relato, el worker puede registrar filas en **`pqrsd_assistant.radicacion_crm`** mediante **`pqrsd_registrar_radicacion_crm`**, generando un identificador interno **`MDE-YYYYMMDD-NNNN`**. Es trazabilidad en bóveda / asistente; **no** reemplaza el radicado oficial del portal web. El manifest puede declarar **`read_only: false`** para exponer **`read_sql`** / **`admin_sql`** acotados a las tablas permitidas (`allowed_tables`), además de las herramientas estructuradas de perfil y CRM.
- **Fuera de alcance:** radicación **completa** sin intervención humana (p. ej. firma, OTP desde Telegram hacia el portal); sustituir la respuesta oficial de la Alcaldía; asesoría jurídica definitiva (solo orientación basada en fuentes citadas).

## Herramientas

| Herramienta | Rol |
|-------------|-----|
| `pqrsd_fetch_canonical` | GET HTTPS a URLs canónicas permitidas (`medellin.gov.co`, `sigesh.medellin.gov.co`), texto legible truncado para el contexto del modelo. |
| `pqrsd_entity_routing` | Devuelve JSON estático con temas frecuentes y entidad sugerida (tabla de desvío, versionada con el template). |
| `tavily_search` | Búsqueda web (requiere `TAVILY_API_KEY`); en este worker el skill `research` pasa `include_domains` a Tavily para limitar resultados al host `medellin.gov.co`. |
| `pqrsd_run_identificacion_step1` | (Con `/sandbox on` y consentimiento) ejecuta en el sandbox el flujo Playwright hacia el formulario de identificación: elección PQRSD identificada vs anónima, relleno de campos acordados y clic en solicitar verificación por correo. |
| `pqrsd_upsert_radicacion_perfil` | Con **consentimiento explícito** para guardar en la bóveda, hace upsert de datos mínimos para radicar (vinculados al chat de Telegram) en `pqrsd_assistant.radicacion_perfil`. |
| `pqrsd_registrar_radicacion_crm` | Con consentimiento, inserta un caso en `pqrsd_assistant.radicacion_crm` con radicado interno `MDE-YYYYMMDD-NNNN` (no sustituye el portal oficial). |
| `read_sql` / `admin_sql` | Si el manifest permite escritura (`read_only: false`), SQL acotado a `allowed_tables` del worker. |

## Dominios y red

- **Saliente:** el worker declara `network_access: true` en el manifest.
- **Fetch directo:** solo hosts en lista blanca explícita en el skill (evita SSRF).

## Criterios de aceptación

1. Existe el template `PQRSD-Assistant` con `manifest.yaml`, cognición (`soul`, `system_prompt`, `domain_closure`) y `schema.sql` mínimo.
2. El skill `pqrsd_portal_fetch.py` registra las tools anteriores y respeta allowlist de hosts.
3. Tests unitarios con HTTP mockeado validan allowlist y respuesta estable ante página conocida.
4. Preguntas sobre **plazos / tiempos de respuesta** del canal PQRSD deben priorizar **`pqrsd_fetch_canonical(pqrsd_home)`** antes que búsqueda genérica web, para alinear la respuesta con la tabla publicada en el portal oficial.
5. En el **gateway**, el worker puede **forzar** la primera invocación de herramienta a **`pqrsd_fetch_canonical`** en turnos sustantivos (no saludos/agradecimientos), para reducir respuestas sin contexto del portal. **Excepción:** con sesión **sandbox** activa y mensaje que indique **radicación / llenado de formulario / automatización**, o con mensaje que indique **intención clara de presentar solicitud/PQRSD/denuncia por el canal Alcaldía** (p. ej. «quiero hacer una solicitud», «cómo interponer una denuncia»), puede **omitirse** ese forzado en ese turno para permitir que el modelo **pregunte datos y opcionalmente persista el perfil** con **`pqrsd_upsert_radicacion_perfil`** antes de **`pqrsd_fetch_canonical`**.
6. El template declara **`browser_sandbox: true`**, `security_policy.yaml` con hosts del portal, y el **Manager** no debe enrutar a **mercenario** cuando el worker asignado es **PQRSD-Assistant** (navegación = `run_browser_sandbox` / Playwright, no stub mercenario).
7. Ante solicitudes de **radicación paso a paso** o **ejecución en sandbox**, el asistente debe poder ofrecer: (a) **guía conversacional** alineada con la primera etapa del portal, o (b) con consentimiento explícito y **`pqrsd_run_identificacion_step1`**, automatizar ese primer paso hasta solicitar el envío del código al correo. No afirmar éxito si las tools muestran bloqueo o error de red; el usuario completa OTP y pasos posteriores en el portal o en VNC.
8. Existen pruebas unitarias del generador de script PQRSD y del contrato básico de la herramienta `pqrsd_run_identificacion_step1`.
9. Tras registro interno exitoso en `pqrsd_assistant.radicacion_crm`, la respuesta visible al usuario incluye el **radicado interno** (`MDE-YYYYMMDD-NNNN`) obtenido de la persistencia, no inventado.

## Referencias

- Portal PQRSD: `https://www.medellin.gov.co/es/pqrsd/`
- Spec de pipeline de investigación (Tavily): `specs/Pipeline_de_Investigación_y_Navegacion_Autonoma_(Tavily+Browser-Use).md` (si existe en el repo).
