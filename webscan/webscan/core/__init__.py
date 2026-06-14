"""WebScan core package: models, engine, HTTP client, plugin API and reporters."""

from .engine import Engine, ScanResult
from .models import Finding, Severity, Target
from .modes import MODES, ModeProfile, get_profile
from .plugin import Plugin, ScanContext, get_plugins, register, registry_names

__all__ = [
    "Engine",
    "ScanResult",
    "Finding",
    "Severity",
    "Target",
    "MODES",
    "ModeProfile",
    "get_profile",
    "Plugin",
    "ScanContext",
    "get_plugins",
    "register",
    "registry_names",
]
