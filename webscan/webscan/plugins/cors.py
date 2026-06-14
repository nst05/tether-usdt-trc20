"""Detect permissive CORS configurations (active, non-destructive)."""

from __future__ import annotations

from typing import AsyncIterator

from ..core.models import Finding, Severity
from ..core.plugin import Plugin, ScanContext, register

_PROBE_ORIGIN = "https://webscan-probe.invalid"


@register
class Cors(Plugin):
    name = "cors"
    title = "CORS misconfiguration"
    severity = Severity.MEDIUM
    cwe = "CWE-942"
    requires_active = True

    async def run(self, ctx: ScanContext) -> AsyncIterator[Finding]:
        resp = await ctx.get(ctx.target.url, headers={"Origin": _PROBE_ORIGIN})
        if resp is None:
            return
        acao = resp.header("access-control-allow-origin")
        acac = resp.header("access-control-allow-credentials").lower() == "true"
        if not acao:
            return

        if acao == "*":
            yield self.finding(
                resp.url,
                title="CORS allows any origin (*)",
                severity=Severity.LOW if not acac else Severity.HIGH,
                description="Access-Control-Allow-Origin is a wildcard.",
                evidence=f"ACAO: *  credentials: {acac}",
                remediation="Restrict allowed origins to a known allowlist.",
            )
        elif acao == _PROBE_ORIGIN:
            yield self.finding(
                resp.url,
                title="CORS reflects arbitrary Origin",
                severity=Severity.HIGH if acac else Severity.MEDIUM,
                description="The server echoes any supplied Origin in ACAO.",
                evidence=f"reflected origin {acao}  credentials: {acac}",
                remediation="Validate Origin against an allowlist instead of reflecting it.",
            )
