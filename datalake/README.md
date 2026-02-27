# DataLake Olist (Parquet)

Esta carpeta contiene la exportación del dataset Olist en formato **Parquet** (una tabla por archivo), más `schema.sql` y `load.sql` para recargar en DuckDB.

## Contenido

- `*.parquet` — Tablas: órdenes, clientes, productos, vendedores, reviews, pagos, etc.
- `schema.sql` — Definición de tablas (CREATE TABLE).
- `load.sql` — Comandos COPY para cargar los Parquet en DuckDB.

## Cómo hablar con estos datos por Telegram (wizard)

Puedes consultar los Parquet en lenguaje natural desde Telegram usando el bot de DuckClaw y el wizard de configuración.

### 1. Crear una base DuckDB con los datos del datalake

Desde la **raíz del repo**:

```bash
# Crear DB y cargar esquema + datos (ajusta la ruta si no estás en la raíz)
cd /ruta/al/repo/duckclaw
duckdb olist_telegram.duckdb < datalake/schema.sql
duckdb olist_telegram.duckdb < datalake/load.sql
```

Si `load.sql` tiene rutas absolutas, edítalo y sustituye por la ruta de tu `datalake/` o genera uno nuevo desde Python:

```python
import duckclaw
db = duckclaw.DuckClaw("olist_telegram.duckdb")
db.execute(open("datalake/schema.sql").read())
# Cargar cada parquet (ruta relativa a donde ejecutas)
for name in ["olist_orders", "olist_customers", "olist_products", ...]:
    db.execute(f"COPY \"{name}\" FROM 'datalake/{name}.parquet' (FORMAT PARQUET)")
```

### 2. Configurar el bot con el wizard

```bash
./scripts/install_duckclaw.sh
```

En el wizard:

1. Indica tu **token de Telegram** (BotFather).
2. Elige modo **langgraph** (respuestas con LLM).
3. Elige **proveedor** (Groq, DeepSeek, OpenAI, MLX, etc.) y configura API key o URL si aplica.
4. Cuando pida **ruta de la base de datos**, usa la DB que tiene los datos del datalake, por ejemplo:
   - `olist_telegram.duckdb` (si está en la raíz del repo)
   - o la ruta absoluta: `/ruta/al/repo/duckclaw/olist_telegram.duckdb`

La configuración se guarda en `~/.config/duckclaw/wizard_config.json` (incluido `db_path`).

### 3. Arrancar el bot

```bash
export DUCKCLAW_DB_PATH="olist_telegram.duckdb"   # o la ruta que usaste en el wizard
python examples/telegram_bot.py
```

O si usas el bot principal que lee la config del wizard:

```bash
python -m duckclaw.agents.telegram_bot
```

### 4. Hablar con los datos en Telegram

Abre tu bot en Telegram y escribe en lenguaje natural, por ejemplo:

- *¿Cuántos pedidos hay?*
- *Top 5 categorías por ventas*
- *Clientes que más compran*
- *Dame un resumen de ventas*

El LLM interpreta la pregunta y ejecuta consultas sobre las tablas cargadas desde los Parquet del datalake.

## Requisitos

- DuckClaw instalado: `pip install -e ".[telegram]"` (o `.[groq]` / `.[langgraph]` según el proveedor).
- Token de Telegram (`TELEGRAM_BOT_TOKEN`).
- API key del proveedor LLM (Groq, DeepSeek, etc.) si usas modo langgraph.
