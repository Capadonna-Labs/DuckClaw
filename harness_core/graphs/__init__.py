__all__ = ["build_loop_graph", "invoke_loop_run", "loop_graph", "build_meditate_graph", "meditate_graph"]


def __getattr__(name: str):
    if name in ("build_loop_graph", "build_meditate_graph", "invoke_loop_run", "loop_graph", "meditate_graph"):
        from harness_core.graphs import loop_graph as lg

        return getattr(lg, name)
    raise AttributeError(name)
