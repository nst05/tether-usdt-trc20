#!/usr/bin/env python3
"""Утилита командной строки для обмена с устройством и офлайн-проверок.

Примеры:
  # собрать кадр и показать его байты (без устройства)
  python3 cli.py build --addr 1 --func 4 --data 05 02

  # разобрать принятый кадр
  python3 cli.py parse 01 04 05 02 <crc_lo> <crc_hi>

  # обмен через реальный порт (нужен pyserial и подключённое устройство)
  python3 cli.py read  --port /dev/ttyUSB0 --addr 1 --index 5 --len 2
  python3 cli.py write --port /dev/ttyUSB0 --addr 1 --index 5 --data DE AD

  # то же против встроенного эмулятора (демонстрация)
  python3 cli.py read  --emulate --addr 1 --index 5 --len 2
"""
from __future__ import annotations

import argparse
import sys

import protocol as P
from device import Device
from emulator import DeviceEmulator


def _hexbytes(items):
    return bytes(int(x, 16) for x in items)


def cmd_build(a):
    frame = P.Frame(a.addr, a.func, _hexbytes(a.data))
    print(P.hexdump(frame.encode()))


def cmd_parse(a):
    raw = _hexbytes(a.bytes)
    try:
        f = P.Frame.decode(raw)
        print(f"OK: addr=0x{f.addr:02X} func=0x{f.func:02X} data={f.data.hex()}")
    except ValueError as e:
        print(f"ОШИБКА: {e}")
        sys.exit(1)


def _make_device(a):
    if a.emulate or not a.port:
        return Device(DeviceEmulator(address=a.addr), address=a.addr, verbose=True)
    from device import SerialTransport
    tr = SerialTransport(a.port, a.baud)
    return Device(tr, address=a.addr, verbose=True)


def cmd_read(a):
    dev = _make_device(a)
    r = dev.read_parameter(a.index, a.len)
    print("Ответ:", r if r else "нет ответа")


def cmd_write(a):
    dev = _make_device(a)
    r = dev.write_parameter(a.index, _hexbytes(a.data))
    print("Ответ:", r if r else "нет ответа")


def cmd_cal_read(a):
    dev = _make_device(a)
    r = dev.read_calibration(a.param)
    if r:
        val = r.data[2] | (r.data[3] << 8)
        print(f"Калибровка[{a.param}] = 0x{val:04X} ({val})")
    else:
        print("нет ответа")


def cmd_cal_write(a):
    dev = _make_device(a)
    r = dev.write_calibration(a.param, a.value)
    print("Ответ:", r if r else "нет ответа")


def main():
    p = argparse.ArgumentParser(description="Клиент протокола устройства MSP430F249")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="собрать кадр и вывести байты")
    b.add_argument("--addr", type=lambda x: int(x, 0), default=1)
    b.add_argument("--func", type=lambda x: int(x, 0), required=True)
    b.add_argument("--data", nargs="*", default=[])
    b.set_defaults(func_handler=cmd_build)

    pr = sub.add_parser("parse", help="разобрать кадр (hex-байты)")
    pr.add_argument("bytes", nargs="+")
    pr.set_defaults(func_handler=cmd_parse)

    common = dict()
    for name, handler in (("read", cmd_read), ("write", cmd_write),
                          ("cal-read", cmd_cal_read), ("cal-write", cmd_cal_write)):
        s = sub.add_parser(name)
        s.add_argument("--port", default=None)
        s.add_argument("--baud", type=int, default=9600)
        s.add_argument("--emulate", action="store_true")
        s.add_argument("--addr", type=lambda x: int(x, 0), default=1)
        if name in ("read", "write"):
            s.add_argument("--index", type=lambda x: int(x, 0), required=True)
        if name == "read":
            s.add_argument("--len", type=int, default=2)
        if name == "write":
            s.add_argument("--data", nargs="+", required=True)
        if name in ("cal-read", "cal-write"):
            s.add_argument("--param", type=lambda x: int(x, 0), required=True)
        if name == "cal-write":
            s.add_argument("--value", type=lambda x: int(x, 0), required=True)
        s.set_defaults(func_handler=handler)

    args = p.parse_args()
    args.func_handler(args)


if __name__ == "__main__":
    main()
