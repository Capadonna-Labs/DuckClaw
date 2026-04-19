#!/usr/bin/env python3
"""
Verificación post-Telegram: lee el DuckDB del asistente PQRSD vía DuckClaw-Gateway (db/read).

Flujo manual sugerido
---------------------
1. PM2 con DuckClaw-Gateway arriba; variables en `.env` (raíz del repo):
   - DUCKCLAW_REPO_ROOT
   - DUCKCLAW_PQRSD_ASSISTANT_DB_PATH (relativo al repo o absoluto)
2. Enviar mensaje al bot de Telegram y completar radicación (perfil + caso).
3. Ejecutar este script (mismo entorno que carga el `.env`).

Nota de producto
------------------
Telegram persiste en ``pqrsd_assistant.radicacion_*``. El Kanban GovTech del CRM Next
suele leer ``pqrsd_crm.tickets`` (otra tabla). Si el caso no aparece en el UI del CRM,
comprueba con este script la tabla del asistente; un puente/sync entre tablas sería
un cambio aparte (spec + db-writer).

Uso
---
  uv run python scripts/verify_pqrsd_telegram_pipeline.py
  uv run python scripts/verify_pqrsd_telegram_pipeline.py --telegram-chat-id 123456789
  CRM_BASE_URL=http://127.0.0.1:3000 uv run python scripts/verify_pqrsd_telegram_pipeline.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx


def _load_dotenv(repo_root: Path) -> None:
    env_path = repo_root / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def _resolve_repo_root() -> Path:
    raw = (os.environ.get("DUCKCLAW_REPO_ROOT") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def _resolve_db_path(repo_root: Path) -> Path:
    rel = (os.environ.get("DUCKCLAW_PQRSD_ASSISTANT_DB_PATH") or "").strip()
    if not rel:
        raise SystemExit(
            "Falta DUCKCLAW_PQRSD_ASSISTANT_DB_PATH en el entorno o en .env"
        )
    p = Path(rel)
    if not p.is_absolute():
        p = (repo_root / rel).resolve()
    return p


def vault_user_id_from_db_path(db_path: Path) -> str:
    """``db/private/{user_id}/archivo.duckdb`` → ``user_id`` para Gateway ACL."""
    parts = db_path.resolve().parts
    for i, part in enumerate(parts):
        if part == "private" and i + 1 < len(parts):
            return parts[i + 1]
    raise SystemExit(
        "No se pudo inferir user_id desde la ruta (se espera .../db/private/<user_id>/...)"
    )


def _gateway_url() -> str:
    return (os.environ.get("DUCKCLAW_GATEWAY_URL") or "http://127.0.0.1:8000").rstrip("/")


def _crm_base_url() -> str | None:
    u = (os.environ.get("CRM_BASE_URL") or "").strip().rstrip("/")
    return u or None


def db_read(
    client: httpx.Client,
    gateway: str,
    *,
    user_id: str,
    db_path: str,
    query: str,
    params: list[Any] | None = None,
) -> list[dict[str, Any]]:
    url = f"{gateway}/api/v1/db/read"
    payload = {
        "query": query,
        "params": params or [],
        "tenant_id": "default",
        "user_id": user_id,
        "db_path": db_path,
    }
    r = client.post(url, json=payload, timeout=60.0)
    if r.status_code != 200:
        raise RuntimeError(f"db/read HTTP {r.status_code}: {r.text}")
    data = r.json()
    return data.get("rows") or []


def _print_section(title: str, rows: list[dict[str, Any]]) -> None:
    print(f"\n=== {title} ({len(rows)} filas) ===")
    if not rows:
        print("(vacío)")
        return
    print(json.dumps(rows, indent=2, ensure_ascii=False, default=str))


def _optional_crm_probe(base: str, client: httpx.Client) -> None:
    """Sondeo best-effort del CRM Next (rutas habituales); no falla el script."""
    candidates = [
        f"{base}/api/crm/tickets",
        f"{base}/api/crm/tickets?idSecretaria=sec-salud",
    ]
    for url in candidates:
        try:
            r = client.get(url, timeout=10.0)
            print(f"\n=== CRM probe GET {url} → {r.status_code} ===")
            if r.status_code == 200:
                try:
                    body = r.json()
                    print(json.dumps(body, indent=2, ensure_ascii=False)[:4000])
                except Exception:
                    print(r.text[:2000])
                return
        except httpx.RequestError as e:
            print(f"\n=== CRM probe {url} error: {e} ===")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verifica radicación PQRSD tras Telegram.")
    parser.add_argument(
        "--telegram-chat-id",
        default="",
        help="Filtra filas por telegram_chat_id (opcional).",
    )
    args = parser.parse_args()

    repo_root = _resolve_repo_root()
    _load_dotenv(repo_root)

    db_path = _resolve_db_path(repo_root)
    if not db_path.is_file():
        raise SystemExit(f"No existe la base: {db_path}")

    user_id = vault_user_id_from_db_path(db_path)
    gateway = _gateway_url()
    db_path_str = str(db_path)

    chat_filter = (args.telegram_chat_id or "").strip()
    params_crm: list[Any] = []
    params_perfil: list[Any] = []
    where_crm = ""
    where_perfil = ""
    if chat_filter:
        where_crm = " WHERE telegram_chat_id = ?"
        where_perfil = " WHERE telegram_chat_id = ?"
        params_crm = [chat_filter]
        params_perfil = [chat_filter]

    # Usar SELECT * y ORDER BY radicado para compatibilidad con DuckDB antiguos sin created_at.
    q_crm = (
        "SELECT * FROM pqrsd_assistant.radicacion_crm"
        f"{where_crm} ORDER BY radicado DESC LIMIT 20"
    )
    q_perfil = (
        "SELECT * FROM pqrsd_assistant.radicacion_perfil"
        f"{where_perfil} ORDER BY telegram_chat_id LIMIT 20"
    )

    print(f"Gateway: {gateway}")
    print(f"DuckDB:  {db_path_str}")
    print(f"user_id: {user_id}")

    with httpx.Client() as client:
        r_health = client.get(f"{gateway}/health", timeout=5.0)
        print(f"GET /health → {r_health.status_code}")

        rows_crm = db_read(
            client,
            gateway,
            user_id=user_id,
            db_path=db_path_str,
            query=q_crm,
            params=params_crm,
        )
        rows_perfil = db_read(
            client,
            gateway,
            user_id=user_id,
            db_path=db_path_str,
            query=q_perfil,
            params=params_perfil,
        )
        _print_section("pqrsd_assistant.radicacion_crm", rows_crm)
        _print_section("pqrsd_assistant.radicacion_perfil", rows_perfil)

        # Misma base: si existe pqrsd_crm.tickets (Kanban CRM), mostrar muestra.
        try:
            meta = db_read(
                client,
                gateway,
                user_id=user_id,
                db_path=db_path_str,
                query=(
                    "SELECT database_name, schema_name, table_name FROM duckdb_tables() "
                    "WHERE schema_name = 'pqrsd_crm' AND table_name = 'tickets'"
                ),
            )
            if meta:
                rows_tickets = db_read(
                    client,
                    gateway,
                    user_id=user_id,
                    db_path=db_path_str,
                    query="SELECT * FROM pqrsd_crm.tickets ORDER BY 1 DESC LIMIT 10",
                )
                _print_section("pqrsd_crm.tickets (muestra)", rows_tickets)
            else:
                print(
                    "\n=== pqrsd_crm.tickets ===\n"
                    "(no existe en esta base; el CRM puede usar otra tabla o otra ruta DuckDB)"
                )
        except RuntimeError as e:
            print(f"\n(No se pudo leer pqrsd_crm: {e})")

        crm_base = _crm_base_url()
        if crm_base:
            _optional_crm_probe(crm_base, client)
        else:
            print(
                "\n(Opcional) Define CRM_BASE_URL=http://127.0.0.1:3000 para sondear la API del CRM."
            )

    if chat_filter:
        ok = any(r.get("telegram_chat_id") == chat_filter for r in rows_crm) and any(
            r.get("telegram_chat_id") == chat_filter for r in rows_perfil
        )
        if not ok:
            print(
                "\nAdvertencia: con el filtro dado no hay filas en ambas tablas.",
                file=sys.stderr,
            )
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
