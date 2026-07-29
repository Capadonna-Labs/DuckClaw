"""Homeostasis action planner owned outside legacy Forge."""

from __future__ import annotations

import json
from typing import Any

from duckclaw.homeostasis.belief_registry import BeliefRegistry
from duckclaw.homeostasis.surprise import compute_surprise, detect_value_scale_mismatch


def _safe_ident(name: str) -> str:
    """Return a safe schema/table identifier."""
    return "".join(c if c.isalnum() or c == "_" else "_" for c in name.strip())


def _safe_key(key: str) -> str:
    """Return a safe belief key for SQL literals controlled by manifests."""
    return "".join(c if c.isalnum() or c == "_" else "_" for c in key.strip())


class HomeostasisManager:
    """Compare observed values with beliefs and return a restore/maintain plan."""

    def __init__(
        self,
        db: Any,
        schema: str,
        registry: BeliefRegistry,
        tools_by_name: dict[str, Any] | None = None,
    ):
        self.db = db
        self.schema = _safe_ident(schema)
        self.registry = registry
        self.tools_by_name = tools_by_name or {}

    def _get_or_create_belief_row(self, belief_key: str, target: float, threshold: float) -> None:
        """Ensure agent_beliefs contains the given belief row."""
        key_safe = _safe_key(belief_key)
        try:
            r = self.db.query(
                f"SELECT 1 FROM {self.schema}.agent_beliefs WHERE belief_key = '{key_safe}' LIMIT 1"
            )
            rows = json.loads(r) if isinstance(r, str) else (r or [])
            exists = len(rows) > 0
        except Exception:
            exists = False
        if exists:
            try:
                self.db.execute(
                    f"UPDATE {self.schema}.agent_beliefs SET target_value = {target}, threshold = {threshold} "
                    f"WHERE belief_key = '{key_safe}'"
                )
            except Exception:
                pass
        else:
            try:
                self.db.execute(
                    f"INSERT INTO {self.schema}.agent_beliefs (belief_key, target_value, observed_value, threshold) "
                    f"VALUES ('{key_safe}', {target}, NULL, {threshold})"
                )
            except Exception:
                pass

    def _update_observed(self, belief_key: str, observed_value: float) -> None:
        """Update observed_value and last_updated for an existing belief."""
        key_safe = _safe_key(belief_key)
        try:
            self.db.execute(
                f"UPDATE {self.schema}.agent_beliefs "
                f"SET observed_value = {observed_value}, last_updated = CURRENT_TIMESTAMP "
                f"WHERE belief_key = '{key_safe}'"
            )
        except Exception:
            pass

    def _normalize_observed_for_belief(
        self,
        belief: Any,
        observed_value: float,
        *,
        settings_lookup: dict[str, float],
    ) -> float:
        from duckclaw.homeostasis.unit_conversion import (
            needs_pct_conversion,
            normalize_observed,
        )

        value_unit = (getattr(belief, "value_unit", None) or "").strip().lower()
        anchor_key = (getattr(belief, "anchor_setting_key", None) or "").strip()
        if value_unit != "percent" or not anchor_key:
            return observed_value
        if not needs_pct_conversion(observed_value, belief.target, belief.threshold):
            return observed_value
        try:
            return normalize_observed(
                observed_value,
                target_unit="pct",
                anchor_setting_key=anchor_key,
                settings_lookup=settings_lookup,
            )
        except ValueError:
            return observed_value

    def check(
        self,
        belief_key: str,
        observed_value: float,
        *,
        auto_update: bool = True,
        invoke_restoration: bool = False,
        settings_lookup: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """Compare observed_value with a belief and return an action plan."""
        belief = self.registry.get_belief(belief_key)
        if not belief:
            return {
                "action": "unknown",
                "message": f"Creencia '{belief_key}' no definida en homeostasis.",
                "belief_key": belief_key,
            }

        observed_value = self._normalize_observed_for_belief(
            belief, observed_value, settings_lookup=settings_lookup or {}
        )

        value_unit = getattr(belief, "value_unit", None)
        if detect_value_scale_mismatch(
            observed_value, belief.target, belief.threshold, value_unit=value_unit
        ):
            return {
                "action": "maintain",
                "message": (
                    f"Observación en {belief_key} no comparable con la meta "
                    f"(escala incompatible: obs={observed_value}, meta={belief.target})."
                ),
                "belief_key": belief_key,
                "observed": observed_value,
                "target": belief.target,
                "scale_mismatch": True,
            }

        result = compute_surprise(
            observed_value,
            belief.target,
            belief.threshold,
            comparison=getattr(belief, "comparison", "symmetric") or "symmetric",
        )

        if auto_update:
            self._get_or_create_belief_row(belief_key, belief.target, belief.threshold)
            self._update_observed(belief_key, observed_value)

        if result.is_anomaly:
            comp = getattr(belief, "comparison", "symmetric") or "symmetric"
            is_drop = False if comp == "ceiling" else observed_value < belief.target
            trigger = self.registry.trigger_for_belief(belief_key, is_drop=is_drop)
            restoration = self.registry.get_action_for_trigger(trigger)
            if not restoration:
                restoration = self.registry.get_action_for_trigger(f"{belief_key}_breach")
            if not restoration:
                restoration = self.registry.get_action_for_trigger(f"{belief_key}_drop")

            skill_to_invoke = restoration.skill if restoration else ""
            message = restoration.message if restoration else f"Anomalía en {belief_key}: delta={result.delta:.4f}"

            if invoke_restoration and skill_to_invoke and skill_to_invoke in self.tools_by_name:
                try:
                    tool = self.tools_by_name[skill_to_invoke]
                    tool.invoke({})
                except Exception as e:
                    message += f" [Error al invocar {skill_to_invoke}: {e}]"

            return {
                "action": "restore",
                "message": message,
                "skill_to_invoke": skill_to_invoke,
                "belief_key": belief_key,
                "delta": result.delta,
                "observed": observed_value,
                "target": belief.target,
                "threshold": belief.threshold,
            }

        return {
            "action": "maintain",
            "message": f"Equilibrio mantenido en {belief_key}.",
            "belief_key": belief_key,
            "delta": result.delta,
            "observed": observed_value,
            "target": belief.target,
        }
