# Secret Settings

## Objetivo

Separar configuración operativa visible de secretos. Runtime Settings puede guardar provider, modelo y base URL; Secret Settings debe manejar API keys y tokens sin enviarlos al browser ni mostrarlos en texto plano.

## Alcance Inicial

Secretos LLM:

- `DEEPSEEK_API_KEY`
- `OPENAI_API_KEY`
- `GROQ_API_KEY`

Secretos de plataforma:

- `DUCKCLAW_ADMIN_API_KEY`
- tokens MCP externos
- webhooks firmados

## Regla DB-first

Los valores no secretos siguen en `main.admin_runtime_settings`:

- `llm.provider`
- `llm.model`
- `llm.base_url`

Los secretos no deben guardarse en `main.admin_runtime_settings` como texto visible. La primera implementación aceptable es:

- `.env` como backend bootstrap/fallback;
- BFF escribe/rota secretos solo desde servidor;
- UI muestra estado enmascarado (`configured`, `missing`, `updated_at`) y nunca el valor.

## API Propuesta

- `GET /secret-settings` — lista estado enmascarado por clave permitida.
- `PUT /secret-settings/{key}` — actualiza secreto permitido desde BFF, con auditoría.
- `DELETE /secret-settings/{key}` — elimina secreto permitido o lo marca como pendiente.

## Seguridad

- Allowlist estricta de claves.
- Requiere rol admin.
- Nunca retornar valores completos al cliente.
- Registrar auditoría con actor, clave, operación y timestamp, no valor.
- Reiniciar o recargar proveedores de inferencia de forma explícita tras rotación.

## UX

La pantalla debe mostrar:

- proveedor/model/base URL desde Runtime Settings;
- estado de API key enmascarado;
- botón “Actualizar secreto” con confirmación;
- advertencia de reinicio si el proveedor necesita recargar env.

## Relación con Platform Orchestrator

El orquestador puede detectar que falta una API key y sugerir abrir Secret Settings. No debe pedir ni almacenar secretos dentro del chat.
