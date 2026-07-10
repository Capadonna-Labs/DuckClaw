"""Deprecated shim — loop handler is canonical."""
from loop_state_delta_handler import *  # noqa: F403
from loop_state_delta_handler import (  # noqa: F401
    _sync_handle_loop_state_delta as _sync_handle_meditate_state_delta,
)
