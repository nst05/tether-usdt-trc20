"""Detect verbose version banners and leaked stack traces (passive)."""

from __future__ import annotations

import re
from typing import AsyncIterator

from ..core.models import Finding, Severity
from ..core.plugin import Plugin, ScanContext, register

# Version numbers in Server / X-Powered-By aid targeted exploitation.
_VERSION = re.compile(r"\d+\.\d+(\.\d+)?")

_STACK_TRACES = [
    re.compile(r"Traceback \(most recent call last\)"),  # Python
    re.compile(r"at [\w.$]+\([\w.]+\.java:\d+\)"),         # Java
    re.compile(r"Fatal error:.*on line \d+", re.I),         # PHP
    re.compile(r"System\.[\w.]+Exception"),                  # .NET
    re.compile(r"<b>Warning</b>:.*on line", re.I),          # PHP warning
]


@register
class InfoDisclosure(Plugin):
    name = "info-disclosure"
    title = "Information disclosure"
    severity = Severity.LOW
    cwe = "CWE-200"

    async def run(self, ctx: ScanContext) -> AsyncIterator[Finding]:
        resp = await ctx.get(ctx.target.url)
        if resp is None:
            return

        for header in ("server", "x-powered-by", "x-aspnet-version"):
            value = resp.header(header)
            if value and _VERSION.search(value):
                yield self.finding(
                    resp.url,
                    title=f"Version banner in {header}",
                    severity=Severity.LOW,
                    description="The response advertises a precise software version.",
                    evidence=f"{header}: {value}",
                    remediation="Suppress or genericize version banners.",
                )

        for pattern in _STACK_TRACES:
            m = pattern.search(resp.text)
            if m:
                yield self.finding(
                    resp.url,
                    title="Stack trace / framework error leaked",
                    severity=Severity.MEDIUM,
                    description="The response contains a server-side stack trace or error.",
                    evidence=m.group(0)[:160],
                    remediation="Return generic error pages; disable debug output in production.",
                )
                break
