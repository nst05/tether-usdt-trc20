"""Scan mode profiles.

Three profiles map to the three operating modes:

* ``safe``    - conservative defaults that never send destructive payloads and
                keep concurrency low so a production host is not knocked over.
* ``stealth`` - adds request jitter, User-Agent rotation and optional proxying
                so the scan is gentler and less bursty against rate limits / WAFs.
* ``cicd``    - tuned for pipelines: deterministic, SARIF-friendly, fails the
                build when findings cross a severity threshold.

These are *defaults*; every field can still be overridden from the CLI.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Severity


@dataclass
class ModeProfile:
    name: str
    concurrency: int = 50
    timeout: float = 15.0
    # Per-request randomized delay window in seconds (min, max).
    jitter: tuple[float, float] = (0.0, 0.0)
    rotate_user_agent: bool = False
    # Active checks send crafted (but non-destructive) payloads. When False,
    # plugins should restrict themselves to passive observation.
    active: bool = True
    # Allow checks that mutate server state (PUT/DELETE probes etc.).
    allow_intrusive: bool = False
    max_requests_per_host: int = 0  # 0 == unlimited
    fail_on: Severity | None = None
    retries: int = 1


def _safe() -> ModeProfile:
    return ModeProfile(
        name="safe",
        concurrency=20,
        timeout=15.0,
        jitter=(0.0, 0.0),
        rotate_user_agent=False,
        active=True,
        allow_intrusive=False,
        retries=1,
    )


def _stealth() -> ModeProfile:
    return ModeProfile(
        name="stealth",
        concurrency=8,
        timeout=25.0,
        jitter=(0.4, 2.0),
        rotate_user_agent=True,
        active=True,
        allow_intrusive=False,
        max_requests_per_host=0,
        retries=2,
    )


def _cicd() -> ModeProfile:
    return ModeProfile(
        name="cicd",
        concurrency=30,
        timeout=20.0,
        jitter=(0.0, 0.0),
        rotate_user_agent=False,
        active=True,
        allow_intrusive=False,
        fail_on=Severity.HIGH,
        retries=2,
    )


_BUILDERS = {"safe": _safe, "stealth": _stealth, "cicd": _cicd}


def get_profile(name: str) -> ModeProfile:
    try:
        return _BUILDERS[name.lower()]()
    except KeyError as exc:
        valid = ", ".join(_BUILDERS)
        raise ValueError(f"unknown mode {name!r}; expected one of {valid}") from exc


MODES: tuple[str, ...] = tuple(_BUILDERS)
