#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Обезличенные («слепые») имена команд для отображения.

В интерфейсе и логах команда показывается как `CMD_###`, а на провод и во все
проверки безопасности (гейт критичных, PROTECTED_WRITE) уходит РЕАЛЬНОЕ имя.
Резолв алиас→реал выполняется в одной точке — `SmtClient.send`, поэтому
отображение не влияет на то, что реально уходит в устройство.

Соответствие строится из порядка команд в smt_commands.json (стабильно):
    команда №i  ->  CMD_<i:03d>
"""
from __future__ import annotations
import json, os, re

_HERE = os.path.dirname(os.path.abspath(__file__))
REAL2ALIAS: dict[str, str] = {}
ALIAS2REAL: dict[str, str] = {}


def _load() -> None:
    try:
        cmds = json.load(open(os.path.join(_HERE, "smt_commands.json"), encoding="utf-8"))["commands"]
    except Exception:
        return
    for i, c in enumerate(cmds):
        name = c.get("name")
        if not name:
            continue
        alias = f"CMD_{i:03d}"
        REAL2ALIAS[name] = alias
        ALIAS2REAL[alias] = name


_load()

# ведущий идентификатор в строке команды: `NAME`, `NAME=value`, `{NAME}`, `/?NAME!`
_TOK = re.compile(r"^(\s*[{}/?!]*\s*)([A-Za-z0-9_]+)(.*)$", re.S)


def to_wire(text: str) -> str:
    """Заменить ведущий алиас на реальное имя (для отправки в устройство).
    Реальное имя или неизвестный токен возвращаются без изменений."""
    m = _TOK.match(str(text))
    if not m:
        return text
    pre, tok, rest = m.groups()
    return pre + ALIAS2REAL.get(tok, tok) + rest


def to_display(name: str) -> str:
    """Реальное имя → показываемый алиас (`CMD_###`)."""
    return REAL2ALIAS.get(str(name).strip(), name)
