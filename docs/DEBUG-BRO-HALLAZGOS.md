# Debug temporal — setup del bro (Fedora / DuckClaw local)

> Documento temporal de hallazgos. Borrar cuando el bro tenga el stack estable.
> Fecha: 2026-05-31

## Síntomas reportados

| # | Síntoma | Pantalla |
|---|---------|----------|
| 1 | Selector de bóveda muestra `(sin bóvedas)` en playground/chat | Admin → DuckDB/Asistente |
| 2 | Tras subir `.md` en RAG, `/knowledge` muestra fuentes `ready` (1 doc · 38 chunks) | Admin → Agentes → RAG |
| 3 | DuckDB Explorer en `db/private/default/duckclaw.duckdb`: `admin_knowledge_sources` vacía | Admin → DuckDB |
| 4 | Agente responde que la tabla está vacía y no usa contexto del documento | Playground |
| 5 | (Previo) modelos OpenRouter `:free` no visibles en admin | Playground → Modelo |

---

## Causa raíz #1 — Hub vs bóveda (split de DuckDB)

**El RAG no vive en la misma DuckDB que consulta el agente por defecto.**

| Componente | DuckDB que abre | Variable / código |
|------------|-----------------|-------------------|
| Upload RAG (`/knowledge`) | **Hub** gateway | `get_gateway_db_path()` → `_enqueue_knowledge_command` |
| Listado RAG (`/knowledge/sources`) | **Hub** | `open_gateway_db()` |
| Inyección RAG en playground | **Hub** | `project_rag_context.py` → `open_gateway_db()` |
| Chat / SQL del agente | **Bóveda private** | `resolved_vault_for_admin_chat` → `db/private/{uid}/*.duckdb` |
| DuckDB Explorer (default) | **Bóveda private** | `resolve_actor_default_vault_path()` |

### Rutas por defecto si no se unifica `.env`

```
Hub (RAG escribe aquí):     db/duckclaw.duckdb
Bóveda (agente lee aquí):  db/private/default/duckclaw.duckdb
```

Migración `duckclaw-migrate` crea/migra el **hub**.  
`bootstrap_dbs.py --core-only` crea la **bóveda private** aparte.

**Resultado:** tablas `admin_knowledge_*` existen en ambos archivos (schema M015), pero **solo el hub tiene filas**. Por eso RAG UI dice `ready` y el agente dice `0 registros`.

### Código de referencia

- Escritura RAG: `services/api-gateway/routers/admin_domains/knowledge.py` (`db_path=get_gateway_db_path()`)
- Inventario RAG chat: `services/api-gateway/routers/admin_domains/playground/project_rag_context.py`
- Explorer bóveda: `services/api-gateway/routers/admin_domains/duckdb_explorer.py`
- Aviso en código: `packages/agents/src/duckclaw/forge/rag/context_provider.py` (`RAG_GUIDANCE_LINE`)

---

## Causa raíz #2 — `(sin bóvedas)` en selector

El selector **no lista el hub**. Solo escanea filesystem:

- `db/private/{vault_user_id}/*.duckdb`
- `db/shared/**/*.duckdb`

Si solo existe `db/duckclaw.duckdb` (hub suelto) y no hay `.duckdb` bajo `private/` o `shared/` → lista vacía → UI muestra `(sin bóvedas)`.

El `{vault_user_id}` resuelve desde:

1. `DUCKCLAW_OWNER_ID` / `DUCKCLAW_ADMIN_CHAT_ID`
2. Perfil admin → `telegram_user_id`
3. Fallback `"default"`

Si la bóveda está en `db/private/default/` pero `DUCKCLAW_OWNER_ID` apunta a otro uid → no aparece.

**Código:** `packages/shared/src/duckclaw/vaults.py` → `list_vault_options_for_user`

---

## Causa raiz #3 — Contexto RAG no llega al chat

Además del split hub/bóveda:

### a) Proyecto obligatorio en playground

RAG solo se inyecta si hay `project_context` (proyecto seleccionado en el selector del playground).

Sin `project_id` en el turno → no hay bloques `[RAG_SOURCE_INVENTORY]` / `[RAG_CONTEXT]`.

**Código:** `services/api-gateway/routers/admin_domains/playground/chat_turn.py`

### b) Dos proyectos “Instalación”

Captura: dropdown con **dos entradas** “Instalación” y dos fuentes RAG con `source_id` distintos.

Si el `.md` se subió al `project_id` A y el chat usa el `project_id` B (mismo nombre), el filtro por proyecto deja inventario/chunks vacíos en ese turno.

### c) Preguntar por nombre de tabla activa SQL en la bóveda

Mensajes como `admin_knowledge_sources` empujan al agente a usar herramientas SQL sobre la **bóveda operativa** (vacía), no sobre el hub RAG.

Política: `packages/agents/src/duckclaw/forge/rag/tool_policy.py` + `db_intent_policy.py`

---

## Problemas de entorno ya vistos (Fedora)

| Error | Causa | Fix |
|-------|-------|-----|
| `pm2: command not found` en `pnpm dev:local` | PM2 no instalado | `npm install -g pm2` o gateway manual: `uv run duckops serve --gateway` |
| `Redis ConnectionError :6379` | Redis apagado | `sudo dnf install redis && sudo systemctl enable --now redis` |
| Gateway: DB not found | Sin migrate | `uv run duckclaw-migrate` |
| `bootstrap_dbs.py` sin `--core-only` falla en `forge/templates` | Carpeta legacy eliminada | `uv run python scripts/bootstrap_dbs.py --core-only --only db/private/default/duckclaw.duckdb` |
| Warning migration 16 / `prompt_policy_registry` | Hub o bóveda sin migrar completa | `duckclaw-migrate` + bootstrap en todas las bóvedas usadas |
| Pydantic V1 + Python 3.14 | Ruido langchain | CI usa 3.12; no bloqueante |

---

## Diagnóstico rápido (copiar/pegar en el clone del bro)

```bash
cd ~/Documents/Projects/DuckClaw   # ajustar ruta real

# 1. Variables críticas
grep -E 'DUCKDB_PATH|DUCKCLAW_REPO_ROOT|DUCKCLAW_GATEWAY|DUCKCLAW_OWNER' .env

# 2. ¿Qué archivos DuckDB existen?
find db -name '*.duckdb' 2>/dev/null | sort

# 3. Conteo RAG en HUB vs BÓVEDA
uv run python - <<'PY'
from duckclaw.gateway_db import get_gateway_db_path
import duckdb
from pathlib import Path

hub = get_gateway_db_path()
vault = Path("db/private/default/duckclaw.duckdb")

def count(path, label):
    p = Path(path)
    if not p.is_file():
        print(f"{label}: NO EXISTE ({p})")
        return
    con = duckdb.connect(str(p), read_only=True)
    try:
        n = con.execute("SELECT count(*) FROM admin_knowledge_sources").fetchone()[0]
        c = con.execute("SELECT count(*) FROM admin_knowledge_chunks").fetchone()[0]
        print(f"{label}: {p}")
        print(f"  sources={n}  chunks={c}")
    except Exception as e:
        print(f"{label}: ERROR {e}")
    finally:
        con.close()

count(hub, "HUB")
count(vault, "VAULT private/default")
PY

# 4. Bóvedas visibles para el admin API (gateway en :8000)
curl -s -H "X-Admin-Key: $DUCKCLAW_ADMIN_API_KEY" \
  http://127.0.0.1:8000/api/v1/admin/runtime/vaults | python -m json.tool

# 5. db-writer vivo
pm2 status | grep -i db-writer
pm2 logs DuckClaw-DB-Writer --lines 30 --nostream
```

### Interpretación

| HUB sources > 0, VAULT sources = 0 | Split confirmado → unificar `DUCKDB_PATH` |
| Ambos = 0 | Upload falló o db-writer no aplicó comandos |
| Ambos > 0 | Split resuelto; revisar `project_id` en playground |

---

## Fix recomendado (orden)

### 1. Unificar hub y bóveda en `.env`

```bash
DUCKDB_PATH=db/private/default/duckclaw.duckdb
DUCKCLAW_REPO_ROOT=/home/bro/Documents/Projects/DuckClaw   # ruta absoluta real
DUCKCLAW_ADMIN_API_KEY=...
DUCKCLAW_GATEWAY_URL=http://127.0.0.1:8000
```

En `apps/duckclaw-admin/.env.local`:

```bash
DUCKCLAW_GATEWAY_URL=http://127.0.0.1:8000
DUCKCLAW_ADMIN_API_KEY=<misma clave que gateway>
```

### 2. Migrar y bootstrap la bóveda canónica

```bash
mkdir -p db/private/default
uv run duckclaw-migrate
uv run python scripts/bootstrap_dbs.py --core-only --only db/private/default/duckclaw.duckdb
```

### 3. Reiniciar stack

```bash
pm2 restart DuckClaw-Gateway DuckClaw-DB-Writer --update-env
# o dev:
pnpm dev:local
```

### 4. Re-subir RAG (o migrar datos del hub viejo)

Tras unificar rutas, volver a subir el `.md` en `/knowledge` con **proyecto Instalación seleccionado**.

Opcional: copiar tablas `admin_knowledge_*` del hub viejo (`db/duckclaw.duckdb`) a la bóveda unificada si no se quiere re-indexar.

### 5. Validar en playground

1. Selector **Proyecto** = Instalación (el `project_id` correcto, no el duplicado si hay dos).
2. Selector **Bóveda** = `[private] db/private/default/duckclaw.duckdb`.
3. Pregunta de contenido del doc (no el nombre de la tabla SQL).
4. En DuckDB Explorer → Run Query:

```sql
SELECT source_id, display_name, status FROM main.admin_knowledge_sources LIMIT 10;
```

Debe devolver filas en la **misma** ruta que muestra “BD DE SESIÓN”.

---

## Checklist de aceptación

- [ ] `find db -name '*.duckdb'` — una sola DuckDB operativa (o hub = vault path)
- [ ] `/runtime/vaults` lista al menos una bóveda (no `(sin bóvedas)`)
- [ ] `/knowledge` y DuckDB Explorer muestran mismos `source_id` / counts
- [ ] Playground con proyecto seleccionado recupera contexto del `.md`
- [ ] `pm2 status` — Gateway + DB-Writer online, Redis OK

---

## Notas OpenRouter (fix ya en branch)

Presets `:free` añadidos en `apps/duckclaw-admin/src/lib/llmModelPresets.ts`.  
En `.env`:

```bash
OPENROUTER_API_KEY=sk-or-...
DUCKCLAW_LLM_PROVIDER=openrouter
DUCKCLAW_LLM_BASE_URL=https://openrouter.ai/api/v1
DUCKCLAW_LLM_MODEL=openrouter/free
```

---

## Archivos clave del repo

| Tema | Archivo |
|------|---------|
| Vault selector | `packages/shared/src/duckclaw/vaults.py` |
| RAG writes | `services/api-gateway/routers/admin_domains/knowledge.py` |
| RAG en chat | `services/api-gateway/routers/admin_domains/playground/project_rag_context.py` |
| Hub path | `packages/shared/src/duckclaw/gateway_db.py` |
| Spec RAG | `docs/specs/features/platform/RAG_TRANSVERSAL_DB_FIRST.md` |
| Runbook | `docs/COMANDOS.md` |
| Hub vs vault UI | `docs/specs/features/platform/ADMIN_IDENTITY_RBAC_ERD.md` (§ DuckDB Explorer) |

---

## Borrar este archivo

Cuando el bro confirme stack OK:

```bash
rm DEBUG-BRO-HALLAZGOS.md
```
