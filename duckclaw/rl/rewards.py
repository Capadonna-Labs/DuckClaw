"""
Clasificación de recompensas para trazas GRPO Olist.

Evalúa cada traza (prompt, completion) y asigna un reward en [-1.0, 1.0]
según formato, validez de tool_call y coherencia prompt→herramienta.
Deja el dataset listo para entrenamiento GRPO.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from duckclaw.bi.grpo_traces import DEFAULT_TRACE_FILE, load_grpo_traces
from duckclaw.bi.agent import OLIST_BI_TOOL_NAMES

# Ruta por defecto para dataset con rewards
TRAIN_DIR = Path(__file__).resolve().parents[2] / "train"
DEFAULT_REWARDED_FILE = TRAIN_DIR / "grpo_olist_rewarded.jsonl"
DEFAULT_GROUPS_FILE = TRAIN_DIR / "grpo_olist_groups.jsonl"


# Mapeo prompt→tools esperados (keywords en prompt → tools coherentes)
_PROMPT_TOOL_MAP: dict[str, frozenset[str]] = {
    "vendedor": frozenset({"get_top_sellers", "plot_top_sellers_bar"}),
    "seller": frozenset({"get_top_sellers", "plot_top_sellers_bar"}),
    "cliente": frozenset({"get_top_customers_by_sales", "get_customers_to_retain", "plot_top_customers_bar"}),
    "customer": frozenset({"get_top_customers_by_sales", "get_customers_to_retain", "plot_top_customers_bar"}),
    "fidelizar": frozenset({"get_customers_to_retain"}),
    "retener": frozenset({"get_customers_to_retain"}),
    "entrega": frozenset({"get_delivery_metrics", "get_delivery_critical_cases", "plot_delivery_days_histogram"}),
    "delivery": frozenset({"get_delivery_metrics", "get_delivery_critical_cases", "plot_delivery_days_histogram"}),
    "tiempo": frozenset({"get_delivery_metrics", "get_delivery_critical_cases", "plot_delivery_days_histogram"}),
    "días": frozenset({"get_delivery_metrics", "get_delivery_critical_cases", "plot_delivery_days_histogram"}),
    "ventas": frozenset({"get_sales_summary", "get_category_sales", "get_top_sellers", "get_top_customers_by_sales", "plot_category_sales_bar", "plot_category_sales_pie", "get_sales_by_month", "plot_sales_by_month", "plot_sales_by_month_line"}),
    "resumen": frozenset({"get_sales_summary"}),
    "ticket": frozenset({"get_sales_summary"}),
    "review": frozenset({"get_review_metrics", "plot_review_score_pie"}),
    "satisfacción": frozenset({"get_review_metrics", "plot_review_score_pie"}),
    "valoración": frozenset({"get_review_metrics", "plot_review_score_pie"}),
    "categoría": frozenset({"get_category_sales", "plot_category_sales_bar", "plot_category_sales_pie"}),
    "torta": frozenset({"plot_category_sales_pie", "plot_review_score_pie"}),
    "pie": frozenset({"plot_category_sales_pie", "plot_review_score_pie"}),
    "circular": frozenset({"plot_category_sales_pie", "plot_review_score_pie"}),
    "gráfica": frozenset({"plot_category_sales_bar", "plot_category_sales_pie", "plot_top_sellers_bar", "plot_review_score_pie", "plot_delivery_days_histogram", "plot_top_customers_bar", "plot_sales_by_month", "plot_sales_by_month_line", "plot_query"}),
    "gráfico": frozenset({"plot_category_sales_bar", "plot_category_sales_pie", "plot_top_sellers_bar", "plot_review_score_pie", "plot_delivery_days_histogram", "plot_top_customers_bar", "plot_sales_by_month", "plot_sales_by_month_line", "plot_query"}),
    "chart": frozenset({"plot_category_sales_bar", "plot_category_sales_pie", "plot_top_sellers_bar", "plot_review_score_pie", "plot_delivery_days_histogram", "plot_top_customers_bar", "plot_sales_by_month", "plot_sales_by_month_line"}),
    "líneas": frozenset({"plot_sales_by_month_line"}),
    "línea": frozenset({"plot_sales_by_month_line"}),
    "scatter": frozenset({"plot_sales_vs_reviews_scatter", "plot_query"}),
    "dispersión": frozenset({"plot_sales_vs_reviews_scatter", "plot_query"}),
    "heatmap": frozenset({"plot_query"}),
    "mapa de calor": frozenset({"plot_query"}),
    "tabla": frozenset({"list_tables"}),
    "tablas": frozenset({"list_tables"}),
    "mes": frozenset({"get_sales_by_month", "plot_sales_by_month", "plot_sales_by_month_line"}),
}

# Args por defecto para completion sintética BUENA
_TOOL_DEFAULT_ARGS: dict[str, dict[str, Any]] = {
    "list_tables": {},
    "get_top_sellers": {"limit": 10},
    "get_top_customers_by_sales": {"limit": 10},
    "get_category_sales": {"limit": 10},
    "get_sales_summary": {},
    "get_delivery_metrics": {},
    "get_review_metrics": {},
    "get_sales_by_month": {},
    "get_delivery_critical_cases": {"days_threshold": 20, "limit": 30},
    "get_customers_to_retain": {"limit": 10, "min_orders": 2},
    "plot_category_sales_bar": {"limit": 5},
    "plot_category_sales_pie": {"limit": 5},
    "plot_top_sellers_bar": {"limit": 10},
    "plot_top_customers_bar": {"limit": 10},
    "plot_sales_by_month": {"year": 2017},
    "plot_sales_by_month_line": {"year": 2017},
    "plot_delivery_days_histogram": {},
    "plot_review_score_pie": {},
    "export_to_excel": {"sql": "SELECT * FROM olist_orders LIMIT 1000", "sheet_name": "datos", "limit": 1000},
}


def _extract_json_objects(text: str) -> list[str]:
    """Extrae objetos JSON {...} con anidamiento."""
    out: list[str] = []
    i = 0
    while i < len(text):
        if text[i] != "{":
            i += 1
            continue
        start = i
        depth = 0
        for j in range(i, len(text)):
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    out.append(text[start : j + 1])
                    i = j + 1
                    break
        else:
            i += 1
    return out


def _parse_tool_calls_from_completion(completion: str) -> list[dict[str, Any]]:
    """Extrae tool-calls del completion (bloque <tool_call> o texto crudo)."""
    text = re.sub(r"<\|eom_id\|>\s*", "", completion)
    text = re.sub(r"<\|eot_id\|>\s*", "", text)
    block = ""
    m = re.search(r"<tool_call>\s*(.*?)\s*</tool_call>", text, re.DOTALL)
    if m:
        block = m.group(1).strip()
    elif '{"tool"' in text or '{"name"' in text:
        block = text
    out: list[dict[str, Any]] = []
    for raw in _extract_json_objects(block):
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        tool = obj.get("tool") or obj.get("name")
        if tool and tool in OLIST_BI_TOOL_NAMES:
            out.append({"tool": str(tool), "args": obj.get("args") or obj.get("parameters") or {}})
    return out


def _expected_tools_for_prompt(prompt: str) -> frozenset[str]:
    """Devuelve el conjunto de tools coherentes para el prompt."""
    prompt_lower = prompt.lower()
    expected: set[str] = set()
    for keyword, tools in _PROMPT_TOOL_MAP.items():
        if keyword in prompt_lower:
            expected.update(tools)
    if not expected:
        return OLIST_BI_TOOL_NAMES  # Sin keywords claros, cualquier tool válida es aceptable
    return frozenset(expected)


def compute_reward(trace: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    """
    Calcula el reward para una traza y devuelve (reward, breakdown).

    Criterios:
    - Formato: thought, tool_call, answer presentes y en orden (+0.25)
    - JSON válido en tool_call (+0.25)
    - Tools válidas (OLIST_BI_TOOL_NAMES) (+0.25)
    - Sin artefactos <|eot_id|>, <|eom_id|> (+0.1)
    - Coherencia: tools usadas coherentes con prompt (+0.15)
    - Penalización: incoherencia fuerte (-1.0), demasiadas tools innecesarias (-0.2)
    """
    prompt = (trace.get("prompt") or "").strip()
    completion = (trace.get("completion") or "").strip()
    breakdown: dict[str, Any] = {"format": 0.0, "json_valid": 0.0, "tools_valid": 0.0, "no_artifacts": 0.0, "coherence": 0.0, "penalty": 0.0}

    if not completion:
        return -1.0, {**breakdown, "reason": "empty_completion"}

    reward = 0.0

    # 1. Formato estructurado
    has_thought = "<thought>" in completion and "</thought>" in completion
    has_tool_call = "<tool_call>" in completion and "</tool_call>" in completion
    has_answer = "<answer>" in completion and "</answer>" in completion
    order_ok = completion.find("<thought>") < completion.find("<tool_call>") < completion.find("<answer>")
    if has_thought and has_tool_call and has_answer and order_ok:
        reward += 0.25
        breakdown["format"] = 0.25

    # 2. JSON válido en tool_call
    tools_parsed = _parse_tool_calls_from_completion(completion)
    if tools_parsed:
        reward += 0.25
        breakdown["json_valid"] = 0.25

    # 3. Tools válidas
    if tools_parsed and all(t["tool"] in OLIST_BI_TOOL_NAMES for t in tools_parsed):
        reward += 0.25
        breakdown["tools_valid"] = 0.25

    # 4. Sin artefactos
    if "<|eot_id|>" not in completion and "<|eom_id|>" not in completion:
        reward += 0.1
        breakdown["no_artifacts"] = 0.1

    # 5. Coherencia prompt → tools
    expected = _expected_tools_for_prompt(prompt)
    used = {t["tool"] for t in tools_parsed}
    if expected and used:
        overlap = len(expected & used) / len(used) if used else 0
        if overlap > 0:
            reward += 0.15 * min(1.0, overlap + 0.5)
            breakdown["coherence"] = 0.15 * min(1.0, overlap + 0.5)
        elif expected != OLIST_BI_TOOL_NAMES:
            # Incoherencia: prompt pide X pero tools son Y
            reward -= 0.5
            breakdown["penalty"] = -0.5

    # 6. Penalización: demasiadas tools cuando una bastaría
    if len(tools_parsed) > 3 and len(expected) < 3 and expected:
        reward -= 0.2
        breakdown["penalty"] = breakdown.get("penalty", 0) - 0.2

    reward = max(-1.0, min(1.0, reward))
    return reward, breakdown


def _normalize_prompt_for_grouping(prompt: str) -> str:
    """Normaliza prompt para agrupar variantes (cuántas/cuantas, mayúsculas, etc.)."""
    if not prompt:
        return ""
    s = prompt.strip().lower()
    for old, new in [("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ü", "u"), ("ñ", "n")]:
        s = s.replace(old, new)
    return " ".join(s.split())


def _normalize_for_heuristic(prompt: str) -> str:
    """Normaliza prompt para matching heurístico (minúsculas, sin acentos)."""
    if not prompt:
        return ""
    s = prompt.strip().lower()
    for old, new in [("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ü", "u"), ("ñ", "n")]:
        s = s.replace(old, new)
    return " ".join(s.split())


def _synthesize_tool_for_prompt(prompt: str) -> tuple[str, dict[str, Any]] | None:
    """
    Mapeo heurístico estricto BI. Devuelve (tool, args) solo si hay match claro.
    None si no hay match → evita Tool Collapse (no enseñar herramienta equivocada).
    """
    p = _normalize_for_heuristic(prompt)
    if not p:
        return None

    # 1. Tabla/Tablas/Disponible → list_tables
    if any(k in p for k in ("tabla", "tablas", "disponible", "disponibles", "cuantas tablas", "cuantos tablas", "listar tablas")):
        return ("list_tables", {})

    # 2. Grafica/Diagrama/Plot/Barras/Torta → herramienta de ploteo
    if any(k in p for k in ("grafica", "grafico", "diagrama", "plot", "barras", "torta", "pie", "circular", "chart")):
        if any(k in p for k in ("torta", "pie", "circular")):
            if any(k in p for k in ("review", "satisfaccion", "valoracion")):
                return ("plot_review_score_pie", {})
            return ("plot_category_sales_pie", _TOOL_DEFAULT_ARGS.get("plot_category_sales_pie", {"limit": 5}))
        if any(k in p for k in ("lineas", "linea")) and "barra" not in p:
            return ("plot_sales_by_month_line", _TOOL_DEFAULT_ARGS.get("plot_sales_by_month_line", {"year": 2017}))
        if any(k in p for k in ("mes", "med", "mensual")) or "ventas por mes" in p or "ventas por med" in p:
            return ("plot_sales_by_month", _TOOL_DEFAULT_ARGS.get("plot_sales_by_month", {"year": 2017}))
        if any(k in p for k in ("vendedor", "seller")):
            return ("plot_top_sellers_bar", _TOOL_DEFAULT_ARGS.get("plot_top_sellers_bar", {"limit": 10}))
        if any(k in p for k in ("cliente", "customer")):
            return ("plot_top_customers_bar", _TOOL_DEFAULT_ARGS.get("plot_top_customers_bar", {"limit": 10}))
        if any(k in p for k in ("categoria", "categorias")):
            return ("plot_category_sales_bar", _TOOL_DEFAULT_ARGS.get("plot_category_sales_bar", {"limit": 5}))
        if any(k in p for k in ("entrega", "delivery", "dias")):
            return ("plot_delivery_days_histogram", {})
        return ("plot_category_sales_bar", _TOOL_DEFAULT_ARGS.get("plot_category_sales_bar", {"limit": 5}))

    # 3. Exporta/Excel/CSV → export_to_excel o get_sales_summary
    if any(k in p for k in ("exporta", "exportar", "excel", "csv")):
        if any(k in p for k in ("categoria", "categorias")):
            return ("export_to_excel", {"sql": "SELECT * FROM olist_order_items LIMIT 1000", "sheet_name": "ventas_categoria", "limit": 1000})
        return ("export_to_excel", _TOOL_DEFAULT_ARGS.get("export_to_excel", {"sql": "SELECT * FROM olist_orders LIMIT 1000", "sheet_name": "datos", "limit": 1000}))

    # 4. Pais/Lugar/Estado → get_top_customers_by_sales
    if any(k in p for k in ("pais", "paises", "lugar", "lugares", "estado", "estados", "region")):
        return ("get_top_customers_by_sales", {"limit": 10})

    # 5. Vendedor/Seller → get_top_sellers
    if any(k in p for k in ("vendedor", "vendedores", "seller", "sellers", "mejores vendedores")):
        return ("get_top_sellers", {"limit": 10})

    return None


def _generate_synthetic_good_completion(prompt: str) -> str | None:
    """
    Genera una completion sintética BUENA (reward 1.2) solo si hay match heurístico claro.
    None si no hay match → evita Tool Collapse.
    """
    res = _synthesize_tool_for_prompt(prompt)
    if res is None:
        return None
    tool, args = res
    args_str = json.dumps(args, ensure_ascii=False)
    return (
        f'<thought>El usuario pregunta: "{prompt[:80]}...". '
        f"Usaré la herramienta {tool} para responder.</thought>\n"
        f'<tool_call>{{"tool": "{tool}", "args": {args_str}}}</tool_call>\n'
        "<answer>Consultando datos...</answer>"
    )


def _is_synthetic_completion(c: dict[str, Any]) -> bool:
    """Detecta completions sintéticas (generadas por _generate_synthetic_good_completion o BAD_SYNTHETIC)."""
    text = (c.get("text") or "").strip()
    reward = float(c.get("reward", 0))
    if text == "Aquí tienes la respuesta sin formato XML ni tool_call.":
        return True
    if reward == 1.2 and "<thought>El usuario pregunta:" in text and "Usaré la herramienta" in text:
        return True
    return False


def _enrich_groups_for_grpo(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Garantiza contraste para GRPO:
    1. Elimina sintéticas previas (para regenerar con heurística actual)
    2. Deduplicación por text
    3. Inyección de contraste (bad si solo positivos, good si solo negativos)
    4. Mínimo 2 completions con recompensas diferentes
    """
    BAD_SYNTHETIC = "Aquí tienes la respuesta sin formato XML ni tool_call."
    result: list[dict[str, Any]] = []

    for g in groups:
        prompt = g.get("prompt", "")
        comps = [c for c in g.get("completions", []) if not _is_synthetic_completion(c)]

        # 1. Deduplicar por text
        seen_text: set[str] = set()
        unique: list[dict[str, Any]] = []
        for c in comps:
            t = (c.get("text") or "").strip()
            if t and t not in seen_text:
                seen_text.add(t)
                unique.append(c)

        rewards = [float(c.get("reward", 0)) for c in unique]
        all_high = all(r >= 0.8 for r in rewards) if rewards else True
        all_low = all(r < 0.8 for r in rewards) if rewards else True
        has_different_rewards = len(set(rewards)) >= 2 if rewards else False
        needs_more = len(unique) < 2 or not has_different_rewards

        # 2. Inyección de contraste
        if all_high and (len(unique) < 2 or not has_different_rewards):
            unique.append({"text": BAD_SYNTHETIC, "reward": -1.0})
        if all_low and (len(unique) < 2 or not has_different_rewards):
            synth_good = _generate_synthetic_good_completion(prompt)
            if synth_good is not None:
                unique.append({"text": synth_good, "reward": 1.2})
            else:
                unique.append({"text": BAD_SYNTHETIC, "reward": -1.0})

        # 3. Re-deduplicar por si la sintética coincidió (poco probable)
        seen_text = {c.get("text", "").strip() for c in unique}
        if len(seen_text) < len(unique):
            seen_text = set()
            final: list[dict[str, Any]] = []
            for c in unique:
                t = (c.get("text") or "").strip()
                if t not in seen_text:
                    seen_text.add(t)
                    final.append(c)
            unique = final

        # Verificar mínimo 2 con rewards diferentes
        rewards = [float(c.get("reward", 0)) for c in unique]
        if len(unique) < 2 or len(set(rewards)) < 2:
            if not any(r < 0.5 for r in rewards):
                unique.append({"text": BAD_SYNTHETIC, "reward": -1.0})
            else:
                synth_good = _generate_synthetic_good_completion(prompt)
                if synth_good is not None:
                    unique.append({"text": synth_good, "reward": 1.2})
                else:
                    unique.append({"text": BAD_SYNTHETIC, "reward": -1.0})

        result.append({"prompt": prompt, "completions": unique})
    return result


def classify_traces(
    input_path: Optional[Path | str] = None,
    output_path: Optional[Path | str] = None,
    *,
    min_reward: float = -1.0,
    include_breakdown: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Carga trazas, clasifica rewards y escribe dataset listo para GRPO.

    - input_path: JSONL de trazas (por defecto train/grpo_olist_traces.jsonl).
    - output_path: JSONL de salida con reward (por defecto train/grpo_olist_rewarded.jsonl).
    - min_reward: filtrar trazas con reward < min_reward (por defecto incluir todas).
    - include_breakdown: incluir desglose del reward en cada registro.

    Devuelve (lista de trazas con reward, estadísticas).
    """
    inp = Path(input_path) if input_path else DEFAULT_TRACE_FILE
    out = Path(output_path) if output_path else DEFAULT_REWARDED_FILE
    out.parent.mkdir(parents=True, exist_ok=True)

    traces = load_grpo_traces(inp)
    groups_dict: dict[str, dict[str, Any]] = {}

    for t in traces:
        r, breakdown = compute_reward(t)
        if r < min_reward:
            continue
        prompt = (t.get("prompt") or "").strip()
        completion = t.get("completion") or ""
        key = _normalize_prompt_for_grouping(prompt)
        if not key:
            continue
        comp = {"text": completion, "reward": r}
        if key in groups_dict:
            groups_dict[key]["completions"].append(comp)
        else:
            groups_dict[key] = {"prompt": prompt, "completions": [comp]}

    groups_list = list(groups_dict.values())
    groups_list = _enrich_groups_for_grpo(groups_list)

    with open(out, "w", encoding="utf-8") as f:
        for g in groups_list:
            f.write(json.dumps(g, ensure_ascii=False) + "\n")

    rewarded = [{"prompt": g["prompt"], "completion": c["text"], "reward": c["reward"]} for g in groups_list for c in g["completions"]]
    rewards = [c["reward"] for g in groups_list for c in g["completions"]]

    stats = {
        "input_path": str(inp),
        "output_path": str(out),
        "total_input": len(traces),
        "total_output": len(rewarded),
        "filtered": len(traces) - len(rewarded),
        "min_reward": min(rewards) if rewards else 0,
        "max_reward": max(rewards) if rewards else 0,
        "avg_reward": sum(rewards) / len(rewards) if rewards else 0,
    }
    return rewarded, stats


def migrate_rewarded_to_groups_format(
    path: Optional[Path | str] = None,
) -> dict[str, Any]:
    """
    Migra grpo_olist_rewarded.jsonl de formato flat a formato grupos.
    Si ya está en grupos, no hace nada.
    """
    p = Path(path) if path else DEFAULT_REWARDED_FILE
    if not p.exists():
        return {"migrated": False, "reason": "file_not_found"}
    groups_dict: dict[str, dict[str, Any]] = {}
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if "completions" in rec:
                    key = _normalize_prompt_for_grouping(rec.get("prompt", ""))
                    if key:
                        groups_dict[key] = rec
                else:
                    prompt = (rec.get("prompt") or "").strip()
                    completion = rec.get("completion") or ""
                    reward = float(rec.get("reward", 0))
                    key = _normalize_prompt_for_grouping(prompt)
                    if key:
                        if key in groups_dict:
                            groups_dict[key]["completions"].append({"text": completion, "reward": reward})
                        else:
                            groups_dict[key] = {"prompt": prompt, "completions": [{"text": completion, "reward": reward}]}
            except json.JSONDecodeError:
                continue
    groups_list = _enrich_groups_for_grpo(list(groups_dict.values()))
    with open(p, "w", encoding="utf-8") as f:
        for g in groups_list:
            f.write(json.dumps(g, ensure_ascii=False) + "\n")
    return {"migrated": True, "groups": len(groups_list), "path": str(p)}


def convert_to_grpo_groups(
    input_path: Optional[Path | str] = None,
    output_path: Optional[Path | str] = None,
    *,
    min_completions_per_prompt: int = 2,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Convierte rewarded.jsonl al formato de grupos GRPO para Unsloth.

    GRPO requiere múltiples completions por prompt para calcular ventajas.
    Formato salida: {"prompt": "...", "completions": [{"text": "...", "reward": 1.0}, ...]}

    - input_path: rewarded.jsonl (por defecto train/grpo_olist_rewarded.jsonl).
    - output_path: grupos (por defecto train/grpo_olist_groups.jsonl).
    - min_completions_per_prompt: mínimo de respuestas por prompt (default 2).
      Prompts con menos se excluyen (gradiente sería 0).

    Devuelve (lista de grupos, estadísticas).
    """
    inp = Path(input_path) if input_path else DEFAULT_REWARDED_FILE
    out = Path(output_path) if output_path else DEFAULT_GROUPS_FILE
    out.parent.mkdir(parents=True, exist_ok=True)

    traces: list[dict[str, Any]] = []
    if inp.exists():
        with open(inp, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if "completions" in rec:
                        traces.extend(
                            {"prompt": rec["prompt"], "completion": c["text"], "reward": c["reward"]}
                            for c in rec["completions"]
                        )
                    else:
                        traces.append(rec)
                except json.JSONDecodeError:
                    continue
    # Agrupar por prompt normalizado
    groups: dict[str, list[dict[str, Any]]] = {}
    for t in traces:
        prompt = (t.get("prompt") or "").strip()
        completion = t.get("completion") or ""
        reward = float(t.get("reward", 0))
        key = _normalize_prompt_for_grouping(prompt)
        if not key:
            continue
        if key not in groups:
            groups[key] = []
        # Usar el prompt original del primer registro del grupo
        groups[key].append({"prompt": prompt, "text": completion, "reward": reward})

    # Filtrar grupos con suficientes completions y construir salida
    result: list[dict[str, Any]] = []
    skipped = 0
    for key, items in groups.items():
        if len(items) < min_completions_per_prompt:
            skipped += 1
            continue
        prompt = items[0]["prompt"]
        completions = [{"text": x["text"], "reward": x["reward"]} for x in items]
        result.append({"prompt": prompt, "completions": completions})

    with open(out, "w", encoding="utf-8") as f:
        for g in result:
            f.write(json.dumps(g, ensure_ascii=False) + "\n")

    total_completions = sum(len(g["completions"]) for g in result)
    stats = {
        "input_path": str(inp),
        "output_path": str(out),
        "input_traces": len(traces),
        "groups_output": len(result),
        "groups_skipped": skipped,
        "total_completions_in_groups": total_completions,
    }
    return result, stats


def load_rewarded_traces(
    path: Optional[Path | str] = None,
    limit: Optional[int] = None,
    min_reward: Optional[float] = None,
    *,
    as_groups: bool = False,
) -> list[dict[str, Any]]:
    """
    Carga trazas ya clasificadas (con reward).

    - path: ruta al .jsonl (por defecto train/grpo_olist_rewarded.jsonl).
    - limit: máximo de registros (o grupos si as_groups=True).
    - min_reward: filtrar por reward >= min_reward (solo si as_groups=False).
    - as_groups: si True, devuelve lista de grupos {prompt, completions}; si False, aplana.
    """
    p = Path(path) if path else DEFAULT_REWARDED_FILE
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if "completions" in rec:
                    if as_groups:
                        if min_reward is not None:
                            rec = {
                                "prompt": rec["prompt"],
                                "completions": [c for c in rec["completions"] if c.get("reward", -1) >= min_reward],
                            }
                            if not rec["completions"]:
                                continue
                        out.append(rec)
                        if limit is not None and len(out) >= limit:
                            break
                    else:
                        for c in rec["completions"]:
                            if min_reward is not None and c.get("reward", -1) < min_reward:
                                continue
                            out.append({"prompt": rec["prompt"], "completion": c["text"], "reward": c["reward"]})
                            if limit is not None and len(out) >= limit:
                                break
                        if limit is not None and len(out) >= limit:
                            break
                else:
                    if min_reward is not None and rec.get("reward", -1) < min_reward:
                        continue
                    out.append(rec)
                    if limit is not None and len(out) >= limit:
                        break
            except json.JSONDecodeError:
                continue
    return out
