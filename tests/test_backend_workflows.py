#!/usr/bin/env python3
"""Интеграционные тесты backend/telemetry без физического оборудования."""
from __future__ import annotations

import argparse
import queue
import socket
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import contextlib

import smt_backend
import smt_client as sc
import smt_server
import smt_telemetry
from smt_backend import Backend


class MemoryTransport:
    def __init__(self):
        self.is_open = True
        self.frame_name = "cr"
        self.last_tx = self.last_raw_rx = self.last_rx = b""
        self.last_echo_removed = False
        self.last_latency_ms = 1
        self.last_attempts = 1
        self.sent = []

    def _answer(self, command):
        if command.startswith("PASSWORD_PROVIDER=") or command.startswith("PASSWORD_OMEGA="):
            return b"OK;"
        if "=" in command or command in {"CLEAR_ARHIVE", "VALVE_OPEN"}:
            return b"OK;"
        values = {
            "DevInfo": "SIM",
            "Volume": "12.5",
            "DEVICE_SN": "ABC123",
            "PASSWORD_PROVIDER": "123456",
            "ArcNumRecords": "7",
        }
        return f"{command}={values.get(command, '1')};".encode()

    def send(self, command, *, retry_safe=False):
        self.sent.append((command, retry_safe))
        self.last_tx = (command + "\r").encode()
        self.last_raw_rx = self.last_rx = self._answer(command)
        return self.last_rx

    def probe(self, command="DevInfo"):
        return self.send(command, retry_safe=True)

    def raw_exchange(self, payload, *, response_timeout=None):
        self.last_tx = bytes(payload)
        self.last_raw_rx = self.last_rx = bytes(reversed(payload))
        return self.last_rx

    def receive_unread(self, *, delete=False):
        return [{"index": 1, "header": '+CMGL: 1,"REC UNREAD"', "text": "DevInfo=SIM"}]

    def send_at(self, command, *, timeout=5.0):
        self.last_tx = (command + "\r").encode()
        self.last_raw_rx = self.last_rx = b"OK\r\n"
        return self.last_rx

    def health_check(self):
        return self.send_at("AT")

    def line_description(self):
        return "MEMORY 9600 8N1"

    def close(self):
        self.is_open = False


def _backend(catalog=None):
    out = queue.Queue()
    backend = Backend(queue.Queue(), out,
                      critical={"Volume", "CLEAR_ARHIVE", "PASSWORD_PROVIDER"},
                      actions={"CLEAR_ARHIVE"}, catalog=catalog or [])
    backend.cli = sc.SmtClient(MemoryTransport())
    backend.mode = "serial"
    return backend, out


def test_backend_service_workflows(monkeypatch):
    catalog = [{"name": "DevInfo"}, {"name": "CLEAR_ARHIVE"}]
    backend, out = _backend(catalog)
    monkeypatch.setattr(smt_backend.sc, "PASSPORT", ["DevInfo", "Volume"])
    monkeypatch.setattr(smt_backend, "SECRET_READS", [("PASSWORD_PROVIDER", "provider")])
    monkeypatch.setattr(smt_backend, "TELE_PARAMS", ["Volume", "DEVICE_SN"])
    monkeypatch.setattr(smt_backend.time, "sleep", lambda _seconds: None)

    backend._preflight()
    backend._read("Volume")
    backend._send("LCD_TIME=5", expert=False)
    backend._auth("PASSWORD_PROVIDER", "123456")
    assert backend.auth_state["verified"] is True
    backend._passport()
    backend._authscan()
    backend._tele_read()
    backend._scan_all()
    backend._batch("READ DevInfo\nSET LCD_TIME=5\nACTION CLEAR_ARHIVE", expert=True, dry_run=True)
    backend._batch("READ DevInfo\nSET LCD_TIME=5\nACTION CLEAR_ARHIVE", expert=True)
    backend._raw_hex("01 02 03", timeout=0.1, expert=True)
    backend._sms_receive(delete=True)
    backend._modem_at("AT+CSQ")

    kinds = []
    while not out.empty():
        kinds.append(out.get_nowait()[0])
    for expected in ("reading", "auth_state", "tele_reading", "snapshot",
                     "batch_done", "raw_result", "sms_messages"):
        assert expected in kinds
    backend._close()
    assert backend.cli is None and backend.mode == "off"


def test_backend_thread_dispatches_and_quits():
    tasks, out = queue.Queue(), queue.Queue()
    backend = Backend(tasks, out)
    backend.start()
    tasks.put({"op": "read", "name": "DevInfo"})
    tasks.put({"op": "quit"})
    backend.join(2)
    assert not backend.is_alive()
    messages = []
    while not out.empty():
        messages.append(out.get_nowait())
    assert any(kind == "log" and "Нет подключения" in payload[1]
               for kind, payload in messages)


class FakeOptic(MemoryTransport):
    def __init__(self, port, baud, **kwargs):
        super().__init__(); self.port = port; self.baud = baud
    def detect_framing(self, command, on_attempt=None):
        if on_attempt is not None:
            on_attempt("cr", 1, True, b"")
        return "cr", self.probe(command)
    def set_framing(self, name): self.frame_name = name


class FakeTcp(MemoryTransport):
    def __init__(self, host, port, **kwargs):
        super().__init__(); self.host = host; self.port = port; self.frame_name = "tcp"


class FakeSms(MemoryTransport):
    def __init__(self, port, phone, **kwargs):
        super().__init__(); self.port = port; self.phone = phone; self.frame_name = "sms-text"


def test_backend_connect_dispatch_for_all_transports(monkeypatch):
    monkeypatch.setattr(smt_backend.sc, "OpticTransport", FakeOptic)
    monkeypatch.setattr(smt_backend.sc, "TcpServerTransport", FakeTcp)
    monkeypatch.setattr(smt_backend.sc, "SmsTransport", FakeSms)
    monkeypatch.setattr(smt_backend, "ss", None)
    backend = Backend(queue.Queue(), queue.Queue())

    backend._connect({"transport": "serial", "port": "COM1", "baud": 9600,
                      "framing": "auto", "bytesize": 8, "parity": "N", "stopbits": 1})
    assert backend.mode == "serial"
    backend._connect({"transport": "tcp", "host": "127.0.0.1", "tcp_port": 40000})
    assert backend.mode == "tcp"
    backend._connect({"transport": "sms", "modem_port": "COM2", "phone": "+7000"})
    assert backend.mode == "sms"
    with pytest.raises(ValueError):
        backend._connect({"transport": "unknown"})
    backend._close()


def _telemetry_packet():
    return smt_telemetry.build_telemetry_packet({
        "Volume": "2.5", "VOLUME_INST": "0.25", "DEVICE_SN": "ABCDEFGH",
    }).encode("latin1")


def test_live_telemetry_server_receives_and_acks(tmp_path, monkeypatch):
    monkeypatch.setattr(smt_telemetry, "HERE", str(tmp_path))
    monkeypatch.setattr(smt_telemetry, "TELEMETRY_DB_PATH", str(tmp_path / "telemetry.sqlite3"))
    out = queue.Queue()
    server = smt_telemetry.TeleServer(0, out, idle=0.05)
    server.start()
    deadline = time.time() + 2
    while (server.srv is None or server.srv.getsockname()[1] == 0) and time.time() < deadline:
        time.sleep(0.01)
    port = server.srv.getsockname()[1]
    with socket.create_connection(("127.0.0.1", port), timeout=1) as client:
        client.sendall(_telemetry_packet())
        client.shutdown(socket.SHUT_WR)
        ack = client.recv(128)
    assert ack.startswith(b"DATA ACCEPT:1")
    deadline = time.time() + 2
    events = []
    while time.time() < deadline:
        with contextlib.suppress(queue.Empty):
            events.append(out.get(timeout=0.05))
        if any(kind == "tele_rx" for kind, _ in events):
            break
    assert any(kind == "tele_rx" for kind, _ in events)
    server.stop(); server.join(2)
    assert list((tmp_path / "sessions").glob("session_*.log"))


def test_tele_send_reports_real_ack():
    ready = threading.Event(); state = {}
    def listener():
        with socket.socket() as srv:
            srv.bind(("127.0.0.1", 0)); srv.listen(1)
            state["port"] = srv.getsockname()[1]; ready.set()
            conn, _ = srv.accept()
            with conn:
                state["data"] = conn.recv(4096)
                conn.sendall(b"ACK")
    thread = threading.Thread(target=listener, daemon=True); thread.start()
    assert ready.wait(1)
    out = queue.Queue()
    smt_telemetry.tele_send("127.0.0.1", state["port"], b"payload", out)
    kind, payload = out.get(timeout=2)
    assert kind == "tele_log" and "ACK 'ACK'" in payload[1]
    assert state["data"] == b"payload"


def test_server_handle_conn_writes_session_and_ack(tmp_path):
    left, right = socket.socketpair()
    args = argparse.Namespace(outdir=str(tmp_path), idle=0.05, max_frame=1024 * 1024,
                              connection_timeout=1.0, quiet=True, crc_scan=False,
                              ack="DATA ACCEPT:{n}\r\n")
    thread = threading.Thread(target=smt_server.handle_conn,
                              args=(left, ("local", 1234), args), daemon=True)
    thread.start()
    right.sendall(_telemetry_packet()); right.shutdown(socket.SHUT_WR)
    ack = right.recv(128)
    thread.join(2); right.close()
    assert ack.startswith(b"DATA ACCEPT:1")
    assert list(tmp_path.glob("session_*.log"))
    assert list(tmp_path.glob("session_*.json"))
