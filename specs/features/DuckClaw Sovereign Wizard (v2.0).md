# DuckClaw Sovereign Wizard (v2.0)

**Objetivo:** Implementar una interfaz de configuración interactiva (TUI) que permita la navegación bidireccional, simplifique el lenguaje técnico y centralice la gestión de servicios (Redis, PM2, Docker, DuckDB) bajo un único flujo declarativo.

## 1. Arquitectura del Wizard (State Machine)
El Wizard dejará de ser un `input()` secuencial. Se implementará como una **Máquina de Estados** usando `prompt_toolkit` o `InquirerPy`.

*   **Navegación:** Cada paso es un `Step`. El usuario puede presionar `Esc` o `Left Arrow` para volver al paso anterior sin perder los datos ya ingresados en la sesión actual.
*   **Persistencia Temporal:** Los cambios se mantienen en un diccionario `draft_config` y solo se escriben a disco (`.env`, `manifest.yaml`, `docker-compose.yml`) al confirmar en la pantalla final de "Review".

## 2. UI/UX y Abstracción de Lenguaje (Human-Centric)
Se aplicará una capa de "Traducción de Dominio" para que los términos de infraestructura no oscurezcan el propósito del sistema.

| Término Técnico | Lenguaje Wizard (Soberano) | Descripción en UI |
| :--- | :--- | :--- |
| **Redis Host/Port** | **Canal de Comunicación** | "El motor que conecta los pensamientos del agente con la base de datos." |
| **DuckDB Path** | **Bóveda de Memoria** | "Ubicación física donde se guardará el conocimiento de tus agentes." |
| **Singleton Writer** | **Escribano de Estado** | "Servicio que garantiza que los datos no se corrompan al escribir." |
| **MCP Server** | **Puente de Integración** | "Permite que el agente hable con Telegram o use herramientas externas." |
| **KV Cache** | **Atención del Modelo** | "Memoria de corto plazo para que el agente no olvide la charla actual." |

## 3. Flujo Cognitivo del Wizard

1.  **Sovereignty Audit (Check inicial):** El Wizard detecta si corre en macOS (M-series), Linux o Docker.
2.  **Core Services:** Configuración de Redis y DuckDB (Auto-detecta si ya existen instancias).
3.  **Identity Setup:** Configuración del `Manager` y el primer `Worker` (Leila, BI, o SIATA).
4.  **Connectivity:** Configuración de túneles (Tailscale/Cloudflare) y tokens de Telegram.
5.  **Orchestration Choice:** ¿Cómo quieres correr DuckClaw? (`PM2` para local, `Docker` para aislamiento total).
6.  **Review & Deploy:** Resumen visual de la configuración y botón de "Ignition".

## 4. Contratos y Atajos (Hotkeys)

Se implementará un `KeyManager` global durante la ejecución del Wizard:

*   `Ctrl + Z`: **Undo/Back** (Vuelve al input anterior).
*   `Ctrl + S`: **Quick Save** (Guarda el progreso actual y sale).
*   `Ctrl + R`: **Service Test** (Prueba la conexión al servicio del paso actual, ej. testea Redis).
*   `Tab`: **Auto-fill** (Sugiere valores por defecto basados en el entorno).

## 5. Gestión de Servicios (The Universal Bridge)

El Wizard generará los artefactos de configuración dinámicamente:

*   **PM2:** Genera/Actualiza `ecosystem.config.js` con las variables de entorno correctas.
*   **Docker:** Genera un `docker-compose.override.yml` y un `.env` para el contenedor.
*   **Redis:** Si el usuario elige "Local Managed", el Wizard intenta levantar Redis vía `brew` o `apt` automáticamente.
*   **Strix Sandbox:** Configura las políticas YAML de acceso a carpetas según la ruta del proyecto.

## 6. Validaciones y Edge Cases

*   **Port Collision:** Si el puerto `8282` (Gateway) está ocupado, el Wizard sugiere el siguiente disponible.
*   **Permission Check:** Valida que el usuario tenga permisos de escritura en `db/private/` antes de avanzar.
*   **Secret Masking:** Los tokens de Telegram y API Keys nunca se muestran en texto plano tras ser ingresados.
*   **Rollback:** Si la escritura de un archivo de configuración falla, el Wizard restaura el backup `.bak` anterior.

## 7. Ejemplo de Interacción (Pseudo-UI)

```text
── DuckClaw Sovereign Wizard v2.0 ──────────────────────────────────────────
[ Paso 2 de 5: Bóveda de Memoria (DuckDB) ]

¿Dónde quieres que tus agentes guarden sus recuerdos?
> [ ] Carpeta local (Recomendado para Mac mini)
  [ ] Volumen Docker
  [ ] Base de datos remota (PostgreSQL Bridge)

Ruta: ./db/sovereign_memory.duckdb  (Ctrl+R para verificar permisos)

[← Back (Esc)]                                           [Next (Enter) →]
────────────────────────────────────────────────────────────────────────────
Atajos: Ctrl+S (Guardar todo) | Ctrl+C (Abortar) | Ctrl+H (Ayuda simple)
```