"""Proxy HTTP/WebSocket hacia noVNC del contenedor browser (token en path).

Montar en el API Gateway con prefix `/api/v1/sandbox/novnc`.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request, WebSocket
from fastapi.responses import RedirectResponse, Response
from starlette.websockets import WebSocketDisconnect

_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


def build_novnc_router() -> APIRouter:
    router = APIRouter()

    @router.get("/view/{token}")
    async def novnc_redirect(token: str, request: Request) -> RedirectResponse:
        target = f"{request.url.path}/vnc.html"
        q = request.url.query
        if q:
            target = f"{target}?{q}"
        return RedirectResponse(url=target, status_code=307)

    @router.api_route(
        "/view/{token}/{full_path:path}",
        methods=["GET", "HEAD", "POST", "PUT", "OPTIONS"],
    )
    async def http_proxy(token: str, full_path: str, request: Request) -> Response:
        from duckclaw.graphs.novnc_registry import resolve_token  # noqa: PLC0415

        _sid, port = resolve_token(token)
        if not port:
            raise HTTPException(status_code=404, detail="Token inválido o expirado")
        path = (full_path or "").lstrip("/")
        if not path:
            path = "vnc.html"
        url = f"http://127.0.0.1:{port}/{path}"
        if request.url.query:
            url = f"{url}?{request.url.query}"
        body = await request.body()
        fwd_headers = {
            k: v
            for k, v in request.headers.items()
            if k.lower() not in _HOP_BY_HOP and k.lower() != "host"
        }
        # #region agent log
        try:
            import json as _json  # noqa: PLC0415
            import time as _time  # noqa: PLC0415

            _log_path = "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-8d6707.log"
            with open(_log_path, "a", encoding="utf-8") as _lf:
                _lf.write(
                    _json.dumps(
                        {
                            "sessionId": "8d6707",
                            "hypothesisId": "H-upstream",
                            "location": "novnc_routes.py:http_proxy:pre",
                            "message": "novnc_http_proxy",
                            "data": {
                                "port": port,
                                "method": request.method,
                                "path": path[:120],
                                "token_prefix": (token or "")[:8],
                            },
                            "timestamp": int(_time.time() * 1000),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        except Exception:
            pass
        # #endregion
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
                r = await client.request(
                    request.method,
                    url,
                    content=body if body else None,
                    headers=fwd_headers,
                )
        except httpx.RequestError as exc:
            # #region agent log
            try:
                import json as _json2  # noqa: PLC0415
                import time as _time2  # noqa: PLC0415

                _log_path2 = "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-8d6707.log"
                with open(_log_path2, "a", encoding="utf-8") as _lf2:
                    _lf2.write(
                        _json2.dumps(
                            {
                                "sessionId": "8d6707",
                                "hypothesisId": "H-upstream",
                                "location": "novnc_routes.py:http_proxy:err",
                                "message": "novnc_upstream_request_error",
                                "data": {
                                    "port": port,
                                    "exc_type": type(exc).__name__,
                                    "exc": str(exc)[:300],
                                },
                                "timestamp": int(_time2.time() * 1000),
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
            except Exception:
                pass
            # #endregion
            raise HTTPException(status_code=502, detail=f"noVNC upstream: {exc}") from exc
        # #region agent log
        try:
            import json as _json3  # noqa: PLC0415
            import time as _time3  # noqa: PLC0415

            _log_path3 = "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-8d6707.log"
            with open(_log_path3, "a", encoding="utf-8") as _lf3:
                _lf3.write(
                    _json3.dumps(
                        {
                            "sessionId": "8d6707",
                            "hypothesisId": "H-upstream",
                            "location": "novnc_routes.py:http_proxy:ok",
                            "message": "novnc_upstream_ok",
                            "data": {"port": port, "status_code": r.status_code},
                            "timestamp": int(_time3.time() * 1000),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        except Exception:
            pass
        # #endregion
        out_h = {k: v for k, v in r.headers.items() if k.lower() not in _HOP_BY_HOP}
        return Response(content=r.content, status_code=r.status_code, headers=out_h)

    @router.websocket("/view/{token}/websockify")
    async def websocket_proxy(websocket: WebSocket, token: str) -> None:
        from duckclaw.graphs.novnc_registry import resolve_token  # noqa: PLC0415

        try:
            import websockets as ws_lib  # noqa: PLC0415
        except ImportError:
            await websocket.close(code=1011)
            return

        _sid, port = resolve_token(token)
        if not port:
            await websocket.close(code=4404)
            return
        uri = f"ws://127.0.0.1:{port}/websockify"
        # #region agent log
        try:
            import json as _json_ws  # noqa: PLC0415
            import time as _time_ws  # noqa: PLC0415

            _log_ws = "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-8d6707.log"
            with open(_log_ws, "a", encoding="utf-8") as _lfw:
                _lfw.write(
                    _json_ws.dumps(
                        {
                            "sessionId": "8d6707",
                            "hypothesisId": "H-ws-proxy",
                            "location": "novnc_routes.py:websocket_proxy:accept",
                            "message": "novnc_ws_route_matched",
                            "data": {
                                "port": port,
                                "token_prefix": (token or "")[:8],
                            },
                            "timestamp": int(_time_ws.time() * 1000),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        except Exception:
            pass
        # #endregion
        await websocket.accept()

        async def pump_client_to_upstream(up: Any) -> None:
            try:
                while True:
                    msg = await websocket.receive()
                    mtype = msg.get("type")
                    if mtype == "websocket.disconnect":
                        break
                    if mtype != "websocket.receive":
                        continue
                    b = msg.get("bytes")
                    t = msg.get("text")
                    if b is not None:
                        await up.send(b)
                    elif t is not None:
                        await up.send(t)
            except WebSocketDisconnect:
                pass

        async def pump_upstream_to_client(up: Any) -> None:
            try:
                while True:
                    data = await up.recv()
                    if isinstance(data, (bytes, bytearray)):
                        await websocket.send_bytes(bytes(data))
                    else:
                        await websocket.send_text(str(data))
            except Exception:
                pass

        try:
            async with ws_lib.connect(uri, max_size=None) as upstream:
                await asyncio.gather(
                    pump_client_to_upstream(upstream),
                    pump_upstream_to_client(upstream),
                    return_exceptions=True,
                )
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass

    return router
