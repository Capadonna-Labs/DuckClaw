"""Módulo RL: clasificación de recompensas para trazas GRPO y entrenamiento."""

__all__ = ["compute_reward", "classify_traces", "load_rewarded_traces", "convert_to_grpo_groups", "migrate_rewarded_to_groups_format"]


def __getattr__(name: str):
    if name in ("compute_reward", "classify_traces", "load_rewarded_traces", "convert_to_grpo_groups", "migrate_rewarded_to_groups_format"):
        from duckclaw.rl.rewards import compute_reward, classify_traces, load_rewarded_traces, convert_to_grpo_groups, migrate_rewarded_to_groups_format
        return {"compute_reward": compute_reward, "classify_traces": classify_traces, "load_rewarded_traces": load_rewarded_traces, "convert_to_grpo_groups": convert_to_grpo_groups, "migrate_rewarded_to_groups_format": migrate_rewarded_to_groups_format}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
