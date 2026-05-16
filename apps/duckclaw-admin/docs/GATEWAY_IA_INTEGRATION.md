# Integración del panel IA con DuckClaw (PQRSD-Assistant)

## Qué hace

El panel «Asistente IA» en el detalle de ticket llama a la ruta Next.js `POST /api/ia/regenerar`, que hace de **proxy** hacia el API Gateway de Duckclaw (p. ej. proceso PM2 **DuckClaw-Gateway**):

`POST {DUCKCLAW_GATEWAY_URL}/api/v1/agent/PQRSD-Assistant/chat`

El cuerpo sigue el contrato `ChatRequest` (mensaje compuesto con contexto del ticket + instrucción del funcionario, `tenant_id: PQRS`, `chat_id: crm-ticket-{idTicket}`).

### Ingesta de correos e `callAiModel`

El triaje de correos (`procesarCorreoConIA` en `src/services/iaTemplateService.ts`) usa el mismo endpoint vía **`callAiModel`** en `src/services/aiService.ts`: primero el gateway con `chat_id: crm-email-triage` y `user_id` derivado de `crm-email-ingesta`. Si el gateway no está configurado, la respuesta está vacía o falla la petición, se puede usar **OpenRouter** como respaldo si existe `OPENROUTER_API_KEY` y no se ha puesto `CRM_IA_OPENROUTER_FALLBACK=false`.

## Variables de entorno

| Variable | Uso |
|----------|-----|
| `DUCKCLAW_GATEWAY_URL` | Base del gateway (preferida en servidor). Ej: `http://127.0.0.1:8000` o URL Tailscale. |
| `NEXT_PUBLIC_DUCKCLAW_GATEWAY_URL` | Opcional; misma URL para que el cliente sepa que el panel puede mostrarse. |
| `NEXT_PUBLIC_API_URL` | Respaldo de la base URL (misma prioridad que en `gatewayBaseUrl()` en código). |
| `CRM_IA_OPENROUTER_FALLBACK` | `true` por defecto: si el gateway falla o no hay URL, usar OpenRouter cuando haya `OPENROUTER_API_KEY`. `false` para exigir solo gateway. |
| `NEXT_PUBLIC_IA_HABILITADA` | Debe ser `true` para mostrar el panel. |
| `DUCKCLAW_GATEWAY_USER_ID_OVERRIDE` | Solo desarrollo: fuerza el `user_id` hacia el gateway si los usuarios mock (`usr-001`, …) no están en la whitelist PQRS. |

## Autenticación en el gateway

Se envían `user_id` = `usuario.idUsuario` y `username` = `usuario.nombreCompleto` (Zustand). Ese par debe existir en la tabla de autorizados del gateway para el tenant **PQRS** (misma lógica que pruebas con `pqrs-interfaz-1`).

## Decisión de producto (riesgo de dominio)

El worker Forge **PQRSD-Assistant** en Duckclaw está pensado principalmente para **orientación al ciudadano** sobre el portal PQRSD. El CRM usa el mismo worker para **redactar respuestas institucionales** a partir del expediente.

**Mitigación aplicada:** el proxy antepondrá al mensaje un bloque explícito `[Modo: redacción de respuesta institucional CRM…]` con el contexto del ticket y la instrucción del funcionario.

**Recomendación:** si en producción se requiere comportamiento distinto (solo redacción, sin herramientas de portal), conviene un worker dedicado en Duckclaw y una entrada en `specs/` (SDD).

## Prueba local (antes de `git push`)

### 1. Arrancar el API Gateway de Duckclaw

En el repo **duckclaw**, con el mismo entorno que usas siempre (PM2, `uvicorn`, etc.), deja el gateway escuchando donde apuntará el CRM (por defecto `http://127.0.0.1:8000`).

Comprueba salud:

```bash
curl -sS http://127.0.0.1:8000/health
```

### 2. Configurar el CRM (Next.js)

En el repo del CRM (`retoPWRSomegahack`):

```bash
cp .env.example .env.local
```

Edita `.env.local` y asegura al menos:

- `DUCKCLAW_GATEWAY_URL=http://127.0.0.1:8000` (o tu host/puerto reales).
- `NEXT_PUBLIC_IA_HABILITADA=true`.

Si los usuarios mock (`usr-001`, etc.) **no** están en la whitelist del gateway para tenant **PQRS**, añade (solo desarrollo):

- `DUCKCLAW_GATEWAY_USER_ID_OVERRIDE=<user_id_que_sí_esté_autorizado>`

### 3. Levantar el frontend

```bash
npm install
npm run dev
```

Abre `http://localhost:3000`, inicia sesión (demo), entra a **un ticket**, despliega **Asistente IA**, escribe una instrucción (≥ 5 caracteres) y pulsa **Generar con IA**. El texto debe aparecer en el panel y copiarse al editor.

### 4. Probar el proxy sin navegador

Sustituye el JSON si tu `user_id` debe ser otro:

```bash
curl -sS -X POST http://localhost:3000/api/ia/regenerar \
  -H 'Content-Type: application/json' \
  -d '{
    "contenidoRaw": "Solicitud de prueba",
    "resumenIa": null,
    "respuestaActual": "",
    "instruccionFuncionario": "Redacta un párrafo de respuesta institucional breve.",
    "secretariaNombre": "Secretaría de Salud",
    "tipoSolicitud": "Peticion",
    "idTicket": "TK-001",
    "duckclawUserId": "usr-001",
    "duckclawUsername": "María Camila Restrepo"
  }'
```

Respuesta esperada: JSON con `{ "text": "..." }`. Si ves `403`/`401`, revisa whitelist u `DUCKCLAW_GATEWAY_USER_ID_OVERRIDE`.

### 5. Probar el gateway directo (misma lógica que el proxy)

```bash
curl -sS -X POST 'http://127.0.0.1:8000/api/v1/agent/PQRSD-Assistant/chat' \
  -H 'Content-Type: application/json' \
  -H 'X-Tenant-Id: PQRS' \
  -d '{
    "message": "Hola, necesito orientación para radicar una PQRSD.",
    "chat_id": "crm-test-local",
    "user_id": "TU_USER_WHITELIST",
    "username": "Test",
    "tenant_id": "PQRS",
    "chat_type": "private"
  }'
```

Debe devolver JSON con `"response": "..."` y en logs del gateway algo como `[PQRS:PQRSD-Assistant]` y la DB PQRSD correcta.

### Checklist antes del push

- [ ] `npm run build` pasa sin errores.
- [ ] Panel IA genera texto con gateway encendido.
- [ ] `.env.local` no se commitea (sigue en `.gitignore`); solo sube `.env.example` actualizado.
