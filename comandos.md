DuckClaw — comandos habituales
Entorno (una vez o tras cambiar deps)
cd /Users/workstation/Developer/duckclaw
source .venv/bin/activate          # activa venv 3.12
uv sync --extra rag-docs           # monorepo + markitdown (PDF/Word)
uv sync                            # solo deps base, sin markitdown
Levantar stack
duckops configure                  # si es primera vez o cambiaste .env
duckops up                         # gateway + redis + servicios
duckops doctor --strict            # health check antes de probar
Admin (otra terminal)
cd apps/duckclaw-admin
npm run dev  