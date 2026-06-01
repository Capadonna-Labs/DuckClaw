"""Manager routing compatibility facade.

Routing currently lives in ``duckclaw.graphs.manager_graph`` while the manager
module is split. This module is the stable target for callers that only need
worker routing/cache helpers.
"""

from duckclaw.graphs.manager_graph import clear_worker_graph_cache

__all__ = ["clear_worker_graph_cache"]

