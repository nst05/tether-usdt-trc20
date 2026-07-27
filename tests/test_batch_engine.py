#!/usr/bin/env python3
"""Тесты расширенного движка пакетных сценариев v4.6."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import pytest
import smt_tools as tools


def test_basic_commands():
    script = "READ DevInfo\nSLEEP 100\nSET Volume=123.45\nACTION VALVE_OPEN"
    steps = tools.parse_batch_script(script, actions={"VALVE_OPEN"})
    assert len(steps) == 4
    assert steps[0].kind == "read" and steps[0].name == "DevInfo"
    assert steps[1].kind == "sleep" and steps[1].delay_ms == 100
    assert steps[2].kind == "write" and steps[2].name == "Volume" and steps[2].value == "123.45"
    assert steps[3].kind == "action" and steps[3].name == "VALVE_OPEN"


def test_repeat():
    script = "REPEAT 3\nREAD Volume"
    steps = tools.parse_batch_script(script)
    assert len(steps) == 1
    assert steps[0].kind == "read"
    assert steps[0].repeat == 3
    assert steps[0].name == "Volume"


def test_loop_endloop():
    script = "LOOP 5\nREAD Volume\nSLEEP 500\nENDLOOP"
    steps = tools.parse_batch_script(script)
    assert len(steps) == 1
    assert steps[0].kind == "loop"
    assert steps[0].repeat == 5
    assert len(steps[0].body) == 2
    assert steps[0].body[0].kind == "read"
    assert steps[0].body[1].kind == "sleep"


def test_nested_loop():
    script = "LOOP 2\nLOOP 3\nREAD X\nENDLOOP\nENDLOOP"
    steps = tools.parse_batch_script(script)
    assert len(steps) == 1
    outer = steps[0]
    assert outer.kind == "loop" and outer.repeat == 2
    assert len(outer.body) == 1
    inner = outer.body[0]
    assert inner.kind == "loop" and inner.repeat == 3
    assert len(inner.body) == 1


def test_if_endif():
    script = "IF ${val} == 123\nREAD Volume\nENDIF"
    steps = tools.parse_batch_script(script)
    assert len(steps) == 1
    assert steps[0].kind == "if"
    assert steps[0].condition == "${val} == 123"
    assert len(steps[0].body) == 1


def test_if_else_endif():
    script = "IF ${x} > 10\nREAD A\nELSE\nREAD B\nENDIF"
    steps = tools.parse_batch_script(script)
    assert len(steps) == 2
    assert steps[0].kind == "if" and steps[0].condition == "${x} > 10"
    assert steps[1].kind == "if" and steps[1].condition == "TRUE"
    assert steps[0].body[0].name == "A"
    assert steps[1].body[0].name == "B"


def test_if_elseif_else():
    script = "IF ${x} == 1\nREAD A\nELSEIF ${x} == 2\nREAD B\nELSE\nREAD C\nENDIF"
    steps = tools.parse_batch_script(script)
    assert len(steps) == 3
    assert steps[0].condition == "${x} == 1"
    assert steps[1].condition == "${x} == 2"
    assert steps[2].condition == "TRUE"


def test_store():
    script = "STORE vol=Volume"
    steps = tools.parse_batch_script(script)
    assert len(steps) == 1
    assert steps[0].kind == "store"
    assert steps[0].name == "Volume"
    assert steps[0].value == "vol"


def test_print():
    script = "PRINT Hello World"
    steps = tools.parse_batch_script(script)
    assert len(steps) == 1
    assert steps[0].kind == "print"
    assert steps[0].value == "Hello World"


def test_assert():
    script = "ASSERT ${x} > 0"
    steps = tools.parse_batch_script(script)
    assert len(steps) == 1
    assert steps[0].kind == "assert"
    assert steps[0].condition == "${x} > 0"


def test_substitute_vars():
    variables = {"vol": "123.45", "name": "Volume"}
    assert tools.substitute_vars("${name}=${vol}", variables) == "Volume=123.45"
    assert tools.substitute_vars("${unknown}", variables) == "${unknown}"


def test_evaluate_condition_equality():
    assert tools.evaluate_condition("${x} == 10", {"x": "10"}) is True
    assert tools.evaluate_condition("${x} == 10", {"x": "20"}) is False
    assert tools.evaluate_condition("${x} != 10", {"x": "20"}) is True


def test_evaluate_condition_numeric():
    assert tools.evaluate_condition("${x} > 5", {"x": "10"}) is True
    assert tools.evaluate_condition("${x} <= 5", {"x": "3"}) is True
    assert tools.evaluate_condition("${x} >= 10", {"x": "10"}) is True


def test_evaluate_condition_regex():
    assert tools.evaluate_condition("${x} =~ ^OK", {"x": "OK done"}) is True
    assert tools.evaluate_condition("${x} =~ ^ERR", {"x": "OK done"}) is False


def test_evaluate_condition_truthy():
    assert tools.evaluate_condition("TRUE", {}) is True
    assert tools.evaluate_condition("FALSE", {}) is False
    assert tools.evaluate_condition("${x}", {"x": "hello"}) is True
    assert tools.evaluate_condition("${x}", {"x": ""}) is False


def test_loop_missing_endloop():
    with pytest.raises(ValueError, match="LOOP без ENDLOOP"):
        tools.parse_batch_script("LOOP 3\nREAD X")


def test_if_missing_endif():
    with pytest.raises(ValueError, match="IF без ENDIF"):
        tools.parse_batch_script("IF ${x} == 1\nREAD X")


def test_repeat_too_large():
    with pytest.raises(ValueError, match="1…10000"):
        tools.parse_batch_script("REPEAT 99999\nREAD X")


def test_comments_preserved():
    script = "# comment\n// another\nREAD X"
    steps = tools.parse_batch_script(script)
    assert len(steps) == 1


def test_complex_scenario():
    """Комплексный сценарий с LOOP, IF, STORE, REPEAT."""
    script = """
# Чтение с проверкой
STORE vol=Volume
IF ${vol} > 100
  PRINT Volume is high: ${vol}
  LOOP 3
    READ Volume
    SLEEP 1000
  ENDLOOP
ELSE
  PRINT Volume is low: ${vol}
  REPEAT 2
  READ Volume
ENDIF
"""
    steps = tools.parse_batch_script(script)
    assert len(steps) >= 1
    assert steps[0].kind == "store"
