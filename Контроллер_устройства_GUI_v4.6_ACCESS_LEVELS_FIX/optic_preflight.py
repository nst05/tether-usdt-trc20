#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Диагностика физического оптопорта без запуска GUI.

Использование:
  python3 optic_preflight.py
  python3 optic_preflight.py /dev/ttyUSB0
  python3 optic_preflight.py COM4 --baud 9600
  python3 optic_preflight.py COM4 --framing crlf
  python3 optic_preflight.py COM4 --auth-scan

Проверка кадрирования выполняется только безопасной командой чтения DevInfo.
"""
from __future__ import annotations

import argparse
import sys

try:
    from serial.tools import list_ports
except ImportError:
    list_ports = None

import smt_client as sc

CANDIDATE_HINTS = (
    "ttyusb", "ttyacm", "usbserial", "usbmodem", "com",
    "ch340", "cp210", "ftdi", "usb serial",
)

ACCESS_DIAGNOSTICS = ["PASWORD_PROVID_VALUE", "ENABLE_OMEGA", "EVENT_OMEGA"]
MASK_MARKERS = ("****", "xxxx", "----")


def discover_ports():
    if list_ports is None:
        return [], []
    ports = list(list_ports.comports())
    candidates = [p for p in ports if any(
        hint in ((p.device or "") + " " + (p.description or "")).lower()
        for hint in CANDIDATE_HINTS
    )]
    return ports, candidates


def hexdump(prefix, data):
    data = data or b""
    return f"{prefix} [{len(data)}] " + " ".join(f"{b:02X}" for b in data)


def classify(value):
    if value in (None, ""):
        return "не отдан"
    low = str(value).lower()
    if any(marker in low for marker in MASK_MARKERS):
        return "маскирован"
    return "прочитан"


def choose_port(explicit):
    if explicit:
        return explicit
    ports, candidates = discover_ports()
    if not ports:
        raise SystemExit("[FAIL] Serial-порты не найдены. Подключи USB-оптоголовку.")
    print("[*] Найдены serial-порты:")
    for item in ports:
        marker = " <- кандидат" if item in candidates else ""
        vidpid = f" VID:PID={item.vid:04X}:{item.pid:04X}" if item.vid is not None and item.pid is not None else ""
        print(f"    {item.device:<18} {item.description or 'serial'}{vidpid}{marker}")
    if len(candidates) == 1:
        print(f"[*] Автовыбор: {candidates[0].device}")
        return candidates[0].device
    raise SystemExit("Укажи порт явно, например: python3 optic_preflight.py COM4")


def main():
    parser = argparse.ArgumentParser(description="Проверка физического оптопорта")
    parser.add_argument("port", nargs="?")
    parser.add_argument("--baud", type=int, default=9600)
    parser.add_argument("--framing", choices=["auto", *sc.FRAMINGS], default="auto")
    parser.add_argument("--probe", default="DevInfo", help="команда чтения после установления связи")
    parser.add_argument("--auth-scan", action="store_true")
    args = parser.parse_args()

    if sc.serial is None:
        print("[FAIL] Нужен pyserial: pip install pyserial")
        return 2
    port = choose_port(args.port)
    print(f"[*] Открываю: {port} · {args.baud} 8N1 · кадр {args.framing}")
    transport = None
    try:
        transport = sc.OpticTransport(port, args.baud)
        if args.framing == "auto":
            framing, raw = transport.detect_framing("DevInfo")
        else:
            transport.set_framing(args.framing)
            raw = transport.probe("DevInfo")
            framing = args.framing

        print(f"[OK] Кадрирование: {framing}")
        print(f"[OK] Задержка ответа: {transport.last_latency_ms} мс")
        print(f"[OK] Само-эхо: {'обнаружено и снято' if transport.last_echo_removed else 'не обнаружено'}")
        print(hexdump("TX", transport.last_tx))
        print(hexdump("RX", transport.last_raw_rx))
        print(f"DevInfo = {sc.value_of(raw, 'DevInfo')!r}")

        client = sc.SmtClient(transport)
        if args.probe and args.probe != "DevInfo":
            value = client.get(args.probe)
            print(f"{args.probe} = {value!r}")
            print(hexdump("TX", transport.last_tx))
            print(hexdump("RX", transport.last_raw_rx))

        if args.auth_scan:
            print("\n[*] Диагностика доступа без чтения PASSWORD_*:")
            for name in ACCESS_DIAGNOSTICS:
                try:
                    value = client.get(name)
                    print(f"    {name:<22} = {value!r:<20} [{classify(value)}]")
                except Exception as exc:
                    print(f"    {name:<22} = <err:{exc}>")
            print("    Текущий уровень напрямую не читается; PASSWORD_* проверяется по ответу команды.")
        return 0
    except Exception as exc:
        print(f"[FAIL] {exc}")
        return 2
    finally:
        if transport is not None:
            transport.close()


if __name__ == "__main__":
    raise SystemExit(main())
