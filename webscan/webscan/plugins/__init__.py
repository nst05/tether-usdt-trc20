"""Built-in plugins.

Importing this package imports every module below, which registers each plugin
with the global registry via the ``@register`` decorator. The bundled set:

    security-headers   cookie-security   secrets          tech-fingerprint
    info-disclosure    cors              clickjacking     http-methods
    directory-listing  exposed-files     sqli             xss
    open-redirect      ssrf              mixed-content
"""

from importlib import import_module

_MODULES = [
    "security_headers",
    "cookie_security",
    "secrets",
    "tech_fingerprint",
    "info_disclosure",
    "cors",
    "clickjacking",
    "http_methods",
    "directory_listing",
    "exposed_files",
    "sqli",
    "xss",
    "open_redirect",
    "ssrf",
    "mixed_content",
]

for _name in _MODULES:
    import_module(f"{__name__}.{_name}")

del import_module, _name
