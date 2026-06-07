# Guía de pruebas — Catálogo DB-first

Verifica que todo funciona sin `forge/templates/` (workers cargados desde BD).

---

## 1. Preparación

```bash
# 1. Limpiar caché anterior (por si acaso)
rm -rf ~/.duckclaw/.catalog_cache

# 2. Iniciar Redis (si no está corriendo)
redis-cli ping || docker run -d --name duckclaw-redis -p 6379:6379 redis:7-alpine

# 3. Iniciar gateway (sin PM2)
uv run duckops serve --gateway

# 4. En otra terminal, iniciar admin UI
cd apps/duckclaw-admin
pnpm install
pnpm dev
```

---

## 2. Bootstrap — Seed automático

El gateway arranca y hace `seed_catalog_if_empty()`:

**Verificar en logs del gateway:**
```
catalog: templates importados desde filesystem
```

**Verificar en BD:**
```bash
uv run python -c "
from duckclaw.graphs.graph_server import get_db
from duckclaw.catalog_worker import list_catalog_template_ids
ids = list_catalog_template_ids(get_db())
print(f'Templates en catálogo: {ids}')
print(f'Total: {len(ids)}')
"
```

Debe mostrar 10 templates: `default, finanz, bi-analyst, job-hunter, manager, pqrsd-assistant, quant-trader, research_worker, siata-analyst, support`

---

## 3. Admin UI — Login

1. Abrir `http://localhost:3000/login`
2. Email: `admin@duckclaw.local` (o el que configuraste en `.env`)
3. Password: el que configuraste en `.env`
4. Click **Sign in**

**Esperado:** Dashboard con health checks: Gateway ✅, Redis ✅, DuckDB ✅

---

## 4. Workers — Listado y creación

### 4.1 Workers desde catálogo

1. Sidebar → **Workers**
2. Deberías ver la lista: `default`, `finanz`, `BI-Analyst`, `Quant-Trader`, etc.

### 4.2 Crear worker desde catálogo

1. Click **+ New Worker**
2. Worker ID: `mi-worker-test`
3. Display name: `Mi Worker de Prueba`
4. Source: `runtime` (creado desde UI, no importado)
5. Click **Save**

**Esperado:** Worker creado en `admin_worker_catalog` con `source_kind=runtime`

### 4.3 Playground — Probar worker

1. Sidebar → **Playground**
2. Seleccionar worker: `default`
3. Escribir: `Hola, ¿qué tablas tienes disponibles?`
4. Click **Send**

**Esperado:** El worker responde listando tablas de `agent_worker` schema.

---

## 5. Proyectos — Creación y workers

### 5.1 Crear proyecto

1. Sidebar → **Projects** → **+ New Project**
2. Project name: `Proyecto Prueba`
3. Descripción: `Test de migración DB-first`
4. Click **Create**

### 5.2 Agregar workers al proyecto

1. En el proyecto, click **+ Add Worker**
2. Seleccionar `finanz` del catálogo
3. Click **Add**

### 5.3 Editar contexto del worker

1. Click en el worker `finanz` dentro del proyecto
2. Tab **Contexts**
3. Click **+ Add Context**
4. Title: `Instrucciones adicionales`
5. Content: `Solo consulta cuentas en COP.`
6. Click **Save**

---

## 6. Skills — Verificación

### 6.1 Skills vienen del catálogo

Cuando un worker se carga desde el catálogo, las skills `skills/*.py` se extraen al caché:

```bash
ls ~/.duckclaw/.catalog_cache/
```

Cada carpeta `<worker_uid>_<hash>` contiene todos los archivos del template.

### 6.2 Verificar skills en runtime

En Playground, seleccionar `finanz` y preguntar:

```
¿Qué herramientas tienes disponibles?
```

**Esperado:** Debe listar `insert_transaction`, `get_monthly_summary`, `read_sql`, etc. — las skills se cargaron desde el caché del catálogo.

---

## 7. Workers sin filesystem — Prueba de aislamiento

### 7.1 Verificar que NO se usa forge/templates/

```bash
# forge/templates/ YA NO EXISTE
ls packages/agents/src/duckclaw/forge/templates/
# Output: "No such file or directory"
```

### 7.2 Cargar worker desde catálogo exclusivamente

```bash
uv run python -c "
from duckclaw.graphs.graph_server import get_db
from duckclaw.catalog_worker import load_manifest_from_catalog

db = get_db()
spec = load_manifest_from_catalog(db, 'finanz', tenant_id='default')
print(f'Worker: {spec.worker_id}')
print(f'Schema: {spec.schema_name}')
print(f'Dir: {spec.worker_dir}')
print(f'Skills: {spec.skills_list}')
print('Cargado desde catálogo: OK')
"
```

### 7.3 Probar que default worker funciona sin BD también

```bash
uv run python -c "
from duckclaw.workers.manifest import load_manifest

# Sin db=... usa el seed filesystem (forge/seed/default/)
spec = load_manifest('default')
print(f'Worker: {spec.worker_id}')
print(f'Desde seed: {spec.worker_dir}')
print('OK')
"
```

---

## 8. DuckOps CLI

### 8.1 Listar workers

```bash
uv run python -c "
from duckclaw.graphs.graph_server import get_db
from duckclaw.workers.template_registry import list_template_ids
ids = list_template_ids(db=get_db())
print(f'Workers disponibles: {ids}')
"
```

### 8.2 Wizard init (simular fresh install)

```bash
# crear BD temporal
uv run python -c "
import duckdb, tempfile
from pathlib import Path
from duckclaw.admin_worker_catalog import ensure_admin_worker_catalog_schema
from duckclaw.catalog_seed import seed_catalog_if_empty

tmp = Path(tempfile.mkdtemp())
db = duckdb.connect(str(tmp / 'test.duckdb'))
ensure_admin_worker_catalog_schema(db)
seeded = seed_catalog_if_empty(db)
print(f'Seed needed: {seeded} (debe ser True)')

# segunda llamada no hace nada (idempotente)
seeded2 = seed_catalog_if_empty(db)
print(f'Seed needed again: {seeded2} (debe ser False)')
print('Idempotencia: OK')
"
```

---

## 9. Smoke test completo

```bash
uv run python -c "
import sys
from pathlib import Path

# 1. Conectar a gateway
from duckclaw.graphs.graph_server import get_db
db = get_db()

# 2. Listar catálogo
from duckclaw.catalog_worker import list_catalog_template_ids
ids = list_catalog_template_ids(db)
print(f'1. Catálogo: {len(ids)} workers')

# 3. Cargar cada worker desde catálogo
from duckclaw.catalog_worker import load_manifest_from_catalog
for wid in ids:
    try:
        spec = load_manifest_from_catalog(db, wid)
        cache_dir = Path(spec.worker_dir)
        files = list(cache_dir.iterdir())
        print(f'2. {wid}: {len(files)} archivos en caché')
    except Exception as e:
        print(f'   {wid} ERROR: {e}')
        sys.exit(1)

# 4. Verificar que seed/default también funciona
from duckclaw.workers.manifest import load_manifest
spec = load_manifest('default')
print(f'3. Seed default: {spec.schema_name}')

print('\\nTODO OK')
"
```

---

## 10. Rollback (si algo falla)

Si algún worker no carga, el gateway intenta catálogo primero y cae a filesystem seed. Si el seed tampoco existe, el error es claro:

```
FileNotFoundError: Worker template not found: .../forge/seed/<worker_id>
```

Para restaurar el seed de `default`:
```bash
# ya está en forge/seed/default/ — si se borró, restaurar:
git checkout HEAD -- packages/agents/src/duckclaw/forge/seed/default/
```
