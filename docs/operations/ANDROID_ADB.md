# Android ADB — limitaciones operativas

La conexión ADB wireless **no es permanente**. No es “configurar una vez y olvidar”.

## Qué rompe la conexión

- Apagar **Depuración inalámbrica** en el teléfono
- Reiniciar el teléfono
- Cambiar de red Wi‑Fi (el puerto debug suele rotar al reactivar)
- Expiración del emparejamiento (Android puede revocar hosts no usados ~7 días)

## Síntomas en admin

- Pestaña **Dispositivos**: ADB offline, batería vacía
- MCP conector **android**: chip “ADB offline”, `has_auth=false`
- Worker con grant al conector **android**: sin tools `mcp_android_*` si ADB/MCP offline

## Reconexión manual

1. Teléfono → Depuración inalámbrica **ON**
2. Si hace falta: **Emparejar con código** (nuevo puerto + código 6 dígitos)
3. Anotar **IP:puerto debug** (pantalla principal, no el diálogo de pair)
4. `.env` del host: `ANDROID_ADB_DEBUG_PORT=<puerto>`
5. Admin MCP drawer → **Conectar ADB** o `POST ops/run` `android_adb_connect`
6. Verificar: `uv run python scripts/verify_android_mcp.py`

## Variables de entorno (ejemplo)

```bash
ANDROID_ADB_HOST=192.0.2.10          # IP Tailscale/LAN del teléfono (RFC5737 ejemplo)
ANDROID_ADB_DEBUG_PORT=5555        # puerto debug wireless (cambia al togglear depuración)
ANDROID_MCP_PORT=8080
ANDROID_MCP_COMMAND='...'          # comando PM2 Android-MCP
```

Pair one-time: `ANDROID_ADB_PAIR_PORT` + `ANDROID_ADB_PAIR_CODE` (solo emparejamiento inicial).
