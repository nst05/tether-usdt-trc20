"""Enumerate enabled HTTP methods via OPTIONS and flag risky ones (active)."""

from __future__ import annotations

from typing import AsyncIterator

from ..core.models import Finding, Severity
from ..core.plugin import Plugin, ScanContext, register

_RISKY = {"PUT", "DELETE", "TRACE", "CONNECT", "PATCH"}


@register
class HttpMethods(Plugin):
    name = "http-methods"
    title = "Risky HTTP methods enabled"
    severity = Severity.MEDIUM
    cwe = "CWE-650"
    requires_active = True

    async def run(self, ctx: ScanContext) -> AsyncIterator[Finding]:
        resp = await ctx.request("OPTIONS", ctx.target.url)
        if resp is None:
            return
        allow = resp.header("allow")
        if not allow:
            return
        methods = {m.strip().upper() for m in allow.split(",") if m.strip()}
        risky = sorted(methods & _RISKY)
        if risky:
            yield self.finding(
                resp.url,
                title=f"Risky HTTP methods advertised: {', '.join(risky)}",
                severity=Severity.HIGH if {"PUT", "DELETE"} & set(risky) else Severity.MEDIUM,
                description="The server advertises potentially dangerous HTTP methods via OPTIONS.",
                evidence=f"Allow: {allow}",
                remediation="Disable unused methods (especially PUT/DELETE/TRACE) at the server/WAF.",
                confidence="tentative",
            )
