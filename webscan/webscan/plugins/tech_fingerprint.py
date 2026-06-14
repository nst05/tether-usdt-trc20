"""Identify server-side technologies from headers and body markers (passive)."""

from __future__ import annotations

import re
from typing import AsyncIterator

from ..core.models import Finding, Severity
from ..core.plugin import Plugin, ScanContext, register

_HEADER_SIGNS = {
    "x-powered-by": "X-Powered-By",
    "server": "Server",
    "x-aspnet-version": "ASP.NET",
    "x-generator": "Generator",
    "x-drupal-cache": "Drupal",
}

_BODY_SIGNS = [
    ("WordPress", re.compile(r"/wp-(content|includes)/", re.I)),
    ("Drupal", re.compile(r"Drupal\.settings|/sites/default/files", re.I)),
    ("Joomla", re.compile(r"/media/jui/|Joomla!", re.I)),
    ("Laravel", re.compile(r"laravel_session|XSRF-TOKEN", re.I)),
    ("React", re.compile(r"data-reactroot|__NEXT_DATA__", re.I)),
    ("Vue.js", re.compile(r"data-v-[0-9a-f]{8}", re.I)),
]


@register
class TechFingerprint(Plugin):
    name = "tech-fingerprint"
    title = "Technology fingerprint"
    severity = Severity.INFO

    async def run(self, ctx: ScanContext) -> AsyncIterator[Finding]:
        resp = await ctx.get(ctx.target.url)
        if resp is None:
            return
        detected: list[str] = []
        for header, label in _HEADER_SIGNS.items():
            value = resp.header(header)
            if value:
                detected.append(f"{label}: {value}")
        for label, pattern in _BODY_SIGNS:
            if pattern.search(resp.text):
                detected.append(label)
        if detected:
            yield self.finding(
                resp.url,
                description="Technologies inferred from response fingerprints.",
                evidence="; ".join(dict.fromkeys(detected)),
                remediation="Avoid leaking precise version/stack details where unnecessary.",
            )
