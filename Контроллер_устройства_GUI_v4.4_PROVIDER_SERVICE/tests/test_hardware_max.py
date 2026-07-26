#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверки реальных транспортов HARDWARE MAX без подключения прибора."""
import os
import socket
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import smt_client as sc
import smt_gui as gui


class FakeSerial:
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
        result = bytes(self._rx[:n])
        del self._rx[:n]
        return result

    def write(self, data):
        data = bytes(data)
        self.writes.append(data)
        self._rx.extend(self.responder(data) or b"")
        return len(data)

    def flush(self):
        return None

    def reset_input_buffer(self):
        self._rx.clear()

    def reset_output_buffer(self):
        return None

    def close(self):
        self.is_open = False


def test_raw_serial_exchange_is_exact():
    fake = FakeSerial(lambda data: b"\xAA\x55" if data == b"\x01\x02\x03" else b"")
    tr = sc.OpticTransport("FAKE", ser=fake, response_timeout=0.2, idle_gap=0.03)
    answer = tr.raw_exchange(b"\x01\x02\x03")
    assert fake.writes == [b"\x01\x02\x03"]
    assert answer == b"\xAA\x55"
    assert tr.last_tx == b"\x01\x02\x03"


def _one_shot_server(response, received, ready):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.bind(("127.0.0.1", 0))
        received["port"] = srv.getsockname()[1]
        srv.listen(1)
        ready.set()
        conn, _ = srv.accept()
        with conn:
            data = bytearray()
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data.extend(chunk)
            received["data"] = bytes(data)
            conn.sendall(response)


def test_tcp_command_transport_real_socket():
    received = {}
    ready = threading.Event()
    thread = threading.Thread(target=_one_shot_server,
                              args=(b"DevInfo=TCP-GATEWAY;\r\n", received, ready),
                              daemon=True)
    thread.start()
    assert ready.wait(2)
    tr = sc.TcpServerTransport("127.0.0.1", received["port"], timeout=2,
                               terminator=b"\r\n")
    raw = tr.send("DevInfo")
    thread.join(2)
    assert received["data"] == b"DevInfo\r\n"
    assert sc.value_of(raw, name="DevInfo") == "TCP-GATEWAY"


def test_hardware_catalog_and_no_demo_module():
    assert len(gui.load_catalog()) == 158
    root = os.path.dirname(HERE)
    assert not os.path.exists(os.path.join(root, "smt_demo.py"))
    assert not os.path.exists(os.path.join(root, "start_demo.bat"))
