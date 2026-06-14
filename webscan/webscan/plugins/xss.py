"""Reflected XSS detection on URL query parameters (active).

Injects a uniquely-tagged, harmless marker and checks whether it is reflected
into the response unencoded in an HTML context. It never executes script; it
only observes whether dangerous characters survive output encoding.
"""

from __future__ import annotations

import secrets as _secrets
from typing import AsyncIterator

from ..core.models import Finding, Severity
from ..core.plugin import Plugin, ScanContext, register
from ..core.urls import query_params, with_param


@register
class ReflectedXss(Plugin):
    name = "xss"
    title = "Possible reflected XSS"
    severity = Severity.HIGH
    cwe = "CWE-79"
    requires_active = True

    async def run(self, ctx: ScanContext) -> AsyncIterator[Finding]:
        params = query_params(ctx.target.url)
        if not params:
            return

        for name, value in params:
            token = "wsx" + _secrets.token_hex(4)
            # Probe contains the characters that matter for HTML-context XSS.
            probe = f"{token}<\"'>"
            test_url = with_param(ctx.target.url, name, probe)
            resp = await ctx.get(test_url)
            if resp is None or token not in resp.text:
                continue
            # If the special characters survive unencoded next to our token,
            # the reflection is likely exploitable.
            idx = resp.text.find(token)
            window = resp.text[idx : idx + len(probe) + 4]
            if "<" in window and ('"' in window or "'" in window):
                yield self.finding(
                    test_url,
                    title=f"Possible reflected XSS in parameter '{name}'",
                    description="Input is reflected into the response without HTML encoding.",
                    evidence=window[:160],
                    remediation="Context-aware output encoding; apply a strict CSP.",
                    confidence="firm",
                    parameter=name,
                )
            else:
                yield self.finding(
                    test_url,
                    title=f"Reflected input in parameter '{name}'",
                    severity=Severity.LOW,
                    description="Input is reflected but appears to be encoded.",
                    evidence=window[:160],
                    remediation="Confirm encoding holds across all output contexts.",
                    confidence="tentative",
                    parameter=name,
                )
