#!/usr/bin/env python3
"""
Pipeline MOC Core-Satellite CFD — specs/features/Core-Satellite HRP Weekly + MOC CFD.md

``MOC_PHASE=calc|remind|expire`` (cron weekday ~14:40 / 14:50 / 14:59 America/Bogota).

En **calc** sin ``--dry-run``, por defecto se activa la auto-ejecución encadenada de señales
``moc_hrp_cfd`` (``DUCKCLAW_MOC_PIPELINE_AUTO_EXECUTE``; ``=0`` para solo HITL). Ver spec.

``--dry-run``: mismas lecturas (vault read-only, IBKR, allocations); sin Telegram, colas DB,
``propose_trade_signal``, ``~/.duckclaw_moc_session.json`` ni inserts semánticos.

``--dry-run --dry-run-notify`` (o ``DUCKCLAW_MOC_DRY_RUN_NOTIFY=1``): al terminar envía **un** mensaje
breve a Telegram (mismo canal que ``send_quant_alert_message``) para validar outbound PM2 sin escrituras.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None  # type: ignore[misc, assignment]

_REPO = Path(__file__).resolve().parent.parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
if str(_REPO / "packages" / "agents" / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "packages" / "agents" / "src"))
if str(_REPO / "packages" / "shared" / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "packages" / "shared" / "src"))
if str(_REPO / "packages" / "core" / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "packages" / "core" / "src"))

try:
    from dotenv import load_dotenv

    load_dotenv(_REPO / ".env")
except ImportError:
    pass

_MOC_STORE = Path.home() / ".duckclaw_moc_session.json"
_STRATEGY = "moc_hrp_cfd"
_MIN_EQUITY = 10_000.0


def _moc_store_write(session_uid: str) -> None:
    payload = {"session_uid": session_uid.strip(), "phase": os.environ.get("MOC_PHASE", "")}
    _MOC_STORE.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _moc_store_read() -> str:
    try:
        if not _MOC_STORE.is_file():
            return ""
        data = json.loads(_MOC_STORE.read_text(encoding="utf-8"))
        return str(data.get("session_uid") or "").strip()
    except Exception:
        return ""


def _mandates_latest(db: Any) -> list[dict[str, Any]]:
    q = """
    WITH rk AS (
      SELECT ticker,
             CAST(hrp_weight_capped AS DOUBLE) AS hrp_weight_capped,
             ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY computed_at DESC) AS rn
      FROM quant_core.hrp_mandates
      WHERE valid_until > CURRENT_TIMESTAMP
    )
    SELECT ticker, hrp_weight_capped FROM rk WHERE rn = 1 ORDER BY ticker
    """
    raw = db.query(q)
    rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
    return [r for r in rows if isinstance(r, dict)]


def _last_fluid_phase(db: Any, ticker: str) -> str:
    esc = ticker.replace("'", "''")
    raw = db.query(
        "SELECT phase FROM quant_core.fluid_state "
        f"WHERE ticker = '{esc}' ORDER BY timestamp DESC LIMIT 1"
    )
    rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
    if rows and isinstance(rows[0], dict):
        return str(rows[0].get("phase") or "SOLID").strip().upper() or "SOLID"
    return "SOLID"


def _moc_cot_now_hhmm() -> str:
    if ZoneInfo is not None:
        try:
            return datetime.now(ZoneInfo("America/Bogota")).strftime("%H:%M")
        except Exception:
            pass
    return datetime.now().strftime("%H:%M")


def _moc_telegram_phase_prefix(phase: str) -> str:
    """Primera línea de alertas Telegram para distinguir calc / remind / expire en el chat."""
    return f"MOC {phase} · {_moc_cot_now_hhmm()} COT\n\n"


def _moc_trading_date_iso_cot() -> str:
    if ZoneInfo is not None:
        try:
            return datetime.now(ZoneInfo("America/Bogota")).date().isoformat()
        except Exception:
            pass
    return datetime.now().date().isoformat()


def _active_session_uid_for_accum(db: Any) -> str:
    try:
        raw = db.query(
            "SELECT session_uid FROM quant_core.trading_sessions WHERE id = 'active' LIMIT 1"
        )
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
        if rows and isinstance(rows[0], dict):
            return str(rows[0].get("session_uid") or "").strip()
    except Exception:
        pass
    return ""


def _load_intraday_accum_payloads(db: Any, session_uid: str, trading_date_iso: str) -> dict[str, dict[str, Any]]:
    if not session_uid.strip():
        return {}
    esc_u = session_uid.replace("'", "''")
    esc_d = trading_date_iso.replace("'", "''")
    try:
        raw = db.query(
            "SELECT ticker, payload FROM quant_core.intraday_moc_accum "
            f"WHERE session_uid = '{esc_u}' AND trading_date = '{esc_d}'::DATE "
            "AND finalized_at IS NULL"
        )
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
    except Exception:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        tku = str(r.get("ticker") or "").strip().upper()
        if not tku:
            continue
        pl = r.get("payload")
        if isinstance(pl, dict):
            out[tku] = dict(pl)
        elif isinstance(pl, str) and pl.strip():
            try:
                pj = json.loads(pl)
                if isinstance(pj, dict):
                    out[tku] = pj
            except json.JSONDecodeError:
                pass
    return out


def _dry_banner(phase: str) -> None:
    print(f"[moc] DRY-RUN phase={phase} — sin Telegram, Redis/escrituras ni propose_trade_signal")


def _moc_outbound_dry_run_ping(phase: str, detail: str) -> bool:
    """POST único a Telegram tras un ``--dry-run`` (validación; no depende del flag ``dry_run`` del job)."""
    try:
        from scripts.quant._job_common import send_quant_alert_message

        text = _moc_telegram_phase_prefix(phase) + "[dry-run ping]\n\n" + (detail or "").strip()
        if len(text) > 7800:
            text = text[:7800] + "\n…(truncado)"
        return bool(send_quant_alert_message(text))
    except Exception as exc:
        print(f"[moc] dry-run telegram ping failed: {exc}", file=sys.stderr, flush=True)
        return False


def _moc_calc_enable_batch_auto_execute_env(*, dry_run: bool) -> None:
    """
    Activa la auto-ejecución encadenada para ``strategy_name=moc_hrp_cfd`` en este proceso
    (``_propose_trade_signal_impl``): requiere ``DUCKCLAW_MOC_BATCH_AUTO_EXECUTE`` y
    ``DUCKCLAW_QUANT_AUTO_EXECUTE_SIGNALS`` (spec Core-Satellite MOC CFD).

    Por defecto **sí** (``DUCKCLAW_MOC_PIPELINE_AUTO_EXECUTE`` ausente o truthy). Opt-out:
    ``DUCKCLAW_MOC_PIPELINE_AUTO_EXECUTE=0|false|off``.
    """
    if dry_run:
        return
    raw = (os.getenv("DUCKCLAW_MOC_PIPELINE_AUTO_EXECUTE") or "1").strip().lower()
    if raw in ("0", "false", "no", "off"):
        print(
            "[moc] batch auto-exec omitido (DUCKCLAW_MOC_PIPELINE_AUTO_EXECUTE=0)",
            file=sys.stderr,
            flush=True,
        )
        return
    os.environ["DUCKCLAW_MOC_BATCH_AUTO_EXECUTE"] = "1"
    os.environ["DUCKCLAW_QUANT_AUTO_EXECUTE_SIGNALS"] = "1"
    print(
        "[moc] batch auto-exec: DUCKCLAW_MOC_BATCH_AUTO_EXECUTE=1 "
        "DUCKCLAW_QUANT_AUTO_EXECUTE_SIGNALS=1 (calc PM2; "
        "DUCKCLAW_MOC_PIPELINE_AUTO_EXECUTE=0 → solo HITL + /execute_all_moc)",
        file=sys.stderr,
        flush=True,
    )


def _moc_notify_telegram_safe(phase: str, detail: str, *, dry_run: bool) -> bool:
    """Best-effort Telegram (mismo canal que ``send_quant_alert_message``). Retorna True si POST 2xx."""
    if dry_run:
        return False
    try:
        from scripts.quant._job_common import send_quant_alert_message

        text = _moc_telegram_phase_prefix(phase) + (detail or "").strip()
        if len(text) > 7800:
            text = text[:7800] + "\n…(truncado)"
        return bool(send_quant_alert_message(text))
    except Exception as exc:
        print(f"[moc] telegram notify failed: {exc}", file=sys.stderr, flush=True)
        return False


def run_calc(*, dry_run: bool = False) -> int:
    from duckclaw.forge.atoms.investor_profile_vss import get_investor_profile
    from duckclaw.forge.atoms.macro_regime_detector import detect_current_regime
    from duckclaw.forge.atoms.moc_allocation import calculate_target_allocation
    from duckclaw.forge.atoms.moc_allocation_v2 import calculate_target_allocation_v2
    from duckclaw.forge.atoms.moc_intraday_hints import apply_intraday_accum_hints_to_allocation
    from duckclaw.forge.skills.quant_market_bridge import _fetch_ib_gateway_ohlcv_impl
    from duckclaw.forge.skills.quant_tool_context import (
        bind_quant_market_evidence_chat,
        note_quant_market_evidence_ticker,
        set_quant_tool_db_path,
        set_quant_tool_tenant_id,
        set_quant_tool_user_id,
    )
    from duckclaw.forge.skills.quant_trader_bridge import _propose_trade_signal_impl

    from scripts.quant._job_common import (
        enqueue_task_audit_warning,
        enqueue_vault_sql,
        fetch_ibkr_equity_and_positions_mv,
        infer_vault_user_id,
        log_quant_outbound_readiness,
        open_duckclaw_readonly_retry,
        send_quant_alert_message,
    )

    if dry_run:
        _dry_banner("calc")

    db_path = (os.environ.get("DUCKCLAW_QUANT_SCRIPT_DB") or "").strip()
    if not db_path or not Path(db_path).expanduser().is_file():
        print("[moc] DUCKCLAW_QUANT_SCRIPT_DB inválido", file=sys.stderr)
        _moc_notify_telegram_safe(
            "calc",
            "Fallo de configuración: DUCKCLAW_QUANT_SCRIPT_DB inválido o archivo inexistente.",
            dry_run=dry_run,
        )
        return 2
    vault_path = str(Path(db_path).expanduser().resolve())
    uid_infer = infer_vault_user_id(vault_path)
    outbound_any_ok = False
    if not dry_run:
        log_quant_outbound_readiness("moc_pipeline", phase="calc")
    _tprefix = _moc_telegram_phase_prefix("calc")

    bind_quant_market_evidence_chat("__moc__")
    set_quant_tool_db_path(vault_path)
    set_quant_tool_user_id(uid_infer)
    set_quant_tool_tenant_id(os.environ.get("DUCKCLAW_QUANT_TENANT_ID", "default"))

    _moc_calc_enable_batch_auto_execute_env(dry_run=dry_run)

    db = open_duckclaw_readonly_retry(vault_path)

    trading_day_iso = _moc_trading_date_iso_cot()
    active_uid_for_accum = _active_session_uid_for_accum(db)
    accum_by_ticker = _load_intraday_accum_payloads(db, active_uid_for_accum, trading_day_iso)

    mandates = _mandates_latest(db)
    if not mandates:
        msg = (
            "⚠️ HRP Mandates expirados o tabla vacía. Ejecutá hrp_weekly_job antes del MOC."
        )
        if dry_run:
            print(f"[moc] (dry-run) alerta que NO se envía:\n{msg}")
        else:
            ok_m = send_quant_alert_message(_tprefix + msg)
            outbound_any_ok |= ok_m
            if not ok_m:
                _moc_notify_telegram_safe(
                    "calc",
                    "Mandates vacíos (salida exit=1): el mensaje principal no se entregó a Telegram; revisa PM2 / outbound.",
                    dry_run=False,
                )
            enqueue_task_audit_warning(
                vault_path,
                tenant_id="default",
                worker_id="moc_pipeline_calc",
                plan_title="MOC_MISSING_HRP_MANDATES",
                query_prefix="no vigentes valid_until > now",
            )
        print("[moc] sin mandates vigentes")
        return 1

    equity, pos_mv, perr = fetch_ibkr_equity_and_positions_mv()
    if perr:
        print("[moc] IBKR:", perr, file=sys.stderr)
    if equity < _MIN_EQUITY:
        cap_msg = (
            "Capital insuficiente para operar HRP-CFD "
            f"(equity {_MIN_EQUITY:.0f} USD requeridos; vista {equity:.0f})."
        )
        if dry_run:
            print(f"[moc] (dry-run) alerta que NO se envía:\n{cap_msg}")
        else:
            ok_c = send_quant_alert_message(_tprefix + cap_msg)
            outbound_any_ok |= ok_c
            if not ok_c:
                _moc_notify_telegram_safe(
                    "calc",
                    "Capital insuficiente (exit=1): el aviso principal no se entregó a Telegram; revisa PM2 / outbound.",
                    dry_run=False,
                )
        return 1

    session_uid = str(uuid.uuid4())
    if not dry_run:
        _moc_store_write(session_uid)
    else:
        print(f"[moc] (dry-run) session_uid simulado (no persistido): {session_uid}")

    tenant_job = os.environ.get("DUCKCLAW_QUANT_TENANT_ID", "default")
    macro_vss_on = str(os.environ.get("DUCKCLAW_MOC_MACRO_VSS") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )
    regime_snapshot: dict[str, Any] | None = None
    investor_profile: dict[str, Any] | None = None
    if macro_vss_on:
        try:
            regime_snapshot = detect_current_regime(db, tenant_job)
            investor_profile = get_investor_profile(db, tenant_job)
        except Exception as exc:
            print("[moc] macro/vss warmup:", exc, file=sys.stderr)
            regime_snapshot = None
            investor_profile = None

    summaries = []
    n_props = 0
    tk_evidence = []

    for row in mandates:
        tk = str(row.get("ticker") or "").strip().upper()
        if not tk:
            continue
        cap_w = float(row.get("hrp_weight_capped") or 0.0)
        fase = _last_fluid_phase(db, tk)

        fetch_raw = _fetch_ib_gateway_ohlcv_impl(db, ticker=tk, timeframe="1d", lookback_days=14)
        try:
            pj = json.loads(fetch_raw) if isinstance(fetch_raw, str) else {}
        except json.JSONDecodeError:
            pj = {}
        if isinstance(pj, dict) and pj.get("status") == "ok":
            note_quant_market_evidence_ticker(tk)
            tk_evidence.append(tk)

        pos_usd = float(pos_mv.get(tk, 0.0))
        if (
            macro_vss_on
            and regime_snapshot is not None
            and investor_profile is not None
        ):
            tgt = calculate_target_allocation_v2(
                ticker=tk,
                fase_fluido=fase,
                hrp_weight_capped=cap_w,
                equity=equity,
                posicion_actual_usd=pos_usd,
                regime=regime_snapshot,
                investor_profile=investor_profile,
            )
        else:
            tgt = calculate_target_allocation(
                ticker=tk,
                fase_fluido=fase,
                hrp_weight_capped=cap_w,
                equity=equity,
                posicion_actual_usd=pos_usd,
            )
        hints_row = accum_by_ticker.get(tk)
        if hints_row and str(tgt.get("action") or "").upper() not in ("SKIP",):
            tgt = apply_intraday_accum_hints_to_allocation(
                tgt,
                hints_row,
                hrp_weight_capped=cap_w,
                equity=equity,
                posicion_actual_usd=pos_usd,
            )
        summaries.append({"ticker": tk, **tgt})
        action = str(tgt.get("action") or "").upper()

        mandate_label = f"moc:{session_uid}:{tk}"
        pct_w = max(float((tgt.get("target_weight") or 0.0) * 100.0), 0.01)
        rationale = str(tgt.get("rationale") or "")

        if action in ("SKIP", "HOLD"):
            continue
        if dry_run and action in ("BUY", "SELL"):
            n_props += 1
            continue
        if action == "BUY":
            raw_p = _propose_trade_signal_impl(
                db,
                mandate_id=mandate_label,
                ticker=tk,
                weight=pct_w,
                rationale=rationale + " · MOC",
                signal_type="ENTRY",
                strategy_name=_STRATEGY,
                session_uid_override=session_uid,
            )
        elif action == "SELL":
            raw_p = _propose_trade_signal_impl(
                db,
                mandate_id=mandate_label,
                ticker=tk,
                weight=max(pct_w, 0.01),
                rationale=rationale + " · MOC",
                signal_type="EXIT",
                strategy_name=_STRATEGY,
                session_uid_override=session_uid,
            )
        else:
            continue
        try:
            pj2 = json.loads(raw_p) if isinstance(raw_p, str) else {}
        except json.JSONDecodeError:
            pj2 = {}
        if isinstance(pj2, dict) and pj2.get("signal_id") and not pj2.get("error"):
            n_props += 1

    hhmm = _moc_cot_now_hhmm()
    hdr_ctx = ""
    if macro_vss_on and regime_snapshot and investor_profile:
        vix = regime_snapshot.get("vix")
        vix_disp = f"{float(vix):.1f}" if vix is not None else "—"
        conf_pct = float(regime_snapshot.get("confidence") or 0.0) * 100.0
        coh = ", ".join(regime_snapshot.get("coherent_assets") or [])
        ctr = ", ".join(regime_snapshot.get("contraindicated_assets") or [])
        md_pct = float(investor_profile.get("max_drawdown_tolerance") or 0.05) * 100.0
        hdr_ctx = (
            f"📊 MOC Macro + VSS — {_moc_cot_now_hhmm()} COT\n"
            f"Régimen: {regime_snapshot.get('regime')} "
            f"(VIX {vix_disp}, conf {conf_pct:.0f}%)\n"
            f"Perfil: {investor_profile.get('risk_tolerance')} · MaxDD declarado ~{md_pct:.0f}%\n\n"
        )
        hdr_ctx += (
            "Coherentes con régimen: " + (coh or "(ninguno en grafo)") + "\n"
            "Contraindicados: " + (ctr or "(ninguno)") + "\n\n"
        )
    lines_body = []
    for s in summaries:
        sa = str(s.get("action")).upper()
        if sa == "HOLD":
            continue
        vul = float(s.get("valvula_final") or s.get("valvula") or 0.0)
        if sa == "SKIP":
            lines_body.append(
                f"{s.get('ticker')}: SKIP\n  {str(s.get('rationale') or '')[:240]}"
            )
            continue
        if macro_vss_on:
            mpen = float(s.get("macro_penalty") or 1.0)
            rationale_short = str(s.get("rationale") or "")[:260]
            lines_body.append(
                f"{s.get('ticker')}: {sa} ${float(s.get('delta_usd') or 0):+,.0f}\n"
                f"  HRP {float((s.get('hrp_weight') or 0))*100:.1f}% · CFD válvula base "
                f"{(float(s.get('valvula_base') or 0))*100:.0f}% → macro ×{mpen:.1f} · "
                f"Válvula final {vul*100:.0f}% · Fase {s.get('fase')}\n"
                f"  {rationale_short}"
            )
        else:
            lines_body.append(
                f"{s.get('ticker')}: {s.get('action')} ${float(s.get('delta_usd') or 0):+,.0f}\n"
                f"  HRP cap: {float((s.get('hrp_weight') or 0))*100:.1f}% · Fase: {s.get('fase')} · "
                f"Válvula: {vul*100:.0f}%"
            )
    _prop_line = (
        f"Propuestas simuladas (dry-run, sin `propose_trade_signal`): {n_props}"
        if dry_run
        else f"Señales generadas propuestas: {n_props}"
    )
    body_core = hdr_ctx + (
        f"📊 MOC Pipeline — {hhmm} COT (calc)\n"
        f"{_prop_line}\n\n"
        + ("\n\n".join(lines_body) if lines_body else "(sin deltas sobre umbral)") + "\n\n"
        + f"Aprobá bloque: /execute_all_moc {session_uid}\n"
        + "Individual: /execute-signal {id}\nVentana hasta ~14:59 COT (expire automático)."
    )
    body = body_core
    if dry_run:
        print("\n--- Telegram body (dry-run, no enviado) ---\n")
        print(body)
        print("--- fin body ---\n")
    else:
        ok_body = send_quant_alert_message(_tprefix + body)
        outbound_any_ok |= ok_body
        if not ok_body:
            _moc_notify_telegram_safe(
                "calc",
                "Calc finalizó (exit 0) pero el resumen principal no obtuvo confirmación HTTP 2xx. "
                "Revisa `telegram_outbound_ok` en stdout y logs `[quant_job]`.",
                dry_run=False,
            )

    tick_list = sorted({str(row.get("ticker") or "").upper() for row in mandates if row.get("ticker")})

    regime_meta: dict[str, Any] | None = None
    inv_meta: dict[str, Any] | None = None
    if regime_snapshot:
        regime_meta = dict(regime_snapshot)
        regime_meta["macro_context_snippets"] = [
            str(x)[:120] for x in (regime_meta.get("macro_context_snippets") or [])[:3]
        ]
    if investor_profile:
        inv_meta = {
            "risk_tolerance": investor_profile.get("risk_tolerance"),
            "max_drawdown_tolerance": investor_profile.get("max_drawdown_tolerance"),
            "excluded_tickers": (investor_profile.get("excluded_tickers") or [])[:16],
            "time_horizon": investor_profile.get("time_horizon"),
            "experience_level": investor_profile.get("experience_level"),
            "n_raw_chunks": len(investor_profile.get("raw_chunk_summaries") or []),
        }
    summary_payload: dict[str, Any] = {
        "session_uid": session_uid,
        "macro_vss_enabled": macro_vss_on,
        "n_proposed_signals": n_props,
        "equity_seen": equity,
        "summaries": summaries[:50],
        "tickers_evidence": tk_evidence,
    }
    if regime_meta:
        summary_payload["regime"] = regime_meta
    if inv_meta:
        summary_payload["investor_profile"] = inv_meta
    summary_json = json.dumps(summary_payload, ensure_ascii=False)
    if dry_run:
        print(
            "[moc] (dry-run) omitido INSERT quant_core.session_ticks; resumen JSON (trunc preview):",
            summary_json[:400] + ("…" if len(summary_json) > 400 else ""),
        )
    else:
        enqueue_vault_sql(
            db_path=vault_path,
            sql=(
                "INSERT INTO quant_core.session_ticks "
                "(session_uid, tick_number, tickers_processed, signals_proposed, cfd_summary, outcome) "
                "VALUES (?, (SELECT COALESCE(MAX(tick_number), 0) + 1 FROM quant_core.session_ticks sx WHERE sx.session_uid = ?), ?, ?, ?, 'MOC_CALC')"
            ),
            params=[session_uid, session_uid, tick_list, float(n_props), summary_json],
            tenant_id=os.environ.get("DUCKCLAW_QUANT_TENANT_ID", "default"),
            user_id_override=uid_infer,
            timeout_sec=60.0,
        )
    _sem_log_ok = str(os.environ.get("DUCKCLAW_MOC_SEMANTIC_LOG") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )
    if _sem_log_ok and not dry_run:
        try:
            _sem_blob = (
                hdr_ctx.strip()
                + "\n\n📌 MOC resumen ejecutable:\n"
                + body_core.strip()
                + "\n"
            ).strip()
            _sem_blob = _sem_blob[:7950]
            _mid = str(uuid.uuid4())
            ok_ins, detail_ins = enqueue_vault_sql(
                db_path=vault_path,
                sql=(
                    "INSERT INTO main.semantic_memory "
                    "(id, content, source, embedding, embedding_status) "
                    "VALUES (?, ?, ?, NULL, 'PENDING')"
                ),
                params=[_mid, _sem_blob, "moc_pipeline_calc"],
                tenant_id=os.environ.get("DUCKCLAW_QUANT_TENANT_ID", "default"),
                user_id_override=uid_infer,
                timeout_sec=60.0,
            )
            if not ok_ins:
                print("[moc] semantic_memory log:", detail_ins[:200], file=sys.stderr)
        except Exception as exc:  # noqa: BLE001
            print("[moc] semantic_memory log failed:", exc, file=sys.stderr)
    elif dry_run and _sem_log_ok:
        print("[moc] (dry-run) omitido INSERT main.semantic_memory (MOC_SEMANTIC_LOG activo)")

    if not dry_run and active_uid_for_accum.strip():
        fin_sql = (
            "UPDATE quant_core.intraday_moc_accum SET finalized_at = CURRENT_TIMESTAMP "
            "WHERE session_uid = ? AND trading_date = CAST(? AS DATE) AND finalized_at IS NULL"
        )
        ok_fin, err_fin = enqueue_vault_sql(
            db_path=vault_path,
            sql=fin_sql,
            params=[active_uid_for_accum.strip(), trading_day_iso],
            tenant_id=os.environ.get("DUCKCLAW_QUANT_TENANT_ID", "default"),
            user_id_override=uid_infer,
            timeout_sec=60.0,
        )
        if not ok_fin:
            print("[moc] finalize intraday_moc_accum:", err_fin, file=sys.stderr)

    print(
        json.dumps(
            {
                "session_uid": session_uid,
                "proposals": n_props,
                "dry_run": dry_run,
                "intraday_accum_tickers": sorted(accum_by_ticker.keys()),
                "telegram_outbound_ok": outbound_any_ok if not dry_run else None,
            },
            ensure_ascii=False,
        )
    )
    return 0


def run_remind(*, dry_run: bool = False) -> int:
    from scripts.quant._job_common import (
        log_quant_outbound_readiness,
        open_duckclaw_readonly_retry,
        send_quant_alert_message,
    )

    if dry_run:
        _dry_banner("remind")

    db_path = (os.environ.get("DUCKCLAW_QUANT_SCRIPT_DB") or "").strip()
    if not db_path or not Path(db_path).expanduser().is_file():
        print("[moc] DUCKCLAW_QUANT_SCRIPT_DB inválido (remind)", file=sys.stderr)
        _moc_notify_telegram_safe(
            "remind",
            "Fallo de configuración: DUCKCLAW_QUANT_SCRIPT_DB inválido o archivo inexistente.",
            dry_run=dry_run,
        )
        return 2
    if not dry_run:
        log_quant_outbound_readiness("moc_pipeline", phase="remind")
    su = _moc_store_read()
    if not su:
        return 0
    db = open_duckclaw_readonly_retry(str(Path(db_path).expanduser().resolve()))
    esc = su.replace("'", "''")
    raw = db.query(
        "SELECT CAST(COUNT(*) AS BIGINT) AS c FROM quant_core.trade_signals "
        f"WHERE session_uid = '{esc}' AND strategy_name = '{_STRATEGY}' AND status = 'PENDING_HITL'"
    )
    rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
    c = int((rows[0] or {}).get("c") or 0) if rows and isinstance(rows[0], dict) else 0
    if c > 0:
        remind_body = (
            _moc_telegram_phase_prefix("remind")
            + f"📝 MOC HITL recordatorio (fase remind — no ejecuta órdenes IBKR) — "
            f"{c} señales `moc_hrp_cfd` en `PENDING_HITL`.\n"
            f"Ejecutá en bloque antes del expire (~14:59 COT):\n`/execute_all_moc {su}`\n"
            "Por defecto el job **calc** PM2 activa auto-ejecución batch (`DUCKCLAW_MOC_PIPELINE_AUTO_EXECUTE`); "
            "`DUCKCLAW_MOC_PIPELINE_AUTO_EXECUTE=0` si querés solo HITL."
        )
        if dry_run:
            print(f"[moc] (dry-run) alerta que NO se envía:\n{remind_body}")
        else:
            if not send_quant_alert_message(remind_body):
                _moc_notify_telegram_safe(
                    "remind",
                    f"HITL pendientes ({c}) pero el recordatorio principal no se entregó; revisa outbound.",
                    dry_run=False,
                )
    elif dry_run:
        print("[moc] (dry-run) remind: 0 señales PENDING_HITL para session_uid store")
    elif not dry_run:
        _moc_notify_telegram_safe(
            "remind",
            "Ciclo OK: 0 señales `PENDING_HITL` para el session_uid del store MOC.",
            dry_run=dry_run,
        )
    return 0


def run_expire(*, dry_run: bool = False) -> int:
    from scripts.quant._job_common import (
        enqueue_vault_sql,
        infer_vault_user_id,
        log_quant_outbound_readiness,
        open_duckclaw_readonly_retry,
        send_quant_alert_message,
    )

    if dry_run:
        _dry_banner("expire")

    db_path = (os.environ.get("DUCKCLAW_QUANT_SCRIPT_DB") or "").strip()
    if not db_path or not Path(db_path).expanduser().is_file():
        print("[moc] DUCKCLAW_QUANT_SCRIPT_DB inválido (expire)", file=sys.stderr)
        _moc_notify_telegram_safe(
            "expire",
            "Fallo de configuración: DUCKCLAW_QUANT_SCRIPT_DB inválido o archivo inexistente.",
            dry_run=dry_run,
        )
        return 2
    vault_path = str(Path(db_path).expanduser().resolve())
    uid_infer = infer_vault_user_id(vault_path)
    su = _moc_store_read()

    sub_pred = (
        "status = 'PENDING_HITL' AND COALESCE(strategy_name, '') = ? "
        "AND ts < CURRENT_TIMESTAMP - INTERVAL '15 minutes'"
    )
    params_x: list[Any] = [_STRATEGY]
    if su:
        sub_pred += " AND session_uid = ?"
        params_x.append(su)

    if dry_run:
        db = open_duckclaw_readonly_retry(vault_path)
        esc_st = _STRATEGY.replace("'", "''")
        su_filter = ""
        if su:
            esc_su = str(su).replace("'", "''")
            su_filter = f" AND session_uid = '{esc_su}'"
        count_sql = (
            "SELECT CAST(COUNT(*) AS BIGINT) AS c FROM quant_core.trade_signals WHERE "
            f"status = 'PENDING_HITL' AND COALESCE(strategy_name, '') = '{esc_st}' "
            f"AND ts < CURRENT_TIMESTAMP - INTERVAL '15 minutes'{su_filter}"
        )
        raw_c = db.query(count_sql)
        rows_c = json.loads(raw_c) if isinstance(raw_c, str) else (raw_c or [])
        n_exp = int((rows_c[0] or {}).get("c") or 0) if rows_c and isinstance(rows_c[0], dict) else 0
        print(
            f"[moc] (dry-run) filas que EXPIRARÍAN (quant_core, >15m, strategy={_STRATEGY}): {n_exp}"
        )
        exp_msg = (
            "⏰ Ventana MOC cerrada. Señales `moc_hrp_cfd` en `PENDING_HITL` &gt; 15 min → `EXPIRED`. "
            "(Otras `strategy_name` no las modifica esta fase expire.)"
        )
        print(f"[moc] (dry-run) alerta que NO se envía:\n{exp_msg}")
        return 0

    log_quant_outbound_readiness("moc_pipeline", phase="expire")

    sql_fw = (
        "UPDATE finance_worker.trade_signals SET status = 'EXPIRED' "
        "WHERE signal_id IN ("
        "SELECT signal_id FROM quant_core.trade_signals WHERE " + sub_pred + ")"
    )
    ok_fw, err_fw = enqueue_vault_sql(
        db_path=vault_path,
        sql=sql_fw,
        params=list(params_x),
        tenant_id=os.environ.get("DUCKCLAW_QUANT_TENANT_ID", "default"),
        user_id_override=uid_infer,
        timeout_sec=60.0,
    )
    if not ok_fw:
        print("[moc] expire finance_worker:", err_fw, file=sys.stderr)

    sql_qc = (
        "UPDATE quant_core.trade_signals SET status = 'EXPIRED', updated_at = CURRENT_TIMESTAMP "
        "WHERE " + sub_pred
    )
    ok, err = enqueue_vault_sql(
        db_path=vault_path,
        sql=sql_qc,
        params=list(params_x),
        tenant_id=os.environ.get("DUCKCLAW_QUANT_TENANT_ID", "default"),
        user_id_override=uid_infer,
        timeout_sec=60.0,
    )
    if not ok:
        print("[moc] expire quant_core:", err, file=sys.stderr)
    expire_lines = [
        _moc_telegram_phase_prefix("expire").rstrip(),
        "⏰ Ventana MOC cerrada. Señales `moc_hrp_cfd` en `PENDING_HITL` &gt; 15 min → `EXPIRED`. "
        "(Otras `strategy_name` no las modifica esta fase expire.)",
    ]
    if not ok_fw:
        expire_lines.append(f"Aviso escritura finance_worker: {(err_fw or '')[:500]}")
    if not ok:
        expire_lines.append(f"Aviso escritura quant_core: {(err or '')[:500]}")
    expire_body = "\n\n".join(expire_lines)
    if not send_quant_alert_message(expire_body):
        _moc_notify_telegram_safe(
            "expire",
            "Expire ejecutado pero el mensaje de resumen no se entregó a Telegram; revisa escrituras y outbound.",
            dry_run=False,
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Pipeline MOC (Core-Satellite CFD).")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo lectura + stdout; sin Telegram, colas, propose ni ~/.duckclaw_moc_session.json",
    )
    parser.add_argument(
        "--dry-run-notify",
        action="store_true",
        help="Solo con --dry-run: al terminar envía un Telegram breve (validación outbound). "
        "Equiv. env DUCKCLAW_MOC_DRY_RUN_NOTIFY=1.",
    )
    args = parser.parse_args()
    dry_run = bool(args.dry_run)
    dry_run_notify = bool(args.dry_run_notify) or (
        (os.getenv("DUCKCLAW_MOC_DRY_RUN_NOTIFY") or "").strip().lower() in ("1", "true", "yes")
    )
    if dry_run_notify and not dry_run:
        print(
            "[moc] --dry-run-notify (o DUCKCLAW_MOC_DRY_RUN_NOTIFY) requiere --dry-run",
            file=sys.stderr,
        )
        return 2

    phase = (os.environ.get("MOC_PHASE") or "calc").strip().lower()
    rc = 2
    try:
        if phase == "calc":
            rc = run_calc(dry_run=dry_run)
        elif phase == "remind":
            rc = run_remind(dry_run=dry_run)
        elif phase == "expire":
            rc = run_expire(dry_run=dry_run)
        else:
            print("MOC_PHASE debe ser calc|remind|expire", file=sys.stderr)
            if not dry_run:
                _moc_notify_telegram_safe(
                    phase or "calc",
                    f"MOC_PHASE inválido `{phase!r}` (esperado calc|remind|expire).",
                    dry_run=dry_run,
                )
            rc = 2
    except Exception as exc:
        print(f"[moc] error no manejado phase={phase!r}: {exc}", file=sys.stderr, flush=True)
        if not dry_run:
            _moc_notify_telegram_safe(
                phase if phase in ("calc", "remind", "expire") else "calc",
                f"Error no manejado: {type(exc).__name__}: {str(exc)[:2000]}",
                dry_run=dry_run,
            )
        rc = 1
    finally:
        if dry_run and dry_run_notify:
            ph = phase if phase in ("calc", "remind", "expire") else "calc"
            host_env = (os.getenv("HOSTNAME") or os.getenv("COMPUTERNAME") or "").strip()
            try:
                host = host_env or socket.gethostname() or "?"
            except Exception:
                host = host_env or "?"
            _moc_outbound_dry_run_ping(
                ph,
                f"exit={rc} · MOC_PHASE={phase!r} · host={host[:120]}\n"
                "Simulación: sin escrituras DB ni Telegram de prod salvo este ping.",
            )
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
