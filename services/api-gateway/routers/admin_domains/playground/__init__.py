"""
Admin Playground — consola de prueba (chat, voz, config LLM/vault/worker).

Paquete explícito bajo ``admin_domains/playground/`` para no mezclar con otros dominios admin.
``playground_chat.py`` en el padre reexporta símbolos legacy para tests e imports existentes.
"""

from routers.admin_domains.playground.router import router

__all__ = ["router"]
