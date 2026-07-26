#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import queue

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import smt_gui
import smt_state
import smt_telemetry_store as telemetry_store


def test_telemetry_store_deduplicates_and_marks_decrease(tmp_path):
    db = tmp_path / "telemetry.sqlite3"
    report1 = {
        "header": {"name": "TELE", "id64": "ABCDEF0123456789"},
        "auth": None,
        "records": [
            {"type": 1, "dt": "2026-07-26 10:00:00", "accumulator": 100000,
             "value": 1.0, "flag": 0},
        ],
    }
    raw1 = b"packet-one"
    packet_id, inserted, anomalies = telemetry_store.ingest(
        str(db), raw1, report1, source_ip="127.0.0.1", source_port=40000)
    assert inserted and anomalies == 0
    same_id, inserted, anomalies = telemetry_store.ingest(
        str(db), raw1, report1, source_ip="127.0.0.1", source_port=40000)
    assert same_id == packet_id and not inserted

    report2 = {
        "header": {"name": "TELE", "id64": "ABCDEF0123456789"},
        "auth": None,
        "records": [
            {"type": 1, "dt": "2026-07-26 11:00:00", "accumulator": 90000,
             "value": 0.5, "flag": 2},
        ],
    }
    _, inserted, anomalies = telemetry_store.ingest(
        str(db), b"packet-two", report2, source_ip="127.0.0.1", source_port=40000)
    assert inserted and anomalies == 1
    stat = telemetry_store.stats(str(db))
    assert stat["packets"] == 2
    assert stat["records"] == 2
    assert stat["anomalies"] == 1
    rows = telemetry_store.recent_records(str(db), anomalies_only=True)
    assert len(rows) == 1
    assert "накопитель уменьшился" in rows[0]["anomaly"]
    assert "флаг=2" in rows[0]["anomaly"]


def test_history_timeline_integrity_and_sequence_analysis():
    records = [
        {"index": 1, "unixtime": 100, "datetime": None,
         "volume": 10.0, "volume_copy": 10.0},
        {"index": 2, "unixtime": 200, "datetime": None,
         "volume": 11.0, "volume_copy": 10.5},
        {"index": 1, "unixtime": 150, "datetime": None,
         "volume": 9.0, "volume_copy": 9.0},
    ]
    enriched, summary = smt_state.analyse_timeline(records)
    assert summary["copy_mismatch"] == 1
    assert summary["time_back"] == 1
    assert summary["index_back"] == 1
    assert summary["volume_back"] == 1
    assert summary["anomalies"] == 2
    assert enriched[1]["integrity_ok"] is False
    assert "показание уменьшилось" in enriched[2]["anomaly"]


def _verified_backend(out_q=None):
    backend = smt_gui.Backend(queue.Queue(), out_q or queue.Queue(),
                              critical={"Volume", "CLEAR_ARHIVE"},
                              actions={"CLEAR_ARHIVE"}, catalog=[])
    backend.auth_state = {"level": "provider", "verified": True,
                          "verified_at": __import__("time").time()}
    return backend


def test_direct_reading_write_is_blocked_without_provider_workflow():
    backend = _verified_backend()
    with pytest.raises(PermissionError, match="Provider"):
        backend._send("Volume=123.4", expert=True)


def test_provider_reading_write_is_verified_and_does_not_clear_archive():
    out_q = queue.Queue()
    backend = _verified_backend(out_q)
    reads = {
        "Volume": iter(["10.0000", "12.5000"]),
        "DEVICE_SN": iter(["SN001"]),
        "ArcNumRecords": iter(["8"]),
    }
    sent = []

    backend._read_value_quiet = lambda name: next(reads[name])
    backend._tx = lambda text, **kwargs: (sent.append((text, kwargs)) or (b"OK", ""))

    backend._write_reading_provider({
        "name": "Volume", "val": "12.5", "expert": True,
        "operator": "engineer-1", "reason": "стендовая поверка",
    })

    assert [item[0] for item in sent] == ["Volume=12.5"]
    assert sent[0][1]["kind"] == "reading-set"
    events = []
    while not out_q.empty():
        events.append(out_q.get_nowait())
    result = next(payload for kind, payload in events if kind == "reading_write_done")
    assert result["old_value"] == "10.0000"
    assert result["new_value"] == "12.5000"
    assert result["archive_count_before"] == "8"
    assert result["archive_changed"] is False


def test_archive_clear_is_separate_and_verified():
    out_q = queue.Queue()
    backend = _verified_backend(out_q)
    reads = {
        "DEVICE_SN": iter(["SN001"]),
        "ArcNumRecords": iter(["8", "0"]),
    }
    sent = []
    backend._read_value_quiet = lambda name: next(reads[name])
    backend._tx = lambda text, **kwargs: (sent.append((text, kwargs)) or (b"OK", ""))

    backend._clear_archive_provider({
        "expert": True, "operator": "engineer-1", "reason": "регламент",
    })

    assert [item[0] for item in sent] == ["CLEAR_ARHIVE"]
    events = []
    while not out_q.empty():
        events.append(out_q.get_nowait())
    result = next(payload for kind, payload in events if kind == "archive_clear_done")
    assert result["archive_count_before"] == "8"
    assert result["archive_count_after"] == "0"


def test_provider_operations_require_expert_and_verified_auth():
    backend = smt_gui.Backend(queue.Queue(), queue.Queue(),
                              critical={"Volume", "CLEAR_ARHIVE"},
                              actions={"CLEAR_ARHIVE"}, catalog=[])
    with pytest.raises(PermissionError, match="Экспертный режим"):
        backend._write_reading_provider({"name": "Volume", "val": "1", "expert": False})
    with pytest.raises(PermissionError, match="Provider"):
        backend._write_reading_provider({
            "name": "Volume", "val": "1", "expert": True,
            "operator": "op", "reason": "test",
        })



def test_direct_clear_archive_is_blocked_outside_provider_workflow():
    backend = _verified_backend()
    with pytest.raises(PermissionError, match="Provider"):
        backend._send("CLEAR_ARHIVE", expert=True)
