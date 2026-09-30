"""IBKR bracket orders skill — ejecuta señales con TP/SL automático."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from langchain_core.tools import StructuredTool

_log = logging.getLogger(__name__)


def register_ibkr_bracket_orders_skill(
    tools_list: list[Any],
    ibkr_bracket_orders_config: Optional[dict] = None,
    vault_db_path: Optional[str] = None,
) -> None:
    """Register IBKR bracket order execution tool.
    
    Args:
        tools_list: List to append tools to
        ibkr_bracket_orders_config: Config dict (enabled check)
        vault_db_path: Path to DuckDB vault (for tp_sl_levels)
    """
    cfg = ibkr_bracket_orders_config if isinstance(ibkr_bracket_orders_config, dict) else {}
    if cfg.get("enabled") is False:
        return

    if not vault_db_path:
        _log.warning(
            "ibkr_bracket_orders skill requires vault_db_path — "
            "tool not registered (tp_sl_levels inaccessible)"
        )
        return

    # Import async bridge — defer to avoid import errors if ib_insync not installed
    try:
        from duckclaw.ibkr_bracket_orders import cancel_open_orders, connect_ibkr
        from duckclaw.signal_execution_bridge import execute_signal_with_bracket
    except ImportError as exc:
        _log.warning(
            f"ibkr_bracket_orders skill import failed: {exc} — "
            "install with: uv sync --extra trading"
        )
        return

    def _execute_signal_bracket_sync(
        signal_id: str,
        ticker: str,
        side: str,
        quantity: int,
        signal_type: str = "ENTRY",
    ) -> str:
        """Ejecuta señal de trading con bracket order (TP/SL automático en IBKR).
        
        Lee niveles TP/SL de tp_sl_levels (ACTIVE), envía bracket order a IBKR
        (main + TP + SL como órdenes GTC), registra en ibkr_orders, y actualiza
        trade_signals.executed_at.

        Si ``signal_type`` es BRACKET/OCA/PROTECTIVE, **no** abre mercado: solo
        coloca OCA protectiva sobre la posición existente (``side`` = lado abierto).
        
        Args:
            signal_id: ID de la señal en trade_signals
            ticker: Símbolo del instrumento (ej: "CEG", "SPY")
            side: "BUY" o "SELL"
            quantity: Cantidad de shares/contratos (entero > 0)
            signal_type: ENTRY (default) | EXIT | BRACKET | OCA | PROTECTIVE
        
        Returns:
            JSON con order_ids, status, TP/SL prices, o error details
        
        Example output:
            {
                "status": "submitted",
                "signal_id": "sig_20260911_CEG_001",
                "ticker": "CEG",
                "side": "BUY",
                "quantity": 994,
                "main_order_id": 12345,
                "tp_order_id": 12346,
                "sl_order_id": 12347,
                "tp_price": 300.0,
                "sl_price": 245.0,
                "timestamp": "2026-09-11T06:00:00+00:00"
            }
        """
        import asyncio

        # ponytail: sync wrapper for async tool — LangChain graph is sync
        # AsyncIO event loop handling depends on whether we're already in async context
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop — create new one (standalone execution)
            loop = None

        coro = execute_signal_with_bracket(
            signal_id=signal_id,
            ticker=ticker,
            side=side,
            quantity=quantity,
            vault_db_path=vault_db_path,
            signal_type=signal_type,
        )
        if loop and loop.is_running():
            # Already in async context (e.g. gateway handler) — use run_in_executor
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                result = future.result(timeout=30)
        else:
            # No async context — run directly
            result = asyncio.run(coro)

        return json.dumps(result, ensure_ascii=False, default=str)

    tools_list.append(
        StructuredTool.from_function(
            _execute_signal_bracket_sync,
            name="execute_signal_with_bracket",
            description=(
                "[IBKR Trading] Ejecuta señal de trading enviando bracket order (main + TP + SL) "
                "a Interactive Brokers. Las órdenes TP/SL son GTC (Good Till Canceled) y se ejecutan "
                "automáticamente cuando el precio alcanza los niveles configurados. "
                "\n\n"
                "Cuándo usar: Después de HITL approval de una señal BUY/SELL que tenga niveles "
                "TP/SL configurados en tp_sl_levels (status=ACTIVE). NO usar para señales sin TP/SL "
                "o antes de approval. "
                "\n\n"
                "signal_type:\n"
                "- ENTRY: abrir posición con bracket (main + TP/SL).\n"
                "- EXIT: cerrar/reducir a mercado (+ TP/SL si aplica). Úsalo cuando el usuario "
                "pide vender/reducir N shares ahora — no preguntes A/B.\n"
                "- BRACKET|OCA|PROTECTIVE: solo TP/SL protectivo (sin market buy). "
                "Nunca uses execute_approved_signal para BRACKET — el hook de broker lo trata como ENTRY. "
                "\n\n"
                "Args: signal_id (str), ticker (str), side ('BUY'|'SELL'), quantity (int > 0), "
                "signal_type (str, default ENTRY). "
                "\n\n"
                "Returns: JSON con order_ids (main, tp, sl), prices, status='submitted' o status='error'. "
                "Copia el JSON completo en tu reporte. Si status='error', revisar campo 'error' y "
                "troubleshoot (Gateway no conectado, TP/SL no configurados, etc)."
            ),
        )
    )

    def _cancel_ibkr_open_orders_sync(
        ticker: str = "",
        order_ids: list[int] | None = None,
        dry_run: bool = True,
    ) -> str:
        """Cancela órdenes abiertas en IBKR por ticker y/o order_id.

        Args:
            ticker: Símbolo opcional, ej. "MU".
            order_ids: IDs de orden IBKR opcionales, ej. [73, 74].
            dry_run: True solo lista coincidencias; False cancela.
        """
        import asyncio

        async def _run() -> dict:
            ib = await connect_ibkr()
            try:
                return await cancel_open_orders(
                    ib,
                    ticker=ticker or None,
                    order_ids=order_ids or None,
                    dry_run=bool(dry_run),
                )
            finally:
                try:
                    await ib.disconnect()
                except Exception:
                    pass

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                result = executor.submit(asyncio.run, _run()).result(timeout=30)
        else:
            result = asyncio.run(_run())
        return json.dumps(result, ensure_ascii=False, default=str)

    tools_list.append(
        StructuredTool.from_function(
            _cancel_ibkr_open_orders_sync,
            name="cancel_ibkr_open_orders",
            description=(
                "[IBKR Trading] Cancela órdenes abiertas existentes en Interactive Brokers "
                "por ticker y/o order_ids. Usar cuando get_ibkr_open_orders muestra órdenes "
                "PreSubmitted/Submitted que bloquean el preflight. Por seguridad dry_run=True "
                "por defecto: primero lista coincidencias; con dry_run=False envía cancelOrder. "
                "Args: ticker (opcional), order_ids (lista opcional de int), dry_run (bool). "
                "Devuelve JSON con matched_count, cancelled_count y detalle de órdenes."
            ),
        )
    )

    def _schedule_ibkr_shares_order_cron_sync(
        ticker: str,
        action: str,
        quantity: int,
        run_date_utc: str,
        cron: str,
        name: str = "",
        paper: bool = True,
        dry_run: bool = True,
    ) -> str:
        """Programa una orden determinista de shares como proceso PM2 con cron_restart.

        La tool crea un wrapper idempotente que sólo ejecuta en ``run_date_utc`` y
        marca un sentinel ``.done`` si el broker script termina OK.
        """
        import os
        import re
        import shlex
        import stat
        import subprocess
        from datetime import datetime
        from pathlib import Path

        ticker_norm = str(ticker or "").strip().upper()
        action_norm = str(action or "").strip().upper()
        if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,15}", ticker_norm):
            raise ValueError("ticker must be a valid uppercase market symbol, e.g. MU")
        if action_norm not in {"BUY", "SELL"}:
            raise ValueError("action must be BUY or SELL")
        try:
            qty = int(quantity)
        except Exception as exc:
            raise ValueError("quantity must be an integer > 0") from exc
        if qty <= 0:
            raise ValueError("quantity must be an integer > 0")
        try:
            datetime.strptime(str(run_date_utc), "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("run_date_utc must use YYYY-MM-DD") from exc

        cron_norm = " ".join(str(cron or "").strip().split())
        if len(cron_norm.split()) != 5 or not re.fullmatch(r"[0-9*/,\-\s]+", cron_norm):
            raise ValueError("cron must be a standard 5-field numeric PM2 cron expression")

        default_name = f"ibkr-{ticker_norm.lower()}-{action_norm.lower()}-{qty}-shares-{run_date_utc.replace('-', '')}"
        raw_name = str(name or default_name).strip()
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw_name).strip("-")
        if not safe_name or len(safe_name) > 80:
            raise ValueError("name must resolve to 1-80 safe chars [A-Za-z0-9_.-]")

        repo_root_raw = (
            os.environ.get("CAPADONNA_DRILLER_ROOT")
            or os.environ.get("DUCKCLAW_REPO_ROOT")
            or "/root/Capadonna-Driller"
        )
        repo_root = Path(repo_root_raw).expanduser()
        broker_script = repo_root / "scripts" / "capadonna" / "broker_execute_signal.py"
        python_bin = repo_root / ".venv" / "bin" / "python"
        if os.name == "nt":
            win_python = repo_root / ".venv" / "Scripts" / "python.exe"
            if win_python.exists():
                python_bin = win_python

        missing = [str(path) for path in (broker_script, python_bin) if not path.exists()]
        if missing:
            raise FileNotFoundError(
                "Cannot schedule order; required runtime files are missing: "
                + ", ".join(missing)
            )

        tasks_dir = repo_root / "tasks" / "pm2"
        script_path = tasks_dir / f"{safe_name}.sh"
        sentinel_path = tasks_dir / f"{safe_name}.done"
        embedded_order = {
            "mode": "shares",
            "ticker": ticker_norm,
            "action": action_norm,
            "quantity": qty,
        }
        embedded_json = json.dumps(embedded_order, separators=(",", ":"), ensure_ascii=True)
        paper_flag = "1" if bool(paper) else "0"

        script = f"""#!/usr/bin/env bash
set -euo pipefail
RUN_DATE_UTC={shlex.quote(str(run_date_utc))}
SENTINEL={shlex.quote(str(sentinel_path))}
TODAY_UTC="$(date -u +%F)"
if [ "$TODAY_UTC" != "$RUN_DATE_UTC" ]; then
  echo "skip: today=$TODAY_UTC run_date=$RUN_DATE_UTC"
  exit 0
fi
if [ -f "$SENTINEL" ]; then
  echo "skip: already executed ($SENTINEL)"
  exit 0
fi
export DUCKCLAW_EMBEDDED_EXECUTE_JSON={shlex.quote(embedded_json)}
cd {shlex.quote(str(repo_root))}
set +e
{shlex.quote(str(python_bin))} {shlex.quote(str(broker_script))} {shlex.quote(safe_name)} {paper_flag}
rc=$?
set -e
if [ "$rc" -eq 0 ]; then
  date -u +"%Y-%m-%dT%H:%M:%SZ" > "$SENTINEL"
fi
exit "$rc"
"""

        pm2_command = [
            "pm2",
            "start",
            str(script_path),
            "--name",
            safe_name,
            "--interpreter",
            "bash",
            "--cron-restart",
            cron_norm,
            "--no-autorestart",
        ]

        result: dict[str, Any] = {
            "status": "dry_run" if dry_run else "scheduled",
            "dry_run": bool(dry_run),
            "name": safe_name,
            "ticker": ticker_norm,
            "action": action_norm,
            "quantity": qty,
            "paper": bool(paper),
            "run_date_utc": str(run_date_utc),
            "cron": cron_norm,
            "repo_root": str(repo_root),
            "script_path": str(script_path),
            "sentinel_path": str(sentinel_path),
            "embedded_order": embedded_order,
            "pm2_command": pm2_command,
            "appears_in_crons_ui": True,
        }
        if dry_run:
            return json.dumps(result, ensure_ascii=False, default=str)

        tasks_dir.mkdir(parents=True, exist_ok=True)
        script_path.write_text(script, encoding="utf-8")
        script_path.chmod(
            stat.S_IRUSR
            | stat.S_IWUSR
            | stat.S_IXUSR
            | stat.S_IRGRP
            | stat.S_IXGRP
        )
        subprocess.run(
            ["pm2", "delete", safe_name],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        created = subprocess.run(
            pm2_command,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        result["pm2_stdout"] = created.stdout[-2000:]
        result["pm2_stderr"] = created.stderr[-2000:]
        return json.dumps(result, ensure_ascii=False, default=str)

    tools_list.append(
        StructuredTool.from_function(
            _schedule_ibkr_shares_order_cron_sync,
            name="schedule_ibkr_shares_order_cron",
            description=(
                "[IBKR Trading] Programa una orden determinista de shares como proceso PM2 "
                "con cron_restart visible en la pantalla Crons. Usa esto cuando el usuario "
                "pide dejar una venta/compra exacta para apertura o una hora concreta. "
                "Por seguridad dry_run=True por defecto: primero devuelve el wrapper, cron y "
                "orden embebida sin crear nada. Con dry_run=False crea tasks/pm2/<name>.sh, "
                "lo registra en PM2 y queda visible en la UI de Crons. "
                "Args: ticker, action BUY|SELL, quantity, run_date_utc YYYY-MM-DD, cron "
                "(5 campos en UTC del VPS), name opcional, paper bool, dry_run bool. "
                "Devuelve JSON auditable con status, pm2_command, script_path y embedded_order."
            ),
        )
    )

    _log.info(
        "IBKR bracket orders skill registrado — "
        "execute_signal_with_bracket/cancel_ibkr_open_orders/"
        "schedule_ibkr_shares_order_cron disponibles"
    )
