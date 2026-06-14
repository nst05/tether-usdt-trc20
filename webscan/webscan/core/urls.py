"""Small URL helpers shared by injection-style plugins."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse


def query_params(url: str) -> list[tuple[str, str]]:
    return parse_qsl(urlparse(url).query, keep_blank_values=True)


def with_param(url: str, name: str, value: str) -> str:
    """Return ``url`` with parameter ``name`` set to ``value`` (others kept)."""
    parsed = urlparse(url)
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    params[name] = value
    new_query = urlencode(params)
    return urlunparse(parsed._replace(query=new_query))


def join(base: str, path: str) -> str:
    return urljoin(base, path)


def same_host(a: str, b: str) -> bool:
    return urlparse(a).hostname == urlparse(b).hostname
