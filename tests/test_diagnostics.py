#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import queue

from smt_core.client import SmtClient
from smt_diagnostics import DiagnosticRecorder, InstrumentedQueue


class FakeTransport:
    def __init__(self):
        self.last_tx = b""
        self.last_raw_rx = b""
        self.last_rx = b""
        self.last_latency_ms = 7
        self.last_attempts = 1
        self.last_echo_removed = False
        self.last_read_truncated = False

    def send(self, cmd: str, *, retry_safe: bool = False) -> bytes:
        del retry_safe
        self.last_tx = (cmd + "\r").encode("latin1")
        self.last_raw_rx = f"{cmd}=OK;".encode("latin1")
        self.last_rx = self.last_raw_rx
        return self.last_rx


def read_events(path):
    with open(path, encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def test_diagnostic_records_full_unmasked_payload_and_exports(tmp_path):
    live = []
    rec = DiagnosticRecorder(str(tmp_path), application="test", version="4.5.4", live_sink=live.append)
    rec.emit("auth", "provider", status="ok", details={
        "command": "PASSWORD_PROVIDER=123456",
        "tx": b"PASSWORD_PROVIDER=123456\r",
        "rx": b"OK;",
    })
    jsonl = rec.jsonl_path
    csv_path = tmp_path / "diagnostic.csv"
    rows = rec.export_csv(str(csv_path))
    rec.close()

    events = read_events(jsonl)
    payload = json.dumps(events, ensure_ascii=False)
    assert "PASSWORD_PROVIDER=123456" in payload
    assert "50 41 53 53 57 4f 52 44" in payload.lower() or "50 41 53 53 57 4f 52 44" in payload.upper()
    assert rows >= 2  # session.start + explicit event
    assert live
    with open(csv_path, encoding="utf-8-sig") as stream:
        assert any(row["action"] == "provider" for row in csv.DictReader(stream))


def test_instrumented_queue_records_every_enqueued_task(tmp_path):
    rec = DiagnosticRecorder(str(tmp_path), application="test", version="4.5.4")
    base = queue.Queue()
    q = InstrumentedQueue(base, rec, component="gui")
    task = {"op": "send", "text": "CLEAR_ARHIVE", "expert": True}
    q.put(task)
    assert q.get_nowait() == task
    path = rec.jsonl_path
    rec.close()
    events = read_events(path)
    queued = [e for e in events if e.get("action") == "task.enqueue"]
    assert queued and queued[-1]["details"]["text"] == "CLEAR_ARHIVE"


def test_client_diagnostics_contains_full_wire_exchange(tmp_path):
    rec = DiagnosticRecorder(str(tmp_path), application="test", version="4.5.4")
    tr = FakeTransport()
    client = SmtClient(tr, diagnostic=rec)
    answer = client.send("Volume", retry_safe=True, mutating=False)
    assert answer == b"Volume=OK;"
    path = rec.jsonl_path
    rec.close()
    events = read_events(path)
    completed = [e for e in events if e.get("component") == "client" and e.get("action") == "command.end"]
    assert completed
    details = completed[-1]["details"]
    assert details["command"] == "Volume"
    assert details["tx"]["latin1"] == "Volume\r"
    assert details["rx_raw"]["latin1"] == "Volume=OK;"


def test_offline_viewer_filters_and_summarizes(tmp_path):
    from smt_diagnostic_viewer import filter_events, iter_events, summarize

    rec = DiagnosticRecorder(str(tmp_path), application="test", version="4.5.4")
    rec.emit("backend", "task.end", status="ok", duration_ms=12.5, details={"op": "read"})
    rec.emit("backend", "task.end", status="error", duration_ms=2.0,
             details={"op": "write"}, error="denied")
    path = rec.jsonl_path
    rec.close()
    selected = list(filter_events(iter_events(path), component="backend", status="error"))
    assert len(selected) == 1
    report = summarize(iter_events(path))
    assert report["events"] >= 4
    assert report["errors"] == 1
    assert report["duration"]["maximum_ms"] == 12.5
