"""
Sleep-time Dreamer: Light (RO DuckDB) → REM (MLX + fallback API) → Deep (quant state deltas).

Ejecutar vía PM2 (02:00 COT) o manualmente con ``uv run ... dreamer_job.py``.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb

def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for d in [here, *here.parents]:
        if (d / "packages" / "agents").is_dir():
            return d
    return here.parents[5]


_REPO_ROOT = _repo_root()
GOLDEN_DATASET_PATH = "packages/agents/train/conversation_traces/golden_dataset.jsonl"

CHUNK_SIZE = 50
MAX_INSIGHTS_PER_RUN = 20
LOOKBACK_HOURS = 24

EXCLUSION_PATTERNS = [
    "Ceguera Sensorial",
    "SANDBOX_",
    "LAKE_EMPTY_BARS",
    "PIPELINE_FROZEN",
    "SKIP_TRACE",
    "DEBUG_DUMP",
]

CONSOLIDATION_PROMPT = """Eres un asistente que consolida fragmentos de conversación en memoria semántica.
Devuelve ÚNICAMENTE un objeto JSON válido (sin fences markdown) con esta forma exacta:
{"insights":[{"topic":"etiqueta breve","insight":"una oración","confidence":0.0}]}
Las claves insight usan hechos inferibles del texto; confidence entre 0 y 1.
"""


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
_log = logging.getLogger("duckclaw.dreamer")


def _golden_dataset_resolved() -> Path:
    rel = os.environ.get("DUCKCLAW_DREAMER_GOLDEN_PATH", GOLDEN_DATASET_PATH).strip()
    p = Path(rel)
    return p if p.is_absolute() else _REPO_ROOT / p


def assert_redis_available_or_exit() -> None:
    """Sin Redis / cola quant no se encola nada: fallo rápido al inicio."""
    url = (os.environ.get("REDIS_URL") or os.environ.get("DUCKCLAW_REDIS_URL") or "").strip()
    if not url:
        _log.error("REDIS_URL / DUCKCLAW_REDIS_URL ausente; abortando dreamer.")
        sys.exit(1)
    try:
        import redis

        r = redis.from_url(url, decode_responses=True)
        r.ping()
    except Exception as exc:  # noqa: BLE001
        _log.error("Redis no disponible (ping falló): %s", exc)
        sys.exit(1)


def _ensure_dreamer_target_db_from_repo_dotenv() -> None:
    """
    PM2 a veces mantiene el entorno del primer ``start`` y no re-ejecuta ``loadDotenv``
    del ecosystem al hacer ``restart``. Si ``DUCKCLAW_DREAMER_TARGET_DB`` falta o viene
    vacía, tomar la línea desde ``${DUCKCLAW_REPO_ROOT}/.env`` (misma convención que otros entrypoints).
    """
    if (os.environ.get("DUCKCLAW_DREAMER_TARGET_DB") or "").strip():
        return
    rr = (os.environ.get("DUCKCLAW_REPO_ROOT") or "").strip() or str(_REPO_ROOT)
    env_path = Path(rr) / ".env"
    if not env_path.is_file():
        return
    try:
        for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
            t = line.strip()
            if not t or t.startswith("#") or "=" not in t:
                continue
            k, _, v = t.partition("=")
            k, v = k.strip(), v.strip()
            if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                v = v[1:-1]
            if k == "DUCKCLAW_DREAMER_TARGET_DB" and v:
                os.environ["DUCKCLAW_DREAMER_TARGET_DB"] = v
                _log.info("DUCKCLAW_DREAMER_TARGET_DB aplicada desde %s", env_path)
                return
    except OSError:
        pass


def _ensure_dreamer_conversation_db_from_repo_dotenv() -> None:
    if (os.environ.get("DUCKCLAW_DREAMER_CONVERSATION_DB") or "").strip():
        return
    rr = (os.environ.get("DUCKCLAW_REPO_ROOT") or "").strip() or str(_REPO_ROOT)
    env_path = Path(rr) / ".env"
    if not env_path.is_file():
        return
    try:
        for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
            t = line.strip()
            if not t or t.startswith("#") or "=" not in t:
                continue
            k, _, v = t.partition("=")
            k, v = k.strip(), v.strip()
            if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                v = v[1:-1]
            if k == "DUCKCLAW_DREAMER_CONVERSATION_DB" and v:
                os.environ["DUCKCLAW_DREAMER_CONVERSATION_DB"] = v
                _log.info("DUCKCLAW_DREAMER_CONVERSATION_DB aplicada desde %s", env_path)
                return
    except OSError:
        pass


def resolve_target_db_path() -> str:
    """
    DuckDB donde el writer aplica deltas (``SEMANTIC_MEMORY_UPSERT``, etc.).

    Suele ser el vault Quant u otro archivo explícito; no tiene por qué coincidir
    con el .duckdb donde Telegram escribió ``telegram_conversation``.
    """
    from duckclaw.gateway_db import get_gateway_db_path, resolve_env_duckdb_path

    _ensure_dreamer_target_db_from_repo_dotenv()

    for key in ("DUCKCLAW_DREAMER_TARGET_DB", "DUCKCLAW_DB_PATH"):
        raw = (os.environ.get(key) or "").strip()
        if raw:
            p = resolve_env_duckdb_path(raw)
            _log.info("Dreamer DuckDB destino (explícito %s): %s", key, p)
            return p
    try:
        gw = (get_gateway_db_path() or "").strip()
        if gw:
            _log.info("Dreamer DuckDB destino (hub gateway): %s", gw)
            return gw
    except Exception:
        pass
    raw_q = (os.environ.get("DUCKCLAW_QUANT_TRADER_DB_PATH") or "").strip()
    if raw_q:
        p = resolve_env_duckdb_path(raw_q)
        _log.info("Dreamer DuckDB destino (fallback Quant vault): %s", p)
        return p
    _log.error(
        "Defina DUCKCLAW_DREAMER_TARGET_DB o rutas de gateway / DUCKCLAW_QUANT_TRADER_DB_PATH en .env."
    )
    sys.exit(1)


def resolve_conversation_db_path(*, target_fallback: str) -> str:
    """
    DuckDB de solo lectura para ``telegram_conversation`` / ``task_audit_log``.

    Por defecto el **hub** del Gateway (donde suelen estar las tablas de Telegram).
    Override: ``DUCKCLAW_DREAMER_CONVERSATION_DB`` (y línea homónima en ``.env``).
    Si no hay hub, reutiliza ``target_fallback`` (un solo archivo).
    """
    from duckclaw.gateway_db import get_gateway_db_path, resolve_env_duckdb_path

    _ensure_dreamer_conversation_db_from_repo_dotenv()
    raw = (os.environ.get("DUCKCLAW_DREAMER_CONVERSATION_DB") or "").strip()
    if raw:
        p = resolve_env_duckdb_path(raw)
        _log.info("Dreamer DuckDB lectura conversación (CONVERSATION_DB): %s", p)
        return p
    try:
        gw = (get_gateway_db_path() or "").strip()
        if gw:
            _log.info("Dreamer DuckDB lectura conversación (hub gateway): %s", gw)
            return gw
    except Exception:
        pass
    _log.info("Dreamer DuckDB lectura conversación (igual que destino): %s", target_fallback)
    return target_fallback


def resolve_user_id(tenant_id: str) -> str:
    env_uid = (os.environ.get("DUCKCLAW_DREAMER_USER_ID") or "").strip()
    return env_uid or tenant_id


def _serialize_cell(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _rows(serialized_cols: list[str], fetch: list[tuple[Any, ...]]) -> list[dict[str, Any]]:
    return [{serialized_cols[i]: _serialize_cell(row[i]) for i in range(len(serialized_cols))} for row in fetch]


def load_raw_history(tenant_id: str, db_path: str) -> tuple[dict[str, Any], bool]:
    """
    Una conexión RO; todas las lecturas; cerrar antes de REM.
    Retorna (history, empty_exit) — si empty_exit, el caller hace sys.exit(0).
    """
    cid = int(tenant_id)
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("America/Bogota")
        now = datetime.now(tz)
    except Exception:
        now = datetime.now()
    cutoff = now - timedelta(hours=LOOKBACK_HOURS)

    con = duckdb.connect(db_path, read_only=True)
    try:
        conv: list[dict[str, Any]] = []
        audit: list[dict[str, Any]] = []
        try:
            rel = con.execute(
                """
                SELECT chat_id, role, content, received_at
                FROM telegram_conversation
                WHERE chat_id = ? AND received_at >= ?
                ORDER BY received_at ASC
                """,
                [cid, cutoff],
            )
            cols = [d[0] for d in rel.description or []]
            conv = _rows(cols, rel.fetchall())
        except Exception as exc:  # noqa: BLE001
            _log.warning("Lectura telegram_conversation omitida: %s", exc)
        try:
            rel2 = con.execute(
                """
                SELECT task_id, tenant_id, worker_id, query_prefix, status, duration_ms, created_at, plan_title
                FROM task_audit_log
                WHERE tenant_id = ? AND created_at >= ?
                ORDER BY created_at ASC
                """,
                [tenant_id, cutoff],
            )
            cols2 = [d[0] for d in rel2.description or []]
            audit = _rows(cols2, rel2.fetchall())
        except Exception as exc:  # noqa: BLE001
            _log.warning("Lectura task_audit_log omitida: %s", exc)
    finally:
        con.close()

    if not conv and not audit:
        _log.info("Sin filas en ventana %sh para tenant/chat_id=%s; nada que soñar.", LOOKBACK_HOURS, tenant_id)
        return {}, True

    return {"conversation": conv, "audit_log": audit}, False


def _llm_invoke_text(llm: Any, full_prompt: str) -> str:
    raw = llm.invoke(full_prompt)
    if hasattr(raw, "content") and raw.content is not None:
        return str(raw.content)
    return str(raw)


def _build_llm_primary() -> Any:
    from duckclaw.integrations.llm_providers import build_llm

    env_p = (os.environ.get("DUCKCLAW_LLM_PROVIDER") or "mlx").strip().lower()
    llm = build_llm(env_p, prefer_env_provider=True)
    if llm is None:
        llm = build_llm("mlx", prefer_env_provider=False)
    if llm is None:
        _log.error("No se pudo construir el LLM principal (mlx / env).")
        sys.exit(1)
    return llm


def _build_llm_deepseek_fallback() -> Any | None:
    if not (os.environ.get("DEEPSEEK_API_KEY") or "").strip():
        return None
    from duckclaw.integrations.llm_providers import build_llm

    return build_llm("deepseek", prefer_env_provider=False)


def _invoke_with_mlx_fallback(llm: Any, prompt: str) -> str:
    try:
        return _llm_invoke_text(llm, prompt)
    except Exception as exc:  # noqa: BLE001
        _log.warning("invoke LLM principal falló: %s", exc)
        fb = _build_llm_deepseek_fallback()
        if fb is None:
            _log.error("Sin fallback API (defina DEEPSEEK_API_KEY).")
            sys.exit(1)
        try:
            return _llm_invoke_text(fb, prompt)
        except Exception as exc2:  # noqa: BLE001
            _log.exception("Fallback DeepSeek también falló: %s", exc2)
            sys.exit(1)


def _parse_insights_json(text: str) -> list[dict[str, Any]]:
    s = text.strip()
    if "```" in s:
        start = s.find("{")
        end = s.rfind("}")
        if start >= 0 and end > start:
            s = s[start : end + 1]
    data = json.loads(s)
    if not isinstance(data, dict):
        return []
    ins = data.get("insights")
    if not isinstance(ins, list):
        return []
    out: list[dict[str, Any]] = []
    for it in ins:
        if not isinstance(it, dict):
            continue
        topic = str(it.get("topic") or "").strip()
        insight = str(it.get("insight") or it.get("insight_text") or "").strip()
        try:
            conf = float(it.get("confidence", 0.0))
        except (TypeError, ValueError):
            conf = 0.0
        if topic and insight:
            out.append({"topic": topic, "insight": insight, "confidence": conf})
    return out


def consolidate_memory(history: dict[str, Any], llm: Any) -> list[dict[str, Any]]:
    conv = list(history.get("conversation") or [])
    if not conv:
        return []

    lines = [f"{r.get('role')}: {r.get('content')}\n" for r in conv]
    aggregated: list[dict[str, Any]] = []
    seen: set[str] = set()

    for start in range(0, len(lines), CHUNK_SIZE):
        chunk = "".join(lines[start : start + CHUNK_SIZE])
        prompt = f"{CONSOLIDATION_PROMPT}\n\n{chunk}"
        try:
            reply = _invoke_with_mlx_fallback(llm, prompt)
            chunk_insights = _parse_insights_json(reply)
        except (json.JSONDecodeError, ValueError):
            _log.warning("JSON inválido en chunk %s; se omite.", start // max(CHUNK_SIZE, 1))
            continue
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001
            _log.warning("Error parseando/consolidando chunk: %s", exc)
            continue

        for it in chunk_insights:
            if float(it.get("confidence") or 0.0) < 0.5:
                continue
            key = (str(it["topic"]) + str(it["insight"]))[:80].lower()
            if key in seen:
                continue
            seen.add(key)
            aggregated.append(it)
            if len(aggregated) >= MAX_INSIGHTS_PER_RUN:
                return aggregated[:MAX_INSIGHTS_PER_RUN]

    return aggregated[:MAX_INSIGHTS_PER_RUN]


def emit_memory_deltas(
    insights: list[dict[str, Any]],
    tenant_id: str,
    user_id: str,
    target_db_path: str,
) -> bool:
    """Devuelve True si al menos un LPUSH tuvo éxito cuando hay insights con contenido."""
    from duckclaw.forge.skills.quant_state_delta import push_quant_state_delta_sync

    if not insights:
        return True
    any_ok = False
    for it in insights:
        payload = {
            "tenant_id": tenant_id,
            "delta_type": "SEMANTIC_MEMORY_UPSERT",
            "user_id": user_id,
            "target_db_path": target_db_path,
            "mutation": {
                "table": "main.semantic_memory",
                "topic": it["topic"],
                "insight": it["insight"],
                "confidence_score": float(it.get("confidence") or 0.0),
                "source": "dreamer_job",
            },
        }
        ok = push_quant_state_delta_sync(payload)
        _log.info("SEMANTIC_MEMORY_UPSERT topic=%r ok=%s", it.get("topic"), ok)
        if ok:
            any_ok = True
        else:
            _log.warning("LPUSH falló para insight topic=%r; se continúa.", it.get("topic"))
    return any_ok


def _matches_exclusion(content: str) -> bool:
    low = content.lower()
    return any(pat.lower() in low for pat in EXCLUSION_PATTERNS)


def is_golden_turn(role: str, content: str) -> bool:
    """Curación relajada: sólo rol usuario, longitud y exclusiones (sin tool_calls en SQL)."""
    if (role or "").strip().lower() not in ("user", "human"):
        return False
    body = (content or "").strip()
    if len(body) < 24:
        return False
    return not _matches_exclusion(body)


def curate_golden_dataset(history: dict[str, Any], tenant_id: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    for row in list(history.get("conversation") or []):
        role = str(row.get("role") or "")
        content = str(row.get("content") or "")
        if not is_golden_turn(role, content):
            continue
        record = {
            "messages": [{"role": role, "content": content}],
            "source": "dreamer_curate",
            "timestamp": row.get("received_at") or "",
            "tenant_id": tenant_id,
        }
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def compact_old_history(
    tenant_id: str,
    user_id: str,
    compaction_db_path: str,
    *,
    days: int = 7,
) -> bool:
    from duckclaw.forge.skills.quant_state_delta import push_quant_state_delta_sync

    payload = {
        "tenant_id": tenant_id,
        "delta_type": "CONVERSATION_COMPACTION",
        "user_id": user_id,
        "target_db_path": compaction_db_path,
        "mutation": {
            "table": "telegram_conversation",
            "chat_id": int(tenant_id),
            "days": int(days),
        },
    }
    ok = push_quant_state_delta_sync(payload)
    _log.info("CONVERSATION_COMPACTION days=%s ok=%s", days, ok)
    return ok


def _deep_phase_allows_compaction(insights: list[dict[str, Any]], pushed_any: bool) -> bool:
    if not insights:
        return True
    return pushed_any


def main() -> None:
    parser = argparse.ArgumentParser(description="Dreamer sleep-time job (Light → REM → Deep).")
    parser.add_argument("--tenant-id", required=True, help="Telegram chat_id (numérico) del tenant.")
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Encola CONVERSATION_COMPACTION tras Deep exitoso (recomendado PM2).",
    )
    parser.add_argument(
        "--compact-days",
        type=int,
        default=7,
        help="Antigüedad mínima en días para borrar filas de telegram_conversation.",
    )
    args = parser.parse_args()
    tenant_id = str(args.tenant_id).strip()
    _log.info("Dreamer inicio tenant_id=%s", tenant_id)

    assert_redis_available_or_exit()
    target_db_path = resolve_target_db_path()
    conversation_db_path = resolve_conversation_db_path(target_fallback=target_db_path)
    user_id = resolve_user_id(tenant_id)

    history, empty_exit = load_raw_history(tenant_id, conversation_db_path)
    if empty_exit:
        _log.info("Dreamer terminado sin trabajo (exit 0).")
        sys.exit(0)

    llm = _build_llm_primary()
    insights = consolidate_memory(history, llm)
    pushed_any = emit_memory_deltas(insights, tenant_id, user_id, target_db_path)

    golden_path = _golden_dataset_resolved()
    try:
        curate_golden_dataset(history, tenant_id, golden_path)
    except Exception as exc:  # noqa: BLE001
        _log.warning("Curación golden falló (no aborta el job): %s", exc)

    if args.compact and _deep_phase_allows_compaction(insights, pushed_any):
        compact_old_history(tenant_id, user_id, conversation_db_path, days=args.compact_days)
    elif args.compact:
        _log.info("Omitiendo compactación: insights pendientes pero sin LPUSH exitoso.")

    _log.info("Dreamer completado tenant_id=%s insights=%s", tenant_id, len(insights))


if __name__ == "__main__":
    main()
