#!/usr/bin/env python3
"""
Pipeline MOC Core-Satellite CFD — specs/features/Core-Satellite HRP Weekly + MOC CFD.md

``MOC_PHASE=calc|remind|expire`` (cron weekday ~14:40 / 14:50 / 14:55 America/Bogota).

``--dry-run``: mismas lecturas (vault read-only, IBKR, allocations); sin Telegram, colas DB,
``propose_trade_signal``, ``~/.duckclaw_moc_session.json`` ni inserts semánticos.
"""

from __future__ import annotations

import argparse
import json
import os
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
        open_duckclaw_readonly_retry,
        send_quant_alert_message,
    )

    if dry_run:
        _dry_banner("calc")

    db_path = (os.environ.get("DUCKCLAW_QUANT_SCRIPT_DB") or "").strip()
    if not db_path or not Path(db_path).expanduser().is_file():
        print("[moc] DUCKCLAW_QUANT_SCRIPT_DB inválido", file=sys.stderr)
        return 2
    vault_path = str(Path(db_path).expanduser().resolve())
    uid_infer = infer_vault_user_id(vault_path)

    bind_quant_market_evidence_chat("__moc__")
    set_quant_tool_db_path(vault_path)
    set_quant_tool_user_id(uid_infer)
    set_quant_tool_tenant_id(os.environ.get("DUCKCLAW_QUANT_TENANT_ID", "default"))

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
            send_quant_alert_message(msg)
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
            send_quant_alert_message(cap_msg)
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
        + "Individual: /execute_signal {id}\nVentana hasta ~14:55 COT (expire automático)."
    )
    body = body_core
    if dry_run:
        print("\n--- Telegram body (dry-run, no enviado) ---\n")
        print(body)
        print("--- fin body ---\n")
    else:
        send_quant_alert_message(body)

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
            },
            ensure_ascii=False,
        )
    )
    return 0


def run_remind(*, dry_run: bool = False) -> int:
    from scripts.quant._job_common import open_duckclaw_readonly_retry, send_quant_alert_message

    if dry_run:
        _dry_banner("remind")

    db_path = (os.environ.get("DUCKCLAW_QUANT_SCRIPT_DB") or "").strip()
    if not db_path or not Path(db_path).expanduser().is_file():
        return 2
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
            f"📝 MOC HITL recordatorio — {c} señales pendientes `PENDING_HITL`.\n"
            f"/execute_all_moc {su}"
        )
        if dry_run:
            print(f"[moc] (dry-run) alerta que NO se envía:\n{remind_body}")
        else:
            send_quant_alert_message(remind_body)
    elif dry_run:
        print("[moc] (dry-run) remind: 0 señales PENDING_HITL para session_uid store")
    return 0


def run_expire(*, dry_run: bool = False) -> int:
    from scripts.quant._job_common import (
        enqueue_vault_sql,
        infer_vault_user_id,
        open_duckclaw_readonly_retry,
        send_quant_alert_message,
    )

    if dry_run:
        _dry_banner("expire")

    db_path = (os.environ.get("DUCKCLAW_QUANT_SCRIPT_DB") or "").strip()
    if not db_path or not Path(db_path).expanduser().is_file():
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
            "⏰ Ventana MOC cerrada. Señales `PENDING_HITL` MOC &gt; 15 min marcadas como EXPIRED."
        )
        print(f"[moc] (dry-run) alerta que NO se envía:\n{exp_msg}")
        return 0

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
    send_quant_alert_message(
        "⏰ Ventana MOC cerrada. Señales `PENDING_HITL` MOC &gt; 15 min marcadas como EXPIRED.",
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Pipeline MOC (Core-Satellite CFD).")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo lectura + stdout; sin Telegram, colas, propose ni ~/.duckclaw_moc_session.json",
    )
    args = parser.parse_args()
    dry_run = bool(args.dry_run)

    phase = (os.environ.get("MOC_PHASE") or "calc").strip().lower()
    if phase == "calc":
        return run_calc(dry_run=dry_run)
    if phase == "remind":
        return run_remind(dry_run=dry_run)
    if phase == "expire":
        return run_expire(dry_run=dry_run)
    print("MOC_PHASE debe ser calc|remind|expire", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
