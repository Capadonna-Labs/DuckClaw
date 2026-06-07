DUCKOPS — Guía rápida para nuevo usuario
========================================

# 1. Clonar e instalar

git clone <repo>
cd duckclaw
uv sync                           # Instalar dependencias Python
pnpm install                      # Solo si usas Admin UI (apps/duckclaw-admin)

# 2. Inicializar (crea .env, base de datos, seed del worker default)

uv run duckops init               # Wizard interactivo
# Durante el wizard se ejecuta automáticamente:
#   - seed_catalog_if_empty()  → importa worker "default" al catálogo DB
#   - Crea tablas del gateway (admin_worker_catalog, etc.)

# 3. Iniciar servicios

# Opción A: Desarrollo (sin PM2)
uv run duckops serve --gateway    # Gateway en :8000
pnpm admin:dev                    # Admin UI en :3000 (otra terminal)

# Opción B: Producción (con PM2)
uv run duckops serve --pm2 --gateway
pnpm admin:build && pnpm admin:start

# 4. Verificar estado

uv run duckops stack status
curl http://127.0.0.1:8000/health

# 5. Probar workers desde catálogo DB

uv run python -c "
from duckclaw.graphs.graph_server import get_db
from duckclaw.catalog_worker import list_catalog_template_ids
ids = list_catalog_template_ids(get_db())
print(f'Workers en catálogo: {ids}')
"

# 6. Crear workers desde Admin UI

# Abrir http://localhost:3000 → Login → Workers → + New Worker
# Los workers se crean en BD (admin_worker_catalog), NO en filesystem.

# 7. Comandos útiles

uv run duckops init --smoke       # Smoke test rápido
uv run duckops db bootstrap       # Crear esquemas iniciales
uv run duckops ingress telegram-register-webhooks  # Registrar webhooks Telegram
uv run python scripts/doctor.py   # Diagnóstico del sistema
uv run pytest tests/ -v -m "not integration"  # Tests unitarios

# 8. Notas importantes

# - Los workers se cargan desde BD (catálogo), no desde forge/templates/
# - forge/templates/ fue eliminado — los templates producto ya no existen
# - Solo "default" está pre-seed en el catálogo
# - Usa Admin UI o duckops catalog para crear tus workers
# - Cada usuario tiene su tenant_id (aislamiento multi-tenant)
# - Los skills de cada worker se extraen a ~/.duckclaw/.catalog_cache/
