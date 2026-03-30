"""
Arranque de Uvicorn bajo PM2.

Al reiniciar (`pm2 restart`), el proceso recibe SIGINT; asyncio/anyio suelen emitir
KeyboardInterrupt con traza vía ``traceback.print_exception`` antes de que
``sys.excepthook`` pueda silenciarlo. Este módulo parchea impresión de trazas y hooks.
"""

from __future__ import annotations

import sys
import threading
import traceback


def main() -> None:
    _orig_tb_print = traceback.print_exception

    def _wrap_print(exc_type, value, tb, *args, **kwargs):  # type: ignore[no-untyped-def]
        if exc_type is KeyboardInterrupt or isinstance(value, KeyboardInterrupt):
            return
        return _orig_tb_print(exc_type, value, tb, *args, **kwargs)

    traceback.print_exception = _wrap_print  # type: ignore[assignment]

    prior_sys_hook = sys.excepthook

    def _sys_excepthook(exc_type, exc, tb):
        if exc_type is KeyboardInterrupt:
            sys.exit(0)
        prior_sys_hook(exc_type, exc, tb)

    sys.excepthook = _sys_excepthook

    prior_thread_hook = threading.excepthook

    def _thread_excepthook(args):  # type: ignore[no-untyped-def]
        if args.exc_type is KeyboardInterrupt:
            return
        prior_thread_hook(args)

    threading.excepthook = _thread_excepthook  # type: ignore[assignment]

    try:
        from uvicorn.main import main as uvicorn_main

        try:
            uvicorn_main()
        except KeyboardInterrupt:
            raise SystemExit(0) from None
    finally:
        sys.excepthook = prior_sys_hook
        threading.excepthook = prior_thread_hook  # type: ignore[assignment]
        traceback.print_exception = _orig_tb_print


if __name__ == "__main__":
    main()
