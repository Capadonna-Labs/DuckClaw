"""
Servidor MCP (streamable HTTP) que reutiliza los grafos ya operativos en DuckClaw.

- **invoke_manager_graph**: si el mensaje empieza por ``/``, ejecuta primero los **fly commands**
  del gateway (``handle_command`` sobre DuckDB RW); si no aplican, mismo pipeline que
  ``POST /invoke`` de :mod:`duckclaw.graphs.graph_server` (Manager + workers).
- **invoke_core_conversation_graph**: grafo ligero con Fly Commands ``/status`` y ``/balance``.
- **open_meteo_current_weather**: clima actual (°C + WMO) vía API pública Open-Meteo (para hosts que sí envían ``tools/call``).
- **list_graph_tools**: metadatos para descubrimiento (modelo activo, rutas REST relacionadas).

**Clientes MCP y Tailscale Funnel**

Los hosts MCP esperan una URL absoluta con path MCP, p. ej. ``https://<nodo>.ts.net/mcp``.
En local: ``http://127.0.0.1:8001/mcp``. Para clientes remotos llegue a tu máquina,
expón el **mismo puerto** donde corre este proceso con Funnel, p. ej.::

    tailscale funnel --bg --yes 8001

La URL pública que muestre ``tailscale funnel status`` + sufijo ``/mcp`` es la que debes
poner en ``mcp_connections.duckclaw.url``. Ver también ``specs/features/CONFIGURACION_TAILSCALE.md``.
Ver documentación Tailscale: ``specs/features/integrations/TAILSCALE_CONFIGURATION.md``.
"""

from __future__ import annotations

import json
import os
from typing import Any

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

_mcp_singleton: FastMCP | None = None


def _tool_result_text(*, headline: str, payload: dict[str, Any]) -> str:
    """
    Muchos hosts MCP suelen mostrar mejor contenido **texto plano** que solo dict anidados.
    Devolvemos un resumen en claro y el JSON completo debajo del separador.
    """
    body = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    return f"{headline.rstrip()}\n\n---\n{body}"


async def _root_probe(_request: Request) -> JSONResponse:
    """Evita 404 en la raíz cuando el Funnel expone el puerto (bots, health checks)."""
    return JSONResponse(
        {
            "service": "duckclaw-mcp",
            "mcp_streamable_http": "/mcp",
            "hint": "MCP: la URL del cliente.*.url debe terminar en /mcp",
        }
    )


def get_duckclaw_mcp() -> FastMCP:
    """Instancia singleton de FastMCP con herramientas registradas."""
    global _mcp_singleton
    if _mcp_singleton is None:
        _mcp_singleton = build_duckclaw_mcp()
    return _mcp_singleton


async def invoke_manager_graph_impl(
    message: str,
    chat_id: str = "mcp",
    tenant_id: str = "",
    history_json: str = "[]",
    username: str | None = None,
    user_id: str | None = None,
    vault_db_path: str | None = None,
) -> str:
    """
    Cuerpo de la herramienta MCP ``invoke_manager_graph`` (expuesto para tests).

    Ver docstring en :func:`build_duckclaw_mcp` / herramienta registrada.
    """
    from duckclaw.graphs.gateway_fly_ephemeral import (
        GatewayFlyError,
        effective_mcp_tenant_id,
        run_gateway_style_fly_command_sync,
    )
    from duckclaw.graphs.graph_server import ainvoke_manager_ephemeral

    raw = (history_json or "").strip() or "[]"
    try:
        history = json.loads(raw)
    except json.JSONDecodeError as e:
        err = {"error": "invalid_history_json", "detail": str(e)}
        return _tool_result_text(headline=f"ERROR: history_json no es JSON válido. {e}", payload=err)
    if not isinstance(history, list):
        err = {"error": "invalid_history_json", "detail": "expected a JSON array"}
        return _tool_result_text(headline="ERROR: history_json debe ser un array JSON.", payload=err)

    eff_tenant = effective_mcp_tenant_id(tenant_id)

    msg_stripped = (message or "").strip()
    if msg_stripped.startswith("/"):
        try:
            fly_reply = run_gateway_style_fly_command_sync(
                message,
                chat_id,
                tenant_id=eff_tenant,
                user_id=user_id,
                username=(username or "") or "",
                vault_db_path=vault_db_path,
            )
        except GatewayFlyError as e:
            err = {"error": "gateway_fly_failed", "detail": str(e)}
            return _tool_result_text(headline=f"ERROR: fly command (DuckDB). {e}", payload=err)
        if fly_reply is not None:
            headline = f"DuckClaw fly — respuesta:\n\n{fly_reply}"
            return _tool_result_text(
                headline=headline,
                payload={"fly": True, "reply": fly_reply},
            )

    try:
        result = await ainvoke_manager_ephemeral(
            message,
            history,
            chat_id,
            tenant_id=eff_tenant,
            user_id=user_id,
            username=username,
        )
    except Exception as e:
        err = {"error": "invoke_failed", "detail": str(e)}
        return _tool_result_text(headline=f"ERROR: falló invoke_manager_graph. {e}", payload=err)

    reply = str((result or {}).get("reply") or "").strip() or "(sin campo reply)"
    headline = f"DuckClaw Manager — respuesta:\n\n{reply}"
    return _tool_result_text(headline=headline, payload=dict(result))


def build_duckclaw_mcp() -> FastMCP:
    """
    Construye FastMCP con ``streamable_http_path`` por defecto ``/mcp`` (path MCP estándar).

    ``host=0.0.0.0`` evita el endurecimiento DNS rebinding solo-local del SDK cuando
    se accede vía hostname Tailscale.
    """
    mcp = FastMCP(
        "duckclaw",
        instructions=(
            "DuckClaw MCP: open_meteo_current_weather (clima por ciudad). "
            "invoke_core_conversation_graph SOLO para mensajes que empiecen exactamente por /status o /balance. "
            "Cualquier otro mensaje que empiece por / (incl. /roles, /workers, /rolees, /help, /team, /vault, /tasks) "
            "DEBE manejarse con invoke_manager_graph pasando message = texto del usuario carácter a carácter; "
            "no respondas listando herramientas MCP en su lugar. "
            "list_graph_tools solo para descubrimiento al inicio del hilo, no como sustituto de /roles ni /workers."
        ),
        host="0.0.0.0",
        streamable_http_path="/mcp",
    )

    mcp.custom_route("/", methods=["GET"], include_in_schema=False)(_root_probe)

    @mcp.tool()
    async def open_meteo_current_weather(
        city: str,
        language: str = "es",
    ) -> str:
        """
        Temperatura actual (°C) y ``weathercode`` WMO para una ciudad, usando solo APIs públicas Open-Meteo.

        Usar cuando el usuario pida clima de un lugar por nombre (p. ej. Medellín, Bogotá).
        """
        import urllib.parse

        import httpx

        q = (city or "").strip()
        if not q:
            return _tool_result_text(
                headline="ERROR: falta el nombre de la ciudad (`city`).",
                payload={"error": "empty_city"},
            )

        lang = (language or "es").strip()[:8] or "es"
        geo_url = (
            "https://geocoding-api.open-meteo.com/v1/search?"
            + urllib.parse.urlencode({"name": q, "count": 1, "language": lang})
        )
        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                geo_r = await client.get(geo_url)
                geo_r.raise_for_status()
                geo = geo_r.json()
        except Exception as e:
            return _tool_result_text(
                headline=f"ERROR: geocoding Open-Meteo falló. {e}",
                payload={"error": "geocode_http", "detail": str(e)},
            )

        results = (geo or {}).get("results") or []
        if not results:
            return _tool_result_text(
                headline=f"No se encontró ciudad para «{q}». Prueba otro nombre o coordenadas.",
                payload={"error": "no_results", "query": q},
            )

        best = results[0]
        lat = best.get("latitude")
        lon = best.get("longitude")
        label = best.get("name") or q
        if lat is None or lon is None:
            return _tool_result_text(
                headline="ERROR: resultado de geocoding sin lat/lon.",
                payload={"raw": best},
            )

        fc_url = (
            "https://api.open-meteo.com/v1/forecast?"
            + urllib.parse.urlencode(
                {
                    "latitude": lat,
                    "longitude": lon,
                    "current_weather": "true",
                }
            )
        )
        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                fc_r = await client.get(fc_url)
                fc_r.raise_for_status()
                fc = fc_r.json()
        except Exception as e:
            return _tool_result_text(
                headline=f"ERROR: forecast Open-Meteo falló. {e}",
                payload={"error": "forecast_http", "detail": str(e)},
            )

        cw = (fc or {}).get("current_weather") or {}
        temp = cw.get("temperature")
        wcode = cw.get("weathercode")
        wind = cw.get("windspeed")
        payload: dict[str, Any] = {
            "city_query": q,
            "resolved": label,
            "latitude": lat,
            "longitude": lon,
            "current_weather": cw,
            "sources": {"geocoding": geo_url.split("?")[0], "forecast": fc_url.split("?")[0]},
        }
        headline = (
            f"Open-Meteo — {label}\n"
            f"Temperatura actual: {temp} °C\n"
            f"weathercode WMO: {wcode}\n"
            f"Viento (si disponible): {wind}"
        )
        return _tool_result_text(headline=headline, payload=payload)

    @mcp.tool()
    async def invoke_manager_graph(
        message: str,
        chat_id: str = "mcp",
        tenant_id: str = "",
        history_json: str = "[]",
        username: str | None = None,
        user_id: str | None = None,
        vault_db_path: str | None = None,
    ) -> str:
        """
        **Obligatorio** cuando el usuario envía un comando que empieza por ``/`` salvo ``/status`` y ``/balance``.

        Incluye: ``/roles``, ``/workers``, ``/rolees``, ``/help``, ``/team``, ``/vault``, ``/tasks``, etc.
        Pasa ``message`` **igual** al texto del usuario (mismo slash, mismas letras; p. ej. ``/rolees`` no lo reescribas).
        DuckClaw ejecuta fly commands sobre DuckDB y devuelve la respuesta; si no aplica fly, usa el grafo Manager.

        **Prohibido** para el modelo del host: inventar la salida de ``/roles`` o ``/workers`` listando herramientas
        MCP (``open_meteo_*``, ``list_graph_tools``, …) en prosa. Siempre llama esta herramienta primero.

        ``tenant_id`` vacío → ``default`` (o ``DUCKCLAW_MCP_DEFAULT_TENANT_ID``). ``user_id`` estable para ACL en ``/team``.
        ``history_json``: array JSON ``[{role, content}]``; puede ser ``[]``.
        """
        return await invoke_manager_graph_impl(
            message,
            chat_id,
            tenant_id=tenant_id,
            history_json=history_json,
            username=username,
            user_id=user_id,
            vault_db_path=vault_db_path,
        )

    @mcp.tool()
    async def invoke_core_conversation_graph(
        user_message: str,
        context_json: str = "{}",
    ) -> str:
        """
        Ejecuta el grafo ``core_graph`` (stub LLM + comandos /status y /balance sin LLM).

        ``context_json``: objeto JSON arbitrario almacenado en ``AgentState.context``.
        """
        from langchain_core.messages import HumanMessage

        from duckclaw.graphs.core_graph import build_core_conversation_graph

        raw_ctx = (context_json or "").strip() or "{}"
        try:
            ctx: dict[str, Any] = dict(json.loads(raw_ctx))
        except json.JSONDecodeError as e:
            err = {"error": "invalid_context_json", "detail": str(e)}
            return _tool_result_text(headline=f"ERROR: context_json no es JSON válido. {e}", payload=err)
        if not isinstance(ctx, dict):
            err = {"error": "invalid_context_json", "detail": "expected a JSON object"}
            return _tool_result_text(headline="ERROR: context_json debe ser un objeto JSON.", payload=err)

        try:
            graph = build_core_conversation_graph()
            out = await graph.ainvoke(
                {"messages": [HumanMessage(content=user_message)], "context": ctx}
            )
        except Exception as e:
            err = {"error": "core_graph_failed", "detail": str(e)}
            return _tool_result_text(headline=f"ERROR: falló core_graph. {e}", payload=err)

        messages = out.get("messages") or []
        last = messages[-1] if messages else None
        content = getattr(last, "content", None) if last is not None else None
        if isinstance(content, list):
            content = json.dumps(content, default=str)
        reply = str(content or "")
        payload = {"reply": reply, "message_count": len(messages)}
        headline = f"DuckClaw core_graph — respuesta:\n\n{reply}"
        return _tool_result_text(headline=headline, payload=payload)

    @mcp.tool()
    async def list_graph_tools() -> str:
        """Lista capacidades del servidor MCP DuckClaw y pistas de despliegue (REST + Funnel)."""
        from duckclaw.graphs import graph_server as gs

        try:
            gs._ensure_llm_config()
            model = gs._resolve_display_model()
        except Exception as e:
            model = f"(unavailable: {e})"
        api_port = (os.environ.get("DUCKCLAW_API_PORT") or "8123").strip()
        mcp_port = (os.environ.get("DUCKCLAW_MCP_PORT") or "8001").strip()
        payload: dict[str, Any] = {
            "mcp_tools": [
                "open_meteo_current_weather",
                "invoke_manager_graph",
                "invoke_core_conversation_graph",
                "list_graph_tools",
            ],
            "invoke_manager_graph_note": (
                "Obligatorio para cualquier mensaje que empiece por / excepto /status y /balance: "
                "llamar invoke_manager_graph(message=texto exacto del usuario). Ejemplos: /roles, /workers, /rolees, /help, /team. "
                "No sustituir esa llamada por una lista en prosa de herramientas MCP. "
                "Fly DuckClaw antes del Manager; tenant vía DUCKCLAW_MCP_DEFAULT_TENANT_ID; opcional vault_db_path."
            ),
            "graph_server_rest": {
                "default_port": api_port,
                "endpoints": ["/invoke", "/stream", "/health", "/graph", "/docs"],
                "hint": "LangGraph API (uvicorn duckclaw.graphs.graph_server) — mismo .env que este MCP.",
            },
            "active_model_display": model,
            "tailscale_funnel": {
                "example": f"tailscale funnel --bg --yes {mcp_port}",
                "mcp_url_shape": "https://<tu-nodo>.ts.net/mcp",
                "docs": "specs/features/CONFIGURACION_TAILSCALE.md",
            },
        }
        tools_line = ", ".join(payload["mcp_tools"])
        headline = (
            "Herramientas MCP DuckClaw disponibles:\n"
            f"- {tools_line}\n"
            f"- Modelo (graph_server): {model}\n"
            "Si el usuario escribió un comando /… (p. ej. /roles): usa invoke_manager_graph con ese texto exacto; "
            "esta lista no sustituye a ese comando."
        )
        return _tool_result_text(headline=headline, payload=payload)

    return mcp


def build_streamable_http_asgi():
    """ASGI listo para uvicorn (incluye lifespan del session manager MCP)."""
    return get_duckclaw_mcp().streamable_http_app()
