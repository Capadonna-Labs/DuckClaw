# Plantillas de configuración (`config/`)

| Archivo | Uso |
|---------|-----|
| `api_gateways_pm2.json.example` | Plantilla PM2 gateway (copiar a `api_gateways_pm2.json`, gitignored) |
| `ecosystem.api.config.cjs` | Generado: `uv run duckops serve --pm2 --gateway` o `sync_gateway_pm2_from_dotenv` |
| `ecosystem.db-writer.config.cjs` | PM2 DB-Writer (`env_file` → `.env`) |
| `ecosystem.mcp.config.cjs` | PM2 DuckClaw-MCP |
| `ecosystem.mlx-vision.config.cjs` | PM2 MLX-Vision (VLM) |
| `ecosystem.mlx.config.cjs` | PM2 MLX-Inference (texto, opcional) |
| `ecosystem.comfyui.config.cjs` | PM2 ComfyUI (`~/ComfyUI`, puerto 8188) |
| `ecosystem.spawn.config.cjs` | PM2 perfil Spawn (Gateway + Admin, sin DB-Writer) |
| `.env.spawn.example` | Plantilla `.env` day-zero VM genérica |
| `mcp_servers.yaml` | Servidores MCP |
| `langgraph.json` | LangGraph dev |
| `lora_config.yaml` | LoRA / train |
| `mypy.ini` | Tipado |

Secretos, rutas DuckDB, Redis, LLM y puertos: **solo** `.env` (raíz). Los ecosystem usan `env_file: path.join(root, ".env")`.
