[DIRECTIVA_GITHUB_PR] Flujo obligatorio para abrir o completar un Pull Request en GitHub (repositorio DuckClaw):

1. **Repositorio**: usa `owner` y `repo` de las variables de entorno `GITHUB_OWNER` / `GITHUB_REPO` (o `DUCKCLAW_GITHUB_OWNER` / `DUCKCLAW_GITHUB_REPO`). Si no están definidas, infiere desde `git remote get-url origin` o usa `Capadonna-Labs` / `DuckClaw`.
2. **Rama**: respeta el nombre de rama que pida el usuario o el plan (p. ej. `fix/quant-hallucination-loop`). No reutilices ramas de features anteriores (`feat/cancel-trade-signal-tool`) salvo que el usuario lo pida explícitamente.
3. **Cambios**: si debes corregir código, edítalo en el sandbox/workspace primero (`run_sandbox` / búsqueda local), luego sube con `push_files` los archivos modificados. No propongas solo comandos shell de git si tienes `push_files` y `create_pull_request`.
4. **Secuencia MCP**: (opcional) `search_code` → `push_files` (owner, repo, branch, files, message) → `create_pull_request` (owner, repo, title, head=branch, base=main). Tras `push_files` exitoso, el siguiente paso **debe** ser `create_pull_request`.
5. **Prohibido en este turno**: bucles de `search_code` sin acción, `cancel_trade_signal`, repetir `/quant_cycle` con tickers inventados, o `--execute auto` si el plan pide desactivar auto-ejecución.
6. **Respuesta final**: incluye el enlace `html_url` del PR y un resumen breve de archivos tocados y del bug corregido.
