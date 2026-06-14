"""Detect pages that lack anti-framing protection (passive)."""

from __future__ import annotations

from typing import AsyncIterator

from ..core.models import Finding, Severity
from ..core.plugin import Plugin, ScanContext, register


@register
class Clickjacking(Plugin):
    name = "clickjacking"
    title = "Missing clickjacking protection"
    severity = Severity.LOW
    cwe = "CWE-1021"

    async def run(self, ctx: ScanContext) -> AsyncIterator[Finding]:
        resp = await ctx.get(ctx.target.url)
        if resp is None:
            return
        xfo = resp.header("x-frame-options")
        csp = resp.header("content-security-policy").lower()
        if xfo or "frame-ancestors" in csp:
            return
        # Only HTML pages are framed.
        if "html" not in resp.header("content-type").lower():
            return
        yield self.finding(
            resp.url,
            description="No X-Frame-Options or CSP frame-ancestors directive present.",
            remediation="Set 'X-Frame-Options: DENY' or CSP 'frame-ancestors none'.",
        )
