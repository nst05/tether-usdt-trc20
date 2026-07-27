#!/usr/bin/env python3
"""Persistent telemetry store for received physical-device packets.

Uses only the Python standard library (sqlite3). Raw packets are deduplicated by
SHA-256, parsed records are retained, and basic sequence anomalies are marked.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import os
import sqlite3
from typing import Any

SCHEMA_VERSION = 1


def _connect(path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    con = sqlite3.connect(path, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS meta(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS packets(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            received_utc TEXT NOT NULL,
            source_ip TEXT NOT NULL DEFAULT '',
            source_port INTEGER,
            raw_sha256 TEXT NOT NULL UNIQUE,
            raw_size INTEGER NOT NULL,
            header_name TEXT NOT NULL DEFAULT '',
            id64 TEXT NOT NULL DEFAULT '',
            auth TEXT NOT NULL DEFAULT '',
            auth_ok INTEGER,
            record_count INTEGER NOT NULL DEFAULT 0,
            raw_text TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS records(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            packet_id INTEGER NOT NULL REFERENCES packets(id) ON DELETE CASCADE,
            seq INTEGER NOT NULL,
            record_type INTEGER,
            device_datetime TEXT NOT NULL DEFAULT '',
            accumulator INTEGER,
            accumulator_m3 REAL,
            value REAL,
            flag INTEGER,
            anomaly TEXT NOT NULL DEFAULT '',
            UNIQUE(packet_id, seq)
        );
        CREATE INDEX IF NOT EXISTS idx_packets_received ON packets(received_utc);
        CREATE INDEX IF NOT EXISTS idx_packets_device ON packets(id64, received_utc);
        CREATE INDEX IF NOT EXISTS idx_records_packet ON records(packet_id, seq);
        """
    )
    con.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('schema_version',?)",
                (str(SCHEMA_VERSION),))
    return con


def _auth_ok(report: dict[str, Any]) -> int | None:
    auth = report.get("auth")
    if not auth:
        return None
    checks = report.get("auth_check") or []
    return 1 if any(bool(x.get("match")) for x in checks) else 0


def _previous_record(con: sqlite3.Connection, id64: str) -> sqlite3.Row | None:
    """Последняя запись устройства по порядку вставки (для межпакетных аномалий)."""
    if not id64:
        return None
    return con.execute(
        """SELECT r.accumulator, r.device_datetime, r.flag
           FROM records r JOIN packets p ON p.id=r.packet_id
           WHERE p.id64=? ORDER BY p.id DESC, r.seq DESC LIMIT 1""",
        (id64,),
    ).fetchone()


def ingest(path: str, raw: bytes, report: dict[str, Any], *,
           source_ip: str = "", source_port: int | None = None) -> tuple[int, bool, int]:
    """Store packet. Returns (packet_id, inserted, anomaly_count)."""
    raw = bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    header = report.get("header") or {}
    id64 = str(header.get("id64") or "")
    records = list(report.get("records") or [])
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    with _connect(path) as con:
        existing = con.execute("SELECT id FROM packets WHERE raw_sha256=?", (digest,)).fetchone()
        if existing:
            return int(existing["id"]), False, 0
        cur = con.execute(
            """INSERT INTO packets(received_utc,source_ip,source_port,raw_sha256,raw_size,
               header_name,id64,auth,auth_ok,record_count,raw_text)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (now, source_ip, source_port, digest, len(raw), str(header.get("name") or ""),
             id64, str(report.get("auth") or ""), _auth_ok(report), len(records),
             raw.decode("latin1", "replace")),
        )
        packet_id = int(cur.lastrowid or 0)
        anomalies = 0
        for seq, item in enumerate(records, 1):
            acc = item.get("accumulator")
            record_dt = str(item.get("dt") or "")
            flag = item.get("flag")
            previous = _previous_record(con, id64)
            prev_acc = previous["accumulator"] if previous else None
            prev_dt = previous["device_datetime"] if previous else ""
            marks: list[str] = []
            out_of_order = bool(prev_dt and record_dt and record_dt < prev_dt)
            if out_of_order:
                if prev_acc is not None and acc is not None and int(acc) >= int(prev_acc):
                    marks.append("время вернулось назад")
            elif prev_acc is not None and acc is not None and int(acc) < int(prev_acc):
                marks.append("накопитель уменьшился")
            if flag not in (None, 0, "0"):
                marks.append(f"флаг={flag}")
            anomaly = "; ".join(marks)
            anomalies += bool(anomaly)
            con.execute(
                """INSERT INTO records(packet_id,seq,record_type,device_datetime,
                   accumulator,accumulator_m3,value,flag,anomaly)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (packet_id, seq, item.get("type"), record_dt, acc,
                 (float(acc) / 10000.0 if acc is not None else None),
                 item.get("value"), flag, anomaly),
            )
            # Следующая запись текущего пакета увидит эту строку через SQL-запрос.
        return packet_id, True, anomalies


def stats(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        return {"packets": 0, "records": 0, "devices": 0, "anomalies": 0,
                "first_utc": "", "last_utc": ""}
    with _connect(path) as con:
        p = con.execute("SELECT COUNT(*) n, MIN(received_utc) first_utc, MAX(received_utc) last_utc FROM packets").fetchone()
        r = con.execute("SELECT COUNT(*) n, SUM(CASE WHEN anomaly<>'' THEN 1 ELSE 0 END) a FROM records").fetchone()
        d = con.execute("SELECT COUNT(DISTINCT id64) n FROM packets WHERE id64<>''").fetchone()
        return {"packets": int(p["n"] or 0), "records": int(r["n"] or 0),
                "devices": int(d["n"] or 0), "anomalies": int(r["a"] or 0),
                "first_utc": p["first_utc"] or "", "last_utc": p["last_utc"] or ""}


def recent_records(path: str, limit: int = 500, *, anomalies_only: bool = False,
                   id64: str = "") -> list[dict[str, Any]]:
    if not os.path.exists(path):
        return []
    where: list[str] = []
    params: list[str | int] = []
    if anomalies_only:
        where.append("r.anomaly<>''")
    if id64:
        where.append("p.id64=?"); params.append(id64)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    params.append(max(1, min(int(limit), 10000)))
    sql = (
        "SELECT p.received_utc,p.source_ip,p.id64,p.auth_ok,p.raw_sha256,"
        "r.seq,r.record_type,r.device_datetime,r.accumulator,r.accumulator_m3,"
        "r.value,r.flag,r.anomaly FROM records r JOIN packets p ON p.id=r.packet_id" +
        clause + " ORDER BY p.id DESC,r.seq DESC LIMIT ?"
    )
    with _connect(path) as con:
        return [dict(row) for row in con.execute(sql, params).fetchall()]


def devices(path: str) -> list[str]:
    if not os.path.exists(path):
        return []
    with _connect(path) as con:
        return [str(r[0]) for r in con.execute(
            "SELECT DISTINCT id64 FROM packets WHERE id64<>'' ORDER BY id64").fetchall()]


def export_csv(path: str, output: str) -> int:
    rows = recent_records(path, 10000)
    cols = ["received_utc", "source_ip", "id64", "auth_ok", "raw_sha256",
            "seq", "record_type", "device_datetime", "accumulator", "accumulator_m3",
            "value", "flag", "anomaly"]
    with open(output, "w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=cols, extrasaction="ignore")
        writer.writeheader(); writer.writerows(reversed(rows))
    return len(rows)
