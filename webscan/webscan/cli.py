"""Command-line interface for WebScan."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from . import plugins as _plugins  # noqa: F401 - imported for side-effect (registration)
from .core import Engine, Severity, Target, get_plugins, get_profile, registry_names
from .core.modes import MODES
from .core.report import render

BANNER = "WebScan - async web vulnerability scanner"

AUTHORIZATION_NOTICE = (
    "WebScan sends HTTP requests, including non-destructive probe payloads, to the\n"
    "targets you specify. Only scan systems you own or have explicit written\n"
    "permission to test. Unauthorized scanning may be illegal."
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="webscan", description=BANNER)
    p.add_argument("targets", nargs="*", help="target URLs (e.g. https://example.com/page?id=1)")
    p.add_argument("-f", "--targets-file", type=Path, help="file with one target URL per line")
    p.add_argument(
        "-m", "--mode", choices=MODES, default="safe",
        help="scan mode profile (default: safe)",
    )
    p.add_argument("--only", help="comma-separated plugin names to run exclusively")
    p.add_argument("--exclude", help="comma-separated plugin names to skip")
    p.add_argument("--list-plugins", action="store_true", help="list available plugins and exit")
    p.add_argument(
        "-o", "--output", choices=("console", "json", "sarif"), default="console",
        help="report format (default: console)",
    )
    p.add_argument("--out-file", type=Path, help="write the report to this file instead of stdout")
    p.add_argument("-c", "--concurrency", type=int, help="override global concurrency")
    p.add_argument("-t", "--timeout", type=float, help="override per-request timeout (seconds)")
    p.add_argument("--proxy", help="route requests through this proxy (e.g. http://127.0.0.1:8080)")
    p.add_argument("--header", action="append", default=[], metavar="K:V", help="extra request header (repeatable)")
    p.add_argument("--insecure", action="store_true", help="do not verify TLS certificates")
    p.add_argument(
        "--fail-on", choices=[s.name.lower() for s in Severity],
        help="exit non-zero if a finding at/above this severity is found (CI use)",
    )
    p.add_argument("--no-color", action="store_true", help="disable ANSI colors in console output")
    p.add_argument("-q", "--quiet", action="store_true", help="only emit the report")
    p.add_argument("-v", "--verbose", action="store_true", help="verbose logging")
    p.add_argument("-y", "--yes", action="store_true", help="skip the authorization confirmation prompt")
    return p


def _load_targets(args: argparse.Namespace) -> list[Target]:
    raw: list[str] = list(args.targets)
    if args.targets_file:
        raw.extend(
            line.strip()
            for line in args.targets_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
    targets: list[Target] = []
    for url in raw:
        if "://" not in url:
            url = "https://" + url
        targets.append(Target(url))
    return targets


def _parse_headers(items: list[str]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for item in items:
        if ":" not in item:
            raise SystemExit(f"invalid --header {item!r}; expected 'Key: Value'")
        key, value = item.split(":", 1)
        headers[key.strip()] = value.strip()
    return headers


def _confirm_authorization(targets: list[Target], assume_yes: bool) -> None:
    if assume_yes or not sys.stdin.isatty():
        return
    print(AUTHORIZATION_NOTICE)
    hosts = ", ".join(sorted({t.host for t in targets}))
    answer = input(f"\nConfirm you are authorized to scan: {hosts} [y/N] ").strip().lower()
    if answer not in ("y", "yes"):
        raise SystemExit("aborted: authorization not confirmed")


async def _run(args: argparse.Namespace) -> int:
    profile = get_profile(args.mode)
    if args.concurrency:
        profile.concurrency = args.concurrency
    if args.timeout:
        profile.timeout = args.timeout
    fail_on = Severity.parse(args.fail_on) if args.fail_on else profile.fail_on

    selected = get_plugins(
        only=args.only.split(",") if args.only else None,
        exclude=args.exclude.split(",") if args.exclude else None,
    )
    if not selected:
        raise SystemExit("no plugins selected")

    targets = _load_targets(args)
    if not targets:
        raise SystemExit("no targets given (pass URLs or --targets-file)")

    _confirm_authorization(targets, args.yes)

    if not args.quiet:
        print(
            f"[*] mode={profile.name} plugins={len(selected)} targets={len(targets)} "
            f"concurrency={profile.concurrency}",
            file=sys.stderr,
        )

    engine = Engine(
        selected,
        profile,
        proxy=args.proxy,
        verify_ssl=not args.insecure,
        extra_headers=_parse_headers(args.header),
    )
    result = await engine.scan(targets)

    report = render(result, args.output, color=not args.no_color)
    if args.out_file:
        args.out_file.write_text(report, encoding="utf-8")
        if not args.quiet:
            print(f"[*] report written to {args.out_file}", file=sys.stderr)
    else:
        print(report)

    if fail_on is not None:
        top = result.highest_severity
        if top is not None and top >= fail_on:
            return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.list_plugins:
        for name in registry_names():
            print(name)
        return 0

    try:
        return asyncio.run(_run(args))
    except KeyboardInterrupt:  # pragma: no cover
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
