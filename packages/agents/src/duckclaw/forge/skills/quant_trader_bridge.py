def _cancel_trade_signal_impl(
    db: Any,
    *,
    signal_id: str,
    reason: str = "",
    force: bool = False,
) -> str:
    """
    Cancela una señal en el ledger HITL (finance_worker.trade_signals y
    quant_core.trade_signals) vía execute_cancel_signal desde on_the_fly_commands.

    No envía órdenes al broker — solo marca CANCELLED en el ledger.
    """
    from duckclaw.graphs.on_the_fly_commands import execute_cancel_signal

    sid = (signal_id or "").strip().lower()
    if not sid:
        return json.dumps({"error": "signal_id requerido"}, ensure_ascii=False)

    cid = get_quant_tool_chat_id() or "default"
    tid = get_quant_tool_tenant_id() or "default"
    force_flag = "--force" if force else ""
    args = f"{sid} {force_flag}".strip()

    try:
        result = execute_cancel_signal(db, cid, args, tenant_id=tid)
    except Exception as exc:
        return json.dumps(
            {"error": f"cancel_trade_signal falló: {str(exc)[:500]}"},
            ensure_ascii=False,
        )

    out: dict[str, Any] = {
        "status": "CANCELLED",
        "signal_id": sid,
        "reason": (reason or "").strip() or "Cancelado por Quant Trader",
        "message": str(result)[:2000],
    }
    return json.dumps(out, ensure_ascii=False)
