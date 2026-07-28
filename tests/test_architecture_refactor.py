#!/usr/bin/env python3
"""Регрессионные тесты архитектурного рефакторинга v4.5.3."""
from __future__ import annotations

import ast
import hashlib
import inspect
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import smt_client as facade
import smt_eventlog
import smt_firmware
import smt_gui
import smt_gui_support
import smt_server
import smt_smart
import smt_state
import smt_tools
from smt_core import commands, interfaces, protocol, transports


def test_public_facade_keeps_old_import_surface():
    assert facade.OpticTransport is transports.OpticTransport
    assert facade.SmtClient.__module__ == "smt_core.client"
    assert facade.command_name("{VALVE_OPEN}") == "VALVE_OPEN"
    assert facade.value_of(b"Volume=1.25;", name="Volume") == "1.25"


def test_command_catalog_is_single_source_for_all_surfaces():
    catalog = commands.load_catalog()
    actions = commands.build_actions(catalog)
    samples = ["DevInfo", "LCD_TIME=5", "CLEAR_ARHIVE", "VALVE_TRY_CLOSE"]
    for sample in samples:
        core = commands.classify_command(sample, actions)
        assert smt_gui.classify_send(sample, actions) == core
        assert facade.is_mutating_command(sample) == (core[1] != "read")


def test_batch_parser_uses_same_action_classification():
    actions = commands.build_actions(commands.load_catalog())
    steps = smt_tools.parse_batch_script("CLEAR_ARHIVE\nDevInfo\nLCD_TIME=5", actions)
    assert [step.kind for step in steps] == ["action", "read", "write"]


def test_transport_classes_conform_to_common_protocol():
    class Dummy:
        frame_name = "dummy"
        last_tx = last_raw_rx = last_rx = b""
        last_latency_ms = last_attempts = 0
        is_open = True
        def send(self, command, *, retry_safe=False): return b"OK"
        def probe(self, probe_cmd="DevInfo"): return b"OK"
        def close(self): self.is_open = False
    assert isinstance(Dummy(), interfaces.CommandTransport)
    for cls in (transports.OpticTransport, transports.SmsTransport, transports.TcpServerTransport):
        send = inspect.signature(cls.send)
        assert "retry_safe" in send.parameters
        assert hasattr(cls, "close")
        assert hasattr(cls, "is_open")


def test_firmware_profile_drives_all_flash_parsers():
    profile = smt_firmware.DEFAULT_PROFILE
    assert profile.checkpoint_halves == smt_state.HALVES
    assert profile.state_record_size == smt_state.REC
    assert profile.records_per_checkpoint_half == smt_state.NREC
    assert (profile.event_log_start, profile.event_log_end) == (smt_eventlog.R0, smt_eventlog.R1)
    assert profile.state_record_size == smt_smart.RECORD_SIZE
    assert profile.smart_data_offset == smt_smart.DATA_OFF


def test_refactor_keeps_god_modules_below_regression_limits():
    assert sum(1 for _ in (ROOT / "smt_client.py").open(encoding="utf-8")) < 100
    assert sum(1 for _ in (ROOT / "smt_gui.py").open(encoding="utf-8")) < 3100
    tree = ast.parse((ROOT / "smt_gui.py").read_text(encoding="utf-8"))
    assert not any(isinstance(node, ast.ClassDef) and node.name == "Backend" for node in tree.body)


def test_catalog_file_remains_exactly_158_commands():
    raw = (ROOT / "smt_commands.json").read_bytes()
    doc = json.loads(raw)
    assert len(doc["commands"]) == 160
    assert hashlib.sha256(raw).hexdigest() == "a41b42c1b0dcfe486b802cab6bc8a66a999ed02544e940b7e2cbe3cb81d24734"


def test_protocol_decodes_utf8_cp1251_and_binary_fallback():
    assert protocol.decode_response("тест".encode()) == "тест"
    assert protocol.decode_response("тест".encode("cp1251")) == "тест"
    assert protocol.decode_response(b"\xff") == "я"


def test_auth_rejects_empty_and_known_error_responses():
    for value in (b"", b"NAK", b"ACCESS_DENIED", b"INCORRECT_PASSWORD"):
        assert protocol.response_has_auth_error(value)
    assert not protocol.response_has_auth_error(b"OK")


def test_server_parser_crc_and_auth_roundtrip():
    body = "{V;1;1;1;26.07.2026,12:00:00;10000;1.00;;0;}"
    inner = body[1:-1].encode("latin1")
    crc = [smt_server.crc16(inner, *smt_server.CRC16_VARIANTS[name])
           for name in ("XMODEM", "KERMIT", "MODBUS")]
    prefix = f"TELE;{crc[0]:04X};{crc[1]:04X};{crc[2]:04X};0123456789ABCDEF;{body}"
    raw = (prefix + "auth=" + hashlib.md5(prefix.encode("latin1")).hexdigest()).encode("latin1")
    report = smt_server.parse_frame(raw)
    assert report["header"]["id64"] == "0123456789ABCDEF"
    assert report["records"][0]["accumulator"] == 10000
    assert any(item["match"] for item in smt_server.auth_check(report["text"], report["auth"]))


def test_eventlog_parser_keeps_newest_duplicate_counter():
    profile = smt_firmware.DEFAULT_PROFILE
    data = bytearray(b"\xff" * (profile.event_log_end + 64))
    for offset, ts, text in ((profile.event_log_start, 1_700_000_000, b"old"),
                             (profile.event_log_start + 0x10, 1_800_000_000, b"new")):
        struct.pack_into("<I", data, offset, ts)
        struct.pack_into("<I", data, offset + 8, 7)
        struct.pack_into("<H", data, offset + 0x0C, 0x0205)
        data[offset + 0x0E:offset + 0x0E + len(text)] = text
        data[offset + 0x0E + len(text)] = 0
    parsed = smt_eventlog.parse(data)
    assert parsed[7] == (1_800_000_000, 0x0205, "new")


def test_snapshot_json_csv_roundtrip(tmp_path):
    values = {"A": "1", "B": "<err:x>"}
    json_path = tmp_path / "snap.json"
    csv_path = tmp_path / "snap.csv"
    smt_tools.save_snapshot_json(str(json_path), values, source="test")
    smt_tools.save_snapshot_csv(str(csv_path), values)
    assert smt_tools.load_snapshot(str(json_path)) == values
    assert smt_tools.load_snapshot(str(csv_path)) == values


def test_gui_support_reexports_telemetry_without_ui_dependency():
    packet = smt_gui_support.build_telemetry_packet({
        "Volume": "1.25", "VOLUME_INST": "0.5", "DEVICE_SN": "ABCDEFGH",
    })
    parsed = smt_server.parse_frame(packet.encode("latin1"))
    assert parsed["header"]["id64"] == "4142434445464748"
    assert parsed["records"][0]["accumulator"] == 12500


def test_gui_build_smoke_under_display():
    import os
    import time

    import pytest
    if not os.environ.get("DISPLAY"):
        pytest.skip("требуется X display; релизный прогон использует xvfb-run")
    import tkinter as tk
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"X display недоступен: {exc}")
    root.withdraw()
    app = smt_gui.build_app(root, selftest=True)
    root.update_idletasks()
    root.update()
    assert app["state"]["connected"] is False
    assert app["log"] is not None
    app["task_q"].put({"op": "quit"})
    for _ in range(10):
        root.update()
        time.sleep(0.01)
    root.destroy()
