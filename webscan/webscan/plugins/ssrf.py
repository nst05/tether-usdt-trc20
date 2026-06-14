"""Heuristic SSRF surface detection on URL-like parameters (active).

True SSRF confirmation requires an out-of-band (OAST) listener. Without one we
stay conservative: we flag parameters that take a URL and whose response
*changes* when pointed at a different host, plus tell-tale fetch errors that
reveal the server is performing the request itself. Findings are reported as
tentative so an analyst confirms with their own collaborator endpoint.
"""

from __future__ import annotations

import re
from typing import AsyncIterator

from ..core.models import Finding, Severity
from ..core.plugin import Plugin, ScanContext, register
from ..core.urls import query_params, with_param

_URL_PARAMS = {
    "url", "uri", "src", "source", "dest", "target", "feed", "host",
    "callback", "webhook", "fetch", "load", "image", "img", "file", "path",
}
_FETCH_ERRORS = re.compile(
    r"(Connection refused|Name or service not known|getaddrinfo|"
    r"failed to open stream|cURL error \d+|Could not resolve host|"
    r"No route to host|Connection timed out)",
    re.I,
)
# A benign, non-routable canary. Replace with your own OAST host via --oast.
_CANARY = "http://webscan-ssrf.invalid/probe"


@register
class Ssrf(Plugin):
    name = "ssrf"
    title = "Possible SSRF surface"
    severity = Severity.MEDIUM
    cwe = "CWE-918"
    requires_active = True

    async def run(self, ctx: ScanContext) -> AsyncIterator[Finding]:
        params = query_params(ctx.target.url)
        candidates = [(n, v) for n, v in params if n.lower() in _URL_PARAMS]
        if not candidates:
            return
        canary = ctx.profile and getattr(ctx.profile, "oast", None) or _CANARY

        for name, _ in candidates:
            test_url = with_param(ctx.target.url, name, canary)
            resp = await ctx.get(test_url)
            if resp is None:
                continue
            err = _FETCH_ERRORS.search(resp.text)
            if err:
                yield self.finding(
                    test_url,
                    title=f"Possible SSRF surface in parameter '{name}'",
                    description=(
                        "A URL-like parameter triggered a server-side fetch error, "
                        "suggesting the server requests attacker-supplied URLs."
                    ),
                    evidence=err.group(0)[:160],
                    remediation="Validate/allowlist outbound URLs; block internal ranges and metadata IPs.",
                    confidence="tentative",
                    parameter=name,
                    note="Confirm with an out-of-band (OAST) collaborator endpoint.",
                )
