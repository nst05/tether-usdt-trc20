#!/usr/bin/env python3
"""
Valkyrie — universal grey/black-box web security scanner for AUTHORIZED testing.

Engine module. Provides the Scanner used both by the CLI (this file) and by the
GUI (valkyrie_gui.py).

Design goals
------------
* Target-agnostic: works against any HTTP(S) application you are allowed to test.
* Behavioral, differential core: calibrate a baseline, then flag responses that
  deviate (5xx errors, large size variance, abnormal latency) under structural
  input mutation — instead of relying only on static payload signatures.
* Confirmation built in: every finding carries concrete proof (the exact request
  and a response excerpt) and a confirmed/potential status. Anomalies that can be
  re-tested (errors, timing) are re-requested to reduce false positives.
* Safe by default: scoped to loopback / private networks, GET-only probing,
  rate-limited, bounded request budget, no destructive actions.

This is a defensive/assessment tool. It deliberately does NOT implement
detection-evasion, traffic obfuscation, credential brute-forcing or any
feature whose only purpose is unauthorized access. Only run it against systems
you own or have explicit written permission to test.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import socket
import ssl
import sys
import time
import uuid
from dataclasses import dataclass, field, asdict
from html.parser import HTMLParser
from statistics import mean, median, pstdev
from urllib.parse import (
    urljoin, urlparse, urlencode, parse_qsl, urlunparse,
)
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


# ── data model ──────────────────────────────────────────────────────────────

SEVERITY_ORDER = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


@dataclass
class Proof:
    """Concrete evidence attached to a finding so it can be independently verified."""
    method: str = "GET"
    url: str = ""
    request_headers: dict = field(default_factory=dict)
    status: int = 0
    response_headers: dict = field(default_factory=dict)
    response_excerpt: str = ""
    elapsed_ms: int = 0


@dataclass
class Finding:
    severity: str          # info|low|medium|high|critical
    title: str
    url: str
    detail: str
    evidence: str = ""
    category: str = ""
    confirmed: bool = False
    confirmation: str = ""             # how it was verified
    proof: Proof = field(default_factory=Proof)
    id: int = 0

    def key(self):
        return (self.title, self.url, self.evidence)


@dataclass
class Baseline:
    latency_mean: float
    latency_std: float
    size_mean: float
    size_std: float
    statuses: dict = field(default_factory=dict)


# ── HTTP client (stdlib only) ───────────────────────────────────────────────

class Client:
    def __init__(self, delay=0.15, timeout=12.0, max_requests=2000,
                 user_agent="Valkyrie/1.1 (authorized-scan)", verify_tls=True,
                 max_body=512_000, cookie=None, stop_check=None):
        self.delay = delay
        self.timeout = timeout
        self.max_requests = max_requests
        self.user_agent = user_agent
        self.max_body = max_body
        self.cookie = cookie
        self.stop_check = stop_check or (lambda: False)
        self.count = 0

        if verify_tls:
            self.ctx = ssl.create_default_context()
        else:
            self.ctx = ssl._create_unverified_context()

    def budget_left(self):
        return self.max_requests - self.count

    def _req_headers(self, extra=None):
        headers = {"User-Agent": self.user_agent, "Accept": "*/*"}
        if self.cookie:
            headers["Cookie"] = self.cookie
        if extra:
            headers.update(extra)
        return headers

    def get(self, url, extra_headers=None) -> Response:
        return self._request("GET", url, None, extra_headers)

    def post(self, url, data, extra_headers=None) -> Response:
        body = urlencode(data).encode("utf-8")
        hdrs = {"Content-Type": "application/x-www-form-urlencoded"}
        if extra_headers:
            hdrs.update(extra_headers)
        return self._request("POST", url, body, hdrs)

    def _request(self, method, url, body, extra_headers) -> Response:
        if self.count >= self.max_requests or self.stop_check():
            return Response(url, 0, 0.0, 0, {}, "", error="stopped-or-budget-exhausted",
                            method=method)
        self.count += 1
        headers = self._req_headers(extra_headers)
        req = Request(url, data=body, headers=headers, method=method)
        t0 = time.perf_counter()
        try:
            with urlopen(req, timeout=self.timeout, context=self.ctx) as resp:
                raw = resp.read(self.max_body)
                elapsed = time.perf_counter() - t0
                rbody = raw.decode(resp.headers.get_content_charset() or "utf-8",
                                   errors="replace")
                hdrs = {k.lower(): v for k, v in resp.headers.items()}
                r = Response(url, resp.status, elapsed, len(raw), hdrs, rbody, method=method)
        except HTTPError as e:
            elapsed = time.perf_counter() - t0
            raw = b""
            try:
                raw = e.read(self.max_body)
            except Exception:
                pass
            rbody = raw.decode("utf-8", errors="replace")
            hdrs = {k.lower(): v for k, v in (e.headers or {}).items()}
            r = Response(url, e.code, elapsed, len(raw), hdrs, rbody, method=method)
        except (URLError, socket.timeout, TimeoutError) as e:
            elapsed = time.perf_counter() - t0
            r = Response(url, 0, elapsed, 0, {}, "", error=str(e), method=method)
        except Exception as e:  # noqa: BLE001 - never let a probe crash the scan
            elapsed = time.perf_counter() - t0
            r = Response(url, 0, elapsed, 0, {}, "", error=repr(e), method=method)
        r.request_headers = headers
        if self.delay and not self.stop_check():
            time.sleep(self.delay)
        return r


@dataclass
class Response:
    url: str
    status: int
    elapsed: float           # seconds
    size: int                # bytes of body
    headers: dict
    body: str
    error: str = ""
    request_headers: dict = field(default_factory=dict)
    method: str = "GET"


# ── HTML parsing: links, forms, parameters ──────────────────────────────────

class _LinkFormParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.forms = []
        self._cur = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        elif tag in ("script", "img", "iframe") and a.get("src"):
            self.links.append(a["src"])
        elif tag == "link" and a.get("href"):
            self.links.append(a["href"])
        elif tag == "form":
            self._cur = {"action": a.get("action", ""),
                         "method": (a.get("method") or "get").lower(),
                         "inputs": []}
        elif tag in ("input", "textarea", "select") and self._cur is not None:
            if a.get("name"):
                self._cur["inputs"].append({
                    "name": a["name"],
                    "type": (a.get("type") or
                             ("textarea" if tag == "textarea" else "text")).lower(),
                    "value": a.get("value", ""),
                })

    def handle_endtag(self, tag):
        if tag == "form" and self._cur is not None:
            self.forms.append(self._cur)
            self._cur = None


def extract_links_forms(base_url, html):
    p = _LinkFormParser()
    try:
        p.feed(html)
    except Exception:
        pass
    links = {urljoin(base_url, l) for l in p.links}
    return links, p.forms


# ── error / reflection signatures and mutations ─────────────────────────────

ERROR_SIGNATURES = [
    "Traceback (most recent call last)", "Werkzeug Debugger",
    "java.lang.", "javax.servlet", "System.Web", "ASP.NET",
    "PHP Warning", "PHP Fatal error", "PHP Notice", "Stack trace:",
    "SQLSTATE", "SQL syntax", "ORA-0", "psql:", "pg_query",
    "You have an error in your SQL syntax", "Microsoft OLE DB",
    "Unclosed quotation mark", "ODBC SQL", "Undefined index",
    "Fatal error", "Notice: Undefined", "Warning: include",
]

SECRET_SIGNATURES = [
    "BEGIN RSA PRIVATE KEY", "BEGIN OPENSSH PRIVATE KEY", "BEGIN PRIVATE KEY",
    "aws_secret_access_key", "SECRET_KEY", "DB_PASSWORD", "API_KEY=",
    "[core]", "ref: refs/heads",  # .git config / HEAD
]

SENSITIVE_PATHS = [
    "/.env", "/.git/config", "/.git/HEAD", "/config.php", "/wp-config.php",
    "/.svn/entries", "/backup.zip", "/backup.sql", "/db.sqlite3",
    "/.DS_Store", "/server-status", "/phpinfo.php", "/.htaccess",
    "/docker-compose.yml", "/.aws/credentials", "/id_rsa",
]

# Signatures that *confirm* a read primitive (local file inclusion / traversal).
LFI_SIGNATURES = [
    "root:x:0:0:", "root:!:0:0:", "daemon:x:", "[fonts]",
    "; for 16-bit app support", "[extensions]",
]

# (probe, expected) pairs for server-side template injection. 7*8=56 avoids
# colliding with common page numbers like 49/14.
SSTI_PROBES = [
    ("{{7*8}}", "56"), ("${7*8}", "56"), ("<%= 7*8 %>", "56"),
    ("#{7*8}", "56"), ("{7*8}", "56"),
]

# parameter names that commonly drive redirects (open-redirect surface)
REDIRECT_PARAM_HINTS = {
    "next", "url", "redirect", "redirect_uri", "redirect_url", "return",
    "returnurl", "return_to", "dest", "destination", "continue", "goto", "to",
}

# Structural mutations — force the backend down un-handled code paths
# without using attack-signature payloads.
MUTATIONS = [
    ("empty", ""),
    ("array", "__ARRAY__"),          # rendered as param[]=1&param[]=2
    ("null_byte", "x\x00y"),
    ("type_confusion", "0e0"),
    ("large_int", "9" * 40),
    ("negative", "-1"),
    ("overflow_str", "A" * 4096),
    ("special", "'\"<>{}|;`$()"),
    ("format", "%n%s%x"),
    ("path", "../../../../etc/passwd"),
    ("unicode", "％００毛"),
]


# ── scope / authorization guard ─────────────────────────────────────────────

def host_is_local(host) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = info[4][0]
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if not (addr.is_loopback or addr.is_private or addr.is_link_local):
            return False
    return True


def _excerpt(text, n=600):
    text = text.replace("\x00", "\\x00")
    return text[:n]


# ── scanner ─────────────────────────────────────────────────────────────────

class Scanner:
    def __init__(self, base_url, client: Client, max_pages=80, fuzz=True,
                 active=True, test_forms=True, idor=True, allow_destructive=False,
                 on_finding=None, on_progress=None):
        self.base = base_url.rstrip("/")
        self.client = client
        self.max_pages = max_pages
        self.fuzz = fuzz
        self.active = active
        self.test_forms_enabled = test_forms
        self.idor_enabled = idor
        self.allow_destructive = allow_destructive
        self.on_finding = on_finding          # callback(Finding)
        self.on_progress = on_progress        # callback(phase, info dict)
        self.origin = urlparse(self.base)
        self.findings: list[Finding] = []
        self._seen_findings = set()
        self._fid = 0
        self.visited = set()
        self.baseline: Baseline | None = None
        self.phase = "idle"

    # -- progress / findings --
    def set_phase(self, phase):
        self.phase = phase
        if self.on_progress:
            self.on_progress(phase, self.progress())

    def progress(self):
        return {
            "phase": self.phase,
            "requests": self.client.count,
            "budget": self.client.max_requests,
            "pages": len(self.visited),
            "findings": len(self.findings),
        }

    def add(self, severity, title, url, detail, evidence="", category="",
            confirmed=False, confirmation="", proof=None):
        f = Finding(severity, title, url, detail, _excerpt(evidence, 500),
                    category, confirmed, confirmation, proof or Proof())
        if f.key() in self._seen_findings:
            return None
        self._fid += 1
        f.id = self._fid
        self._seen_findings.add(f.key())
        self.findings.append(f)
        if self.on_finding:
            self.on_finding(f)
        return f

    @staticmethod
    def proof_from(r: Response) -> Proof:
        return Proof(
            method=r.method, url=r.url,
            request_headers=dict(r.request_headers),
            status=r.status,
            response_headers=dict(list(r.headers.items())[:25]),
            response_excerpt=_excerpt(r.body),
            elapsed_ms=int(r.elapsed * 1000),
        )

    def same_origin(self, url):
        u = urlparse(url)
        return (u.scheme in ("http", "https") and u.netloc == self.origin.netloc)

    # -- phase 1: baseline calibration --
    def calibrate(self, samples=5):
        self.set_phase("calibrating")
        lat, siz, statuses = [], [], {}
        for _ in range(samples):
            r = self.client.get(self.base)
            if r.error:
                continue
            lat.append(r.elapsed)
            siz.append(r.size)
            statuses[r.status] = statuses.get(r.status, 0) + 1
        if not lat:
            self.add("info", "Target unreachable during calibration", self.base,
                     "No successful baseline responses; check the URL and that the "
                     "server is running.", confirmed=True,
                     confirmation="No HTTP response received on repeated requests.")
            return
        self.baseline = Baseline(
            latency_mean=mean(lat),
            latency_std=pstdev(lat) if len(lat) > 1 else 0.0,
            size_mean=mean(siz),
            size_std=pstdev(siz) if len(siz) > 1 else 0.0,
            statuses=statuses,
        )

    # -- phase 2: passive posture checks --
    def passive_checks(self, r: Response):
        h = r.headers
        url = r.url
        proof = self.proof_from(r)
        for header, sev, why in [
            ("content-security-policy", "medium", "no CSP — XSS / data-injection mitigations absent"),
            ("x-content-type-options", "low", "missing nosniff — MIME sniffing possible"),
            ("x-frame-options", "low", "no anti-clickjacking header (or CSP frame-ancestors)"),
            ("strict-transport-security", "low", "no HSTS (only relevant over HTTPS)"),
            ("referrer-policy", "info", "no referrer policy"),
        ]:
            if header not in h:
                # deterministic: the header is simply absent in the response
                self.add(sev, f"Missing security header: {header}", url, why,
                         category="headers", confirmed=True,
                         confirmation="Header absent from the live response.",
                         proof=proof)
        if "server" in h and any(c.isdigit() for c in h["server"]):
            self.add("info", "Server version disclosed", url,
                     "Server banner leaks software/version, aiding fingerprinting.",
                     evidence=h["server"], category="info-leak", confirmed=True,
                     confirmation="Value read directly from Server header.", proof=proof)
        if "x-powered-by" in h:
            self.add("info", "Technology disclosed via X-Powered-By", url,
                     "Reveals backend stack.", evidence=h["x-powered-by"],
                     category="info-leak", confirmed=True,
                     confirmation="Value read directly from X-Powered-By header.",
                     proof=proof)
        set_cookie = h.get("set-cookie", "")
        if set_cookie:
            low = set_cookie.lower()
            if "httponly" not in low:
                self.add("medium", "Cookie without HttpOnly", url,
                         "Session cookie readable by JavaScript (XSS → session theft).",
                         evidence=set_cookie, category="cookies", confirmed=True,
                         confirmation="HttpOnly flag absent from Set-Cookie.", proof=proof)
            if "samesite" not in low:
                self.add("low", "Cookie without SameSite", url,
                         "Cookie sent cross-site → CSRF exposure.",
                         evidence=set_cookie, category="cookies", confirmed=True,
                         confirmation="SameSite attribute absent from Set-Cookie.",
                         proof=proof)
            if self.origin.scheme == "https" and "secure" not in low:
                self.add("medium", "Cookie without Secure over HTTPS", url,
                         "Cookie may leak over plaintext.", evidence=set_cookie,
                         category="cookies", confirmed=True,
                         confirmation="Secure flag absent over an HTTPS origin.",
                         proof=proof)
        for sig in ERROR_SIGNATURES:
            if sig in r.body:
                self.add("high", "Verbose error / stack trace disclosure", url,
                         "Response leaks server-side error internals.",
                         evidence=sig, category="info-leak", confirmed=True,
                         confirmation=f"Error signature '{sig}' present in response body.",
                         proof=proof)
                break

    # -- phase 3: recon of well-known/sensitive paths --
    def recon(self):
        self.set_phase("recon")
        extra = set()
        for path in ("/robots.txt", "/sitemap.xml"):
            r = self.client.get(self.base + path)
            if r.status == 200 and r.body.strip():
                for line in r.body.splitlines():
                    line = line.strip()
                    if line.lower().startswith(("disallow:", "allow:")):
                        p = line.split(":", 1)[1].strip()
                        if p and p != "/":
                            extra.add(urljoin(self.base, p))
                    if line.startswith("<loc>"):
                        loc = line.replace("<loc>", "").replace("</loc>", "").strip()
                        if self.same_origin(loc):
                            extra.add(loc)
        for path in SENSITIVE_PATHS:
            if self.client.budget_left() <= 0 or self.client.stop_check():
                break
            r = self.client.get(self.base + path)
            if r.status == 200 and r.size > 0:
                # confirm by inspecting body for secret signatures where possible
                leaked = next((s for s in SECRET_SIGNATURES if s in r.body), "")
                sev = "critical" if leaked else "high"
                conf = bool(leaked)
                self.add(sev, "Sensitive path is accessible", r.url,
                         "A sensitive/configuration path returned 200 with content. "
                         + ("Body matches a known secret/VCS signature."
                            if leaked else
                            "Verify it does not expose secrets, source or internals."),
                         evidence=(f"signature: {leaked}" if leaked
                                   else f"status=200 size={r.size}"),
                         category="exposure", confirmed=conf,
                         confirmation=(f"Returned 200 and body contains '{leaked}'."
                                       if leaked else
                                       "Returned 200; content type/secret not auto-verified."),
                         proof=self.proof_from(r))
        return extra

    # -- phase 4: crawl --
    def crawl(self, seeds):
        self.set_phase("crawling")
        queue = [self.base] + sorted(seeds)
        param_urls = set()
        forms_seen = []
        while (queue and len(self.visited) < self.max_pages
               and self.client.budget_left() > 0 and not self.client.stop_check()):
            url = queue.pop(0)
            norm = url.split("#")[0]
            if norm in self.visited or not self.same_origin(norm):
                continue
            self.visited.add(norm)
            r = self.client.get(norm)
            self.set_phase("crawling")
            if r.error:
                continue
            self.passive_checks(r)
            if urlparse(norm).query:
                param_urls.add(norm)
            if "html" in r.headers.get("content-type", ""):
                links, forms = extract_links_forms(norm, r.body)
                for fm in forms:
                    fm["page"] = norm
                    forms_seen.append(fm)
                for l in links:
                    l = l.split("#")[0]
                    if self.same_origin(l) and l not in self.visited:
                        if urlparse(l).query:
                            param_urls.add(l)
                        queue.append(l)
        return param_urls, forms_seen

    # -- phase 5: behavioral differential fuzzing + confirmation --
    def fuzz_params(self, param_urls):
        if not self.fuzz or not self.baseline:
            return
        self.set_phase("fuzzing")
        for url in sorted(param_urls):
            if self.client.budget_left() <= 0 or self.client.stop_check():
                break
            parsed = urlparse(url)
            params = parse_qsl(parsed.query, keep_blank_values=True)
            if not params:
                continue
            base_r = self.client.get(url)
            local_size = base_r.size
            local_lat = base_r.elapsed
            for idx, (name, val) in enumerate(params):
                for mut_name, payload in MUTATIONS:
                    if self.client.budget_left() <= 0 or self.client.stop_check():
                        break
                    mutated = self._mutate(parsed, params, idx, payload)
                    r = self.client.get(mutated)
                    self.set_phase("fuzzing")
                    self._analyze_delta(r, mutated, name, mut_name,
                                        local_size, local_lat)
                if self.active and not self.client.stop_check():
                    send = (lambda p, _i=idx:
                            self.client.get(self._mutate(parsed, params, _i, p)))
                    self._confirm_injections(url, name, val, local_size, send)

    def _mutate(self, parsed, params, idx, payload):
        new = list(params)
        name = new[idx][0]
        if payload == "__ARRAY__":
            new = [(k, v) for j, (k, v) in enumerate(new) if j != idx]
            new += [(f"{name}[]", "1"), (f"{name}[]", "2")]
        else:
            new[idx] = (name, payload)
        q = urlencode(new)
        return urlunparse(parsed._replace(query=q))

    # -- active, confirming exploit checks (own/authorized targets only) --
    # All checks are sender-based: `send(payload)` applies the payload to the
    # single input under test (a GET parameter OR a form field) and returns the
    # Response. This lets the same confirmation logic drive GET and POST probes.
    def _confirm_injections(self, label, field, baseval, base_size, send,
                            test_redirect=None):
        """Run payloads that *prove* a vulnerability class with concrete output."""
        if test_redirect is None:
            test_redirect = field.lower() in REDIRECT_PARAM_HINTS
        self._chk_reflection(label, field, send)
        self._chk_ssti(label, field, send)
        self._chk_traversal(label, field, send)
        self._chk_sqli(label, field, baseval, base_size, send)
        self._chk_cmdi(label, field, baseval, send)
        if test_redirect:
            self._chk_open_redirect(label, field, send)

    def _chk_reflection(self, label, field, send):
        if self.client.budget_left() <= 0 or self.client.stop_check():
            return
        marker = "vzq" + uuid.uuid4().hex[:8] + "zqv"
        probe = "<%s>" % marker
        r = send(probe)
        if r.error:
            return
        if probe in r.body:
            self.add("high", "Reflected unencoded input (XSS-capable)", label,
                     f"Input '{field}' is reflected with '<' and '>' intact, "
                     "so injected markup is not output-encoded.",
                     evidence=f"reflected verbatim: {probe}", category="xss",
                     confirmed=True,
                     confirmation="A unique probe containing angle brackets was "
                                  "returned byte-for-byte in the response body.",
                     proof=self.proof_from(r))
        elif marker in r.body:
            self.add("info", "Input reflected (encoded)", label,
                     f"Input '{field}' is reflected but angle brackets appear "
                     "encoded. Confirm context-specific encoding.",
                     evidence=marker, category="xss", confirmed=False,
                     confirmation="Marker present but brackets not verbatim; "
                                  "needs manual context review.",
                     proof=self.proof_from(r))

    def _chk_ssti(self, label, field, send):
        for probe, expected in SSTI_PROBES:
            if self.client.budget_left() <= 0 or self.client.stop_check():
                return
            r = send(probe)
            if r.error:
                continue
            if expected in r.body and probe not in r.body:
                self.add("critical", "Server-Side Template Injection (confirmed)", label,
                         f"Input '{field}': template expression '{probe}' was "
                         f"evaluated to '{expected}', proving server-side code "
                         "evaluation (SSTI → often RCE).",
                         evidence=f"{probe} -> {expected}", category="ssti",
                         confirmed=True,
                         confirmation="Injected arithmetic was computed by the "
                                      "template engine and returned as its result.",
                         proof=self.proof_from(r))
                return

    def _chk_traversal(self, label, field, send):
        for payload in ("../../../../../../etc/passwd",
                        "....//....//....//....//etc/passwd",
                        "..\\..\\..\\..\\windows\\win.ini"):
            if self.client.budget_left() <= 0 or self.client.stop_check():
                return
            r = send(payload)
            if r.error:
                continue
            sig = next((s for s in LFI_SIGNATURES if s in r.body), "")
            if sig:
                self.add("critical", "Path traversal / Local File Inclusion (confirmed)",
                         label, f"Input '{field}' returned host file contents using "
                         f"'{payload}'.",
                         evidence=f"file signature: {sig}", category="lfi",
                         confirmed=True,
                         confirmation=f"Response body contains the OS file marker '{sig}'.",
                         proof=self.proof_from(r))
                return

    def _chk_sqli(self, label, field, baseval, base_size, send):
        if self.client.budget_left() <= 0 or self.client.stop_check():
            return
        err_r = send(baseval + "'")
        if not err_r.error:
            sig = next((s for s in ERROR_SIGNATURES
                        if s in err_r.body and ("SQL" in s or "ORA-" in s
                                                or "psql" in s or "SQLSTATE" in s
                                                or "quotation" in s or "ODBC" in s)), "")
            if sig:
                self.add("high", "SQL injection — error-based (confirmed)", label,
                         f"Input '{field}': a single quote triggered a database "
                         "error, indicating input reaches a SQL statement unsanitized.",
                         evidence=sig, category="sqli", confirmed=True,
                         confirmation=f"DB error signature '{sig}' appeared after "
                                      "injecting a quote.",
                         proof=self.proof_from(err_r))
                return
        if self.client.budget_left() < 2 or self.client.stop_check():
            return
        t_r = send(baseval + "' OR '1'='1")
        f_r = send(baseval + "' AND '1'='2")
        if t_r.error or f_r.error:
            return
        if (t_r.status == f_r.status == 200
                and abs(t_r.size - f_r.size) > max(64, base_size * 0.25)
                and t_r.size != base_size):
            self.add("high", "SQL injection — boolean-based (potential)", label,
                     f"Input '{field}': TRUE and FALSE SQL conditions produced "
                     f"materially different responses ({t_r.size} vs {f_r.size} bytes), "
                     "suggesting the input alters query logic.",
                     evidence=f"true={t_r.size}B false={f_r.size}B", category="sqli",
                     confirmed=False,
                     confirmation="Differential size between boolean conditions; "
                                  "verify with a manual payload.",
                     proof=self.proof_from(t_r))

    def _chk_cmdi(self, label, field, baseval, send):
        sleep_secs = 5
        for sep in (f"; sleep {sleep_secs}", f"| sleep {sleep_secs}",
                    f"`sleep {sleep_secs}`", f"$(sleep {sleep_secs})",
                    f"& timeout {sleep_secs}"):
            if self.client.budget_left() < 2 or self.client.stop_check():
                return
            payload = baseval + sep
            r = send(payload)
            if not r.error and r.elapsed >= sleep_secs - 1:
                r2 = send(payload)
                if not r2.error and r2.elapsed >= sleep_secs - 1:
                    self.add("critical", "OS command injection — time-based (confirmed)",
                             label, f"Input '{field}': injecting '{sep.strip()}' delayed "
                             f"the response by ~{r.elapsed:.1f}s twice, proving the input "
                             "reaches an OS command.",
                             evidence=f"{sep.strip()} -> {r.elapsed:.1f}s / {r2.elapsed:.1f}s",
                             category="cmdi", confirmed=True,
                             confirmation="Injected sleep delay reproduced on a second "
                                          "request.",
                             proof=self.proof_from(r))
                    return

    def _chk_open_redirect(self, label, field, send):
        marker = "valkyrie-redirect.example"
        for payload in (f"https://{marker}/", f"//{marker}/"):
            if self.client.budget_left() <= 0 or self.client.stop_check():
                return
            r = send(payload)
            loc = r.headers.get("location", "")
            if marker in loc and (loc.startswith("http") or loc.startswith("//")):
                self.add("medium", "Open redirect (confirmed)", label,
                         f"Input '{field}' is reflected into the Location header, "
                         "allowing redirection to an attacker-controlled host.",
                         evidence=f"Location: {loc}", category="redirect",
                         confirmed=True,
                         confirmation="External host appeared in the redirect Location.",
                         proof=self.proof_from(r))
                return

    # -- phase 6: form (POST/GET) testing with CSRF passthrough --
    DESTRUCTIVE_HINTS = ("delete", "remove", "destroy", "drop", "logout",
                         "cancel", "close", "restore", "reset", "wipe")
    CSRF_FIELD_HINTS = ("csrf", "authenticity_token", "__requestverificationtoken",
                        "_token", "nonce")
    SKIP_INPUT_TYPES = {"hidden", "submit", "button", "image", "file",
                        "checkbox", "radio", "reset"}

    def _is_destructive(self, action):
        path = urlparse(action).path.lower()
        return any(h in path for h in self.DESTRUCTIVE_HINTS)

    def _submit(self, action, method, data):
        if method == "post":
            return self.client.post(action, data)
        parsed = urlparse(action)
        merged = parse_qsl(parsed.query, keep_blank_values=True) + list(data.items())
        return self.client.get(urlunparse(parsed._replace(query=urlencode(merged))))

    def test_forms(self, forms):
        if not (self.active and self.test_forms_enabled) or not forms:
            return
        self.set_phase("forms")
        seen = set()
        for fm in forms:
            if self.client.budget_left() <= 0 or self.client.stop_check():
                break
            action = urljoin(fm.get("page", self.base), fm.get("action") or "")
            action = action or fm.get("page", self.base)
            if not self.same_origin(action):
                continue
            method = fm.get("method", "get")
            inputs = fm.get("inputs", [])
            names = tuple(sorted(i["name"] for i in inputs))
            key = (action, method, names)
            if key in seen:
                continue
            seen.add(key)
            if method == "post" and self._is_destructive(action) \
                    and not self.allow_destructive:
                self.add("info", "Skipped potentially destructive form", action,
                         "A POST form whose action looks state-changing "
                         f"({action}) was not submitted to avoid data loss. "
                         "Enable destructive testing to include it.",
                         category="forms", confirmed=False,
                         confirmation="Skipped by safety policy.")
                continue
            # baseline submission values (carry hidden values incl. CSRF token)
            data = {}
            for i in inputs:
                data[i["name"]] = i.get("value") or "valkyrie"
            base = self._submit(action, method, data)
            self.set_phase("forms")
            if base.error:
                continue
            bsize = base.size
            for i in inputs:
                if self.client.budget_left() <= 0 or self.client.stop_check():
                    break
                name = i["name"]
                itype = (i.get("type") or "text").lower()
                if itype in self.SKIP_INPUT_TYPES:
                    continue
                if any(h in name.lower() for h in self.CSRF_FIELD_HINTS):
                    continue
                baseval = data.get(name, "") or ""
                label = f"{method.upper()} {action} [{name}]"
                send = (lambda p, _n=name:
                        self._submit(action, method, {**data, _n: p}))
                self._confirm_injections(label, name, baseval, bsize, send,
                                         test_redirect=name.lower() in REDIRECT_PARAM_HINTS)

    # -- phase 7: IDOR / object enumeration on numeric identifiers --
    def idor_scan(self, candidate_urls):
        if not (self.active and self.idor_enabled):
            return
        self.set_phase("idor")
        targets = self._idor_candidates(candidate_urls)
        for (kind, sig), info in list(targets.items()):
            if self.client.budget_left() <= 4 or self.client.stop_check():
                break
            self._probe_idor(kind, info)

    def _idor_candidates(self, urls):
        """Find endpoints keyed by a numeric path segment or numeric query value."""
        cands = {}
        for url in urls:
            u = urlparse(url)
            segs = u.path.split("/")
            for i, s in enumerate(segs):
                if s.isdigit() and len(s) <= 9:
                    tmpl = "/".join(segs[:i] + ["{}"] + segs[i + 1:])
                    cands.setdefault(("path", tmpl + "?" + u.query),
                                     {"url": url, "base": int(s), "seg": i,
                                      "segs": segs, "query": u.query})
            for k, v in parse_qsl(u.query, keep_blank_values=True):
                if v.isdigit() and len(v) <= 9:
                    cands.setdefault(("query", u.path + "|" + k),
                                     {"url": url, "base": int(v), "param": k})
        return cands

    def _build_idor_url(self, info, new_id, kind):
        if kind == "path":
            segs = list(info["segs"])
            segs[info["seg"]] = str(new_id)
            parsed = urlparse(info["url"])
            return urlunparse(parsed._replace(path="/".join(segs)))
        parsed = urlparse(info["url"])
        params = parse_qsl(parsed.query, keep_blank_values=True)
        params = [(k, str(new_id) if k == info["param"] else v) for k, v in params]
        return urlunparse(parsed._replace(query=urlencode(params)))

    def _probe_idor(self, kind, info):
        base_id = info["base"]
        ids = []
        for cand in (1, 2, 3, base_id, base_id + 1, base_id + 2):
            if cand >= 1 and cand not in ids:
                ids.append(cand)
        accessible = []      # (id, response) returning 200 with content
        bodies = {}
        for tid in ids:
            if self.client.budget_left() <= 0 or self.client.stop_check():
                break
            u = self._build_idor_url(info, tid, kind)
            r = self.client.get(u)
            if not r.error and r.status == 200 and r.size > 0:
                accessible.append((tid, r))
                bodies[tid] = r.body[:2000]
        # distinct objects = different bodies among accessible ids
        distinct = len({b for b in bodies.values()})
        if len(accessible) >= 2 and distinct >= 2:
            sample_id, sample_r = accessible[0]
            ident = info.get("param", f"path segment #{info.get('seg')}")
            self.add("high", "Insecure Direct Object Reference / object enumeration",
                     sample_r.url,
                     f"Identifier '{ident}' can be walked: {len(accessible)} ids "
                     f"({', '.join(str(i) for i, _ in accessible)}) each return a "
                     f"distinct 200 object with no access-control boundary observed. "
                     "Objects are directly addressable by id.",
                     evidence=f"{len(accessible)} accessible / {distinct} distinct bodies",
                     category="idor", confirmed=True,
                     confirmation="Multiple sequential ids returned different objects "
                                  "with HTTP 200 in the same (unauthorized) context.",
                     proof=self.proof_from(sample_r))

    def _analyze_delta(self, r, url, param, mut_name, base_size, base_lat):
        if r.error:
            if "timed out" in r.error.lower() or "timeout" in r.error.lower():
                # confirm a timing/DoS lead by retrying
                confirmed, samples = self._confirm_timeout(url)
                self.add("medium", "Time-based anomaly (possible DoS / blind injection)",
                         url, f"Mutation '{mut_name}' on '{param}' caused a timeout — "
                         "algorithmic complexity or blind injection surface.",
                         evidence=r.error, category="dos", confirmed=confirmed,
                         confirmation=(f"Timeout reproduced on retry ({samples})."
                                       if confirmed else
                                       "Single timeout; could be transient."),
                         proof=self.proof_from(r))
            return
        if r.status >= 500:
            confirmed, again = self._confirm_status(url, 500)
            self.add("high", "Unhandled server error under input mutation", url,
                     f"Mutation '{mut_name}' on parameter '{param}' produced HTTP "
                     f"{r.status} — an unhandled backend exception (input validation "
                     "or injection surface).",
                     evidence=f"status={r.status}", category="error-anomaly",
                     confirmed=confirmed,
                     confirmation=(f"Re-request reproduced a {again} response."
                                   if confirmed else
                                   "Not reproduced on retry; may be transient."),
                     proof=self.proof_from(r))
            for sig in ERROR_SIGNATURES:
                if sig in r.body:
                    self.add("high", "Stack trace exposed under input mutation", url,
                             f"Error body leaks internals after '{mut_name}' on '{param}'.",
                             evidence=sig, category="info-leak", confirmed=True,
                             confirmation=f"Error signature '{sig}' present in 5xx body.",
                             proof=self.proof_from(r))
                    break
            return
        b = self.baseline
        thresh = max(base_lat * 5, b.latency_mean + 6 * b.latency_std, 2.5)
        if r.elapsed > thresh and r.elapsed > 1.5:
            confirmed, med = self._confirm_slow(url, thresh)
            self.add("medium", "Time-delay anomaly", url,
                     f"Mutation '{mut_name}' on '{param}' took {r.elapsed:.2f}s vs "
                     f"~{base_lat:.2f}s baseline (heavy code path / possible DoS).",
                     evidence=f"{r.elapsed:.2f}s", category="dos", confirmed=confirmed,
                     confirmation=(f"Re-measured median {med:.2f}s stays above "
                                   f"{thresh:.2f}s threshold." if confirmed else
                                   "Did not stay slow on re-measurement."),
                     proof=self.proof_from(r))
        if base_size > 0:
            ratio = r.size / max(base_size, 1)
            if (ratio > 3 or ratio < 0.33) and abs(r.size - base_size) > 512:
                self.add("low", "Response size variance anomaly", url,
                         f"Mutation '{mut_name}' on '{param}' shifted body size "
                         f"{base_size}→{r.size} bytes — inspect for hidden/debug data.",
                         evidence=f"{base_size}->{r.size}", category="anomaly",
                         confirmed=False,
                         confirmation="Single-sample size delta; verify manually.",
                         proof=self.proof_from(r))

    # -- confirmation helpers --
    def _confirm_status(self, url, code):
        r = self.client.get(url)
        return (r.status >= code, r.status)

    def _confirm_timeout(self, url):
        hits = 0
        for _ in range(2):
            r = self.client.get(url)
            if r.error and ("timeout" in r.error.lower() or "timed out" in r.error.lower()):
                hits += 1
        return (hits >= 1, f"{hits}/2 retries")

    def _confirm_slow(self, url, thresh):
        samples = []
        for _ in range(3):
            r = self.client.get(url)
            if not r.error:
                samples.append(r.elapsed)
        if not samples:
            return (False, 0.0)
        med = median(samples)
        return (med > thresh, med)

    # -- orchestration --
    def run(self):
        self.calibrate()
        seeds = self.recon()
        param_urls, forms = self.crawl(seeds)
        self.fuzz_params(param_urls)
        self.test_forms(forms)
        self.idor_scan(set(param_urls) | set(self.visited))
        self.set_phase("done")
        return self.findings


# ── reporting (CLI) ─────────────────────────────────────────────────────────

def print_report(scanner: Scanner, started, fmt="text"):
    findings = sorted(scanner.findings,
                      key=lambda f: (-SEVERITY_ORDER.get(f.severity, 0),
                                     not f.confirmed))
    if fmt == "json":
        out = {
            "target": scanner.base,
            "requests": scanner.client.count,
            "pages_visited": len(scanner.visited),
            "duration_sec": round(time.time() - started, 1),
            "baseline": asdict(scanner.baseline) if scanner.baseline else None,
            "findings": [asdict(f) for f in findings],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    C = {"critical": "\033[95m", "high": "\033[91m", "medium": "\033[93m",
         "low": "\033[96m", "info": "\033[90m"}
    R = "\033[0m"
    use_color = sys.stdout.isatty()

    def col(s, sev):
        return f"{C.get(sev,'')}{s}{R}" if use_color else s

    print()
    print("=" * 72)
    print(f"  Valkyrie scan report — {scanner.base}")
    print("=" * 72)
    if scanner.baseline:
        b = scanner.baseline
        print(f"  baseline: latency {b.latency_mean*1000:.0f}ms "
              f"(±{b.latency_std*1000:.0f}ms), size ~{b.size_mean:.0f}B, "
              f"statuses {b.statuses}")
    print(f"  pages: {len(scanner.visited)}   requests: {scanner.client.count}   "
          f"duration: {time.time()-started:.1f}s")
    print("-" * 72)
    counts = {}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    print("  " + "  ".join(col(f"{s}:{counts.get(s,0)}", s)
                           for s in ("critical", "high", "medium", "low", "info")))
    confirmed_n = sum(1 for f in findings if f.confirmed)
    print(f"  confirmed: {confirmed_n}/{len(findings)}")
    print("-" * 72)
    if not findings:
        print("  No findings. (Absence of findings is not proof of security.)")
    for f in findings:
        tag = "CONFIRMED" if f.confirmed else "potential"
        print(f"  [{col(f.severity.upper(), f.severity)}] ({tag}) {f.title}")
        print(f"        url:    {f.url}")
        print(f"        detail: {f.detail}")
        if f.evidence:
            print(f"        evidence: {f.evidence}")
        if f.confirmation:
            print(f"        verify: {f.confirmation}")
        print()
    print("=" * 72)
    print("  'potential' findings are leads — validate manually. Test only what")
    print("  you are authorized to test.")
    print("=" * 72)


# ── CLI ─────────────────────────────────────────────────────────────────────

def build_scanner_from_args(args):
    target = args.target
    if "://" not in target:
        target = "http://" + target
    host = urlparse(target).hostname
    if not host:
        raise SystemExit("error: could not parse a hostname from target")
    if not host_is_local(host) and not args.i_am_authorized:
        raise SystemExit(
            "REFUSING TO SCAN: target is not loopback/private.\n"
            "This tool is for systems you own or are authorized to test.\n"
            "If you have explicit permission, re-run with --i-am-authorized.")
    client = Client(delay=args.delay, timeout=args.timeout,
                    max_requests=args.max_requests, verify_tls=not args.insecure,
                    cookie=args.cookie)
    return Scanner(target, client, max_pages=args.max_pages, fuzz=not args.no_fuzz,
                   active=not args.no_active, test_forms=not args.no_forms,
                   idor=not args.no_idor, allow_destructive=args.allow_destructive)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Valkyrie — universal web security scanner for AUTHORIZED testing.")
    ap.add_argument("target", help="Base URL, e.g. http://localhost:5000")
    ap.add_argument("--max-pages", type=int, default=80, help="crawl page cap")
    ap.add_argument("--max-requests", type=int, default=2000, help="total request budget")
    ap.add_argument("--delay", type=float, default=0.15, help="delay between requests (s)")
    ap.add_argument("--timeout", type=float, default=12.0, help="per-request timeout (s)")
    ap.add_argument("--no-fuzz", action="store_true", help="passive/crawl only")
    ap.add_argument("--no-active", action="store_true",
                    help="skip active exploit-confirmation payloads (SSTI/SQLi/LFI/cmdi)")
    ap.add_argument("--no-forms", action="store_true",
                    help="skip form (POST/GET) field testing")
    ap.add_argument("--no-idor", action="store_true",
                    help="skip IDOR / object-enumeration on numeric ids")
    ap.add_argument("--allow-destructive", action="store_true",
                    help="also submit forms whose action looks state-changing "
                         "(delete/restore/...). Use only on disposable test data.")
    ap.add_argument("--cookie", default=None, help="Cookie header for authenticated scans")
    ap.add_argument("--insecure", action="store_true", help="skip TLS verification")
    ap.add_argument("--json", action="store_true", help="JSON output")
    ap.add_argument("--i-am-authorized", action="store_true",
                    help="confirm you may test a non-local target")
    args = ap.parse_args(argv)
    scanner = build_scanner_from_args(args)
    started = time.time()
    try:
        scanner.run()
    except KeyboardInterrupt:
        print("\n[interrupted] reporting partial results...", file=sys.stderr)
    print_report(scanner, started, fmt="json" if args.json else "text")
    return 0


if __name__ == "__main__":
    sys.exit(main())
