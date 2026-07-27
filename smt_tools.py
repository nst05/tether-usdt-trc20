#!/usr/bin/env python3
"""Снимки конфигурации, сравнение и пакетные сценарии для дипломной версии.

Расширенный движок сценариев v4.6: REPEAT, LOOP/ENDLOOP, IF/ELSEIF/ELSE/ENDIF,
переменные ${var}, STORE, PRINT, ASSERT.
"""
from __future__ import annotations

import csv
import datetime
import json
import os
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field

from smt_core.commands import classify_command

_VAR_RE = re.compile(r"\$\{(\w+)\}")


@dataclass
class BatchStep:
    line: int
    kind: str
    name: str = ""
    value: str = ""
    delay_ms: int = 0
    source: str = ""
    repeat: int = 0
    condition: str = ""
    body: list[BatchStep] = field(default_factory=list)


def _strip_comment(src: str) -> str:
    return re.split(r"\s+(?:#|//)", src, maxsplit=1)[0].strip()


def _parse_lines(lines: list[tuple[int, str]], actions: set[str]) -> list[BatchStep]:
    """Рекурсивный разбор строк сценария с блочными конструкциями."""
    steps: list[BatchStep] = []
    i = 0
    while i < len(lines):
        line_no, src = lines[i]
        line = _strip_comment(src)
        if not line:
            i += 1; continue
        head, _, tail = line.partition(" ")
        op = head.upper(); tail = tail.strip()

        if op == "ENDLOOP" or op == "ENDIF" or op == "ELSE" or op == "ELSEIF":
            break

        if op in {"REPEAT"}:
            try:
                count = int(tail) if tail else 1
            except ValueError as exc:
                raise ValueError(f"строка {line_no}: REPEAT требует целое число") from exc
            if count < 1 or count > 10000:
                raise ValueError(f"строка {line_no}: REPEAT допускает 1…10000 итераций")
            if i + 1 >= len(lines):
                raise ValueError(f"строка {line_no}: REPEAT без следующей команды")
            inner = _parse_lines(lines[i + 1:i + 2], actions)
            if not inner:
                raise ValueError(f"строка {line_no}: REPEAT — пустая команда")
            step = inner[0]
            step.repeat = count
            step.source = f"REPEAT {count} × {step.source}"
            steps.append(step)
            i += 2; continue

        if op == "LOOP":
            try:
                count = int(tail) if tail else 1
            except ValueError as exc:
                raise ValueError(f"строка {line_no}: LOOP требует целое число итераций") from exc
            if count < 1 or count > 10000:
                raise ValueError(f"строка {line_no}: LOOP допускает 1…10000 итераций")
            body_lines: list[tuple[int, str]] = []
            depth = 1; j = i + 1
            while j < len(lines):
                bline = _strip_comment(lines[j][1])
                bop = bline.partition(" ")[0].upper()
                if bop == "LOOP":
                    depth += 1
                elif bop == "ENDLOOP":
                    depth -= 1
                    if depth == 0:
                        break
                body_lines.append(lines[j])
                j += 1
            if depth != 0:
                raise ValueError(f"строка {line_no}: LOOP без ENDLOOP")
            body = _parse_lines(body_lines, actions)
            steps.append(BatchStep(line_no, "loop", repeat=count, body=body, source=src))
            i = j + 1; continue

        if op == "IF":
            if not tail:
                raise ValueError(f"строка {line_no}: IF требует условие")
            branches: list[tuple[str, list[BatchStep]]] = []
            body_lines_if: list[tuple[int, str]] = []
            depth = 1; j = i + 1
            current_cond = tail
            while j < len(lines):
                bline = _strip_comment(lines[j][1])
                bop = bline.partition(" ")[0].upper()
                if bop == "IF":
                    depth += 1
                    body_lines_if.append(lines[j])
                elif bop == "ENDIF":
                    depth -= 1
                    if depth == 0:
                        branches.append((current_cond, _parse_lines(body_lines_if, actions)))
                        break
                elif depth == 1 and bop in ("ELSE", "ELSEIF"):
                    branches.append((current_cond, _parse_lines(body_lines_if, actions)))
                    body_lines_if = []
                    if bop == "ELSEIF":
                        current_cond = bline.partition(" ")[2].strip()
                        if not current_cond:
                            raise ValueError(f"строка {lines[j][0]}: ELSEIF требует условие")
                    else:
                        current_cond = "TRUE"
                else:
                    body_lines_if.append(lines[j])
                j += 1
            if depth != 0:
                raise ValueError(f"строка {line_no}: IF без ENDIF")
            for cond, body in branches:
                steps.append(BatchStep(line_no, "if", condition=cond, body=body, source=src))
            i = j + 1; continue

        if op in {"SLEEP", "WAIT", "PAUSE"}:
            try:
                ms = int(tail)
            except ValueError as exc:
                raise ValueError(f"строка {line_no}: SLEEP требует целое число миллисекунд") from exc
            if not 0 <= ms <= 600000:
                raise ValueError(f"строка {line_no}: пауза должна быть 0…600000 мс")
            steps.append(BatchStep(line_no, "sleep", delay_ms=ms, source=src)); i += 1; continue

        if op in {"READ", "GET"}:
            if not tail or "=" in tail:
                raise ValueError(f"строка {line_no}: READ требует имя команды")
            steps.append(BatchStep(line_no, "read", name=tail, source=src)); i += 1; continue

        if op in {"SET", "WRITE"}:
            if "=" not in tail:
                raise ValueError(f"строка {line_no}: SET требует NAME=value")
            name, value = tail.split("=", 1)
            if not name.strip():
                raise ValueError(f"строка {line_no}: пустое имя команды")
            steps.append(BatchStep(line_no, "write", name=name.strip(), value=value.strip(), source=src))
            i += 1; continue

        if op in {"ACTION", "DO", "RUN"}:
            if not tail or "=" in tail:
                raise ValueError(f"строка {line_no}: ACTION требует имя команды")
            steps.append(BatchStep(line_no, "action", name=tail, source=src)); i += 1; continue

        if op == "STORE":
            if "=" not in tail:
                raise ValueError(f"строка {line_no}: STORE требует VAR=COMMAND")
            var_name, cmd_name = tail.split("=", 1)
            if not var_name.strip() or not cmd_name.strip():
                raise ValueError(f"строка {line_no}: STORE — пустое имя переменной или команды")
            steps.append(BatchStep(line_no, "store", name=cmd_name.strip(), value=var_name.strip(), source=src))
            i += 1; continue

        if op == "PRINT":
            steps.append(BatchStep(line_no, "print", value=tail, source=src)); i += 1; continue

        if op == "ASSERT":
            if not tail:
                raise ValueError(f"строка {line_no}: ASSERT требует условие")
            steps.append(BatchStep(line_no, "assert", condition=tail, source=src)); i += 1; continue

        name, kind = classify_command(line, actions)
        if kind == "write":
            _, value = line.split("=", 1)
            steps.append(BatchStep(line_no, kind, name=name, value=value.strip(), source=src))
        else:
            steps.append(BatchStep(line_no, kind, name=name, source=src))
        i += 1
    return steps


def parse_batch_script(text: str, actions: Iterable[str] = ()) -> list[BatchStep]:
    """Разобрать сценарий.

    Поддержка: READ, GET, SET, WRITE, ACTION, SLEEP/WAIT/PAUSE,
    REPEAT N <cmd>, LOOP N / ENDLOOP, IF cond / ELSEIF / ELSE / ENDIF,
    STORE var=CMD, PRINT msg, ASSERT cond, а также сырой NAME / NAME=value.
    Переменные ${var} подставляются при выполнении.
    Комментарии # и //.
    """
    action_set = set(actions)
    numbered: list[tuple[int, str]] = []
    for line_no, raw in enumerate(text.splitlines(), 1):
        src = raw.strip()
        if not src or src.startswith("#") or src.startswith("//"):
            continue
        numbered.append((line_no, src))
    return _parse_lines(numbered, action_set)


def substitute_vars(text: str, variables: dict[str, str]) -> str:
    """Подставить ${var} в строку из словаря переменных."""
    def _repl(m: re.Match) -> str:
        return variables.get(m.group(1), m.group(0))
    return _VAR_RE.sub(_repl, text)


def evaluate_condition(cond: str, variables: dict[str, str]) -> bool:
    """Вычислить условие сценария.

    Форматы:
      ${var} == value    — точное сравнение
      ${var} != value    — неравенство
      ${var} =~ regex    — совпадение с регулярным выражением
      ${var} > N         — числовое сравнение (>, <, >=, <=)
      ${var}             — истина если переменная непустая
      TRUE               — всегда истина
    """
    cond = cond.strip()
    if cond.upper() == "TRUE":
        return True
    if cond.upper() == "FALSE":
        return False

    for op_str, op_fn in [
        ("=~", lambda a, b: bool(re.search(b, a))),
        ("!=", lambda a, b: a != b),
        ("==", lambda a, b: a == b),
        (">=", lambda a, b: _num_cmp(a, b, lambda x, y: x >= y)),
        ("<=", lambda a, b: _num_cmp(a, b, lambda x, y: x <= y)),
        (">", lambda a, b: _num_cmp(a, b, lambda x, y: x > y)),
        ("<", lambda a, b: _num_cmp(a, b, lambda x, y: x < y)),
    ]:
        if op_str in cond:
            left, right = cond.split(op_str, 1)
            left = substitute_vars(left.strip(), variables)
            right = substitute_vars(right.strip(), variables)
            return op_fn(left, right)

    resolved = substitute_vars(cond, variables)
    return bool(resolved and resolved.lower() not in ("", "0", "false", "none"))


def _num_cmp(a: str, b: str, fn) -> bool:
    try:
        return fn(float(a), float(b))
    except (ValueError, TypeError):
        return fn(a, b)


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


def build_coverage_matrix(
    catalog: list[dict],
    snapshot: dict[str, str],
    actions: set[str] | None = None,
) -> list[dict]:
    """Построить матрицу покрытия 158/158 команд по результатам снимка.

    Для каждой команды каталога определяется статус:
      - OK        — получен корректный ответ
      - ERROR     — ошибка при опросе
      - SKIP      — действие (не опрашивалось)
      - MISSING   — команда не была опрошена
    """
    actions = actions or set()
    rows: list[dict] = []
    ok = err = skip = miss = 0
    for cmd in catalog:
        name = cmd["name"]
        val = snapshot.get(name)
        if val is None:
            status = "MISSING"; miss += 1
        elif name in actions:
            status = "SKIP"; skip += 1
        elif isinstance(val, str) and (val.startswith("<err:") or val.startswith("<no response")):
            status = "ERROR"; err += 1
        else:
            status = "OK"; ok += 1
        rows.append({
            "name": name, "group": cmd.get("group", ""),
            "type": cmd.get("type", ""), "value": val or "",
            "status": status,
        })
    return rows


def export_coverage_csv(path: str, matrix: list[dict]) -> int:
    """Экспортировать матрицу покрытия в CSV."""
    ok = sum(1 for r in matrix if r["status"] == "OK")
    total = len(matrix)
    with open(path, "w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["#", "command", "group", "type", "value", "status"])
        for i, r in enumerate(matrix, 1):
            writer.writerow([i, r["name"], r["group"], r["type"], r["value"], r["status"]])
        writer.writerow([])
        writer.writerow(["", "ИТОГО", f"{ok}/{total}",
                         f"{ok * 100 / total:.1f}%" if total else "0%", "", ""])
    return total


def coverage_summary(matrix: list[dict]) -> dict:
    """Статистика покрытия."""
    total = len(matrix)
    by_status = {}
    for r in matrix:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    ok = by_status.get("OK", 0)
    return {
        "total": total, "ok": ok,
        "error": by_status.get("ERROR", 0),
        "skip": by_status.get("SKIP", 0),
        "missing": by_status.get("MISSING", 0),
        "coverage_pct": round(ok * 100 / total, 1) if total else 0.0,
    }
