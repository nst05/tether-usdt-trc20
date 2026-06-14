"""Scan response bodies for accidentally exposed secrets (passive)."""

from __future__ import annotations

import re
from typing import AsyncIterator

from ..core.models import Finding, Severity
from ..core.plugin import Plugin, ScanContext, register

# (label, compiled pattern). Patterns target well-known, high-signal formats to
# keep the false-positive rate low.
_PATTERNS = [
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,48}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[0-9A-Za-z]{36}\b")),
    ("Stripe secret key", re.compile(r"\bsk_live_[0-9A-Za-z]{24,}\b")),
    ("Private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
]


@register
class Secrets(Plugin):
    name = "secrets"
    title = "Exposed secret in response"
    severity = Severity.HIGH
    cwe = "CWE-200"

    async def run(self, ctx: ScanContext) -> AsyncIterator[Finding]:
        resp = await ctx.get(ctx.target.url)
        if resp is None:
            return
        for label, pattern in _PATTERNS:
            match = pattern.search(resp.text)
            if not match:
                continue
            token = match.group(0)
            redacted = token[:6] + "…" + token[-4:] if len(token) > 12 else token
            yield self.finding(
                resp.url,
                title=f"Possible {label} exposed",
                severity=Severity.CRITICAL if "PRIVATE KEY" in label else Severity.HIGH,
                description=f"A value matching the {label} format was found in the response body.",
                evidence=redacted,
                remediation="Rotate the credential and remove it from served content.",
                confidence="tentative",
            )
