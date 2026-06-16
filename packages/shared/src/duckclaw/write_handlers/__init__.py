"""Domain-scoped typed DuckDB write handlers.

Modules in this package expose pure handler functions. Callers own
transactions; handlers must not open DuckDB connections or commit/rollback.
"""

