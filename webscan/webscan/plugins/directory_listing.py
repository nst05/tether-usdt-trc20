"""Detect directories that serve an auto-generated index listing (passive)."""

from __future__ import annotations

import re
from typing import AsyncIterator

from ..core.models import Finding, Severity
from ..core.plugin import Plugin, ScanContext, register

_SIGNS = [
    re.compile(r"<title>Index of /", re.I),
    re.compile(r"<h1>Index of /", re.I),
    re.compile(r"Directory listing for /", re.I),  # Python http.server
    re.compile(r"\[To Parent Directory\]", re.I),  # IIS
]


@register
class DirectoryListing(Plugin):
    name = "directory-listing"
    title = "Directory listing enabled"
    severity = Severity.MEDIUM
    cwe = "CWE-548"

    async def run(self, ctx: ScanContext) -> AsyncIterator[Finding]:
        resp = await ctx.get(ctx.target.url)
        if resp is None or resp.status != 200:
            return
        for pattern in _SIGNS:
            if pattern.search(resp.text):
                yield self.finding(
                    resp.url,
                    description="The server returns an auto-generated directory index.",
                    evidence=pattern.pattern,
                    remediation="Disable automatic directory indexing (e.g. 'Options -Indexes').",
                )
                return
