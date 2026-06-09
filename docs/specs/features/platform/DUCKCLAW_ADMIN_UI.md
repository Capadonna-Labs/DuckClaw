# DuckClaw Admin UI

Spec normativa (SDD) de la consola `apps/duckclaw-admin`: login, bootstrap del gateway, playground de chat y superficies operativas.

## Bootstrap público (pre-login)

La pantalla de login consulta el estado del gateway **sin** credenciales de admin. El contrato es:

| Método | Ruta | Auth | Descripción |
|--------|------|------|-------------|
| GET /bootstrap/status | — | Ninguna (proxy Next → `resolveAdminBootstrapStatus`) | Salud del gateway, PM2 y si el login puede intentarse |

Respuesta (`AdminBootstrapStatus`):

- `canAttemptLogin` — `true` solo si el gateway responde y la clave admin es válida o aún no se ha comprobado por falta de config local.
- `code` — `ready` \| `gateway_unconfigured` \| `gateway_unreachable` \| `admin_key_missing` \| `admin_key_invalid`
- `pm2Status` — estado de `DuckClaw-Gateway` vía `pm2 jlist` (`online`, `missing`, `stopped`, `errored`, `unknown`).
- `recoveryCommand` — comando sugerido para levantar el stack (p. ej. `pnpm stack:up`).

Implementación:

- `apps/duckclaw-admin/src/lib/adminBootstrapStatus.ts` — `gatewayBase()`, probes a `/health` y `/api/v1/admin/health`.
- `apps/duckclaw-admin/src/app/api/admin/bootstrap/status/route.ts` — **no** usa `requireAdminRouteAuth` ni `DUCKCLAW_ADMIN_API_KEY` en el handler; solo reenvía el diagnóstico público.

La UI de login deshabilita el submit cuando `bootstrap.canAttemptLogin` es `false` y muestra `BootstrapStatusBanner` con mensajes de gateway caído o arrancando.

## Playground / chat

- Composer con texto, adjuntos de imagen y notas de voz vía `MediaAttachMenu`.
- **Voz automática (TTS):** apagada por defecto. Solo se puede activar si `GET /playground/config` devuelve `voice.available=true` (sensory node configurado y `tts_loaded`). Sin TTS activo, ni mensajes de texto ni notas de voz solicitan síntesis de respuesta.
- Notas de voz: `useVoiceNoteRecorder` + `sendVoiceNote` en `useAdminChat`; reproducción TTS en `ChatBubble` (`Escuchar respuesta`) cuando voz automática está ON y sensory responde.

## Referencias

- `apps/duckclaw-admin/docs/architecture.md` — mapa de rutas BFF.
- `ADMIN_RUNTIME_SETTINGS.md` — settings DB-first post-login.
