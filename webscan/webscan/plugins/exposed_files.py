"""Probe a small list of commonly-leaked sensitive paths (active, GET only).

Only idempotent GET requests are made, against well-known conventional paths.
This mirrors what any web server log already sees from background scanners.
"""

from __future__ import annotations

from typing import AsyncIterator

from ..core.models import Finding, Severity
from ..core.plugin import Plugin, ScanContext, register
from ..core.urls import join

# path -> (severity, marker that confirms a real hit, label)
_PATHS = [
    ("/.git/config", Severity.HIGH, "[core]", "Exposed .git repository"),
    ("/.env", Severity.HIGH, "=", "Exposed .env file"),
    ("/.svn/entries", Severity.MEDIUM, "", "Exposed .svn metadata"),
    ("/.DS_Store", Severity.LOW, "", "Exposed .DS_Store"),
    ("/backup.zip", Severity.MEDIUM, "", "Exposed backup archive"),
    ("/config.php.bak", Severity.HIGH, "", "Exposed PHP config backup"),
    ("/phpinfo.php", Severity.MEDIUM, "phpinfo()", "Exposed phpinfo()"),
    ("/server-status", Severity.MEDIUM, "Apache Server Status", "Exposed Apache server-status"),
]


@register
class ExposedFiles(Plugin):
    name = "exposed-files"
    title = "Exposed sensitive file"
    severity = Severity.HIGH
    cwe = "CWE-538"
    requires_active = True

    async def run(self, ctx: ScanContext) -> AsyncIterator[Finding]:
        base = ctx.target.base
        for path, sev, marker, label in _PATHS:
            url = join(base, path)
            resp = await ctx.get(url, allow_redirects=False)
            if resp is None or resp.status != 200:
                continue
            # Guard against soft-404s that return 200 for everything.
            if marker and marker not in resp.text:
                continue
            if not resp.text.strip():
                continue
            yield self.finding(
                url,
                title=label,
                severity=sev,
                description=f"A request for {path} returned HTTP 200 with content.",
                evidence=f"status 200, {len(resp.text)} bytes",
                remediation="Block access to this path or remove the file from the web root.",
                confidence="firm" if marker else "tentative",
            )
