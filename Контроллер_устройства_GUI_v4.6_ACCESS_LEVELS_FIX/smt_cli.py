#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Командная утилита для реального прибора: serial, TCP и GSM/SMS."""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from decimal import Decimal, InvalidOperation

import smt_client as sc

HERE = os.path.dirname(os.path.abspath(__file__))
READING_COMMANDS = {"Volume", "VOLUME_GLOB", "VOLUME_COMMIS", "VOLUME_DISC"}


def load_catalog():
    with open(os.path.join(HERE, "smt_commands.json"), encoding="utf-8") as stream:
        return json.load(stream)["commands"]


def add_actions(parser):
    group = parser.add_argument_group("операция")
    group.add_argument("--get", metavar="NAME", help="прочитать параметр")
    group.add_argument("--send", metavar="COMMAND", help="отправить NAME, NAME=value или действие")
    group.add_argument("--passport", action="store_true", help="снять паспорт прибора")
    group.add_argument("--scan-all", metavar="FILE", help="READ-аудит каталога в JSON/CSV")
    group.add_argument("--raw-hex", metavar="HEX", help="передать точные байты (нужен --expert)")
    group.add_argument("--set-reading", metavar="VALUE",
                       help="записать показание при разрешении F1/F2 и проверить read-back")
    group.add_argument("--reading-command", choices=sorted(READING_COMMANDS), default="VOLUME_GLOB",
                       help="какой накопитель записать (по умолчанию VOLUME_GLOB)")
    group.add_argument("--auth-level", choices=["provider", "omega"],
                       help="предъявить пароль соответствующего уровня перед операцией")
    group.add_argument("--access-password", default=os.environ.get("SMT_ACCESS_PASSWORD", ""),
                       help="пароль выбранного уровня; предпочтительно через SMT_ACCESS_PASSWORD")
    group.add_argument("--provider-password", default=os.environ.get("SMT_PROVIDER_PASSWORD", ""),
                       help=argparse.SUPPRESS)
    group.add_argument("--no-readback", action="store_true",
                       help="после SET не выполнять проверочное чтение")
    group.add_argument("--expert", action="store_true", help="разрешить критические записи/действия")


def parser_build():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="transport", required=True)

    serial_p = sub.add_parser("serial", help="USB-оптопорт / последовательный порт")
    serial_p.add_argument("port")
    serial_p.add_argument("--baud", type=int, default=9600)
    serial_p.add_argument("--framing", choices=["auto", *sc.FRAMINGS], default="auto")
    serial_p.add_argument("--bytesize", type=int, choices=[5, 6, 7, 8], default=8)
    serial_p.add_argument("--parity", choices=["N", "E", "O", "M", "S"], default="N")
    serial_p.add_argument("--stopbits", type=float, choices=[1, 1.5, 2], default=1)
    serial_p.add_argument("--timeout", type=float, default=2.5)
    serial_p.add_argument("--idle-gap", type=float, default=0.25)
    serial_p.add_argument("--read-retries", type=int, default=1)
    serial_p.add_argument("--xonxoff", action="store_true")
    serial_p.add_argument("--rtscts", action="store_true")
    serial_p.add_argument("--dsrdtr", action="store_true")
    serial_p.add_argument("--dtr", action="store_true")
    serial_p.add_argument("--rts", action="store_true")
    add_actions(serial_p)

    tcp_p = sub.add_parser("tcp", help="реальный командный TCP-шлюз")
    tcp_p.add_argument("host")
    tcp_p.add_argument("port", type=int)
    tcp_p.add_argument("--timeout", type=float, default=3.0)
    tcp_p.add_argument("--idle-gap", type=float, default=0.25)
    tcp_p.add_argument("--terminator", choices=["none", "cr", "lf", "crlf"], default="crlf")
    add_actions(tcp_p)

    sms_p = sub.add_parser("sms", help="GSM-модем с AT-командами")
    sms_p.add_argument("modem_port")
    sms_p.add_argument("phone")
    sms_p.add_argument("--baud", type=int, default=115200)
    sms_p.add_argument("--prefix", default="")
    sms_p.add_argument("--timeout", type=float, default=20.0)
    sms_p.add_argument("--at", metavar="COMMAND", help="выполнить AT-команду модема")
    sms_p.add_argument("--inbox", action="store_true", help="прочитать непрочитанные SMS")
    sms_p.add_argument("--delete", action="store_true", help="удалить SMS после чтения")
    add_actions(sms_p)
    return parser


def open_transport(args):
    if args.transport == "serial":
        tr = sc.OpticTransport(
            args.port, args.baud, response_timeout=args.timeout, idle_gap=args.idle_gap,
            read_retries=args.read_retries, bytesize=args.bytesize, parity=args.parity,
            stopbits=args.stopbits, xonxoff=args.xonxoff, rtscts=args.rtscts,
            dsrdtr=args.dsrdtr, dtr=args.dtr, rts=args.rts,
        )
        if args.framing == "auto":
            frame, probe = tr.detect_framing("DevInfo")
        else:
            tr.set_framing(args.framing)
            probe = tr.probe("DevInfo")
            frame = args.framing
        print(f"Подключено: {tr.line_description()} · кадр {frame}")
        print(f"DevInfo = {sc.value_of(probe, name='DevInfo')!r}")
        return tr
    if args.transport == "tcp":
        terms = {"none": b"", "cr": b"\r", "lf": b"\n", "crlf": b"\r\n"}
        tr = sc.TcpServerTransport(args.host, args.port, timeout=args.timeout,
                                   idle_gap=args.idle_gap, terminator=terms[args.terminator])
        probe = tr.probe("DevInfo")
        print(f"Подключено: TCP {args.host}:{args.port}")
        print(f"DevInfo = {sc.value_of(probe, name='DevInfo')!r}")
        return tr
    tr = sc.SmsTransport(args.modem_port, args.phone, baud=args.baud,
                         response_timeout=args.timeout, prefix=args.prefix)
    health = tr.health_check()
    print(f"GSM-модем готов: {args.modem_port} · SMS → {args.phone}")
    print(sc.decode_response(health).strip())
    return tr


def write_scan(path, values):
    if path.lower().endswith(".csv"):
        with open(path, "w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["command", "value"])
            writer.writerows(values.items())
    else:
        with open(path, "w", encoding="utf-8") as stream:
            json.dump({"source": "physical", "values": values}, stream,
                      ensure_ascii=False, indent=2)



def parse_reading(value):
    text = str(value).strip().replace(",", ".")
    if not text:
        raise ValueError("показание не задано")
    try:
        result = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"некорректное показание: {value!r}") from exc
    if not result.is_finite():
        raise ValueError("показание должно быть конечным числом")
    return result


def catalog_item(name):
    return next((item for item in load_catalog() if item.get("name") == name), None)


def require_access(cli, args):
    if not args.expert:
        raise PermissionError("Операция с изменением требует --expert")
    level = args.auth_level or ("provider" if args.provider_password else None)
    password = args.access_password or args.provider_password
    if not level or not password:
        raise PermissionError(
            "Укажи --auth-level provider|omega и --access-password "
            "(или переменную SMT_ACCESS_PASSWORD)")
    command = sc.ACCESS_AUTH_COMMANDS[level]
    if args.transport == "sms":
        raw = cli.send(f"{command}={password}", expert=True, mutating=True)
        print(sc.decode_response(raw).strip() or repr(raw))
        print(f"Пароль {level} отправлен по SMS; активный уровень подтвердит только ответ прибора.")
        return {"level": level, "verified": False, "sms_sent": True}
    return sc.authenticate_access(cli, level, password)


def require_command_write_access(name, level):
    item = catalog_item(name)
    if item is None:
        raise KeyError(f"{name}: нет в каталоге")
    column = item.get("prov") if level == "provider" else item.get("user")
    if column != "0101":
        label = "F1/Provider" if level == "provider" else "F2/Omega"
        raise PermissionError(f"{name}: запись запрещена {label} ({column})")


def set_reading_authorized(cli, tr, args):
    del tr
    auth = require_access(cli, args)
    command = args.reading_command
    require_command_write_access(command, auth["level"])
    target = parse_reading(args.set_reading)
    target_text = format(target, "f")
    raw = cli.send(f"{command}={target_text}", expert=True, mutating=True)
    print(sc.decode_response(raw).strip() or repr(raw))
    if args.no_readback or args.transport == "sms":
        print(f"{command}={target_text}: команда отправлена без read-back")
        return
    after = cli.get(command)
    actual = parse_reading(after)
    tolerance = max(abs(target) * Decimal("0.000000001"), Decimal("0.000001"))
    if abs(actual - target) > tolerance:
        raise RuntimeError(f"read-back не совпал: ожидалось {target}, прибор вернул {actual}")
    print(f"{command}={after}: read-back подтверждён")


def main(argv=None):
    args = parser_build().parse_args(argv)
    tr = open_transport(args)
    cli = sc.SmtClient(tr)
    try:
        if args.transport == "sms" and args.at:
            print(sc.decode_response(tr.send_at(args.at)).strip())
        if args.transport == "sms" and args.inbox:
            for item in tr.receive_unread(delete=args.delete):
                print(f"#{item['index']} {item['header']}\n{item['text']}\n")
        if args.raw_hex:
            if not args.expert:
                raise PermissionError("--raw-hex требует --expert")
            raw_exchange = getattr(tr, "raw_exchange", None)
            if raw_exchange is None:
                raise RuntimeError("транспорт не поддерживает RAW HEX")
            data = bytes.fromhex(args.raw_hex.replace("0x", "").replace(",", " "))
            answer = raw_exchange(data)
            print(f">> {data.hex(' ').upper()}\n<< {answer.hex(' ').upper()}")
        if args.get:
            print(f"{args.get} = {cli.get(args.get)!r}")
        if args.set_reading is not None:
            set_reading_authorized(cli, tr, args)
        if args.send:
            name = sc.command_name(args.send)
            mutating = "=" in args.send or name in sc.IMPERATIVE_ACTIONS
            auth = None
            if args.auth_level or args.access_password or args.provider_password:
                auth = require_access(cli, args)
            if mutating and auth is not None:
                require_command_write_access(name, auth["level"])
            raw = cli.send(args.send, expert=args.expert, mutating=mutating)
            print(sc.decode_response(raw).strip() or repr(raw))
        if args.passport:
            if args.transport == "sms":
                raise RuntimeError("паспорт по SMS не запускается автоматически")
            for name, value in cli.get_all().items():
                print(f"{name:<24} = {value!r}")
        if args.scan_all:
            if args.transport == "sms":
                raise RuntimeError("полный аудит по SMS не запускается автоматически")
            catalog = load_catalog()
            actions = sc.IMPERATIVE_ACTIONS | {
                item["name"] for item in catalog if "действие" in (item.get("type") or "").lower()
            }
            values = {}
            for index, item in enumerate(catalog, 1):
                name = item["name"]
                if name in actions:
                    values[name] = "<action: skipped>"
                elif name in sc.SECRET_NAMES:
                    values[name] = "<secret: skipped>"
                else:
                    try:
                        values[name] = cli.get(name)
                    except Exception as exc:
                        values[name] = f"<err:{exc}>"
                print(f"[{index:03d}/{len(catalog)}] {name} = {values[name]!r}")
                time.sleep(0.015)
            write_scan(args.scan_all, values)
            print(f"Снимок сохранён: {args.scan_all}")
    finally:
        tr.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ОШИБКА: {exc}", file=sys.stderr)
        raise SystemExit(2)
