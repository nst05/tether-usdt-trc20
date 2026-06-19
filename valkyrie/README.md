# Valkyrie — universal web security scanner

A self-contained, dependency-free web application scanner for **authorized**
security testing (your own servers / explicit written permission). It combines a
crawler, a behavioral differential anomaly engine, and active exploit-confirmation
checks, with a full local web GUI.

> ⚠️ **Authorized use only.** Active checks send real payloads
> (`sleep`, `{{7*8}}`, `../etc/passwd`, SQL conditions). Run them against systems
> you own or are permitted to test. Non-local targets are refused unless you
> explicitly confirm authorization. The tool contains **no** detection-evasion,
> traffic-obfuscation, or credential brute-forcing — it is an assessment tool,
> not an attack framework.

## Why "behavioral"?

Instead of relying only on static signatures, the engine first **calibrates a
baseline** (latency, response size, status distribution), then mutates input and
flags responses that **deviate** — 5xx errors, abnormal latency, large size
variance. On top of that, the active layer runs targeted payloads that **prove**
a vulnerability class and attach the request + response as evidence.

## What it checks

**Passive / posture**
- Missing security headers (CSP, nosniff, X-Frame-Options, HSTS, Referrer-Policy)
- Cookie flags (HttpOnly / SameSite / Secure)
- Server / X-Powered-By version disclosure
- Verbose error / stack-trace disclosure

**Recon**
- `robots.txt` / `sitemap.xml` parsing (feeds the crawl)
- Sensitive paths (`.env`, `.git/config`, backups, …) — confirmed by matching
  known secret/VCS signatures in the body

**Behavioral differential fuzzing** (per discovered GET parameter)
- Structural mutations: empty, array injection, null byte, type confusion,
  large/negative int, overflow, special chars, format string, path, unicode
- Anomaly detection: unhandled 5xx, time-delay, response-size variance
- Reflected-input detection (encoded vs unencoded → XSS-capable)

**Active confirmation** (proves exploitability) — on GET parameters *and* form fields
- **SSTI** — `{{7*8}}`/`${7*8}`/`<%=7*8%>` evaluated to `56`
- **Path traversal / LFI** — `/etc/passwd` / `win.ini` content returned
- **SQL injection** — error-based (DB error on a quote) and boolean-based
  (TRUE vs FALSE divergence)
- **OS command injection** — time-based, reproduced on retry
- **Open redirect** — external host reflected into `Location`
- **Reflected XSS** — unique markup probe returned unencoded

**Form testing**
- Parses `<form>`s found while crawling and submits them (POST or GET),
  carrying hidden fields through — including the **CSRF token** — so the same
  injection battery runs against each editable field.
- State-changing forms (action contains `delete`, `restore`, `logout`, …) are
  **skipped by default**; enable `--allow-destructive` only on disposable data.

**IDOR / object enumeration**
- Detects endpoints keyed by a numeric path segment (`/item/5`) or numeric
  query value (`?id=5`) and walks neighbouring ids. **Confirmed** when several
  sequential ids each return a distinct 200 object with no access-control
  boundary — i.e. objects are directly addressable by id.

Every finding is tagged **confirmed** (proven / deterministic) or **potential**
(a lead to validate manually) and carries a `proof` block with the exact request
and a response excerpt.

## Usage

No installation, pure Python 3 standard library.

### GUI (recommended)

```bash
python3 valkyrie_gui.py
# opens http://127.0.0.1:8787  (dashboard binds to loopback only)
```

Configure the target and options, **Start scan**, watch live progress, filter by
severity, click any finding to see its proof. **Export JSON** saves the report.

### CLI

```bash
python3 valkyrie.py http://localhost:5000
python3 valkyrie.py http://localhost:5000 --json > report.json
python3 valkyrie.py http://localhost:5000 --no-active          # behavioral only
python3 valkyrie.py http://localhost:5000 --cookie "session=…" # authenticated
```

Key flags: `--max-pages`, `--max-requests` (request budget), `--delay`,
`--timeout`, `--no-fuzz`, `--no-active`, `--no-forms`, `--no-idor`,
`--allow-destructive`, `--insecure` (skip TLS verify),
`--i-am-authorized` (required for non-local targets).

## Safety defaults

- Loopback/private targets only unless authorization is explicitly confirmed.
- Form submission is on by default, but **state-changing forms are skipped**
  unless `--allow-destructive` is set — run that only against disposable data.
- Rate-limited (`--delay`) and bounded by a request budget (`--max-requests`).
- Bodies are read up to a cap; no detection-evasion or brute-forcing.

## Interpreting results

`confirmed` findings have concrete proof and should be triaged first.
`potential` findings (timing/size deltas, boolean-SQLi heuristics) are leads —
open the proof, reproduce manually, and confirm before reporting. The absence of
findings is **not** proof of security.
