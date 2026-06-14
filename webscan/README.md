# WebScan

An asynchronous web vulnerability scanner written in pure Python. Built on
`asyncio` + `aiohttp` so a single event loop can keep thousands of requests in
flight without paying for a thread per connection — the same idea the article
that inspired this project describes.

> ⚠️ **Authorized testing only.** WebScan sends HTTP requests (including
> non‑destructive probe payloads) to whatever targets you point it at. Only
> scan systems you own or have **explicit written permission** to test.
> Unauthorized scanning may be illegal in your jurisdiction.

## Why async, not threads

A scanner is almost entirely I/O‑bound — it spends its life waiting on the
network. Threads add memory and context‑switch overhead and force you to reason
about locks. With `asyncio` a single `HttpClient` (see
`webscan/core/http.py`) owns the connection pool and a global concurrency
semaphore, so every plugin shares one polite, well‑behaved client.

## Install

```bash
cd webscan
python -m pip install -e .
# or, without installing:
python -m pip install -r requirements.txt
```

Requires Python 3.10+.

## Usage

```bash
# Safe mode (default): conservative concurrency, no destructive payloads
webscan https://example.com/search?q=test

# List the built-in plugins
webscan --list-plugins

# Run only specific checks
webscan --only sqli,xss,secrets https://example.com/?id=1

# Stealth mode: request jitter + User-Agent rotation + optional proxy
webscan -m stealth --proxy http://127.0.0.1:8080 https://example.com/?id=1

# CI/CD mode: SARIF output, fail the build on HIGH+ findings
webscan -m cicd -o sarif --out-file results.sarif --fail-on high \
        --targets-file targets.txt
```

Run it as a module if you prefer: `python -m webscan ...`.

### Exit codes

| code | meaning                                              |
|------|------------------------------------------------------|
| 0    | scan completed, threshold (if any) not crossed       |
| 2    | a finding at/above `--fail-on` severity was found    |
| 130  | interrupted                                          |

## Scan modes

| mode      | concurrency | jitter | UA rotation | intended use                         |
|-----------|-------------|--------|-------------|--------------------------------------|
| `safe`    | low (20)    | none   | no          | won't knock over a production host   |
| `stealth` | low (8)     | 0.4–2s | yes         | gentle, less bursty against WAFs     |
| `cicd`    | medium (30) | none   | no          | deterministic, SARIF + fail‑on       |

All profile fields can be overridden from the CLI (`--concurrency`,
`--timeout`, `--proxy`, `--header`, …).

## Built-in plugins (15)

| name                | severity | type    | what it checks                                  |
|---------------------|----------|---------|-------------------------------------------------|
| `security-headers`  | low–med  | passive | missing CSP/HSTS/X‑Content‑Type‑Options/…       |
| `cookie-security`   | low      | passive | cookies missing Secure/HttpOnly/SameSite        |
| `secrets`           | high–crit| passive | leaked API keys / tokens / private keys in body |
| `tech-fingerprint`  | info     | passive | server stack inferred from headers/body         |
| `info-disclosure`   | low–med  | passive | version banners and leaked stack traces         |
| `cors`              | low–high | active  | wildcard / origin‑reflecting CORS               |
| `clickjacking`      | low      | passive | no X‑Frame‑Options / CSP frame‑ancestors        |
| `http-methods`      | med–high | active  | risky methods (PUT/DELETE/TRACE) via OPTIONS     |
| `directory-listing` | medium   | passive | auto‑generated directory indexes                |
| `exposed-files`     | low–high | active  | `.git`, `.env`, backups, `phpinfo`, … (GET only)|
| `sqli`              | high     | active  | error‑based SQL injection in query params       |
| `xss`               | low–high | active  | reflected XSS in query params                   |
| `open-redirect`     | medium   | active  | user‑controlled redirect targets                |
| `ssrf`              | medium   | active  | URL‑like params that trigger server‑side fetch  |
| `mixed-content`     | low      | passive | HTTPS pages loading HTTP sub‑resources          |

*Passive* plugins only observe responses. *Active* plugins send crafted but
non‑destructive probes and are skipped automatically when a mode disables
active checks.

## Writing a plugin (≈20–30 lines)

Subclass `Plugin`, decorate with `@register`, implement `run`:

```python
from webscan.core.plugin import Plugin, register
from webscan.core.models import Severity

@register
class RobotsLeak(Plugin):
    name = "robots-leak"
    title = "Sensitive path in robots.txt"
    severity = Severity.LOW

    async def run(self, ctx):
        resp = await ctx.get(ctx.target.base + "/robots.txt")
        if resp and "admin" in resp.text.lower():
            yield self.finding(
                resp.url,
                evidence="robots.txt references an admin path",
                remediation="Don't rely on robots.txt to hide sensitive paths.",
            )
```

Drop the file into `webscan/plugins/`, add its module name to
`webscan/plugins/__init__.py`, and it's part of every scan.

## CI/CD + GitHub Code Scanning

WebScan emits SARIF 2.1.0, which GitHub Code Scanning ingests natively. A ready
workflow lives in `.github/workflows/webscan.yml`: it runs the scan, uploads the
SARIF, and surfaces findings in the Security tab. Set `--fail-on` to gate merges
on severity.

## Known limitations

Honest about scope (as the source article was):

- No POST/form‑body fuzzing — query‑parameter checks only.
- No complex authentication flows (OAuth, multi‑step login). Static creds can be
  passed via `--header`.
- No WebSocket testing.
- SSRF detection is heuristic; confirm with your own out‑of‑band (OAST) listener.

Great for fast recon and quick wins; not a replacement for a full DAST suite.

## Tests

```bash
python -m pip install -e ".[dev]"
pytest
```

## License

MIT.
