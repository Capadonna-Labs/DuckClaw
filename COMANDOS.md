# COMANDOS — Despliegue rápido DuckClaw

Guía mínima para levantar el entorno desde la **raíz del repositorio** (`duckclaw/`).  
Para contexto y arquitectura, ver **[docs/Installation.md](docs/Installation.md)** (DuckOps Wizard, PM2, seguridad).

---

## 0. Prerrequisitos

- **Node / PM2** (opcional): solo si el wizard registra procesos con PM2.
- **uv**: gestor de dependencias Python del monorepo.
- **Docker** (opcional): forma más simple de correr Redis.

```bash
cd /ruta/al/repo/duckclaw
```

---

## 1. Redis

### Opción A — Docker (recomendada en dev)

```bash
docker run --name redis -d -p 6379:6379 redis
```

Comprobar que responde:

```bash
docker exec -it redis redis-cli ping
```

Debe devolver `PONG`.

Detener o borrar el contenedor cuando no lo necesites:

```bash
docker stop redis
docker rm redis
```

### Opción B — Redis instalado en el sistema

Si ya tienes `redis-server` en el PATH:

```bash
redis-server
```

(En otra terminal) verificación:

```bash
redis-cli ping
```

Variables típicas en `.env` (el wizard puede escribirlas):

```env
REDIS_URL=redis://localhost:6379/0
```

---

## 2. Dependencias Python del monorepo

```bash
uv sync
```

Con extra Telegram (bot por long polling), si lo necesitas:

```bash
uv sync --extra telegram
```

---

## 3. Wizard — aprovisionamiento interactivo

Inicializa `.env`, rutas de DuckDB, PM2/systemd según el flujo del proyecto:

```bash
uv run duckops init
```

Detalle de fases y seguridad: [docs/Installation.md](docs/Installation.md).

---

## 4. API Gateway (desarrollo)

Desde la raíz del repo:

```bash
uv run duckops serve --gateway
```

Equivalente orientativo (si prefieres llamar uvicorn a mano; ajusta host/puerto):

```bash
cd services/api-gateway
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Comprobación rápida:

```bash
curl -s http://127.0.0.1:8000/health
```

(Si usas `DUCKCLAW_TAILSCALE_AUTH_KEY`, añade la cabecera `X-Tailscale-Auth-Key` en las peticiones, salvo rutas públicas documentadas.)

---

## 5. DB Writer (si usas escrituras encoladas)

El wizard puede registrarlo en PM2. Arranque manual orientativo:

```bash
uv run python services/db-writer/main.py
```

---

## 6. Orden sugerido (resumen)

| Paso | Comando |
|------|---------|
| 1 | `docker run --name redis -d -p 6379:6379 redis` **o** `redis-server` |
| 2 | `redis-cli ping` → `PONG` |
| 3 | `uv sync` |
| 4 | `uv run duckops init` |
| 5 | `uv run duckops serve --gateway` |
| 6 | (Opcional) `uv run python services/db-writer/main.py` o PM2 según [Installation.md](docs/Installation.md) |

---

## 7. Cheat sheet del día a día

```bash
uv run duckops init              # Reconfigurar / instalar
uv run duckops serve --gateway    # Solo gateway en dev
pm2 status                        # Si usas PM2 tras el wizard
pm2 logs DuckClaw-DB-Writer      # Auditar escrituras
pm2 flush #Vaciado de cache
pm2 restart DuckClaw-Gateway --update-env # Reinicio Gateway 
```

Más comandos: sección **6. Guía Rápida de Operación** en [docs/Installation.md](docs/Installation.md).
