#!/usr/bin/env python3
"""Офлайн-анализ полного диагностического JSONL v4.5.4."""
from __future__ import annotations

import argparse
import collections
import json
import sys
from collections.abc import Iterable, Iterator

from smt_diagnostics import export_jsonl_to_csv


def iter_events(path: str) -> Iterator[dict]:
    with open(path, encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                yield {
                    "type": "diagnostic-parse-error",
                    "seq": number,
                    "status": "error",
                    "component": "viewer",
                    "action": "json.decode",
                    "error": str(exc),
                    "details": {"line": line},
                }
                continue
            yield event


def filter_events(
    events: Iterable[dict], *, component: str = "", action: str = "",
    status: str = "", contains: str = "",
) -> Iterator[dict]:
    component = component.lower().strip()
    action = action.lower().strip()
    status = status.lower().strip()
    contains = contains.lower().strip()
    for event in events:
        if component and component not in str(event.get("component", "")).lower():
            continue
        if action and action not in str(event.get("action", "")).lower():
            continue
        if status and status != str(event.get("status", "")).lower():
            continue
        if contains and contains not in json.dumps(event, ensure_ascii=False).lower():
            continue
        yield event


def summarize(events: Iterable[dict]) -> dict:
    rows = list(events)
    statuses = collections.Counter(str(x.get("status", "")) for x in rows)
    components = collections.Counter(str(x.get("component", "")) for x in rows)
    actions = collections.Counter(
        f"{x.get('component', '')}.{x.get('action', '')}" for x in rows)
    durations = [float(x["duration_ms"]) for x in rows if x.get("duration_ms") is not None]
    errors = [x for x in rows if x.get("error") or x.get("status") == "error"]
    return {
        "events": len(rows),
        "statuses": dict(statuses.most_common()),
        "components": dict(components.most_common()),
        "top_actions": dict(actions.most_common(25)),
        "errors": len(errors),
        "duration": {
            "count": len(durations),
            "average_ms": (sum(durations) / len(durations)) if durations else 0,
            "maximum_ms": max(durations) if durations else 0,
        },
        "first_ts": rows[0].get("ts", "") if rows else "",
        "last_ts": rows[-1].get("ts", "") if rows else "",
    }


def parser_build() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jsonl", help="файл diagnostic_*.jsonl")
    parser.add_argument("--component", default="")
    parser.add_argument("--action", default="")
    parser.add_argument("--status", default="")
    parser.add_argument("--contains", default="", help="поиск по полному JSON события")
    parser.add_argument("--summary", action="store_true", help="вывести сводку")
    parser.add_argument("--csv", metavar="FILE", help="экспортировать весь JSONL в CSV")
    parser.add_argument("--pretty", action="store_true", help="полный JSON с отступами")
    return parser


def main(argv=None) -> int:
    args = parser_build().parse_args(argv)
    if args.csv:
        exported = export_jsonl_to_csv(args.jsonl, args.csv)
        print(f"Экспортировано событий: {exported} → {args.csv}", file=sys.stderr)
    rows = list(filter_events(
        iter_events(args.jsonl), component=args.component, action=args.action,
        status=args.status, contains=args.contains))
    if args.summary:
        print(json.dumps(summarize(rows), ensure_ascii=False, indent=2))
        return 0
    for event in rows:
        if args.pretty:
            print(json.dumps(event, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(event, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
