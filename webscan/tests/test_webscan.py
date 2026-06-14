"""Offline tests: no network. A fake context feeds canned responses to plugins."""

from __future__ import annotations

import json

import pytest

from webscan import plugins as _plugins  # noqa: F401 - register built-ins
from webscan.core.engine import ScanResult
from webscan.core.http import Response
from webscan.core.models import Finding, Severity, Target
from webscan.core.modes import get_profile
from webscan.core.plugin import ScanContext, registry_names
from webscan.core.report import render_json, render_sarif
from webscan.core.urls import query_params, with_param


class FakeHttp:
    """Stands in for HttpClient; returns a Response from a routing function."""

    def __init__(self, router):
        self._router = router

    async def get(self, url, **kwargs):
        return self._router("GET", url, kwargs)

    async def request(self, method, url, **kwargs):
        return self._router(method, url, kwargs)


def make_ctx(url, router, mode="safe"):
    return ScanContext(Target(url), FakeHttp(router), get_profile(mode))


def resp(url, status=200, headers=None, text=""):
    return Response(url=url, status=status, headers=headers or {}, text=text, elapsed=0.01)


# --- pure helpers ---------------------------------------------------------

def test_severity_ordering_and_parse():
    assert Severity.CRITICAL > Severity.HIGH > Severity.MEDIUM
    assert Severity.parse("high") is Severity.HIGH
    with pytest.raises(ValueError):
        Severity.parse("nope")


def test_with_param_preserves_other_params():
    url = "https://x.test/a?id=1&q=hi"
    out = with_param(url, "id", "9")
    params = dict(query_params(out))
    assert params["id"] == "9" and params["q"] == "hi"


def test_finding_fingerprint_is_stable():
    f1 = Finding("p", "t", Severity.LOW, "u", evidence="e")
    f2 = Finding("p", "t", Severity.LOW, "u", evidence="e")
    assert f1.fingerprint == f2.fingerprint


def test_registry_has_fifteen_plugins():
    assert len(registry_names()) == 15


# --- reporters ------------------------------------------------------------

def test_sarif_is_valid_json_with_rules():
    result = ScanResult(targets=[Target("https://x.test")])
    result.findings = [Finding("sqli", "SQLi", Severity.HIGH, "https://x.test/?id=1'", evidence="ORA-00933")]
    doc = json.loads(render_sarif(result))
    assert doc["version"] == "2.1.0"
    run = doc["runs"][0]
    assert run["tool"]["driver"]["rules"][0]["id"] == "sqli"
    assert run["results"][0]["level"] == "error"


def test_json_report_roundtrips():
    result = ScanResult(targets=[Target("https://x.test")])
    result.findings = [Finding("secrets", "key", Severity.CRITICAL, "https://x.test")]
    doc = json.loads(render_json(result))
    assert doc["stats"]["findings"] == 1
    assert doc["findings"][0]["severity"] == "critical"


# --- plugin behavior ------------------------------------------------------

@pytest.mark.asyncio
async def test_security_headers_flags_missing():
    from webscan.plugins.security_headers import SecurityHeaders

    def router(method, url, kw):
        return resp(url, headers={"Content-Type": "text/html"})

    ctx = make_ctx("https://x.test/", router)
    findings = [f async for f in SecurityHeaders().run(ctx)]
    titles = {f.title for f in findings}
    assert any("content-security-policy" in t for t in titles)


@pytest.mark.asyncio
async def test_secrets_detects_aws_key():
    from webscan.plugins.secrets import Secrets

    body = "config = { key: 'AKIAIOSFODNN7EXAMPLE' }"

    def router(method, url, kw):
        return resp(url, text=body)

    ctx = make_ctx("https://x.test/app.js", router)
    findings = [f async for f in Secrets().run(ctx)]
    assert findings and findings[0].severity >= Severity.HIGH


@pytest.mark.asyncio
async def test_sqli_detects_error_vs_baseline():
    from webscan.plugins.sqli import SqlInjection

    def router(method, url, kw):
        if "%27" in url or "'" in url:
            return resp(url, text="You have an error in your SQL syntax; check the manual for MySQL")
        return resp(url, text="normal page")

    ctx = make_ctx("https://x.test/item?id=5", router)
    findings = [f async for f in SqlInjection().run(ctx)]
    assert findings and findings[0].cwe == "CWE-89"


@pytest.mark.asyncio
async def test_xss_reflection_unencoded():
    from webscan.plugins.xss import ReflectedXss

    def router(method, url, kw):
        # Echo back the raw param value (simulating no encoding).
        from urllib.parse import parse_qs, urlparse
        q = parse_qs(urlparse(url).query)
        val = q.get("name", [""])[0]
        return resp(url, text=f"<div>hi {val}</div>")

    ctx = make_ctx("https://x.test/?name=bob", router)
    findings = [f async for f in ReflectedXss().run(ctx)]
    assert findings and findings[0].severity == Severity.HIGH


@pytest.mark.asyncio
async def test_active_plugin_skipped_when_inactive():
    from webscan.plugins.sqli import SqlInjection

    profile = get_profile("safe")
    profile.active = False
    assert SqlInjection().should_run(profile) is False
