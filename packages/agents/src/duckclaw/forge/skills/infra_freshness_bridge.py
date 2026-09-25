"""
Infra Freshness Bridge — registra tools genéricas de salud de infraestructura
(cron PM2 registrado, antigüedad de datos en una tabla) en workers con el skill
opt-in ``infra_freshness``.

Sin lógica de vertical: nombres de proceso PM2 y de tabla/columna los decide
quien llama la tool (manifiesto/prompt del worker), nunca hardcodeados aquí.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, List

from langchain_core.tools import StructuredTool

# Identificador simple, o schema.tabla — sin comillas ni espacios, evita inyección
# SQL al interpolar table/columna (los identificadores no son parametrizables).
_TABLE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")
_COLUMN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_ident(raw: str, pattern: re.Pattern[str], *, label: str) -> tuple[str | None, str | None]:
    ident = (raw or "").strip()
    if not ident or len(ident) > 128 or not pattern.fullmatch(ident):
        return None, f"{label} inválido: solo letras/números/guion_bajo (tabla admite un 'schema.tabla')."
    return ident, None


def register_infra_freshness_skill(tools_list: List[Any], db: Any) -> None:
    """Registra assess_cron_registered y assess_table_freshness. Llamar solo cuando
    el manifiesto del worker declara el skill ``infra_freshness``."""
    try:

        def assess_cron_registered(pm2_name: str) -> str:
            """Verifica si un proceso PM2 con ese nombre exacto existe y su cron_restart.

            Nota: jobs con cron_restart suelen aparecer status=stopped entre fires;
            eso no significa que el cron falte. found+has_cron es el criterio útil.
            """
            name = (pm2_name or "").strip()
            if not name:
                return json.dumps({"error": "pm2_name vacío"}, ensure_ascii=False)
            try:
                from duckclaw.ops.toolchain import run_pm2

                proc = run_pm2("jlist", timeout=30)
            except Exception as exc:
                return json.dumps(
                    {"error": f"PM2 no disponible: {str(exc)[:400]}"}, ensure_ascii=False
                )
            if proc.returncode != 0:
                return json.dumps(
                    {
                        "error": "PM2 no respondió",
                        "detail": (proc.stderr or proc.stdout or "")[:500],
                    },
                    ensure_ascii=False,
                )
            try:
                procs = json.loads(proc.stdout or "[]")
            except json.JSONDecodeError:
                return json.dumps({"error": "Salida de PM2 inválida"}, ensure_ascii=False)
            for p in procs if isinstance(procs, list) else []:
                if not isinstance(p, dict) or p.get("name") != name:
                    continue
                env = p.get("pm2_env") or {}
                status = env.get("status")
                has_cron = bool(env.get("cron_restart"))
                return json.dumps(
                    {
                        "found": True,
                        "name": name,
                        "has_cron": has_cron,
                        "cron_restart": env.get("cron_restart") or None,
                        "status": status,
                        "restarts": env.get("restart_time"),
                        "pm_uptime_epoch_ms": env.get("pm_uptime"),
                        "between_fires_ok": bool(has_cron and status == "stopped"),
                        "message": (
                            "Cron registrado; status=stopped entre ejecuciones es normal."
                            if has_cron and status == "stopped"
                            else None
                        ),
                    },
                    ensure_ascii=False,
                )
            return json.dumps(
                {
                    "found": False,
                    "name": name,
                    "message": "Ningún proceso PM2 con ese nombre está registrado en este host.",
                },
                ensure_ascii=False,
            )

        def assess_table_freshness(
            table: str,
            timestamp_column: str = "timestamp",
            max_age_hours: float = 48.0,
            ticker_column: str = "",
            tickers: str = "",
        ) -> str:
            """Compara MAX(timestamp_column) contra umbral; opcionalmente filtra por tickers.

            tickers: lista separada por comas. Si se pasa, exige ticker_column
            (p.ej. 'ticker') y calcula MAX solo sobre esas filas — evita que un
            símbolo fresco oculte otros stale en la misma tabla.
            """
            tbl, err = _safe_ident(table, _TABLE_RE, label="table")
            if err:
                return json.dumps({"error": err}, ensure_ascii=False)
            col, err2 = _safe_ident(timestamp_column, _COLUMN_RE, label="timestamp_column")
            if err2:
                return json.dumps({"error": err2}, ensure_ascii=False)
            try:
                threshold_h = max(0.0, float(max_age_hours))
            except (TypeError, ValueError):
                threshold_h = 48.0

            ticker_list = [t.strip().upper() for t in (tickers or "").split(",") if t.strip()]
            tcol = (ticker_column or "").strip()
            where_sql = ""
            if ticker_list:
                if not tcol:
                    tcol = "ticker"
                tcol_safe, err3 = _safe_ident(tcol, _COLUMN_RE, label="ticker_column")
                if err3:
                    return json.dumps({"error": err3}, ensure_ascii=False)
                esc = ",".join("'" + t.replace("'", "''") + "'" for t in ticker_list)
                where_sql = f" WHERE UPPER(TRIM({tcol_safe})) IN ({esc})"

            try:
                raw = db.query(f"SELECT MAX({col}) AS latest FROM {tbl}{where_sql}")
                rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
            except Exception as exc:
                return json.dumps(
                    {"error": f"Consulta falló: {str(exc)[:400]}", "table": tbl},
                    ensure_ascii=False,
                )
            latest = None
            if rows and isinstance(rows[0], dict):
                latest = rows[0].get("latest")
            if latest is None:
                return json.dumps(
                    {
                        "table": tbl,
                        "latest_timestamp": None,
                        "within_threshold": False,
                        "tickers_filter": ticker_list or None,
                        "message": "Sin filas o valor nulo.",
                    },
                    ensure_ascii=False,
                )
            try:
                ts = datetime.fromisoformat(str(latest).replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                age_hours = (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0
            except Exception as exc:
                return json.dumps(
                    {
                        "table": tbl,
                        "latest_timestamp": str(latest),
                        "error": f"No se pudo interpretar el timestamp: {str(exc)[:300]}",
                    },
                    ensure_ascii=False,
                )
            return json.dumps(
                {
                    "table": tbl,
                    "latest_timestamp": str(latest),
                    "age_hours": round(age_hours, 2),
                    "threshold_hours": threshold_h,
                    "within_threshold": age_hours <= threshold_h,
                    "tickers_filter": ticker_list or None,
                },
                ensure_ascii=False,
            )

        tools_list.append(
            StructuredTool.from_function(
                assess_cron_registered,
                name="assess_cron_registered",
                description=(
                    "Verifica si un proceso PM2 (nombre exacto) existe en este host y si tiene "
                    "cron_restart. Devuelve JSON: found, has_cron, cron_restart, status, "
                    "between_fires_ok. status=stopped con has_cron=true es normal entre fires "
                    "(no lo trates como cron perdido)."
                ),
            )
        )
        tools_list.append(
            StructuredTool.from_function(
                assess_table_freshness,
                name="assess_table_freshness",
                description=(
                    "Compara MAX(timestamp) de una tabla ('schema.tabla') vs umbral en horas "
                    "(default 48). Opcional: tickers='XLU,META' + ticker_column='ticker' para "
                    "no dejar que un símbolo fresco oculte otros stale. "
                    "Para fluid_state usa timestamp_column='timestamp' (no updated_at). "
                    "Si fluid_state está viejo pero ohlcv fresco: refresca CFD, no reinicies host."
                ),
            )
        )
    except Exception:
        pass
