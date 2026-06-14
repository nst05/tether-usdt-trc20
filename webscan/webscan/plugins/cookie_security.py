"""Flag cookies issued without Secure / HttpOnly / SameSite (passive)."""

from __future__ import annotations

from typing import AsyncIterator

from ..core.models import Finding, Severity
from ..core.plugin import Plugin, ScanContext, register


@register
class CookieSecurity(Plugin):
    name = "cookie-security"
    title = "Insecure cookie attributes"
    severity = Severity.LOW
    cwe = "CWE-614"

    async def run(self, ctx: ScanContext) -> AsyncIterator[Finding]:
        resp = await ctx.get(ctx.target.url)
        if resp is None:
            return
        # A response may set several cookies; aiohttp folds duplicate headers,
        # so split conservatively on the cookie boundary.
        raw = resp.header("set-cookie")
        if not raw:
            return
        for chunk in raw.split("\n"):
            cookie = chunk.strip()
            if not cookie or "=" not in cookie:
                continue
            name = cookie.split("=", 1)[0]
            lower = cookie.lower()
            missing = [
                flag
                for flag in ("secure", "httponly", "samesite")
                if flag not in lower
            ]
            if not missing:
                continue
            # Secure flag only meaningful over HTTPS.
            if ctx.target.scheme != "https" and missing == ["secure"]:
                continue
            yield self.finding(
                resp.url,
                title=f"Cookie '{name}' missing: {', '.join(missing)}",
                description="Session/state cookies should set Secure, HttpOnly and SameSite.",
                evidence=cookie[:120],
                remediation="Add the missing attributes when issuing the cookie.",
            )
