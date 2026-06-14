"""Reporters: console, JSON and SARIF 2.1.0 (GitHub Code Scanning)."""

from __future__ import annotations

import json
from typing import Any

from .engine import ScanResult
from .models import Finding, Severity

_COLORS = {
    Severity.CRITICAL: "\033[95m",
    Severity.HIGH: "\033[91m",
    Severity.MEDIUM: "\033[93m",
    Severity.LOW: "\033[94m",
    Severity.INFO: "\033[90m",
}
_RESET = "\033[0m"


def render_console(result: ScanResult, *, color: bool = True) -> str:
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("WebScan report")
    lines.append("=" * 60)
    lines.append(
        f"targets: {len(result.targets)}   findings: {len(result.findings)}   "
        f"requests: {result.requests_sent} (failed {result.requests_failed})"
    )
    lines.append("")

    if not result.findings:
        lines.append("No findings.")
    for f in result.findings:
        tag = f"[{f.severity.name}]"
        if color:
            tag = f"{_COLORS.get(f.severity, '')}{tag}{_RESET}"
        lines.append(f"{tag} {f.title}  ({f.plugin}, {f.confidence})")
        lines.append(f"    url:      {f.url}")
        if f.evidence:
            lines.append(f"    evidence: {_truncate(f.evidence)}")
        if f.remediation:
            lines.append(f"    fix:      {f.remediation}")
        lines.append("")

    if result.errors:
        lines.append(f"errors: {len(result.errors)}")
        for err in result.errors[:20]:
            lines.append(f"    ! {err}")

    counts = _severity_counts(result.findings)
    summary = "  ".join(f"{s.name.lower()}={counts[s]}" for s in reversed(Severity) if counts[s])
    lines.append("-" * 60)
    lines.append(f"summary: {summary or 'clean'}")
    return "\n".join(lines)


def render_json(result: ScanResult) -> str:
    payload: dict[str, Any] = {
        "tool": "webscan",
        "targets": [t.url for t in result.targets],
        "stats": {
            "requests_sent": result.requests_sent,
            "requests_failed": result.requests_failed,
            "findings": len(result.findings),
        },
        "findings": [f.to_dict() for f in result.findings],
        "errors": result.errors,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def render_sarif(result: ScanResult) -> str:
    """Render SARIF 2.1.0 consumable by GitHub Code Scanning."""
    rules: dict[str, dict[str, Any]] = {}
    sarif_results: list[dict[str, Any]] = []

    for f in result.findings:
        rule_id = f.plugin
        if rule_id not in rules:
            rules[rule_id] = {
                "id": rule_id,
                "name": f.title,
                "shortDescription": {"text": f.title},
                "defaultConfiguration": {"level": _sarif_level(f.severity)},
                "properties": {"security-severity": _security_severity(f.severity)},
            }
            if f.cwe:
                rules[rule_id]["properties"]["tags"] = ["security", f.cwe]
        sarif_results.append(
            {
                "ruleId": rule_id,
                "level": _sarif_level(f.severity),
                "message": {"text": f"{f.title}. {f.description} {f.evidence}".strip()},
                "locations": [
                    {"physicalLocation": {"artifactLocation": {"uri": f.url}}}
                ],
                "partialFingerprints": {"webscan/v1": f.fingerprint},
            }
        )

    sarif = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "WebScan",
                        "informationUri": "https://example.invalid/webscan",
                        "version": "0.1.0",
                        "rules": list(rules.values()),
                    }
                },
                "results": sarif_results,
            }
        ],
    }
    return json.dumps(sarif, indent=2, ensure_ascii=False)


def _sarif_level(sev: Severity) -> str:
    if sev >= Severity.HIGH:
        return "error"
    if sev == Severity.MEDIUM:
        return "warning"
    return "note"


def _security_severity(sev: Severity) -> str:
    # GitHub maps these numeric scores to its own severity buckets.
    return {
        Severity.CRITICAL: "9.5",
        Severity.HIGH: "8.0",
        Severity.MEDIUM: "5.5",
        Severity.LOW: "3.0",
        Severity.INFO: "1.0",
    }[sev]


def _severity_counts(findings: list[Finding]) -> dict[Severity, int]:
    counts = {s: 0 for s in Severity}
    for f in findings:
        counts[f.severity] += 1
    return counts


def _truncate(text: str, length: int = 160) -> str:
    text = " ".join(text.split())
    return text if len(text) <= length else text[: length - 1] + "…"


def render(result: ScanResult, fmt: str, *, color: bool = True) -> str:
    fmt = fmt.lower()
    if fmt == "console":
        return render_console(result, color=color)
    if fmt == "json":
        return render_json(result)
    if fmt == "sarif":
        return render_sarif(result)
    raise ValueError(f"unknown format {fmt!r}")
