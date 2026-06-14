"""Detect open redirects on likely redirect parameters (active)."""

from __future__ import annotations

from typing import AsyncIterator
from urllib.parse import urlparse

from ..core.models import Finding, Severity
from ..core.plugin import Plugin, ScanContext, register
from ..core.urls import query_params, with_param

_REDIRECT_PARAMS = {
    "url", "next", "redirect", "redirect_uri", "return", "returnurl",
    "return_to", "dest", "destination", "continue", "goto", "rurl", "target",
}
_CANARY = "https://webscan-redirect.invalid/"


@register
class OpenRedirect(Plugin):
    name = "open-redirect"
    title = "Open redirect"
    severity = Severity.MEDIUM
    cwe = "CWE-601"
    requires_active = True

    async def run(self, ctx: ScanContext) -> AsyncIterator[Finding]:
        params = query_params(ctx.target.url)
        candidates = [n for n, _ in params if n.lower() in _REDIRECT_PARAMS]
        if not candidates:
            return

        for name in candidates:
            test_url = with_param(ctx.target.url, name, _CANARY)
            resp = await ctx.get(test_url, allow_redirects=False)
            if resp is None or resp.status not in (301, 302, 303, 307, 308):
                continue
            location = resp.header("location")
            if urlparse(location).hostname == "webscan-redirect.invalid":
                yield self.finding(
                    test_url,
                    title=f"Open redirect via parameter '{name}'",
                    description="A user-controlled parameter sets the redirect target.",
                    evidence=f"Location: {location}",
                    remediation="Allow redirects only to a vetted allowlist of paths/hosts.",
                    parameter=name,
                )
