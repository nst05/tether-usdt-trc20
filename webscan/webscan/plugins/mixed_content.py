"""Flag HTTPS pages that reference resources over plain HTTP (passive)."""

from __future__ import annotations

import re
from typing import AsyncIterator

from ..core.models import Finding, Severity
from ..core.plugin import Plugin, ScanContext, register

_HTTP_RESOURCE = re.compile(
    r"""(?:src|href)\s*=\s*["'](http://[^"']+)["']""", re.I
)


@register
class MixedContent(Plugin):
    name = "mixed-content"
    title = "Mixed content on HTTPS page"
    severity = Severity.LOW
    cwe = "CWE-311"

    async def run(self, ctx: ScanContext) -> AsyncIterator[Finding]:
        if ctx.target.scheme != "https":
            return
        resp = await ctx.get(ctx.target.url)
        if resp is None:
            return
        matches = _HTTP_RESOURCE.findall(resp.text)
        # Ignore plain anchor links to other sites; focus on loaded sub-resources.
        loaded = [m for m in matches if not m.lower().endswith((".html", "/"))]
        if loaded:
            sample = ", ".join(dict.fromkeys(loaded))[:200]
            yield self.finding(
                resp.url,
                description=f"{len(loaded)} resource(s) referenced over insecure HTTP.",
                evidence=sample,
                remediation="Serve all sub-resources over HTTPS; consider 'upgrade-insecure-requests'.",
            )
