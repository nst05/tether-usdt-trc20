"""Plugin base class, scan context and the global plugin registry.

Writing a new check is deliberately small: subclass :class:`Plugin`, set a few
class attributes and implement :meth:`run`. A typical plugin is 20-30 lines.

Example::

    from webscan.core.plugin import Plugin, register
    from webscan.core.models import Finding, Severity

    @register
    class HelloPlugin(Plugin):
        name = "hello"
        title = "Example check"
        severity = Severity.INFO

        async def run(self, ctx):
            resp = await ctx.get(ctx.target.url)
            if resp and "secret" in resp.text:
                yield self.finding(ctx.target.url, evidence="found 'secret'")
"""

from __future__ import annotations

from typing import AsyncIterator, Iterable, Type

from .http import HttpClient, Response
from .models import Finding, Severity, Target
from .modes import ModeProfile


class ScanContext:
    """Everything a plugin needs to do its work for one target."""

    def __init__(self, target: Target, http: HttpClient, profile: ModeProfile) -> None:
        self.target = target
        self.http = http
        self.profile = profile

    async def get(self, url: str, **kwargs) -> Response | None:
        return await self.http.get(url, **kwargs)

    async def request(self, method: str, url: str, **kwargs) -> Response | None:
        return await self.http.request(method, url, **kwargs)

    @property
    def active(self) -> bool:
        return self.profile.active

    @property
    def allow_intrusive(self) -> bool:
        return self.profile.allow_intrusive


class Plugin:
    """Base class for all checks."""

    #: short machine name, unique across plugins (e.g. "sqli").
    name: str = ""
    #: human readable title used in reports.
    title: str = ""
    #: default severity for findings produced by this plugin.
    severity: Severity = Severity.INFO
    #: CWE identifier, e.g. "CWE-89".
    cwe: str | None = None
    #: when True the plugin sends crafted payloads and is skipped in passive runs.
    requires_active: bool = False
    #: when True the plugin may change server state; skipped unless intrusive.
    requires_intrusive: bool = False

    def should_run(self, profile: ModeProfile) -> bool:
        if self.requires_active and not profile.active:
            return False
        if self.requires_intrusive and not profile.allow_intrusive:
            return False
        return True

    def finding(
        self,
        url: str,
        *,
        title: str | None = None,
        severity: Severity | None = None,
        description: str = "",
        evidence: str = "",
        remediation: str = "",
        confidence: str = "firm",
        **extra,
    ) -> Finding:
        return Finding(
            plugin=self.name,
            title=title or self.title,
            severity=severity if severity is not None else self.severity,
            url=url,
            description=description,
            evidence=evidence,
            remediation=remediation,
            cwe=self.cwe,
            confidence=confidence,
            extra=extra,
        )

    async def run(self, ctx: ScanContext) -> AsyncIterator[Finding]:
        raise NotImplementedError
        yield  # pragma: no cover - makes this an async generator


_REGISTRY: dict[str, Type[Plugin]] = {}


def register(cls: Type[Plugin]) -> Type[Plugin]:
    """Class decorator that adds a plugin to the global registry."""
    if not cls.name:
        raise ValueError(f"{cls.__name__} must define a non-empty 'name'")
    if cls.name in _REGISTRY:
        raise ValueError(f"duplicate plugin name {cls.name!r}")
    _REGISTRY[cls.name] = cls
    return cls


def all_plugins() -> list[Type[Plugin]]:
    return list(_REGISTRY.values())


def get_plugins(only: Iterable[str] | None = None, exclude: Iterable[str] | None = None) -> list[Plugin]:
    only_set = {n.strip() for n in only} if only else None
    exclude_set = {n.strip() for n in exclude} if exclude else set()
    selected: list[Plugin] = []
    for name, cls in _REGISTRY.items():
        if only_set is not None and name not in only_set:
            continue
        if name in exclude_set:
            continue
        selected.append(cls())
    return selected


def registry_names() -> list[str]:
    return sorted(_REGISTRY)
