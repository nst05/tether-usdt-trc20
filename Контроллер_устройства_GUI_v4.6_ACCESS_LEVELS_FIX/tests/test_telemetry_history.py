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


def _catalog():
    return [
        {"name": "Volume", "prov": "0000", "user": "0100", "type": "f/цел"},
        {"name": "VOLUME_GLOB", "prov": "0101", "user": "0000", "type": "f/цел"},
        {"name": "VOLUME_DISC", "prov": "0101", "user": "0101", "type": "f"},
        {"name": "CLEAR_ARHIVE", "prov": "0101", "user": "0101", "type": "действие"},
    ]


def _verified_backend(out_q=None, level="provider"):
    backend = smt_gui.Backend(queue.Queue(), out_q or queue.Queue(),
                              critical={"Volume", "VOLUME_GLOB", "VOLUME_DISC", "CLEAR_ARHIVE"},
                              actions={"CLEAR_ARHIVE"}, catalog=_catalog())
    backend.auth_state = {"level": level, "verified": True,
                          "verified_at": __import__("time").time()}
    return backend


def test_direct_low_level_reading_write_is_not_blocked():
    backend = _verified_backend()
    sent = []
    backend._tx = lambda text, **kwargs: (sent.append((text, kwargs)) or (b"OK", ""))
    backend._send("Volume=123.4", expert=True)
    assert [item[0] for item in sent] == ["Volume=123.4"]


def test_authorized_reading_write_with_optional_readback():
    out_q = queue.Queue()
    backend = _verified_backend(out_q)
    sent = []
    backend._read_value_quiet = lambda name: "12.5000"
    backend._tx = lambda text, **kwargs: (sent.append((text, kwargs)) or (b"OK", ""))

    backend._write_verified({
        "name": "VOLUME_GLOB", "val": "12.5", "expert": True, "verify": True,
    })

    assert [item[0] for item in sent] == ["VOLUME_GLOB=12.5"]
    events = []
    while not out_q.empty():
        events.append(out_q.get_nowait())
    result = next(payload for kind, payload in events if kind == "reading_write_done")
    assert result["new_value"] == "12.5000"
    assert result["verified"] is True


def test_authorized_reading_write_can_skip_readback():
    out_q = queue.Queue()
    backend = _verified_backend(out_q, level="omega")
    sent = []
    backend._read_value_quiet = lambda name: (_ for _ in ()).throw(AssertionError("read-back called"))
    backend._tx = lambda text, **kwargs: (sent.append((text, kwargs)) or (b"OK", ""))

    backend._write_verified({
        "name": "VOLUME_DISC", "val": "12.5", "expert": True, "verify": False,
    })
    assert [item[0] for item in sent] == ["VOLUME_DISC=12.5"]
    events = []
    while not out_q.empty():
        events.append(out_q.get_nowait())
    result = next(payload for kind, payload in events if kind == "reading_write_done")
    assert result["new_value"] == "12.5"
    assert result["verified"] is False


def test_catalog_write_requires_confirmed_level_and_f1_f2_permission():
    backend = smt_gui.Backend(queue.Queue(), queue.Queue(),
                              critical={"Volume", "VOLUME_GLOB"},
                              actions=set(), catalog=_catalog())
    with pytest.raises(PermissionError, match="Сначала предъяви пароль"):
        backend._write_verified({"name": "VOLUME_GLOB", "val": "1", "expert": True})
    backend.auth_state = {"level": "provider", "verified": True, "verified_at": 1}
    with pytest.raises(PermissionError, match="запрещена"):
        backend._write_verified({"name": "Volume", "val": "1", "expert": True})
    with pytest.raises(PermissionError, match="Экспертный режим"):
        backend._write_verified({"name": "VOLUME_GLOB", "val": "1", "expert": False})


def test_direct_clear_archive_is_available_in_expert_mode():
    backend = _verified_backend()
    sent = []
    backend._tx = lambda text, **kwargs: (sent.append((text, kwargs)) or (b"OK", ""))
    backend._send("CLEAR_ARHIVE", expert=True)
    assert [item[0] for item in sent] == ["CLEAR_ARHIVE"]



def test_gui_auth_provider_does_not_probe_pasword_provid_value():
    out_q = queue.Queue()
    backend = smt_gui.Backend(queue.Queue(), out_q, catalog=_catalog())
    backend.mode = "serial"
    sent = []
    backend._tx = lambda text, **kwargs: (sent.append(text) or (b"OK;\r\n", ""))
    backend._auth("provider", "123456")
    assert sent == ["PASSWORD_PROVIDER=123456"]
    assert backend.auth_state["level"] == "provider"
    assert backend.auth_state["verified"] is True


def test_gui_has_only_confirmed_access_levels():
    assert "Provider (F1 · f)" in smt_gui.LEVELS
    assert "Omega (F2 · U)" in smt_gui.LEVELS
    assert not any("Завод" in x or "Factory" in x for x in smt_gui.LEVELS)
    assert set(smt_gui.AUTH_LEVELS) == {"Provider", "Omega"}


def test_access_matrix_controls_write_permission():
    item = {"prov": "0101", "user": "0100"}
    assert smt_gui.access_at_level(item, "Provider (F1 · f)")[2] is True
    assert smt_gui.access_at_level(item, "Omega (F2 · U)")[2] is False
    assert smt_gui.access_at_level(item, "Не определён")[2] is False
