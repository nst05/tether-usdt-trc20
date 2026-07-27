#!/usr/bin/env python3
"""Снимки конфигурации, сравнение и пакетные сценарии для дипломной версии."""
from __future__ import annotations

import csv
import datetime
import json
import os
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass

from smt_core.commands import classify_command


@dataclass
class BatchStep:
    line: int
    kind: str
    name: str = ""
    value: str = ""
    delay_ms: int = 0
    source: str = ""


def parse_batch_script(text: str, actions: Iterable[str] = ()) -> list[BatchStep]:
    """Разобрать сценарий.

    Поддержка: READ NAME, GET NAME, SET NAME=value, WRITE NAME=value,
    ACTION NAME, SLEEP <ms>, а также сырой NAME / NAME=value. Комментарии # и //.
    """
    action_set = set(actions)
    steps: list[BatchStep] = []
    for line_no, raw in enumerate(text.splitlines(), 1):
        src = raw.strip()
        if not src or src.startswith("#") or src.startswith("//"):
            continue
        line = re.split(r"\s+(?:#|//)", src, maxsplit=1)[0].strip()
        head, _, tail = line.partition(" ")
        op = head.upper(); tail = tail.strip()
        if op in {"SLEEP", "WAIT", "PAUSE"}:
            try:
                ms = int(tail)
            except ValueError as exc:
                raise ValueError(f"строка {line_no}: SLEEP требует целое число миллисекунд") from exc
            if not 0 <= ms <= 600000:
                raise ValueError(f"строка {line_no}: пауза должна быть 0…600000 мс")
            steps.append(BatchStep(line_no, "sleep", delay_ms=ms, source=src)); continue
        if op in {"READ", "GET"}:
            if not tail or "=" in tail:
                raise ValueError(f"строка {line_no}: READ требует имя команды")
            steps.append(BatchStep(line_no, "read", name=tail, source=src)); continue
        if op in {"SET", "WRITE"}:
            if "=" not in tail:
                raise ValueError(f"строка {line_no}: SET требует NAME=value")
            name, value = tail.split("=", 1)
            if not name.strip():
                raise ValueError(f"строка {line_no}: пустое имя команды")
            steps.append(BatchStep(line_no, "write", name=name.strip(), value=value.strip(), source=src)); continue
        if op in {"ACTION", "DO", "RUN"}:
            if not tail or "=" in tail:
                raise ValueError(f"строка {line_no}: ACTION требует имя команды")
            steps.append(BatchStep(line_no, "action", name=tail, source=src)); continue
        # Сырой протокол классифицируется тем же источником истины, что GUI/CLI.
        name, kind = classify_command(line, action_set)
        if kind == "write":
            _, value = line.split("=", 1)
            steps.append(BatchStep(line_no, kind, name=name, value=value.strip(), source=src))
        else:
            steps.append(BatchStep(line_no, kind, name=name, source=src))
    return steps


def snapshot_document(values: dict, *, source: str = "unknown", meta: dict | None = None) -> dict:
    return {
        "format": "smt-snapshot-v1",
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "meta": dict(meta or {}),
        "values": dict(values),
    }


def save_snapshot_json(path: str, values: dict, *, source: str = "unknown", meta: dict | None = None) -> None:
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(snapshot_document(values, source=source, meta=meta), stream,
                  ensure_ascii=False, indent=2)


def save_snapshot_csv(path: str, values: dict) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["command", "value", "status"])
        for name, value in sorted(values.items()):
            status = "error" if isinstance(value, str) and value.startswith("<err:") else "ok"
            writer.writerow([name, value, status])


def load_snapshot(path: str) -> dict:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        out = {}
        with open(path, encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                name = row.get("command") or row.get("name")
                if name:
                    out[name] = row.get("value", "")
        return out
    with open(path, encoding="utf-8") as stream:
        obj = json.load(stream)
    if isinstance(obj, dict) and isinstance(obj.get("values"), dict):
        return obj["values"]
    if isinstance(obj, dict):
        return obj
    raise ValueError("неизвестный формат снимка")


def compare_snapshots(left: dict, right: dict) -> list[dict]:
    rows = []
    missing = object()
    for name in sorted(set(left) | set(right)):
        a_raw = left.get(name, missing)
        b_raw = right.get(name, missing)
        status = ("added" if a_raw is missing else
                  "removed" if b_raw is missing else
                  "same" if str(a_raw) == str(b_raw) else "changed")
        rows.append({"name": name,
                     "left": "<нет>" if a_raw is missing else a_raw,
                     "right": "<нет>" if b_raw is missing else b_raw,
                     "status": status})
    return rows


def steps_as_dicts(steps: Iterable[BatchStep]) -> list[dict]:
    return [asdict(x) for x in steps]
