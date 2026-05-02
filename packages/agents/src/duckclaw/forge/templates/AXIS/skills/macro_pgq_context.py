"""Skill: grafo PGQ macro Quant (solo lectura) — régimen ⇄ activos."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import StructuredTool


def get_tools(db: Any, schema_name: str, spec: Any = None) -> list:
    _ = schema_name
    _ = spec

    def inspect_macro_pgq(regime_focus: str = "") -> str:
        """
        Resumen grafo PGQ macro: si pasas régimen tipo REGIMEN_RISK_OFF, lista coherentes /
        contraindicados usando las mismas reglas que MOC v2. Vacío = solo conteos.
        """
        from duckclaw.forge.atoms.macro_regime_detector import query_pgq_assets_for_regime

        def _rows(sql: str) -> list[dict]:
            raw = db.query(sql)
            return json.loads(raw) if isinstance(raw, str) else (raw or [])

        out: list[str] = []
        try:
            rn = _rows(
                "SELECT COUNT(*)::BIGINT AS c FROM quant_core.macro_nodes"
            )
            mc = (
                _rows(
                    """
                    SELECT name, node_type
                    FROM quant_core.macro_nodes
                    ORDER BY node_type ASC, name ASC
                    LIMIT 80
                    """
                )
                or []
            )
            nc = rn[0].get("c") if rn and isinstance(rn[0], dict) else "?"
            out.append(f"📊 PGQ macro — nodos totales: {nc}")
            by_type: dict[str, list[str]] = {}
            for row in mc:
                if not isinstance(row, dict):
                    continue
                nt = str(row.get("node_type") or "?").strip()
                nm = str(row.get("name") or "").strip()
                if not nm:
                    continue
                by_type.setdefault(nt, []).append(nm)
            for nt, names in sorted(by_type.items(), key=lambda x: x[0]):
                preview = ", ".join(names[:24])
                if len(names) > 24:
                    preview += f" … (+{len(names) - 24})"
                out.append(f"- **{nt}**: {preview}")
        except Exception as exc:  # noqa: BLE001
            return f"PGQ: no se pudo leer `quant_core.macro_*` ({exc})"

        rg = (regime_focus or "").strip().upper()
        if not rg:
            return "\n".join(out) + "\n\n_Para filas por régimen, pasa `regime_focus=REGIMEN_RISK_ON`._"

        if not rg.startswith("REGIMEN_"):
            return (
                "\n".join(out)
                + f"\n\n⚠️ `regime_focus` debe ser un nodo REGIMEN_* (recibí `{regime_focus[:40]}`)."
            )

        try:
            coh = query_pgq_assets_for_regime(
                db,
                rg,
                ["REFUGIO_DURANTE", "BENEFICIADO_POR", "CORRELACIONADO_EN"],
                0.5,
            )
            bad = query_pgq_assets_for_regime(
                db,
                rg,
                ["CONTRAINDICADO_EN", "PRESIONADO_POR"],
                0.4,
            )
        except Exception as exc:  # noqa: BLE001
            return "\n".join(out) + f"\n\nPGQ filtro `{rg}`: error {exc}"

        out.append(f"\n🎯 Régimen **{rg}**")
        out.append("- Coherentes / refugio / correlacionados: " + (", ".join(coh) or "(ninguno)"))
        out.append("- Contraindicados / presionados: " + (", ".join(bad) or "(ninguno)"))
        return "\n".join(out)

    return [
        StructuredTool.from_function(
            inspect_macro_pgq,
            name="inspect_macro_pgq",
            description=(
                "Grafo macro PGQ Quant: nodos/aristas coherentes/contraindicados por REGIMEN_*. "
                "Usa regime_focus REGIMEN_RISK_OFF para listar ACTIVOs alineados (misma lógica MOC)."
            ),
        ),
    ]
