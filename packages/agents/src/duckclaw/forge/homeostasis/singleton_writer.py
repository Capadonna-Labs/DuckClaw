"""Legacy facade for singleton writer queue helpers.

The implementation is owned by :mod:`duckclaw.db_write_queue`. Keep this
module as a temporary import-compatibility shim only.
"""

from __future__ import annotations

from duckclaw.db_write_queue import (
    WriteQueueBridge,
    _is_write_sql,
    enqueue_write,
    execute_write_direct,
    run_consumer,
)

__all__ = [
    "WriteQueueBridge",
    "_is_write_sql",
    "enqueue_write",
    "execute_write_direct",
    "run_consumer",
]


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--consume", action="store_true", help="Ejecutar consumidor de cola")
    parser.add_argument("--db-path", default=None, help="Ruta a DuckDB")
    args = parser.parse_args()
    if args.consume:
        run_consumer(db_path=args.db_path)
    else:
        print("Uso: python -m duckclaw.forge.homeostasis.singleton_writer --consume")
