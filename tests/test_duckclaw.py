import duckclaw

# Inicializar en memoria o archivo
db = duckclaw.DuckClaw("test.duckdb")

# Crear tabla
db.execute("CREATE TABLE IF NOT EXISTS test (id INTEGER, name TEXT)")
db.execute("INSERT INTO test VALUES (1, 'Slayer-8B'), (2, 'Navigator-3B')")

# Consultar
result = db.query("SELECT * FROM test")
print(f"Versión de DuckDB: {db.get_version()}")
print(f"Datos en DuckClaw: {result}")