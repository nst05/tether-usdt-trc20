"""Detect missing or weak HTTP security response headers (passive)."""

from __future__ import annotations

from typing import AsyncIterator

from ..core.models import Finding, Severity
from ..core.plugin import Plugin, ScanContext, register

# header -> (severity, remediation)
_EXPECTED = {
    "content-security-policy": (
        Severity.MEDIUM,
        "Define a Content-Security-Policy to mitigate XSS and data injection.",
    ),
    "strict-transport-security": (
        Severity.MEDIUM,
        "Send Strict-Transport-Security to enforce HTTPS (HSTS).",
    ),
    "x-content-type-options": (
        Severity.LOW,
        "Set 'X-Content-Type-Options: nosniff' to stop MIME sniffing.",
    ),
    "x-frame-options": (
        Severity.LOW,
        "Set X-Frame-Options or a CSP frame-ancestors directive.",
    ),
    "referrer-policy": (
        Severity.INFO,
        "Set a Referrer-Policy to limit referrer leakage.",
    ),
}


@register
class SecurityHeaders(Plugin):
    name = "security-headers"
    title = "Missing security header"
    severity = Severity.LOW
    cwe = "CWE-693"

    async def run(self, ctx: ScanContext) -> AsyncIterator[Finding]:
        resp = await ctx.get(ctx.target.url)
        if resp is None:
            return
        present = {k.lower() for k in resp.headers}
        # HSTS only matters over HTTPS.
        for header, (sev, fix) in _EXPECTED.items():
            if header == "strict-transport-security" and ctx.target.scheme != "https":
                continue
            if header not in present:
                yield self.finding(
                    resp.url,
                    title=f"Missing security header: {header}",
                    severity=sev,
                    description=f"Response does not set the {header} header.",
                    remediation=fix,
                )
