#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Тесты физического клиента и журнала сессии — без железа.

Порт подменяется FakeSerial через внутреннюю инъекцию OpticTransport(ser=...).
Это тест-заглушка транспорта, а НЕ эмулятор прибора в приложении.
"""
import os, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import smt_client as sc
import smt_session as ssn


class FakeSerial:
    """Мини-порт: на каждый write() кладёт ответ от responder(tx) в буфер чтения."""
    def __init__(self, responder):
        self.responder = responder
        self.is_open = True
        self._rx = bytearray()
        self.writes = []
        self.dtr = False
        self.rts = False

    @property
    def in_waiting(self):
        return len(self._rx)

    def read(self, n):
        if not self._rx:
            return b""
        n = min(n, len(self._rx))
        out = bytes(self._rx[:n]); del self._rx[:n]
        return out

    def write(self, b):
        self.writes.append(bytes(b))
        self._rx.extend(self.responder(bytes(b)) or b"")
        return len(b)

    def flush(self): pass
    def reset_input_buffer(self): self._rx.clear()
    def reset_output_buffer(self): pass
    def close(self): self.is_open = False


def _transport(responder):
    return sc.OpticTransport("FAKE", 9600, idle_gap=0.03,
                             response_timeout=0.4, read_retries=1, ser=FakeSerial(responder))


# ─────────────────────────── тесты транспорта ─────────────────────────── #
def test_command_name_and_protected():
    assert sc.command_name("SERVER_URL=1.2.3.4:1") == "SERVER_URL"
    assert sc.command_name("{VALVE_OPEN}") == "VALVE_OPEN"
    assert sc.command_name("/?DevInfo!") == "DevInfo"
    assert sc.is_protected("VALVE_OPEN")
    assert sc.is_protected("WARNING_CLEAR")
    assert sc.is_protected("SERVER_URL=x")
    assert not sc.is_protected("STATUS_SYSTEM")     # статус — не критичная запись


def test_framing_detect_via_devinfo():
    def responder(tx):
        return b"DevInfo=SIM;\r\n" if tx == b"DevInfo\r" else b""
    tr = _transport(responder)
    name, resp = tr.detect_framing("DevInfo")
    assert name == "cr"
    assert b"DevInfo=SIM" in resp


def test_echo_stripped_but_value_preserved():
    # эхо = точная копия отправленных байтов; после него — настоящий ответ
    payload = b"DevInfo\r"
    raw = b"DevInfo\r" + b"DevInfo=SIM;\r\n"
    clean, removed = sc.strip_optical_echo("DevInfo", payload, raw)
    assert removed is True
    assert clean.startswith(b"DevInfo=SIM")
    # без эха: NAME=value НЕ должен срезаться
    clean2, removed2 = sc.strip_optical_echo("DevInfo", payload, b"DevInfo=SIM;")
    assert removed2 is False and clean2 == b"DevInfo=SIM;"


def test_fragmented_response_assembled():
    # ответ выдаётся двумя фрагментами — сборка по межбайтовой паузе
    chunks = [b"Volume=1.2", b"8;\r\n"]
    state = {"i": 0}
    def responder(tx):
        # первый write — вернуть оба фрагмента (буфер отдаст их частями через read)
        return b"".join(chunks)
    tr = _transport(responder)
    tr.set_framing("cr")
    raw = tr.send("Volume", retry_safe=True)
    assert sc.value_of(raw, name="Volume") == "1.28"


def test_read_retries_but_write_never():
    calls = {"n": 0}
    def responder(tx):
        calls["n"] += 1
        return b""                                   # никогда не отвечаем
    tr = _transport(responder)
    tr.set_framing("cr")
    cli = sc.SmtClient(tr)
    # чтение: retry_safe → 1 + read_retries(1) = 2 попытки
    calls["n"] = 0
    cli.send("Volume", retry_safe=True, mutating=False)
    assert calls["n"] == 2, calls["n"]
    # запись: повтор запрещён даже при retry_safe=True
    calls["n"] = 0
    cli.send("LCD_TIME=5", retry_safe=True, mutating=True, expert=False)
    assert calls["n"] == 1, calls["n"]


def test_protected_gate_write_and_action():
    tr = _transport(lambda tx: b"OK;\r\n")
    tr.set_framing("cr")
    cli = sc.SmtClient(tr)
    # запись критичного параметра без expert — отказ
    try:
        cli.send("SERVER_URL=1.2.3.4:1", mutating=True, expert=False)
        assert False, "ожидался PermissionError"
    except PermissionError:
        pass
    # действие (без '=') тоже критично и блокируется
    try:
        cli.send("VALVE_OPEN", mutating=True, expert=False)
        assert False, "ожидался PermissionError для действия"
    except PermissionError:
        pass
    # с expert=True — проходит
    cli.send("VALVE_OPEN", mutating=True, expert=True)
    # ЧТЕНИЕ защищённого имени (get) — разрешено без expert
    cli.send("VALVE", mutating=False)               # не должно бросать


# ─────────────────────────── тесты журнала ─────────────────────────── #
def test_session_records_and_masks_secret():
    with tempfile.TemporaryDirectory() as d:
        rec = ssn.SessionRecorder(d)
        rec.header(port="FAKE", baud=9600, framing="cr", devinfo="SIM")
        rec.record(kind="read", name="Volume", cmd="Volume", value="1.28",
                   rx_raw=b"Volume=1.28;", latency_ms=12, ok=True)
        rec.record(kind="auth", name="PASSWORD_PROVIDER", cmd="PASSWORD_PROVIDER=123456",
                   value="123456", secret=True, expert=True, critical=True)
        csv_path = os.path.join(d, "out.csv")
        n = rec.export_csv(csv_path)
        rec.close()
        assert n == 2, n
        blob = open(rec.jsonl_path, encoding="utf-8").read()
        assert "123456" not in blob                 # секрет не сохранён
        assert "•••" in blob                        # значение замаскировано
        csv_text = open(csv_path, encoding="utf-8").read()
        assert "Volume" in csv_text and "1.28" in csv_text
        assert "123456" not in csv_text             # маска и в CSV


def test_imperative_actions_route_as_action():
    """Критичные действия (в т.ч. с опечаткой/пропуском в каталоге) должны
    классифицироваться как ДЕЙСТВИЕ, а не чтение, и требовать экспертного режима."""
    import smt_gui as gui
    catalog = gui.load_catalog()
    actions = gui.build_actions(catalog)
    for name in ("VALVE_TRY_CLOSE", "CLEAR_SABOTAG", "VALVE_OPEN"):
        assert name in actions, f"{name} не в множестве действий"
        nm, kind = gui.classify_send(name, actions)     # «голое» имя
        assert kind == "action", f"{name} уехал как {kind}, а не action"
        assert nm in sc.PROTECTED_WRITE                  # значит будет за expert-гейтом
    # чтение параметра-имени (не императив) остаётся чтением
    nm, kind = gui.classify_send("VALVE", actions)       # состояние актуатора — read
    assert kind == "read"


def test_action_available_in_expert_only():
    """Действие блокируется без expert и проходит с expert (доступно в эксперт-режиме)."""
    tr = _transport(lambda tx: b"OK;\r\n")
    tr.set_framing("cr")
    cli = sc.SmtClient(tr)
    try:
        cli.send("VALVE_TRY_CLOSE", mutating=True, expert=False)
        assert False, "должно блокироваться без expert"
    except PermissionError:
        pass
    cli.send("VALVE_TRY_CLOSE", mutating=True, expert=True)   # доступно в эксперт-режиме


def test_alias_resolves_real_name_on_wire_and_gate():
    """Обезличенное имя CMD_### должно резолвиться в реальное ДО гейта и провода:
    критичное блокируется без expert; на провод уходит настоящее имя."""
    import smt_aliases as al2
    a_valve = al2.REAL2ALIAS["VALVE_OPEN"]
    a_dt = al2.REAL2ALIAS["DATETIME"]
    assert a_valve.startswith("CMD_") and al2.to_wire(a_valve) == "VALVE_OPEN"
    assert al2.to_display("VALVE_OPEN") == a_valve

    tr = _transport(lambda tx: b"OK;\r\n")
    tr.set_framing("cr")
    cli = sc.SmtClient(tr)
    # критичное действие по алиасу — блок без expert
    try:
        cli.send(a_valve, mutating=True, expert=False)
        assert False, "алиас критичного действия должен блокироваться"
    except PermissionError:
        pass
    # с expert — проходит, и на ПРОВОД уходит РЕАЛЬНОЕ имя
    tr.ser.writes.clear()
    cli.send(a_valve, mutating=True, expert=True)
    assert any(b"VALVE_OPEN" in w for w in tr.ser.writes), tr.ser.writes
    assert not any(a_valve.encode() in w for w in tr.ser.writes)   # алиас не уходит
    # чтение параметра по алиасу — реальное имя на проводе
    tr.ser.writes.clear()
    cli.send(a_dt, mutating=False)
    assert any(b"DATETIME" in w for w in tr.ser.writes)


def _backend_with_fake(catalog):
    """Backend поверх FakeSerial: любой read возвращает NAME=<val>; поток не стартуем,
    методы вызываем синхронно и разбираем очередь out_q."""
    import queue, smt_gui
    def responder(tx):
        name = sc.command_name(sc.decode_response(bytes(tx)))
        return (name + "=42;\r\n").encode()
    tr = _transport(responder); tr.set_framing("cr")
    tq, oq = queue.Queue(), queue.Queue()
    be = smt_gui.Backend(tq, oq, smt_gui.build_critical(catalog),
                         smt_gui.build_actions(catalog), catalog)
    be.cli = sc.SmtClient(tr)
    return be, oq, tr


def _drain_profile(oq):
    prof = None
    while not oq.empty():
        kind, payload = oq.get()
        if kind == "profile":
            prof = payload
    return prof


def test_readall_snapshot_covers_all_parameters():
    import smt_gui
    catalog = smt_gui.load_catalog()
    actions = smt_gui.build_actions(catalog)
    be, oq, _ = _backend_with_fake(catalog)
    be._readall()
    prof = _drain_profile(oq)
    assert prof is not None
    expected = {c["name"] for c in catalog if c["name"] not in actions}
    assert set(prof) == expected                      # все ПАРАМЕТРЫ прочитаны
    assert all(not str(v).startswith("<err:") for v in prof.values())


def test_readall_never_sends_action_names():
    import smt_gui
    catalog = smt_gui.load_catalog()
    actions = smt_gui.build_actions(catalog)
    be, oq, tr = _backend_with_fake(catalog)
    be._readall()
    wire = b"\n".join(tr.ser.writes)
    for act in actions:                                # ни одно действие не ушло на провод
        assert act.encode() not in wire, act


def test_groupread_reads_only_its_group():
    import smt_gui
    catalog = smt_gui.load_catalog()
    actions = smt_gui.build_actions(catalog)
    group = "Фильтр Калмана"
    be, oq, _ = _backend_with_fake(catalog)
    be._groupread(group)
    prof = _drain_profile(oq)
    expected = {c["name"] for c in catalog
                if c["group"] == group and c["name"] not in actions}
    assert set(prof) == expected


def run_all():
    fns = [g for n, g in sorted(globals().items()) if n.startswith("test_") and callable(g)]
    ok = 0
    for fn in fns:
        fn(); print(f"  PASS {fn.__name__}"); ok += 1
    print(f"ИТОГО: {ok}/{len(fns)} тестов прошли")
    return ok == len(fns)


if __name__ == "__main__":
    sys.exit(0 if run_all() else 1)
