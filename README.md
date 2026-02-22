# DuckClaw

High-performance C++ analytical memory layer for sovereign AI agents. Powered by [DuckDB](https://duckdb.org/), optimized for Apple Silicon (M4), and designed for high-precision structural memory in agentic workflows.

## Features

- **Native DuckDB**: Full SQL in-process, no external server
- **Python bindings**: Simple API via pybind11 (`execute`, `query`, `get_version`)
- **Structured results**: Queries return list-of-dicts (JSON-like) for easy integration
- **File or in-memory**: Use a path for persistence or `:memory:` for ephemeral DBs

## Installation

From the project root:

```bash
uv pip install -e .
# or
pip install -e .
```

**Requirements**: Python ≥3.9, CMake ≥3.18, C++17 toolchain, pybind11. DuckDB is bundled via the build.

## Development workflow

```bash
# 1) Create/install editable package
uv pip install -e .

# 2) Run quick local test
uv run python tests/test_duckclaw.py
```

If import errors appear, reinstall with `uv pip install -e .` and run the test again.

## Quick start

```python
import duckclaw

# Persisted database (file) or ":memory:" for in-memory
db = duckclaw.DuckClaw("my_db.duckdb")

# DDL and DML
db.execute("CREATE TABLE IF NOT EXISTS test (id INTEGER, name TEXT)")
db.execute("INSERT INTO test VALUES (1, 'Slayer-8B'), (2, 'Navigator-3B')")

# Query returns list of dicts
result = db.query("SELECT * FROM test")
print(db.get_version())  # e.g. v0.0.1
print(result)             # [{'id': '1', 'name': 'Slayer-8B'}, {'id': '2', 'name': 'Navigator-3B'}]
```

**Example output:**

```
Versión de DuckDB: v0.0.1
Datos en DuckClaw: [{'id': '1', 'name': 'Slayer-8B'}, {'id': '2', 'name': 'Navigator-3B'}]
```

## API

| Method | Description |
|--------|-------------|
| `DuckClaw(path)` | Opens a DB at `path`; use `":memory:"` for in-memory. |
| `execute(sql)` | Runs a statement with no result (CREATE, INSERT, UPDATE, etc.). |
| `query(sql)` | Runs a SELECT and returns `list[dict[str, str]]`. |
| `get_version()` | Returns the DuckDB version string. |

## License

MIT
