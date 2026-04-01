"""
Plantilla de referencia — MQL5 + Playwright en run_browser_sandbox.
Copia y adapta la URL; no importar este archivo (el código va entero en `code` de la tool).

Estrategia de carga: networkidle + espera fija para hidratación (React/Vue).
Selectores de código: pre, code, .b-code-block, textarea.mql4 (patrones habituales en mql5.com).
"""
from __future__ import annotations

import asyncio
import json
import sys
import traceback
from urllib.parse import urlparse

from playwright.async_api import async_playwright

# Segunda variante para reintento (PROTOCOLO MQL5 en system_prompt).
UA_PRIMARY = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
UA_RETRY = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.2 Safari/605.1.15"
)

# MQL5 suele volcar el fuente en estos nodos (además de pre/code genéricos).
MQL5_CODE_SELECTOR = "pre, code, .b-code-block, textarea.mql4"

# Tiempo extra tras networkidle para que frameworks rendericen el bloque de código.
POST_LOAD_HYDRATION_MS = 5000


def _log_stderr(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


async def _element_code_text(el) -> str:
    """Texto útil de un nodo de código (textarea usa input_value si aplica)."""
    try:
        tag = await el.evaluate("e => e.tagName && e.tagName.toLowerCase()")
        if tag == "textarea":
            try:
                v = await el.input_value()
                if v and v.strip():
                    return v.strip()
            except Exception:  # noqa: BLE001
                pass
        t = (await el.inner_text()).strip()
        if t:
            return t
    except Exception as e:  # noqa: BLE001
        _log_stderr(f"element text: {e}")
    return ""


async def extract_mql5_stealth(url: str, *, user_agent: str = UA_PRIMARY, goto_timeout_ms: int = 90_000) -> dict:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    is_mql5 = "mql5.com" in host

    extra_headers: dict[str, str] = {
        "Accept-Language": "es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    if is_mql5:
        extra_headers["Referer"] = "https://www.mql5.com/"

    out: dict = {"url": url, "title": None, "description": None, "code_snippets": [], "errors": []}

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            context = await browser.new_context(
                user_agent=user_agent,
                viewport={"width": 1920, "height": 1080},
                locale="es-ES",
                extra_http_headers=extra_headers,
            )
            await context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )
            page = await context.new_page()
            await page.goto(url, wait_until="networkidle", timeout=goto_timeout_ms)
            await page.wait_for_timeout(POST_LOAD_HYDRATION_MS)

            try:
                await page.wait_for_selector("body", timeout=15_000)
            except Exception as e:  # noqa: BLE001
                _log_stderr(f"wait_for_selector body: {e}")

            try:
                out["title"] = await page.title()
            except Exception as e:  # noqa: BLE001
                out["errors"].append(f"title: {e!s}")

            description_candidates = [
                '[itemprop="description"]',
                "article",
                "main",
                ".description",
                "#description",
                ".product-description",
                ".text",
            ]
            for sel in description_candidates:
                try:
                    loc = page.locator(sel).first
                    if await loc.count() > 0:
                        text = (await loc.inner_text()).strip()
                        if len(text) > 80:
                            out["description"] = text[:50_000]
                            break
                except Exception as e:  # noqa: BLE001
                    _log_stderr(f"selector {sel}: {e}")

            try:
                elements = await page.query_selector_all(MQL5_CODE_SELECTOR)
                for i, el in enumerate(elements[:50]):
                    try:
                        t = await _element_code_text(el)
                        if len(t) > 20 and (
                            "#" in t
                            or "void " in t
                            or "int " in t
                            or "double " in t
                            or "input " in t
                            or "=" in t
                        ):
                            out["code_snippets"].append(t[:30_000])
                    except Exception as e:  # noqa: BLE001
                        _log_stderr(f"code node[{i}]: {e}")
            except Exception as e:  # noqa: BLE001
                out["errors"].append(f"code extraction: {e!s}")

            await browser.close()
    except Exception as e:  # noqa: BLE001
        out["errors"].append(traceback.format_exc())
        out["errors"].append(str(e))

    return out


if __name__ == "__main__":
    TARGET = "https://www.mql5.com/es/code/12345"  # sustituir por la URL real
    result = asyncio.run(extract_mql5_stealth(TARGET))
    print(json.dumps(result, ensure_ascii=False))
