"""The async scan engine.

Responsibilities:

* build a single shared :class:`HttpClient`,
* fan out every selected plugin across every target as concurrent tasks,
* collect, deduplicate and return findings,
* isolate plugin crashes so one broken check cannot abort the whole scan.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from .http import HttpClient
from .models import Finding, Target
from .modes import ModeProfile
from .plugin import Plugin, ScanContext

log = logging.getLogger("webscan.engine")


@dataclass
class ScanResult:
    targets: list[Target]
    findings: list[Finding] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    requests_sent: int = 0
    requests_failed: int = 0

    @property
    def highest_severity(self):
        return max((f.severity for f in self.findings), default=None)


class Engine:
    def __init__(
        self,
        plugins: list[Plugin],
        profile: ModeProfile,
        *,
        proxy: str | None = None,
        verify_ssl: bool = True,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.plugins = plugins
        self.profile = profile
        self.proxy = proxy
        self.verify_ssl = verify_ssl
        self.extra_headers = extra_headers

    async def scan(self, targets: list[Target]) -> ScanResult:
        result = ScanResult(targets=targets)
        active_plugins = [p for p in self.plugins if p.should_run(self.profile)]
        skipped = [p.name for p in self.plugins if p not in active_plugins]
        if skipped:
            log.info("skipping plugins not allowed by mode %s: %s", self.profile.name, ", ".join(skipped))

        async with HttpClient(
            concurrency=self.profile.concurrency,
            timeout=self.profile.timeout,
            jitter=self.profile.jitter,
            rotate_user_agent=self.profile.rotate_user_agent,
            proxy=self.proxy,
            retries=self.profile.retries,
            verify_ssl=self.verify_ssl,
            extra_headers=self.extra_headers,
        ) as http:
            tasks = [
                asyncio.create_task(self._run_one(plugin, target, http))
                for target in targets
                for plugin in active_plugins
            ]
            for batch in await asyncio.gather(*tasks, return_exceptions=True):
                if isinstance(batch, Exception):
                    result.errors.append(repr(batch))
                    continue
                findings, error = batch
                result.findings.extend(findings)
                if error:
                    result.errors.append(error)

            result.requests_sent = http.stats.sent
            result.requests_failed = http.stats.failed

        result.findings = _dedupe(result.findings)
        result.findings.sort(key=lambda f: (-int(f.severity), f.plugin, f.url))
        return result

    async def _run_one(self, plugin: Plugin, target: Target, http: HttpClient):
        ctx = ScanContext(target, http, self.profile)
        findings: list[Finding] = []
        error: str | None = None
        try:
            async for finding in plugin.run(ctx):
                findings.append(finding)
        except Exception as exc:  # noqa: BLE001 - isolate plugin failures
            error = f"plugin {plugin.name!r} on {target.url}: {exc!r}"
            log.warning(error)
        return findings, error


def _dedupe(findings: list[Finding]) -> list[Finding]:
    seen: set[str] = set()
    out: list[Finding] = []
    for f in findings:
        if f.fingerprint in seen:
            continue
        seen.add(f.fingerprint)
        out.append(f)
    return out
