"""Error-based SQL injection detection on URL query parameters (active).

Strategy: for each query parameter, append a single quote and look for database
error signatures appearing in the response that were *not* present in the
baseline. This is a detection heuristic only - it never attempts to extract or
modify data.
"""

from __future__ import annotations

import re
from typing import AsyncIterator

from ..core.models import Finding, Severity
from ..core.plugin import Plugin, ScanContext, register
from ..core.urls import query_params, with_param

_DB_ERRORS = re.compile(
    r"(SQL syntax.*MySQL|valid MySQL result|PostgreSQL.*ERROR|"
    r"Warning.*\bpg_|SQLite/JDBCDriver|SQLite3::|"
    r"Microsoft OLE DB Provider for SQL Server|ODBC SQL Server Driver|"
    r"ORA-\d{5}|Oracle error|quoted string not properly terminated|"
    r"Unclosed quotation mark after the character string)",
    re.I,
)

_MARKER = "'\"`"  # quote payload likely to break naive query construction


@register
class SqlInjection(Plugin):
    name = "sqli"
    title = "Possible SQL injection (error-based)"
    severity = Severity.HIGH
    cwe = "CWE-89"
    requires_active = True

    async def run(self, ctx: ScanContext) -> AsyncIterator[Finding]:
        params = query_params(ctx.target.url)
        if not params:
            return
        baseline = await ctx.get(ctx.target.url)
        baseline_text = baseline.text if baseline else ""

        for name, value in params:
            test_url = with_param(ctx.target.url, name, value + _MARKER)
            resp = await ctx.get(test_url)
            if resp is None:
                continue
            match = _DB_ERRORS.search(resp.text)
            if match and not _DB_ERRORS.search(baseline_text):
                yield self.finding(
                    test_url,
                    title=f"Possible SQL injection in parameter '{name}'",
                    description="Injecting a quote produced a database error not seen in baseline.",
                    evidence=match.group(0)[:160],
                    remediation="Use parameterized queries / prepared statements.",
                    confidence="firm",
                    parameter=name,
                )
