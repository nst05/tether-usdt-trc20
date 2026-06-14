"""WebScan - an async web vulnerability scanner with a small plugin API.

For authorized security testing only.
"""

__version__ = "0.1.0"

from .core import Engine, Finding, Plugin, ScanResult, Severity, Target  # noqa: F401

__all__ = ["Engine", "Finding", "Plugin", "ScanResult", "Severity", "Target", "__version__"]
