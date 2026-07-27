#!/usr/bin/env python3
import os
import queue
import sys

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
    # Физический порядок кольца сортируется по времени до анализа, поэтому
    # ложных откатов времени/индекса здесь больше нет.
    assert summary["time_back"] == 0
    assert summary["index_back"] == 0
    assert summary["volume_back"] == 1
    assert summary["anomalies"] == 2
    assert enriched[2]["integrity_ok"] is False
    assert "показание уменьшилось" in enriched[1]["anomaly"]


def _verified_backend(out_q=None):
    backend = smt_gui.Backend(queue.Queue(), out_q or queue.Queue(),
                              critical={"Volume", "CLEAR_ARHIVE"},
                              actions={"CLEAR_ARHIVE"}, catalog=[])
    backend.auth_state = {"level": "provider", "verified": True,
                          "verified_at": __import__("time").time()}
    return backend


def test_direct_low_level_reading_write_is_not_blocked():
    backend = _verified_backend()
    sent = []
    backend._tx = lambda text, **kwargs: (sent.append((text, kwargs)) or (b"OK", ""))
    backend._send("Volume=123.4", expert=True)
    assert [item[0] for item in sent] == ["Volume=123.4"]


def test_provider_reading_write_with_optional_readback():
    out_q = queue.Queue()
    backend = _verified_backend(out_q)
    sent = []
    backend._read_value_quiet = lambda name: "12.5000"
    backend._tx = lambda text, **kwargs: (sent.append((text, kwargs)) or (b"OK", ""))

    backend._write_reading_provider({
        "name": "Volume", "val": "12.5", "expert": True, "verify": True,
    })

    assert [item[0] for item in sent] == ["Volume=12.5"]
    events = []
    while not out_q.empty():
        events.append(out_q.get_nowait())
    result = next(payload for kind, payload in events if kind == "reading_write_done")
    assert result["new_value"] == "12.5000"
    assert result["verified"] is True


def test_provider_reading_write_can_skip_readback():
    out_q = queue.Queue()
    backend = _verified_backend(out_q)
    sent = []
    backend._read_value_quiet = lambda name: (_ for _ in ()).throw(AssertionError("read-back called"))
    backend._tx = lambda text, **kwargs: (sent.append((text, kwargs)) or (b"OK", ""))

    backend._write_reading_provider({
        "name": "Volume", "val": "12.5", "expert": True, "verify": False,
    })
    assert [item[0] for item in sent] == ["Volume=12.5"]
    events = []
    while not out_q.empty():
        events.append(out_q.get_nowait())
    result = next(payload for kind, payload in events if kind == "reading_write_done")
    assert result["new_value"] == "12.5"
    assert result["verified"] is False


def test_provider_button_requires_expert_and_verified_auth():
    backend = smt_gui.Backend(queue.Queue(), queue.Queue(),
                              critical={"Volume", "CLEAR_ARHIVE"},
                              actions={"CLEAR_ARHIVE"}, catalog=[])
    with pytest.raises(PermissionError, match="Экспертный режим"):
        backend._write_reading_provider({"name": "Volume", "val": "1", "expert": False})
    with pytest.raises(PermissionError, match="Provider"):
        backend._write_reading_provider({"name": "Volume", "val": "1", "expert": True})


def test_direct_clear_archive_is_available_in_expert_mode():
    backend = _verified_backend()
    sent = []
    backend._tx = lambda text, **kwargs: (sent.append((text, kwargs)) or (b"OK", ""))
    backend._send("CLEAR_ARHIVE", expert=True)
    assert [item[0] for item in sent] == ["CLEAR_ARHIVE"]




def test_telemetry_out_of_order_packet_does_not_create_false_decrease(tmp_path):
    db = tmp_path / "telemetry_order.sqlite3"
    device = "ORDER001122334455"
    newer = {"header": {"name": "TELE", "id64": device}, "auth": None,
             "records": [{"type": 1, "dt": "2026-07-26 10:00:00",
                           "accumulator": 100000, "value": 1.0, "flag": 0}]}
    older = {"header": {"name": "TELE", "id64": device}, "auth": None,
             "records": [{"type": 1, "dt": "2026-07-26 09:00:00",
                           "accumulator": 90000, "value": 1.0, "flag": 0}]}
    telemetry_store.ingest(str(db), b"newer", newer)
    _, inserted, anomalies = telemetry_store.ingest(str(db), b"older", older)
    assert inserted is True
    assert anomalies == 0


def test_pick_half_uses_newest_valid_record():
    import struct
    data = bytearray(b"\xff" * 0x800000)

    def put(base, index, ts, volume):
        struct.pack_into("<d", data, base + 0x00, volume)
        struct.pack_into("<d", data, base + 0x10, volume)
        struct.pack_into("<I", data, base + 0x40, index)
        struct.pack_into("<I", data, base + 0x5C, 0xA5A50001)
        struct.pack_into("<I", data, base + 0x74, ts)

    put(0x7FE000, 10, 1_700_000_000, 10.0)
    put(0x7FC000, 11, 1_800_000_000, 11.0)
    assert smt_state.pick_half(data) == 0x7FC000


def test_checkpoint_validity_requires_matching_copy():
    import struct
    data = bytearray(b"\x00" * 0x80)
    struct.pack_into("<d", data, 0x00, 10.0)
    struct.pack_into("<d", data, 0x10, 9.0)
    struct.pack_into("<I", data, 0x5C, 0xA5A50001)
    struct.pack_into("<I", data, 0x74, 1_700_000_000)
    row = smt_state.parse_record(data, 0)
    assert row["marker_valid"] is True
    assert row["copy_ok"] is False
    assert row["valid"] is False
