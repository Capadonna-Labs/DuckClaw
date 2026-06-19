"""Optional runtime extensions loaded from external repos via environment variables."""

from duckclaw.extensions.fly import (
    dispatch_extension_fly_command,
    extension_fly_read_only_command_names,
    invalidate_extension_fly_cache,
)
from duckclaw.extensions.skills import (
    get_worker_skill_hooks,
    invalidate_extension_skills_cache,
    invoke_extension_worker_skill_hooks,
)

__all__ = [
    "dispatch_extension_fly_command",
    "extension_fly_read_only_command_names",
    "get_worker_skill_hooks",
    "invalidate_extension_fly_cache",
    "invalidate_extension_skills_cache",
    "invoke_extension_worker_skill_hooks",
]
