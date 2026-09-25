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

        def assess_cron_registered(pm2_name: str, crontab_pattern: str = "") -> str:
            """Verifica cron por PM2 (nombre exacto) y/o crontab del host.

            Si PM2 no tiene el proceso, busca en ``crontab -l`` el nombre o
            ``crontab_pattern`` (p.ej. hrp_weekly_job). Jobs one-shot con
            cron_restart suelen aparecer status=stopped entre fires — no es fallo.
            """
            name = (pm2_name or "").strip()
            pattern = (crontab_pattern or "").strip() or name
            if not name and not pattern:
                return json.dumps({"error": "pm2_name vacío"}, ensure_ascii=False)

            pm2_payload: dict[str, Any] | None = None
            if name:
                try:
                    from duckclaw.ops.toolchain import run_pm2

                    proc = run_pm2("jlist", timeout=30)
                except Exception as exc:
                    proc = None
                    pm2_err = str(exc)[:400]
                else:
                    pm2_err = None
                    if proc.returncode != 0:
                        pm2_err = (proc.stderr or proc.stdout or "")[:500]
                    else:
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
                            pm2_payload = {
                                "found": True,
                                "name": name,
                                "has_cron": has_cron,
                                "cron_restart": env.get("cron_restart") or None,
                                "status": status,
                                "restarts": env.get("restart_time"),
                                "pm_uptime_epoch_ms": env.get("pm_uptime"),
                                "between_fires_ok": bool(has_cron and status == "stopped"),
                                "source": "pm2",
                                "message": (
                                    "Cron registrado; status=stopped entre ejecuciones es normal."
                                    if has_cron and status == "stopped"
                                    else None
                                ),
                            }
                            break
                        if pm2_payload is None:
                            pm2_err = f"Ningún proceso PM2 llamado {name}"

            crontab_lines: list[str] = []
            needles = [n for n in {name.lower(), pattern.lower()} if n]
            try:
                import subprocess

                out = subprocess.check_output(
                    ["crontab", "-l"], stderr=subprocess.DEVNULL, text=True, timeout=10
                )
                for line in out.splitlines():
                    if not line.strip() or line.strip().startswith("#"):
                        continue
                    low = line.lower()
                    if any(tok and tok in low for tok in needles):
                        crontab_lines.append(line.strip())
            except Exception:
                pass

            if pm2_payload and pm2_payload.get("has_cron"):
                if crontab_lines:
                    pm2_payload["crontab_lines"] = crontab_lines[:5]
                    pm2_payload["also_in_crontab"] = True
                return json.dumps(pm2_payload, ensure_ascii=False)

            if crontab_lines:
                return json.dumps(
                    {
                        "found": True,
                        "name": name or pattern,
                        "has_cron": True,
                        "cron_restart": None,
                        "status": None,
                        "source": "crontab",
                        "crontab_lines": crontab_lines[:5],
                        "between_fires_ok": True,
                        "message": (
                            "Cron encontrado en crontab del host (no requiere proceso PM2 permanente). "
                            "No reportes found=false solo porque PM2 no liste el nombre."
                        ),
                        "pm2": pm2_payload,
                    },
                    ensure_ascii=False,
                )

            if pm2_payload is not None:
                # Proceso PM2 sin cron_restart y sin crontab
                pm2_payload["message"] = (
                    pm2_payload.get("message")
                    or "Proceso PM2 encontrado pero sin cron_restart ni línea en crontab."
                )
                return json.dumps(pm2_payload, ensure_ascii=False)

            return json.dumps(
                {
                    "found": False,
                    "name": name or pattern,
                    "has_cron": False,
                    "source": None,
                    "message": (
                        "No hay proceso PM2 con ese nombre ni línea matching en crontab. "
                        "Pasa crontab_pattern con un token del script (p.ej. hrp_weekly_job) "
                        "si el job vive en crontab y no en PM2."
                    ),
                    "pm2_error": pm2_err if name else None,
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
                    "Verifica cron por PM2 (pm2_name exacto, cron_restart) y/o crontab del host. "
                    "Opcional crontab_pattern: token en `crontab -l` (p.ej. hrp_weekly_job) si el "
                    "job no es proceso PM2 permanente. JSON: found, has_cron, source "
                    "(pm2|crontab), between_fires_ok. status=stopped con has_cron=true es normal "
                    "entre fires — no lo trates como cron perdido."
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
