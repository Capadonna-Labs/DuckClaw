__all__ = ["build_meditate_graph", "invoke_meditate_run", "meditate_graph"]


def __getattr__(name: str):
    if name in ("build_meditate_graph", "invoke_meditate_run", "meditate_graph"):
        from harness_core.graphs import meditate_graph as mg

        return getattr(mg, name)
    raise AttributeError(name)
