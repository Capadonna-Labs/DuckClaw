# discord-mcp (Exil) en VPS / Mac

Empaqueta Exil Discord MCP en Docker con `network_mode: host` y Puerto **8010** para no chocar con Duckclaw Gateway (**8000**).

**Mac Mini — MCP nativo (`python -m discord_mcp.main`):** El proceso **`discord_mcp` en el puerto 8000 suele NO salir de tu `pm2 list`** (DuckClaw-Gateway sí); lo arranca casi siempre **Cursor** al cargar el servidor MCP desde **`~/.cursor/mcp.json`**. El archivo `config/ecosystem.discord-mcp.config.cjs` lo añadimos como **opción** si quieres MCP bajo PM2 en **8010** — **no** se inicia solo y **no sustituye** corregir Cursor.

Si Duckclaw escucha **8000** y Funnel usa **`http://127.0.0.1:8000`**, MCP **no** debe enlazar `127.0.0.1:8000` (intercepta loopback → Telegram ve 404 en texto plano). Opciones:

- **Si ya hay discord_mcp ocupando 127.0.0.1:8000:** desde la raíz del repo ejecuta **`bash scripts/telegram/stop_discord_mcp_port_8000.sh`** (solo mata ese caso) y **reinicia Cursor** si vuelve a subir el MCP en 8000.
- **Prevención:** en `~/.cursor/mcp.json`, para la entrada que lanza `-m discord_mcp.main`, fija **`"env": { "HOST": "127.0.0.1", "PORT": "8010" }`** (véase **`cursor.discord-mcp.mac.example.json`**). Reinicia Cursor o “Reload MCP”.
- `./infra/discord-mcp-exil/run-local-mac.sh` (manual, 127.0.0.1:8010) y Cursor en modo **`url`** contra `http://127.0.0.1:8010/mcp` si tu transport es HTTP.
- **Opcional PM2:** `DISCORD_MCP_PYTHON=/ruta/al/python pm2 start config/ecosystem.discord-mcp.config.cjs` — solo si quieres MCP fuera de Cursor.

**Discord:** MCP abre segunda sesión Gateway (`discord.py`). Si `capadonna-bot` usa el mismo Bot Token que envías por `Authorization`, fallará; crea segunda app Discord para MCPOps.

Despliegue remoto ejemplo:

```bash
./infra/discord-mcp-exil/sync-to-vps.sh capadonna@100.97.151.69
ssh capadonna@100.97.151.69 'cd ~/services/discord-mcp-exil && docker compose up -d --build'
```

Cursor `~/.cursor/mcp.json`: `http://100.97.151.69:8010/mcp` con `"Authorization": "<token_bot_MCP_ops>"`.
