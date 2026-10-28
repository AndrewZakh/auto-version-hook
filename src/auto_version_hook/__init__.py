"""auto-version-hook: git pre-commit hook that bumps a YAML version by branch name."""

from .config import AppConfig, ConfigError, load_config
from .flow import BranchClass
from .hook import HookError, HookResult, run_hook
from .versions import RegexVersion, VersionSpec

__version__ = "0.3.0"

__all__ = [
    "AppConfig",
    "BranchClass",
    "ConfigError",
    "HookError",
    "HookResult",
    "RegexVersion",
    "VersionSpec",
    "load_config",
    "run_hook",
]
