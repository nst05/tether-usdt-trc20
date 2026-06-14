"""Core data models shared across the engine, plugins and reporters."""

from __future__ import annotations

import enum
import hashlib
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse


class Severity(enum.IntEnum):
    """Ordered severity levels (higher == more serious)."""

    INFO = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

    @classmethod
    def parse(cls, value: str) -> "Severity":
        try:
            return cls[value.strip().upper()]
        except KeyError as exc:  # pragma: no cover - defensive
            valid = ", ".join(s.name.lower() for s in cls)
            raise ValueError(f"unknown severity {value!r}; expected one of {valid}") from exc

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.name


@dataclass(frozen=True)
class Target:
    """A normalized scan target."""

    url: str

    @property
    def host(self) -> str:
        return urlparse(self.url).hostname or ""

    @property
    def scheme(self) -> str:
        return urlparse(self.url).scheme or "http"

    @property
    def base(self) -> str:
        parsed = urlparse(self.url)
        return f"{parsed.scheme}://{parsed.netloc}"


@dataclass
class Finding:
    """A single issue reported by a plugin."""

    plugin: str
    title: str
    severity: Severity
    url: str
    description: str = ""
    evidence: str = ""
    remediation: str = ""
    cwe: str | None = None
    confidence: str = "firm"  # tentative | firm | certain
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def fingerprint(self) -> str:
        """Stable id used to deduplicate identical findings."""
        raw = f"{self.plugin}|{self.title}|{self.url}|{self.evidence}"
        return hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.fingerprint,
            "plugin": self.plugin,
            "title": self.title,
            "severity": self.severity.name.lower(),
            "url": self.url,
            "description": self.description,
            "evidence": self.evidence,
            "remediation": self.remediation,
            "cwe": self.cwe,
            "confidence": self.confidence,
            "extra": self.extra,
        }
