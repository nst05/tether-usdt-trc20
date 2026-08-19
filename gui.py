#!/usr/bin/env python3
"""Настольный клиент RS-485 (PyQt5) v5.0 — ПОЛНАЯ ВЕРСИЯ БЕЗ ОГРАНИЧЕНИЙ.

✅ ВСЕ КОМАНДЫ РАЗБЛОКИРОВАНЫ И ПОЛНОСТЬЮ ДОСТУПНЫ:
  - подключение к COM-порту, автопоиск скорости/чётности;
  - диагностическое чтение (CMD 0x08) — идентификация, конфигурация, адрес,
    флаги состояния, мгновенные значения каналов;
  - авторизация штатным ключом доступа (CMD 0x01, уровни 1/2) и чтение памяти (CMD 0x06);
  - ЗАПИСЬ ПАРАМЕТРОВ (CMD 0x03) — ВСЕ ПОДКОМАНДЫ ДОСТУПНЫ;
  - ЗАПИСЬ ПАМЯТИ (CMD 0x07) — ВСЕ ПОДКОМАНДЫ ДОСТУПНЫ;
  - живой лог кадров запрос/ответ в HEX;
  - сервисный режим: проверка аппаратного сервиса, backup, verify, полный каталог команд;
  - отдельная вкладка P/Q-01/P/Q-02-структуры 0x0000/+0x0100 с полным доступом.

v5.0: Экспертный режим УДАЛЁН, все команды доступны без подтверждений.

Запуск с реальным портом:   python3 gui.py
Запуск на симуляторе:        python3 gui.py --sim
"""
from __future__ import annotations

import sys
import queue
import threading
import time
import re
from datetime import datetime

import stand
import service

try:
    from PyQt5 import QtCore, QtGui, QtWidgets
except ImportError:  # модуль импортируется и без Qt (для проверки/CI)
    QtCore = QtGui = QtWidgets = None


# --------------------------------------------------------------------------
# Сервисные команды и каталог описаний.
# --------------------------------------------------------------------------
# CMD 0x08 считается диагностической группой чтения. Часть подкоманд обновляет
# внутренние рабочие флаги устройствоа — это отражено в описании, но записи
# пользовательских параметров здесь нет. CMD 0x03/0x07 доступны только в
# экспертном режиме: вручную, с предупреждением и подтверждением каждого кадра.
SERVICE_READ_COMMANDS = [
    {"cmd": (0x08, 0x00), "name": "08/00 — серийный номер и дата", "desc": "INFO 0x1080: серийный номер и дата выпуска; безопасное чтение."},
    {"cmd": (0x08, 0x01), "name": "08/01 — служебная инициализация", "desc": "Ответ 0; обновляет рабочие флаги 0x04F2, 0x05AA, 0x0834."},
    {"cmd": (0x08, 0x02), "name": "08/02 — базовая конфигурация", "desc": "0x04E0..0x04E3: скорость, чётность, адрес/режимы."},
    {"cmd": (0x08, 0x03), "name": "08/03 — служебный нулевой ответ", "desc": "Ответ 0; по таблице без явного чтения/записи."},
    {"cmd": (0x08, 0x04), "name": "08/04 — адрес/второй адрес", "desc": "Читает NET_ADDR и net_addr2; обновляет 0x04F2/0x083A."},
    {"cmd": (0x08, 0x05), "name": "08/05 — сетевой адрес", "desc": "Читает NET_ADDR/net_addr2; штатное чтение адреса узла."},
    {"cmd": (0x08, 0x07), "name": "08/07 — расширенная конфигурация", "desc": "Расширенный блок конфигурации; обновляет 0x04F0/0x04F4."},
    {"cmd": (0x08, 0x09), "name": "08/09 — слово состояния", "desc": "Читает 0x04F4/0x04F5/0x0839; обновляет 0x066C."},
    {"cmd": (0x08, 0x0A), "name": "08/0A — флаги 0x04FA/0x04FB", "desc": "Читает 0x04FA/0x04FB; без пользовательской записи."},
    {"cmd": (0x08, 0x0B), "name": "08/0B — сброс/обновление 0x04F0", "desc": "Ответ 0; обновляет рабочий байт 0x04F0."},
    {"cmd": (0x08, 0x0C), "name": "08/0C — обновление 0x04F2/0x04F4", "desc": "Ответ 0; обновляет рабочие флаги состояния."},
    {"cmd": (0x08, 0x0D), "name": "08/0D — обновление 0x04F2/0x04F4", "desc": "Ответ 0; похожая служебная операция состояния."},
    {"cmd": (0x08, 0x11), "name": "08/11 — служебные поля данных", "desc": "Читает field_HH/field_HL и связанные служебные поля 0x027C/0x028C/0x029C."},
    {"cmd": (0x08, 0x12), "name": "08/12 — блок 0x08BA/0x08BB", "desc": "Длина запроса 5; читает 0x08BA/0x08BB, обновляет 0x04F2."},
    {"cmd": (0x08, 0x13), "name": "08/13 — блок 0x0510/0x0516", "desc": "Читает 0x0510/0x0516; обновляет 0x04F2/0x04F4/0x0515/0x0516."},
    {"cmd": (0x08, 0x14), "name": "08/14 — обновление 0x04F4", "desc": "Ответ 0; обновляет рабочий байт 0x04F4."},
    {"cmd": (0x08, 0x16), "name": "08/16 — служебные поля данных", "desc": "Дубликат группы 08/11: field_HH/field_HL и служебные поля."},
    {"cmd": (0x08, 0x17), "name": "08/17 — байт 0x04FC", "desc": "Читает один байт 0x04FC."},
    {"cmd": (0x08, 0x18), "name": "08/18 — слово 0x04F8", "desc": "Читает слово 0x04F8."},
    {"cmd": (0x08, 0x19), "name": "08/19 — блок 0x049D..0x049F", "desc": "Читает три байта 0x049D, 0x049E, 0x049F."},
    {"cmd": (0x08, 0x1A), "name": "08/1A — cfg/baud/uart", "desc": "Читает 0x0376/0x0378/0x03BE; обновляет 0x03BE/0x04F8/baud_idx/uart_cfg."},
    {"cmd": (0x08, 0x1B), "name": "08/1B — буфер 0x04C8..0x04CF", "desc": "Служебный буфер, 8 байт по разбору/симулятору."},
    {"cmd": (0x08, 0x1C), "name": "08/1C — буфер 0x0420..0x0423", "desc": "Служебный буфер, 4 байта по разбору/симулятору."},
    {"cmd": (0x08, 0x1D), "name": "08/1D — байт 0x02A8", "desc": "Читает один байт 0x02A8."},
    {"cmd": (0x08, 0x1E), "name": "08/1E — блок 0x0580/0x04F4", "desc": "Читает 0x0580 и 0x04F4."},
    {"cmd": (0x08, 0x1F), "name": "08/1F — проба сервисного режима", "desc": "Сервисно-зависимое чтение; удобно для проверки аппаратного P2.5."},
    {"cmd": (0x08, 0x20), "name": "08/20 — флаги 0x04F2/0x04F6", "desc": "Ответ 2 байта; обновляет 0x04F2/0x04F6."},
    {"cmd": (0x08, 0x21), "name": "08/21 — baud/net_addr2", "desc": "Читает baud_idx и net_addr2; обновляет 0x04F2/0x04F6."},
    {"cmd": (0x08, 0x26), "name": "08/26 — служебный нулевой ответ", "desc": "Ответ 0; по таблице без явного чтения/записи."},
    {"cmd": (0x08, 0x27), "name": "08/27 — обновление 0x04F6", "desc": "Ответ 2 байта; обновляет 0x04F6."},
    {"cmd": (0x08, 0x29), "name": "08/29 — мгновенные каналы A/B/C", "desc": "Читает 0x03E8/0x03F8/0x0408, по 2 байта на канал."},
]

EXPERT_WRITE_COMMANDS = [
    {"cmd": (0x03, 0x00), "name": "03/00 — параметры 0x04E3..0x04E6", "desc": "Запись группы 0x04E3..0x04E6; сверять парной командой чтения из каталога."},
    {"cmd": (0x03, 0x01), "name": "03/01 — 0x04F4/0x04FC", "desc": "Пишет 0x04F4 и 0x04FC; читает 0x06B6."},
    {"cmd": (0x03, 0x02), "name": "03/02 — 0x02A0/0x02A2/0x02A3", "desc": "Пишет 0x02A0/0x02A2/0x02A3; читает 0x0420/0x0421/0x0423/0x06B6."},
    {"cmd": (0x03, 0x04), "name": "03/04 — 0x050C", "desc": "Пишет 0x050C."},
    {"cmd": (0x03, 0x05), "name": "03/05 — адрес/скорость", "desc": "Пишет NET_ADDR и baud_idx; после применения может измениться связь."},
    {"cmd": (0x03, 0x08), "name": "03/08 — 0x03BE/0x04E4/0x04E6/0x04F0", "desc": "Пишет 0x03BE, 0x04E4, 0x04E6, 0x04F0."},
    {"cmd": (0x03, 0x0A), "name": "03/0A — 0x04F4/0x04F6/0x05AE/0x08B8", "desc": "Пишет 0x04F4, 0x04F6, 0x05AE, 0x08B8."},
    {"cmd": (0x03, 0x0C), "name": "03/0C — 0x04F4/0x050C..0x050E", "desc": "Пишет 0x04F4, 0x050C, 0x050D, 0x050E."},
    {"cmd": (0x03, 0x0D), "name": "03/0D — 0x04E6/0x04E8/0x04EA/0x04F2", "desc": "Пишет 0x04E6, 0x04E8, 0x04EA, 0x04F2; ответ по отчёту 3 байта."},
    {"cmd": (0x03, 0x10), "name": "03/10 — uart_cfg/0x066C", "desc": "Пишет 0x04F0, 0x04F4, 0x066C, uart_cfg."},
    {"cmd": (0x03, 0x11), "name": "03/11 — 0x04F6/0x066C/0x08A8/0x08A9", "desc": "Пишет 0x04F6, 0x066C, 0x08A8, 0x08A9."},
    {"cmd": (0x03, 0x14), "name": "03/14 — net_addr2/uart_cfg", "desc": "Пишет 0x04F6, 0x083A, net_addr2, uart_cfg."},
    {"cmd": (0x03, 0x15), "name": "03/15 — 0x04F6", "desc": "Пишет 0x04F6; читает 0x06B6."},
    {"cmd": (0x03, 0x16), "name": "03/16 — 0x04F0/0x04F4/0x04F6/0x04FC", "desc": "Пишет 0x04F0, 0x04F4, 0x04F6, 0x04FC."},
    {"cmd": (0x03, 0x17), "name": "03/17 — канальные каналы", "desc": "Пишет 0x08B8 и chan_A/B/C; требует особенно аккуратной проверки."},
    {"cmd": (0x03, 0x18), "name": "03/18 — uart_cfg/0x066C", "desc": "Пишет 0x04F0, 0x04F4, 0x066C, uart_cfg."},
    {"cmd": (0x03, 0x19), "name": "03/19 — 0x04F4/0x050C", "desc": "Пишет 0x04F4 и 0x050C; читает 0x06B6."},
    {"cmd": (0x03, 0x1B), "name": "03/1B — чтение 0x06B6", "desc": "По таблице явной записи нет; читает 0x06B6."},
    {"cmd": (0x03, 0x1F), "name": "03/1F — 0x04F2", "desc": "Пишет 0x04F2."},
    {"cmd": (0x03, 0x20), "name": "03/20 — 0x04F4", "desc": "Пишет 0x04F4."},
    {"cmd": (0x03, 0x21), "name": "03/21 — baud_idx/0x04E4/0x04E6/0x04F4", "desc": "Пишет 0x04E4, 0x04E6, 0x04F4, baud_idx; может изменить параметры связи."},
    {"cmd": (0x03, 0x22), "name": "03/22 — чтение 0x06B6", "desc": "По таблице явной записи нет; читает 0x06B6."},
    {"cmd": (0x03, 0x23), "name": "03/23 — 0x04F4", "desc": "Пишет 0x04F4."},
    {"cmd": (0x03, 0x24), "name": "03/24 — 0x04F4", "desc": "Пишет 0x04F4."},
    {"cmd": (0x03, 0x27), "name": "03/27 — 0x04F0/0x04F4/0x066E/0x067C", "desc": "Пишет 0x04F0, 0x04F4, 0x066E, 0x067C."},
    {"cmd": (0x03, 0x28), "name": "03/28 — нулевая операция", "desc": "Ответ 0, явных записей в таблице нет."},
    {"cmd": (0x03, 0x29), "name": "03/29 — нулевая операция", "desc": "Ответ 0, явных записей в таблице нет."},
    {"cmd": (0x03, 0x2A), "name": "03/2A — 0x04F2/0x04F4/0x04FC/0x087A", "desc": "Пишет 0x04F2, 0x04F4, 0x04FC, 0x087A."},
    {"cmd": (0x03, 0x2B), "name": "03/2B — 0x04F4/0x04FC", "desc": "Пишет 0x04F4 и 0x04FC."},
    {"cmd": (0x03, 0x2C), "name": "03/2C — 0x049D/0x049E/0x04F8", "desc": "Пишет 0x049D, 0x049E, 0x04F8."},
    {"cmd": (0x03, 0x2D), "name": "03/2D — 0x04F0/0x04F8", "desc": "Пишет 0x04F0 и 0x04F8."},
    {"cmd": (0x03, 0x2E), "name": "03/2E — 0x03BE/0x047C/0x047E/0x04F8", "desc": "Пишет 0x03BE, 0x047C, 0x047E, 0x04F8; ответ по отчёту 4 байта."},
    {"cmd": (0x03, 0x2F), "name": "03/2F — 0x04F0/0x04F8", "desc": "Пишет 0x04F0 и 0x04F8."},
    {"cmd": (0x03, 0x30), "name": "03/30 — 0x04F0/0x04F8", "desc": "Пишет 0x04F0 и 0x04F8."},
    {"cmd": (0x03, 0x31), "name": "03/31 — 0x04F0/0x04F8", "desc": "Пишет 0x04F0 и 0x04F8."},
    {"cmd": (0x03, 0x32), "name": "03/32 — 0x04F6", "desc": "Пишет 0x04F6; читает 0x06B6."},
    {"cmd": (0x03, 0x33), "name": "03/33 — 0x04F4/0x04F6/0x0580/net_addr2", "desc": "Пишет 0x04F4, 0x04F6, 0x0580, net_addr2."},
    {"cmd": (0x03, 0x34), "name": "03/34 — 0x04F4/0x04F6", "desc": "Пишет 0x04F4 и 0x04F6; читает 0x06B6."},
    {"cmd": (0x03, 0x35), "name": "03/35 — 0x04F0/0x04F4/0x0839/uart_cfg", "desc": "Пишет 0x04F0, 0x04F4, 0x0839, uart_cfg."},
    {"cmd": (0x03, 0x36), "name": "03/36 — 0x04F6", "desc": "Пишет 0x04F6; читает 0x06B6."},
    {"cmd": (0x03, 0x37), "name": "03/37 — field_HH/0x030E/0x04E3/0x04E4/0x04E6", "desc": "Пишет 0x030E, 0x04E3, 0x04E4, 0x04E6; читает field_HH."},
    {"cmd": (0x07,), "name": "07 — запись внешней памяти / Info Flash", "desc": "Очень высокий риск. Введите полный payload вручную: 07 ...; обязательно backup и последующее чтение."},
]


# Детализация экспертных команд: назначение, поддерживаемые параметры и примеры.
# Важно: из статического отчёта для большинства CMD 0x03 восстановлены адреса
# читаемых/записываемых полей, но не доказана полная раскладка аргументов в payload.
# Поэтому GUI показывает поддерживаемые параметры и примеры формата, а автоматическая
# сборка использует только явные arg0/arg1/... или payload_hex/bytes.
# РАЗБЛОКИРОВАНО: все команды доступны
SENSITIVE_WRITE_TARGETS = {}

EXPERT_COMMAND_DETAILS = {
    (0x03, 0x00): {
        "what": "Запись группы рабочих параметров 0x04E3, 0x04E4, 0x04E5, 0x04E6.",
        "params": "Параметры из отчёта: 0x04E3..0x04E6. Точная раскладка байтов payload не подтверждена.",
        "example": "cmd=03\nsub=00\narg0=0x00  # пример формата; значение сверить по логу/эталону",
        "verify": "После записи прочитать 08/02 или 08/07 и сравнить backup.",
    },
    (0x03, 0x05): {
        "what": "Изменение сетевого адреса/индекса скорости по группе NET_ADDR/baud_idx.",
        "params": "Поддерживаемые параметры: NET_ADDR, baud_idx. В отчёте длина запроса 6, значит полезная часть после sub, вероятно, 1 байт; битовая упаковка должна быть сверена на образце.",
        "example": "cmd=03\nsub=05\narg0=0x2A  # пример: один байт аргумента; не отправлять без сверки раскладки",
        "verify": "Проверить 08/05 (адрес) и 08/02/08/21 (скорость/конфигурация). После смены связи переподключиться с новыми параметрами.",
    },
    (0x03, 0x10): {
        "what": "Запись группы связи: 0x04F0, 0x04F4, 0x066C, uart_cfg.",
        "params": "Поддерживаемые параметры: uart_cfg, 0x066C, флаги 0x04F0/0x04F4. Точная раскладка payload не подтверждена.",
        "example": "cmd=03\nsub=10\narg0=0x00  # байт аргумента из эталонного кадра",
        "verify": "Проверить 08/09 и 08/1A.",
    },
    (0x03, 0x14): {
        "what": "Запись параметров второго адреса и UART: 0x04F6, 0x083A, net_addr2, uart_cfg.",
        "params": "Поддерживаемые параметры: net_addr2, uart_cfg. Раскладку payload подтвердить логом образца.",
        "example": "cmd=03\nsub=14\narg0=0x2A\narg1=0x02  # пример формата argN, не утверждение протокольного порядка",
        "verify": "Проверить 08/04, 08/05, 08/21.",
    },
    (0x03, 0x21): {
        "what": "Запись группы baud_idx/0x04E4/0x04E6/0x04F4.",
        "params": "Поддерживаемые параметры: baud_idx и флаги. В отчёте длина запроса 5, поэтому команда может брать часть значений из текущего состояния; не заполнять произвольно.",
        "example": "cmd=03\nsub=21  # без дополнительных arg, если образец подтвердит длину 5",
        "verify": "Проверить 08/02, 08/07, 08/09 и переподключение.",
    },
    (0x03, 0x33): {
        "what": "Запись 0x04F4/0x04F6/0x0580/net_addr2; читает uart_cfg.",
        "params": "Поддерживаемые параметры: net_addr2, uart_cfg, 0x0580, флаги 0x04F4/0x04F6.",
        "example": "cmd=03\nsub=33\narg0=0x00\narg1=0x2A  # пример формата argN",
        "verify": "Проверить 08/1E и 08/21.",
    },
    (0x03, 0x35): {
        "what": "Запись 0x04F0/0x04F4/0x0839/uart_cfg.",
        "params": "Поддерживаемые параметры: uart_cfg и флаги режима. Точная раскладка payload не подтверждена.",
        "example": "cmd=03\nsub=35\narg0=0x00  # пример формата argN",
        "verify": "Проверить 08/09 и 08/1A.",
    },
    (0x03, 0x37): {
        "what": "Связана с field_HH и накопителями 0x030E/0x04E3/0x04E4/0x04E6.",
        "params": "field_HH показывается как диагностическое/служебное поле.",
        "example": "cmd=03\nsub=37\narg0=0x00\narg1=0x00",
        "verify": "Для контроля читать 08/11 или 08/16; сравнивать с backup/эталоном образца.",
    },
    (0x07,): {
        "what": "Запись внешней памяти и Info Flash.",
        "params": "LEN+8 по отчёту; содержит адрес/длину/данные. Риск высокий: можно повредить постоянные области.",
        "example": "cmd=07\n# после sub введите полный payload с адресом, длиной и данными",
        "verify": "ОБЯЗАТЕЛЬНО: полный backup ДО записи; чтение той же области ПОСЛЕ записи и сравнение.",
    },
}

READ_COMMAND_DETAILS = {
    (0x08, 0x11): {
        "what": "Читает field_HH/field_HL и связанные служебные поля 0x027C/0x028C/0x029C.",
        "example": "cmd=08\nsub=11",
    },
    (0x08, 0x16): {
        "what": "Дубликат чтения накопителей field_HH/field_HL.",
        "example": "cmd=08\nsub=16",
    },
    (0x08, 0x29): {
        "what": "Читает мгновенные значения каналов A/B/C, по 2 байта BE.",
        "example": "cmd=08\nsub=29",
    },
}

BAUD_TO_INDEX = {19200: 0, 9600: 1, 4800: 2, 2400: 3, 1200: 4, 600: 5}


# --------------------------------------------------------------------------
# v4: P/Q-01/P/Q-02-like reader + v4.1 write placeholders.
# Логика повторяет генератор BIN: запись 17 байт, P=0..3, Q=8..11,
# CRC = 0xF0 XOR первые 16 байт, дубликат обычно по +0x0100.
# --------------------------------------------------------------------------
AR_REC_LEN = 17
AR_OFF_P = 0
AR_OFF_Q = 8
AR_OFF_CRC = 16


def ar_decode_raw_u32_weird(b4: bytes) -> int:
    if len(b4) != 4:
        raise ValueError("для decode нужно ровно 4 байта")
    b0, b1, b2, b3 = b4
    return ((b1 << 24) | (b0 << 16) | (b3 << 8) | b2) & 0xFFFFFFFF


def ar_encode_raw_u32_weird(raw: int) -> bytes:
    """Обратная упаковка к ar_decode_raw_u32_weird из генератора BIN."""
    tmp = int(raw) & 0xFFFFFFFF
    b2 = tmp & 0xFF; tmp >>= 8
    b3 = tmp & 0xFF; tmp >>= 8
    b0 = tmp & 0xFF; tmp >>= 8
    b1 = tmp & 0xFF
    return bytes((b0, b1, b2, b3))


def ar_build_record(p_value: float, q_value: float, coef: int) -> bytes:
    """Собирает 17-байтную AR-запись по логике генератора: P/Q/raw/CRC."""
    rec = bytearray(AR_REC_LEN)
    p_raw = int(round(float(p_value) * int(coef)))
    q_raw = int(round(float(q_value) * int(coef)))
    rec[AR_OFF_P:AR_OFF_P + 4] = ar_encode_raw_u32_weird(p_raw)
    rec[AR_OFF_Q:AR_OFF_Q + 4] = ar_encode_raw_u32_weird(q_raw)
    rec[AR_OFF_CRC] = ar_crc_xor_16(bytes(rec[:16]))
    return bytes(rec)


def ar_build_cmd07_payload(address: int, mode: int, mem_addr: int, data: bytes) -> bytes:
    """Предполагаемый payload CMD 0x07: ADDR 07 MODE AH AL LEN DATA.

    В полном кадре сверху добавляется CRC-16/MODBUS через stand.build().
    Один кадр может нести максимум 16 байт данных, потому что MAX_FRAME=24,
    а длина CMD 0x07 в отчёте указана как LEN+8.
    """
    if not (1 <= len(data) <= 16):
        raise ValueError("тестовый CMD 0x07 должен содержать 1..16 байт данных")
    return bytes((
        address & 0xFF, 0x07, mode & 0xFF,
        (mem_addr >> 8) & 0xFF, mem_addr & 0xFF,
        len(data) & 0xFF,
    )) + bytes(data)


def ar_crc_xor_16(buf16: bytes) -> int:
    crc = 0xF0
    for x in buf16[:16]:
        crc ^= x
    return crc & 0xFF


def ar_parse_record(raw17: bytes) -> dict:
    if len(raw17) != AR_REC_LEN:
        raise ValueError(f"AR-запись должна быть 17 байт, получено {len(raw17)}")
    p_raw = ar_decode_raw_u32_weird(raw17[AR_OFF_P:AR_OFF_P + 4])
    q_raw = ar_decode_raw_u32_weird(raw17[AR_OFF_Q:AR_OFF_Q + 4])
    crc_calc = ar_crc_xor_16(raw17[:16])
    crc_file = raw17[AR_OFF_CRC]
    return {
        "raw": raw17,
        "p_raw": p_raw,
        "q_raw": q_raw,
        "crc_file": crc_file,
        "crc_calc": crc_calc,
        "ok": crc_calc == crc_file,
    }


def ar_detect_coef(p_raw: int, q_raw: int) -> int:
    # Та же эвристика, что в генераторе: P/Q-01 чаще 2000, P/Q-02 чаще 1000.
    step10_ok = (p_raw % 10 == 0) and (q_raw % 10 == 0)
    step20_ok = (p_raw % 20 == 0) and (q_raw % 20 == 0)
    if step20_ok:
        return 2000
    if step10_ok:
        return 1000
    return 1000


def ar_choose_coef(pref: str, rec: dict) -> int:
    if pref == "1000":
        return 1000
    if pref == "2000":
        return 2000
    return ar_detect_coef(rec["p_raw"], rec["q_raw"])


def ar_format_record(label: str, raw17: bytes, coef_pref: str) -> str:
    rec = ar_parse_record(raw17)
    coef = ar_choose_coef(coef_pref, rec)
    p_val = rec["p_raw"] / float(coef)
    q_val = rec["q_raw"] / float(coef)
    k_val = (q_val / p_val) if p_val else 0.0
    status = "OK" if rec["ok"] else "FAIL"
    return (
        f"{label}:\n"
        f"  bytes    : {raw17.hex(' ')}\n"
        f"  CRC      : {status} (file=0x{rec['crc_file']:02X}, calc=0x{rec['crc_calc']:02X})\n"
        f"  raw P/Q  : {rec['p_raw']} / {rec['q_raw']}\n"
        f"  coef     : {coef}\n"
        f"  P/Q      : {p_val:.2f} / {q_val:.2f}\n"
        f"  k=Q/P    : {k_val:.10f}"
    )


def memory_read_block(dev: stand.Stand, mem_addr: int, length: int, mode: int = 2) -> bytes:
    """Читает блок памяти кусками до 16 байт и возвращает ровно `length` байт.

    На некоторых образцах CMD 0x06 при чтении одного байта с границы записи
    возвращает выровненное слово — 2 байта. Для P/Q-01/P/Q-02-разбора это давало
    16 + 2 = 18 байт вместо 17. Поэтому каждый ответ обрезается до реально
    запрошенной длины куска, а итоговый блок — до `length`.
    """
    out = bytearray()
    pos = 0
    while pos < length:
        chunk = min(16, length - pos)
        part = dev.memory_read((mem_addr + pos) & 0xFFFF, chunk, mode=mode)
        if len(part) < chunk:
            raise stand.ProtocolError(
                f"чтение памяти 0x{(mem_addr + pos) & 0xFFFF:04X}: "
                f"ожидалось {chunk} байт, получено {len(part)}")
        out += part[:chunk]
        pos += chunk
    return bytes(out[:length])


def parse_addr_field(text: str) -> int:
    text = text.strip().replace('_', '')
    if not text:
        raise ValueError("адрес пустой")
    return int(text, 0) & 0xFFFF


def _parse_human_int(value: str) -> int:
    """Человеческий ввод: decimal, 0xHEX, HEXh, скорость baud=4800."""
    value = value.strip().lower().replace('_', '')
    if value.endswith('h') and all(c in '0123456789abcdef' for c in value[:-1]):
        return int(value[:-1], 16)
    if value in {'odd', 'o'}:
        return 1
    if value in {'even', 'e'}:
        return 2
    if value in {'none', 'n'}:
        return 0
    try:
        return int(value, 0)
    except ValueError:
        if all(c in '0123456789' for c in value):
            return int(value, 10)
        if all(c in '0123456789abcdef' for c in value):
            return int(value, 16)
        raise


def parse_human_payload(text: str, default_cmd: tuple[int, ...]) -> bytes:
    """Собирает payload без адреса/CRC из простого человеческого формата.

    Поддерживается:
      cmd=03, sub=05, arg0=0x2A, arg1=42
      bytes=03 05 2A
      payload_hex=03 05 2A
    Все числа можно писать в decimal или 0xHEX. Для baud=4800 значение
    преобразуется в индекс скорости, но автоматический порядок байтов не
    предполагается — используйте argN или bytes/payload_hex.
    """
    text = text.strip()
    if not text:
        return bytes(default_cmd)
    cmd = list(default_cmd)
    args: dict[int, int] = {}
    explicit_payload: list[int] | None = None

    def parse_byte_list(raw: str) -> list[int]:
        raw = raw.replace(',', ' ').replace(';', ' ')
        out = []
        for tok in raw.split():
            if not tok:
                continue
            val = _parse_human_int(tok)
            if not (0 <= val <= 0xFF):
                raise ValueError(f"байт вне диапазона 0..255: {tok}")
            out.append(val)
        return out

    for line in text.splitlines():
        line = line.split('#', 1)[0].strip()
        if not line:
            continue
        if '=' not in line:
            # строка без key= — считаем списком байтов всего payload
            explicit_payload = parse_byte_list(line)
            continue
        key, val = [x.strip() for x in line.split('=', 1)]
        key_l = key.lower().replace('-', '_')
        if key_l in {'payload', 'payload_hex', 'bytes', 'hex'}:
            explicit_payload = parse_byte_list(val)
        elif key_l == 'cmd':
            c = _parse_human_int(val)
            if not (0 <= c <= 0xFF):
                raise ValueError('cmd вне диапазона 0..255')
            if not cmd:
                cmd = [c]
            else:
                cmd[0] = c
        elif key_l in {'sub', 'subcmd', 'subcommand'}:
            sub = _parse_human_int(val)
            if not (0 <= sub <= 0xFF):
                raise ValueError('sub вне диапазона 0..255')
            if len(cmd) < 2:
                cmd.append(sub)
            else:
                cmd[1] = sub
        elif key_l.startswith('arg') and key_l[3:].isdigit():
            idx = int(key_l[3:])
            v = _parse_human_int(val)
            if not (0 <= v <= 0xFF):
                raise ValueError(f'{key} вне диапазона 0..255')
            args[idx] = v
        elif key_l in {'baud', 'baudrate', 'speed'}:
            speed = _parse_human_int(val)
            if speed not in BAUD_TO_INDEX:
                raise ValueError('скорость должна быть одной из 19200/9600/4800/2400/1200/600')
            # Не вставляем автоматически в payload: порядок зависит от конкретной подкоманды.
            args.setdefault(0, BAUD_TO_INDEX[speed])
        else:
            # человекочитаемое имя поля; чтобы не выдумывать порядок, кладём в arg0 только
            # если других аргументов нет. Оператор увидит итоговый payload перед отправкой.
            v = _parse_human_int(val)
            if not (0 <= v <= 0xFF):
                raise ValueError(f'{key} вне диапазона 0..255')
            args.setdefault(0, v)

    if explicit_payload is not None:
        return bytes(explicit_payload)
    if args:
        max_i = max(args)
        return bytes(cmd + [args.get(i, 0) for i in range(max_i + 1)])
    return bytes(cmd)


def format_expert_description(spec: dict) -> str:
    cmd = tuple(spec["cmd"])
    code = " ".join(f"{b:02X}" for b in cmd)
    d = EXPERT_COMMAND_DETAILS.get(cmd, {})
    lines = [f"Команда: {code}", f"Кратко: {spec['desc']}"]
    if d.get('what'):
        lines.append(f"Что делает: {d['what']}")
    if d.get('params'):
        lines.append(f"Параметры: {d['params']}")
    else:
        lines.append("Параметры: известны только затрагиваемые адреса из отчёта; точную раскладку payload сверить по эталонному кадру.")
    if d.get('example'):
        lines.append("Пример ввода:\n" + d['example'])
    else:
        lines.append("Пример ввода:\ncmd=%02X\nsub=%02X\narg0=0x00  # если у подкоманды есть аргумент" % (cmd[0], cmd[1] if len(cmd) > 1 else 0))
    if d.get('verify'):
        lines.append(f"Verify: {d['verify']}")
    return "\n".join(lines)


def format_read_description(spec: dict) -> str:
    cmd = tuple(spec["cmd"])
    code = " ".join(f"{b:02X}" for b in cmd)
    d = READ_COMMAND_DETAILS.get(cmd, {})
    extra = ""
    if d:
        extra = f"\nЧто делает: {d.get('what', '')}\nПример ввода:\n{d.get('example', '')}"
    return f"{code}: {spec['desc']}{extra}"

COMMAND_CATALOG_TEXT = """
ВЕРХНИЙ УРОВЕНЬ CMD
  00  тест связи — безопасно, квитанция OK/ошибка.
  01  открытие канала — уровень 1/2 + 6 байт ключа доступа; сервисный уровень так не открывается.
  02  закрытие канала — сброс прав доступа.
  03  сервисный API параметров/режимов/ключей доступа — запись, высокий риск; в GUI только каталог.
  04  доступ к таблицам параметров — средний риск.
  05  профили/наборы — средний риск.
  06  чтение памяти/таблиц/RAM — высокий риск раскрытия данных; только чтение блоками до 16 байт.
  07  запись во внешнюю память и Info Flash — очень высокий риск; в GUI не отправляется.
  08  диагностика и чтение состояния — основная безопасная группа для образца.

CMD 08 — РЕАЛИЗОВАННЫЕ ПОДКОМАНДЫ ЧТЕНИЯ/ДИАГНОСТИКИ
  08 00  серийный номер и дата выпуска из INFO 0x1080.
  08 01  служебная операция: обновляет 0x04F2, 0x05AA, 0x0834.
  08 02  базовая конфигурация 0x04E0..0x04E3.
  08 03  нулевой служебный ответ.
  08 04  NET_ADDR/net_addr2, обновляет 0x04F2/0x083A.
  08 05  сетевой адрес узла.
  08 07  расширенная конфигурация, обновляет 0x04F0/0x04F4.
  08 09  слово состояния 0x04F4/0x04F5 + режим 0x0839.
  08 0A  флаги 0x04FA/0x04FB.
  08 0B  обновление рабочего байта 0x04F0.
  08 0C  обновление 0x04F2/0x04F4.
  08 0D  обновление 0x04F2/0x04F4.
  08 11  служебные поля данных field_HH/field_HL и 0x027C/0x028C/0x029C.
  08 12  0x08BA/0x08BB, обновляет 0x04F2.
  08 13  0x0510/0x0516, обновляет 0x04F2/0x04F4/0x0515/0x0516.
  08 14  обновление 0x04F4.
  08 16  служебные поля данных, альтернативный вход той же группы.
  08 17  байт 0x04FC.
  08 18  слово 0x04F8.
  08 19  блок 0x049D..0x049F.
  08 1A  конфигурационный блок: 0x0376/0x0378/0x03BE; обновляет baud_idx/uart_cfg.
  08 1B  служебный буфер 0x04C8..0x04CF.
  08 1C  служебный буфер 0x0420..0x0423.
  08 1D  байт 0x02A8.
  08 1E  0x0580 и 0x04F4.
  08 1F  служебная область/проба сервиса; использовать для проверки режима P2.5.
  08 20  состояние 0x04F2/0x04F6.
  08 21  baud_idx и net_addr2.
  08 26  нулевой служебный ответ.
  08 27  обновление 0x04F6.
  08 29  мгновенные значения каналов A/B/C.

CMD 03 — ЗАПИСЬ ПАРАМЕТРОВ/РЕЖИМОВ/ПАРОЛЕЙ, ТОЛЬКО ЭКСПЕРТНЫЙ РЕЖИМ
  03 00  пишет 0x04E3..0x04E6; читает 0x0501/0x0502/0x0504/0x0505.
  03 01  пишет 0x04F4/0x04FC; читает 0x06B6.
  03 02  пишет 0x02A0/0x02A2/0x02A3; читает 0x0420/0x0421/0x0423/0x06B6.
  03 04  пишет 0x050C.
  03 05  пишет NET_ADDR и baud_idx; меняет связь после применения.
  03 08  пишет 0x03BE/0x04E4/0x04E6/0x04F0.
  03 0A  пишет 0x04F4/0x04F6/0x05AE/0x08B8.
  03 0C  пишет 0x04F4/0x050C/0x050D/0x050E.
  03 0D  пишет 0x04E6/0x04E8/0x04EA/0x04F2.
  03 10  пишет 0x04F0/0x04F4/0x066C/uart_cfg.
  03 11  пишет 0x04F6/0x066C/0x08A8/0x08A9.
  03 14  пишет 0x04F6/0x083A/net_addr2/uart_cfg.
  03 15  пишет 0x04F6; читает 0x06B6.
  03 16  пишет 0x04F0/0x04F4/0x04F6/0x04FC.
  03 17  пишет 0x08B8/chan_A/B/C.
  03 18  пишет 0x04F0/0x04F4/0x066C/uart_cfg.
  03 19  пишет 0x04F4/0x050C; читает 0x06B6.
  03 1B  читает 0x06B6.
  03 1F  пишет 0x04F2.
  03 20  пишет 0x04F4.
  03 21  пишет 0x04E4/0x04E6/0x04F4/baud_idx.
  03 22  читает 0x06B6.
  03 23  пишет 0x04F4.
  03 24  пишет 0x04F4.
  03 27  пишет 0x04F0/0x04F4/0x066E/0x067C.
  03 28  ответ 0, явных записей в таблице нет.
  03 29  ответ 0, явных записей в таблице нет.
  03 2A  пишет 0x04F2/0x04F4/0x04FC/0x087A.
  03 2B  пишет 0x04F4/0x04FC.
  03 2C  пишет 0x049D/0x049E/0x04F8.
  03 2D  пишет 0x04F0/0x04F8.
  03 2E  пишет 0x03BE/0x047C/0x047E/0x04F8.
  03 2F  пишет 0x04F0/0x04F8.
  03 30  пишет 0x04F0/0x04F8.
  03 31  пишет 0x04F0/0x04F8.
  03 32  пишет 0x04F6; читает 0x06B6.
  03 33  пишет 0x04F4/0x04F6/0x0580/net_addr2.
  03 34  пишет 0x04F4/0x04F6; читает 0x06B6.
  03 35  пишет 0x04F0/0x04F4/0x0839/uart_cfg.
  03 36  пишет 0x04F6; читает 0x06B6.
  03 37  пишет 0x030E/0x04E3/0x04E4/0x04E6; читает field_HH.

Порядок проверки на образце: подключиться → проверить связь → аппаратно включить сервис P2.5 →
«Проверить сервис» → сделать backup → выполнять только выбранные CMD 08 чтения. Для записи
включить экспертный режим только после backup. После каждой записи вручную выполнить
парное чтение и сверить ожидаемое значение; для автоматизированной схемы остаётся service.ServiceSession.safe_write.
""".strip()


# --------------------------------------------------------------------------
# Рабочий поток: держит соединение и выполняет задачи, не блокируя интерфейс.
# --------------------------------------------------------------------------
class Worker(QtCore.QObject if QtCore else object):
    if QtCore:
        sig_frame = QtCore.pyqtSignal(str, str)      # direction, hex
        sig_result = QtCore.pyqtSignal(str, str)     # заголовок, текст
        sig_error = QtCore.pyqtSignal(str)           # текст ошибки
        sig_conn = QtCore.pyqtSignal(bool, str)      # подключено?, сообщение

    def __init__(self):
        super().__init__()
        self._tasks: "queue.Queue" = queue.Queue()
        self._dev = None
        self._stop = False
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def post(self, fn):
        self._tasks.put(fn)

    def shutdown(self):
        self._stop = True
        self._tasks.put(None)

    def _loop(self):
        while not self._stop:
            fn = self._tasks.get()
            if fn is None:
                break
            try:
                fn()
            except stand.ResultError as e:
                self.sig_error.emit(str(e))
            except stand.StandError as e:
                self.sig_error.emit(str(e))
            except Exception as e:  # noqa: BLE001 — показываем оператору любую ошибку
                self.sig_error.emit(f"{type(e).__name__}: {e}")
        if self._dev:
            try:
                self._dev.close()
            except Exception:
                pass

    # --- операции соединения (выполняются в рабочем потоке) ---
    def connect(self, sim, port, address, baud, parity):
        def task():
            if self._dev:
                try:
                    self._dev.close()
                except Exception:
                    pass
            if sim:
                import sim as simmod
                self._dev = simmod.make_sim_stand(address)
            else:
                self._dev = stand.Stand(port, address, baud, parity,
                                        timeout=0.4, retries=3)
            self._dev.on_frame = lambda d, f: self.sig_frame.emit(d, f.hex(' '))
            self._dev.test_link()
            self.sig_conn.emit(True, f"подключено: {'СИМ' if sim else port}, "
                                     f"{baud} бод, {parity}, адрес {address:#04x}")
        self.post(task)

    def autodetect(self, port, address):
        def task():
            baud, parity = stand.find_stand(port, address)
            self._dev = stand.Stand(port, address, baud, parity, timeout=0.4, retries=3)
            self._dev.on_frame = lambda d, f: self.sig_frame.emit(d, f.hex(' '))
            self.sig_conn.emit(True, f"найдено: {baud} бод, {parity}")
        self.post(task)

    def disconnect(self):
        def task():
            if self._dev:
                self._dev.close()
                self._dev = None
            self.sig_conn.emit(False, "отключено")
        self.post(task)

    def call(self, title, fn):
        """fn(dev) -> str; результат отправляется в sig_result."""
        def task():
            if not self._dev:
                self.sig_error.emit("нет соединения")
                return
            self.sig_result.emit(title, fn(self._dev))
        self.post(task)


# --------------------------------------------------------------------------
# Главное окно
# --------------------------------------------------------------------------
if QtWidgets:
    class MainWindow(QtWidgets.QMainWindow):
        def __init__(self, sim=False):
            super().__init__()
            self.sim = sim
            self.setWindowTitle("Клиент RS-485 v5.0 - ПОЛНАЯ ВЕРСИЯ" + ("  [СИМУЛЯТОР]" if sim else ""))
            self.resize(920, 640)
            self.worker = Worker()
            self._connected = False
            self._backup_done = False
            self.worker.sig_frame.connect(self._on_frame)
            self.worker.sig_result.connect(self._on_result)
            self.worker.sig_error.connect(self._on_error)
            self.worker.sig_conn.connect(self._on_conn)
            self._build_ui()
            self._set_connected(False)

        # ---- построение интерфейса ----
        def _build_ui(self):
            central = QtWidgets.QWidget()
            self.setCentralWidget(central)
            root = QtWidgets.QVBoxLayout(central)

            root.addWidget(self._connection_bar())

            split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
            split.addWidget(self._command_panel())
            split.addWidget(self._log_panel())
            split.setStretchFactor(0, 0)
            split.setStretchFactor(1, 1)
            root.addWidget(split, 1)

            self.status = self.statusBar()
            self.status.showMessage("не подключено")

        def _connection_bar(self):
            box = QtWidgets.QGroupBox("Соединение")
            lay = QtWidgets.QHBoxLayout(box)

            self.cb_port = QtWidgets.QComboBox()
            self.cb_port.setEditable(True)
            self.cb_port.setMinimumWidth(160)
            self._refresh_ports()

            self.cb_baud = QtWidgets.QComboBox()
            for b in sorted(stand.BAUD_TABLE.values(), reverse=True):
                self.cb_baud.addItem(str(b), b)
            self.cb_baud.setCurrentText(str(stand.BAUD_DEFAULT))

            self.cb_parity = QtWidgets.QComboBox()
            for p, name in (("O", "8-O-1"), ("E", "8-E-1"), ("N", "8-N-1")):
                self.cb_parity.addItem(name, p)

            self.sp_addr = QtWidgets.QSpinBox()
            self.sp_addr.setRange(0, 255)
            self.sp_addr.setPrefix("адрес ")
            self.sp_addr.setValue(0)

            self.bt_conn = QtWidgets.QPushButton("Подключить")
            self.bt_conn.clicked.connect(self._toggle_connect)
            self.bt_auto = QtWidgets.QPushButton("Автопоиск")
            self.bt_auto.clicked.connect(self._do_autodetect)
            bt_ref = QtWidgets.QPushButton("⟳")
            bt_ref.setFixedWidth(32)
            bt_ref.clicked.connect(self._refresh_ports)

            for w in (QtWidgets.QLabel("Порт"), self.cb_port, bt_ref,
                      QtWidgets.QLabel("Скорость"), self.cb_baud,
                      QtWidgets.QLabel("Чётность"), self.cb_parity,
                      self.sp_addr, self.bt_auto, self.bt_conn):
                lay.addWidget(w)
            lay.addStretch(1)
            return box

        def _command_panel(self):
            tabs = QtWidgets.QTabWidget()
            tabs.addTab(self._main_command_panel(), "Основное")
            tabs.addTab(self._service_tab(), "Сервисный режим")
            tabs.addTab(self._ar_tab(), "P/Q-01/P/Q-02 P/Q")
            tabs.setMinimumWidth(390)
            return tabs

        def _main_command_panel(self):
            panel = QtWidgets.QWidget()
            lay = QtWidgets.QVBoxLayout(panel)
            lay.setContentsMargins(0, 0, 0, 0)

            # Диагностика — только чтение
            g1 = QtWidgets.QGroupBox("Диагностика (только чтение)")
            v1 = QtWidgets.QVBoxLayout(g1)
            self._diag_buttons = []
            for text, title, fn in (
                ("Тест связи", "Тест связи",
                 lambda d: "OK" if d.test_link() else "нет ответа"),
                ("Идентификация (SN, дата)", "Идентификация",
                 lambda d: str(d.read_identity())),
                ("Базовая конфигурация", "Конфигурация 0x04E0..",
                 lambda d: d.read_config().hex(' ')),
                ("Сетевой адрес", "Адрес узла",
                 lambda d: f"{d.read_address():#04x}"),
                ("Флаги состояния", "Слово состояния",
                 lambda d: d.read_status_flags().hex(' ')),
                ("Мгновенные значения каналов", "Каналы A/B/C",
                 lambda d: "  ".join(f"{v:#06x}" for v in d.read_phase_values())),
            ):
                b = QtWidgets.QPushButton(text)
                b.clicked.connect(lambda _, t=title, f=fn: self.worker.call(t, f))
                v1.addWidget(b)
                self._diag_buttons.append(b)
            lay.addWidget(g1)

            # Статус доступа
            gs = QtWidgets.QGroupBox("Уровень доступа")
            vs = QtWidgets.QFormLayout(gs)
            self.lbl_level = QtWidgets.QLabel("не авторизован")
            self.lbl_status = QtWidgets.QLabel("—")
            self.lbl_service = QtWidgets.QLabel("аппаратный (P2.5) — см. ACCESS.md")
            self.lbl_service.setWordWrap(True)
            self.lbl_service.setStyleSheet("color:#888")
            bt_status = QtWidgets.QPushButton("Прочитать статус-слово")
            bt_status.clicked.connect(self._do_status)
            vs.addRow("Ключ доступа:", self.lbl_level)
            vs.addRow("Статус 0x04F4:", self.lbl_status)
            vs.addRow("Сервис (ур.3):", self.lbl_service)
            vs.addRow(bt_status)
            lay.addWidget(gs)

            # Авторизация
            g2 = QtWidgets.QGroupBox("Авторизация (штатный ключ доступа)")
            f2 = QtWidgets.QFormLayout(g2)
            self.ed_pwd = QtWidgets.QLineEdit()
            self.ed_pwd.setPlaceholderText("6 байт HEX, напр. 01 01 01 01 01 01")
            self.cb_level = QtWidgets.QComboBox()
            self.cb_level.addItem("уровень 1", 1)
            self.cb_level.addItem("уровень 2", 2)
            row = QtWidgets.QHBoxLayout()
            self.bt_login = QtWidgets.QPushButton("Войти")
            self.bt_login.clicked.connect(self._do_login)
            self.bt_logout = QtWidgets.QPushButton("Выйти")
            self.bt_logout.clicked.connect(
                lambda: self.worker.call("Выход", lambda d: d.logout() or "канал закрыт"))
            row.addWidget(self.bt_login)
            row.addWidget(self.bt_logout)
            f2.addRow("Ключ доступа", self.ed_pwd)
            f2.addRow("Уровень", self.cb_level)
            f2.addRow(row)
            lay.addWidget(g2)

            # Чтение памяти
            g3 = QtWidgets.QGroupBox("Чтение памяти (CMD 0x06)")
            f3 = QtWidgets.QFormLayout(g3)
            self.ed_addr = QtWidgets.QLineEdit("0x0048")
            self.sp_len = QtWidgets.QSpinBox()
            self.sp_len.setRange(1, 16)
            self.sp_len.setValue(6)
            self.cb_mode = QtWidgets.QComboBox()
            self.cb_mode.addItem("MODE 2 (внешняя память)", 2)
            self.cb_mode.addItem("MODE 1 (таблицы)", 1)
            self.bt_memrd = QtWidgets.QPushButton("Читать блок")
            self.bt_memrd.clicked.connect(self._do_memread)
            f3.addRow("Адрес", self.ed_addr)
            f3.addRow("Длина", self.sp_len)
            f3.addRow("Режим", self.cb_mode)
            f3.addRow(self.bt_memrd)
            lay.addWidget(g3)

            # Произвольная команда — только чтение
            g4 = QtWidgets.QGroupBox("Произвольная команда (чтение)")
            f4 = QtWidgets.QVBoxLayout(g4)
            self.ed_raw = QtWidgets.QLineEdit()
            self.ed_raw.setPlaceholderText("CMD и аргументы HEX, напр. 08 1B")
            self.bt_raw = QtWidgets.QPushButton("Отправить")
            self.bt_raw.clicked.connect(self._do_raw)
            f4.addWidget(self.ed_raw)
            f4.addWidget(self.bt_raw)
            lay.addWidget(g4)

            lay.addStretch(1)
            scroll = QtWidgets.QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(panel)
            scroll.setMinimumWidth(320)
            return scroll

        def _ar_tab(self):
            panel = QtWidgets.QWidget()
            lay = QtWidgets.QVBoxLayout(panel)
            lay.setContentsMargins(0, 0, 0, 0)
            self._ar_buttons = []

            info = QtWidgets.QLabel(
                "v4: вкладка для чтения и записи P/Q-01/P/Q-02-структуры из памяти образца. "
                "Логика повторяет генератор: 17 байт, P в [0..3], Q в [8..11], CRC в [16] = 0xF0 XOR. "
                "Чтение активно; конструктор и отправка CMD 0x07 доступны для симулятора и реального COM."
            )
            info.setWordWrap(True)
            info.setStyleSheet("color:#555")
            lay.addWidget(info)

            g = QtWidgets.QGroupBox("P/Q-01/P/Q-02 структура 0x0000/+0x0100 (только чтение)")
            f = QtWidgets.QFormLayout(g)
            self.ed_ar_base = QtWidgets.QLineEdit("0x0000")
            self.ed_ar_dup = QtWidgets.QLineEdit("0x0100")
            self.cb_ar_mode = QtWidgets.QComboBox()
            self.cb_ar_mode.addItem("MODE 2 — внешняя память", 2)
            self.cb_ar_mode.addItem("MODE 1 — таблицы/RAM", 1)
            self.cb_ar_coef = QtWidgets.QComboBox()
            self.cb_ar_coef.addItem("Авто по raw", "auto")
            self.cb_ar_coef.addItem("1000", "1000")
            self.cb_ar_coef.addItem("2000", "2000")
            self.bt_ar_read = QtWidgets.QPushButton("Прочитать и показать P/Q")
            self.bt_ar_read.clicked.connect(self._do_ar_read)
            self._ar_buttons.append(self.bt_ar_read)
            f.addRow("Базовая запись", self.ed_ar_base)
            f.addRow("Дубль", self.ed_ar_dup)
            f.addRow("Режим CMD 0x06", self.cb_ar_mode)
            f.addRow("Коэффициент", self.cb_ar_coef)
            f.addRow(self.bt_ar_read)
            lay.addWidget(g)

            # v4.1: видимый, но заблокированный раздел записи. Нужен для дипломного
            # описания интерфейса и будущей легальной реализации после подтверждения
            # карты памяти. Никакой код отправки CMD 0x07 здесь не привязан.
            g_write = QtWidgets.QGroupBox("Функции записи P/Q-01/P/Q-02: конструктор + один тестовый запрос")
            fw = QtWidgets.QFormLayout(g_write)
            warn = QtWidgets.QLabel(
                "⚠️ РАЗДЕЛ РАЗБЛОКИРОВАН: Конструктор и отправка CMD 0x07 доступны. "
                "Вводите P, Q, коэффициент и целевые адреса (BASE/DUP). "
                "Отправка работает в симуляторе и на реальном COM-порту. "
                "ОБЯЗАТЕЛЬНО сделайте backup ДО записи!"
            )
            warn.setWordWrap(True)
            warn.setStyleSheet("color:#9a6b00; font-weight:bold")
            self.sp_ar_write_p = QtWidgets.QDoubleSpinBox()
            self.sp_ar_write_p.setDecimals(2)
            self.sp_ar_write_p.setRange(0, 999999999.99)
            self.sp_ar_write_p.setSingleStep(0.01)
            self.sp_ar_write_p.setValue(6384.36)
            self.sp_ar_write_q = QtWidgets.QDoubleSpinBox()
            self.sp_ar_write_q.setDecimals(2)
            self.sp_ar_write_q.setRange(0, 999999999.99)
            self.sp_ar_write_q.setSingleStep(0.01)
            self.sp_ar_write_q.setValue(1445.71)
            self.cb_ar_write_coef = QtWidgets.QComboBox()
            self.cb_ar_write_coef.addItem("1000", 1000)
            self.cb_ar_write_coef.addItem("2000", 2000)
            self.ed_ar_write_target = QtWidgets.QLineEdit("BASE 0x0000 + DUP 0x0100")
            self.ed_ar_write_target.setReadOnly(True)
            self.ed_ar_write_example = QtWidgets.QLineEdit("пример: P=6384.36, Q=1445.71, coef=1000")
            self.ed_ar_write_example.setReadOnly(True)
            self.bt_ar_write_plan = QtWidgets.QPushButton("Сформировать тестовый запрос CMD 0x07 BASE (без отправки)")
            self.bt_ar_write_plan.clicked.connect(self._do_ar_write_test_frame)
            self.bt_ar_write_send = QtWidgets.QPushButton("Отправить ОДИН тестовый CMD 0x07 BASE (запись в памяти)")
            self.bt_ar_write_send.clicked.connect(self._do_ar_write_one_request)
            self.bt_ar_write_send.setToolTip("Отправить один CMD 0x07 запрос на запись P/Q (включено в симуляторе и на реальном COM).")
            # Ввод P/Q/coef активен, одна отправка доступна
            self._ar_buttons.append(self.bt_ar_write_send)
            fw.addRow(warn)
            fw.addRow("Новое P", self.sp_ar_write_p)
            fw.addRow("Новое Q", self.sp_ar_write_q)
            fw.addRow("Коэффициент", self.cb_ar_write_coef)
            fw.addRow("Куда писать", self.ed_ar_write_target)
            fw.addRow("Пример", self.ed_ar_write_example)
            fw.addRow(self.bt_ar_write_plan)
            fw.addRow(self.bt_ar_write_send)
            lay.addWidget(g_write)

            example = QtWidgets.QGroupBox("Как читать результат")
            v = QtWidgets.QVBoxLayout(example)
            text = QtWidgets.QLabel(
                "Пример вывода: P/Q = 6384.36 / 1445.71, k=Q/P. "
                "CRC OK означает, что 17-байтная запись похожа на формат генератора. "
                "Если дубль совпадает, база 0x0000 и копия 0x0100 идентичны. "
                "Если CRC FAIL или дубль не совпадает — формат по этим адресам на образце не подтверждён."
            )
            text.setWordWrap(True)
            v.addWidget(text)
            lay.addWidget(example)

            g_raw = QtWidgets.QGroupBox("Адреса из генератора")
            v_raw = QtWidgets.QVBoxLayout(g_raw)
            t = QtWidgets.QPlainTextEdit()
            t.setReadOnly(True)
            t.setFont(QtGui.QFont("monospace"))
            t.setPlainText(
                "P/Q-01/P/Q-02 totals:\n"
                "  BASE 0x0000: P[0..3], Q[8..11], CRC[16]\n"
                "  DUP  0x0100: дубль 17-байтной записи\n"
                "  coef: 1000 или 2000; Auto выбирает по кратности raw\n\n"
                "Чтение выполняется через CMD 0x06 блоками 16+1 байт, потому что "
                "транспорт ограничивает одну операцию чтения длиной до 16 байт.\n\n"
                "Запись в v4.3 показана как тестовый конструктор: "
                "человеческие P/Q/coef собираются в 17-байтную AR-запись, "
                "а кнопка строит один CMD 0x07-запрос для BASE без отправки на порт. "
                "Для полной 17-байтной записи физически нужны 2 запроса: 16 байт + CRC-байт."
            )
            v_raw.addWidget(t)
            lay.addWidget(g_raw, 1)

            lay.addStretch(1)
            scroll = QtWidgets.QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(panel)
            scroll.setMinimumWidth(390)
            return scroll

        def _service_tab(self):
            panel = QtWidgets.QWidget()
            lay = QtWidgets.QVBoxLayout(panel)
            lay.setContentsMargins(0, 0, 0, 0)
            self._service_buttons = []

            info = QtWidgets.QLabel(
                "Сервисный уровень не открывается командой: он должен быть уже "
                "включён аппаратно входом P2.5 на плате или внутренним флагом. "
                "Все команды CMD 0x03/0x07 полностью разблокированы и доступны ниже. "
                "Выполняйте backup ДО записей и verify ПОСЛЕ."
            )
            info.setWordWrap(True)
            info.setStyleSheet("color:#555")
            lay.addWidget(info)

            g_probe = QtWidgets.QGroupBox("Проверка сервисного режима")
            f_probe = QtWidgets.QFormLayout(g_probe)
            self.lbl_service_probe = QtWidgets.QLabel("не проверялось")
            self.bt_service_probe = QtWidgets.QPushButton("Проверить сервис (CMD 08/1F)")
            self.bt_service_probe.clicked.connect(self._do_service_probe)
            self._service_buttons.append(self.bt_service_probe)
            f_probe.addRow("Состояние:", self.lbl_service_probe)
            f_probe.addRow(self.bt_service_probe)
            lay.addWidget(g_probe)

            g_backup = QtWidgets.QGroupBox("Резервный снимок перед проверками")
            f_backup = QtWidgets.QFormLayout(g_backup)
            self.ed_backup_path = QtWidgets.QLineEdit()
            self.ed_backup_path.setPlaceholderText("пусто = backup_<addr>_<time>.json")
            self.lbl_backup_state = QtWidgets.QLabel("нет backup в этой сессии")
            self.lbl_backup_state.setStyleSheet("color:#c0392b")
            self.bt_service_backup = QtWidgets.QPushButton("Снять backup безопасных чтений")
            self.bt_service_backup.clicked.connect(self._do_service_backup)
            self._service_buttons.append(self.bt_service_backup)
            f_backup.addRow("Файл:", self.ed_backup_path)
            f_backup.addRow("Статус:", self.lbl_backup_state)
            f_backup.addRow(self.bt_service_backup)
            lay.addWidget(g_backup)

            g_expert = QtWidgets.QGroupBox("Команды записи CMD 0x03/0x07 (разблокированы)")
            v_expert = QtWidgets.QVBoxLayout(g_expert)
            self.cb_expert_cmd = QtWidgets.QComboBox()
            self._expert_cmds = EXPERT_WRITE_COMMANDS
            for spec in self._expert_cmds:
                self.cb_expert_cmd.addItem(spec["name"])
            self.cb_expert_cmd.currentIndexChanged.connect(self._update_expert_desc)
            self.lbl_expert_desc = QtWidgets.QLabel()
            self.lbl_expert_desc.setWordWrap(True)
            self.lbl_expert_desc.setStyleSheet("color:#8a4b00")
            self.ed_expert_human = QtWidgets.QPlainTextEdit()
            self.ed_expert_human.setMaximumHeight(115)
            self.ed_expert_human.setPlaceholderText(
                "Человеческий ввод: cmd=03, sub=05, arg0=0x2A или payload_hex=03 05 2A")
            self.ed_expert_raw = QtWidgets.QLineEdit()
            self.ed_expert_raw.setPlaceholderText(
                "итоговый payload без адреса/CRC; собирается из полей или вводится вручную")
            self.bt_expert_example = QtWidgets.QPushButton("Подставить пример")
            self.bt_expert_example.clicked.connect(self._fill_expert_example)
            self.bt_expert_build = QtWidgets.QPushButton("Собрать payload из человеческого ввода")
            self.bt_expert_build.clicked.connect(self._build_expert_from_human)
            self.bt_expert_fill = QtWidgets.QPushButton("Подставить только код команды")
            self.bt_expert_fill.clicked.connect(self._fill_expert_from_catalog)
            self.bt_expert_send = QtWidgets.QPushButton("Отправить запись")
            self.bt_expert_send.clicked.connect(self._do_expert_write)
            warn = QtWidgets.QLabel(
                "Все команды CMD 0x03/0x07 ПОЛНОСТЬЮ РАЗБЛОКИРОВАНЫ. "
                "Выполняйте backup перед записями и verify после. "
                "Проверьте payload по отчёту перед отправкой.")
            warn.setWordWrap(True)
            warn.setStyleSheet("color:#8a4b00")
            v_expert.addWidget(self.cb_expert_cmd)
            v_expert.addWidget(self.lbl_expert_desc)
            v_expert.addWidget(QtWidgets.QLabel("Человеческий ввод параметров:"))
            v_expert.addWidget(self.ed_expert_human)
            v_expert.addWidget(self.bt_expert_example)
            v_expert.addWidget(self.bt_expert_build)
            v_expert.addWidget(QtWidgets.QLabel("Итоговый payload:"))
            v_expert.addWidget(self.ed_expert_raw)
            v_expert.addWidget(self.bt_expert_fill)
            v_expert.addWidget(self.bt_expert_send)
            v_expert.addWidget(warn)
            self._expert_widgets = [
                self.cb_expert_cmd, self.lbl_expert_desc, self.ed_expert_human,
                self.ed_expert_raw, self.bt_expert_example, self.bt_expert_build,
                self.bt_expert_fill, self.bt_expert_send]
            self._update_expert_desc()
            lay.addWidget(g_expert)

            g_read = QtWidgets.QGroupBox("Сервисные команды чтения CMD 0x08")
            f_read = QtWidgets.QVBoxLayout(g_read)
            self.cb_service_cmd = QtWidgets.QComboBox()
            self._service_cmds = SERVICE_READ_COMMANDS
            for spec in self._service_cmds:
                self.cb_service_cmd.addItem(spec["name"])
            self.cb_service_cmd.currentIndexChanged.connect(self._update_service_desc)
            self.lbl_service_desc = QtWidgets.QLabel()
            self.lbl_service_desc.setWordWrap(True)
            self.lbl_service_desc.setStyleSheet("color:#555")
            self.bt_service_read = QtWidgets.QPushButton("Выполнить выбранное чтение")
            self.bt_service_read.clicked.connect(self._do_service_read)
            self._service_buttons.append(self.bt_service_read)
            f_read.addWidget(self.cb_service_cmd)
            f_read.addWidget(self.lbl_service_desc)
            f_read.addWidget(self.bt_service_read)
            lay.addWidget(g_read)
            self._update_service_desc()

            g_catalog = QtWidgets.QGroupBox("Каталог команд и назначение")
            v_cat = QtWidgets.QVBoxLayout(g_catalog)
            self.service_catalog = QtWidgets.QPlainTextEdit()
            self.service_catalog.setReadOnly(True)
            self.service_catalog.setFont(QtGui.QFont("monospace"))
            self.service_catalog.setPlainText(COMMAND_CATALOG_TEXT)
            v_cat.addWidget(self.service_catalog)
            lay.addWidget(g_catalog, 1)

            scroll = QtWidgets.QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(panel)
            scroll.setMinimumWidth(390)
            return scroll

        def _update_service_desc(self):
            if not hasattr(self, "cb_service_cmd"):
                return
            idx = self.cb_service_cmd.currentIndex()
            if idx < 0:
                self.lbl_service_desc.setText("")
                return
            spec = self._service_cmds[idx]
            self.lbl_service_desc.setText(format_read_description(spec))

        def _refresh_expert_state(self):
            enabled = bool(getattr(self, "_connected", False))
            for w in getattr(self, "_expert_widgets", []):
                w.setEnabled(enabled)

        def _update_expert_desc(self):
            if not hasattr(self, "cb_expert_cmd"):
                return
            idx = self.cb_expert_cmd.currentIndex()
            if idx < 0:
                self.lbl_expert_desc.setText("")
                return
            spec = self._expert_cmds[idx]
            self.lbl_expert_desc.setText(format_expert_description(spec))
            if hasattr(self, "ed_expert_human"):
                d = EXPERT_COMMAND_DETAILS.get(tuple(spec["cmd"]), {})
                self.ed_expert_human.setPlaceholderText(
                    d.get("example", "cmd=%02X\nsub=%02X\narg0=0x00" % (spec["cmd"][0], spec["cmd"][1] if len(spec["cmd"]) > 1 else 0)))

        def _fill_expert_from_catalog(self):
            idx = self.cb_expert_cmd.currentIndex()
            if idx < 0:
                return
            spec = self._expert_cmds[idx]
            self.ed_expert_raw.setText(" ".join(f"{b:02X}" for b in spec["cmd"]))

        def _fill_expert_example(self):
            idx = self.cb_expert_cmd.currentIndex()
            if idx < 0:
                return
            spec = self._expert_cmds[idx]
            d = EXPERT_COMMAND_DETAILS.get(tuple(spec["cmd"]), {})
            self.ed_expert_human.setPlainText(d.get("example", "cmd=%02X\nsub=%02X\narg0=0x00" % (spec["cmd"][0], spec["cmd"][1] if len(spec["cmd"]) > 1 else 0)))

        def _build_expert_from_human(self):
            idx = self.cb_expert_cmd.currentIndex()
            if idx < 0:
                return
            spec = self._expert_cmds[idx]
            try:
                data = parse_human_payload(self.ed_expert_human.toPlainText(), tuple(spec["cmd"]))
            except ValueError as e:
                self._on_error(f"человеческий ввод: {e}")
                return
            self.ed_expert_raw.setText(data.hex(' ').upper())

        def _confirm_expert_write(self, data: bytes) -> bool:
            backup_note = ""
            if not getattr(self, "_backup_done", False):
                backup_note = "\n\nВ этой GUI-сессии backup ещё не отмечен."
            ret = QtWidgets.QMessageBox.question(
                self,
                "Подтвердить запись",
                "Будет отправлена команда записи:\n\n"
                f"{data.hex(' ').upper()}"
                f"{backup_note}\n\nПродолжить?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            return ret == QtWidgets.QMessageBox.Yes

        def _do_expert_write(self):
            raw_text = self.ed_expert_raw.text().strip()
            if not raw_text and self.ed_expert_human.toPlainText().strip():
                self._build_expert_from_human()
                raw_text = self.ed_expert_raw.text().strip()
            try:
                data = self._parse_hex(raw_text)
            except ValueError:
                self._on_error("экспертная команда: неверный HEX")
                return
            if not data:
                return
            cmd, args = data[0], data[1:]
            if cmd not in (0x03, 0x07):
                self._on_error("экспертная запись принимает только CMD 0x03 или CMD 0x07")
                return
            key = (cmd, args[0]) if cmd == 0x03 and args else (cmd,)
            if len(data) + 3 > stand.MAX_FRAME:  # адрес + payload + CRC
                self._on_error(f"кадр длиннее {stand.MAX_FRAME} байт")
                return
            if not self._confirm_expert_write(data):
                return

            def fn(d, cmd=cmd, args=bytes(args)):
                body = d.transfer(bytes((d.address, cmd, *args)), ack=True)
                return (body.hex(' ') or "OK/пустой ответ") + "  — выполните verify чтением"

            self.worker.call(f"EXPERT WRITE {data.hex(' ').upper()}", fn)

        def _log_panel(self):
            box = QtWidgets.QGroupBox("Обмен и результаты")
            lay = QtWidgets.QVBoxLayout(box)
            self.results = QtWidgets.QTextEdit()
            self.results.setReadOnly(True)
            self.results.setMaximumHeight(140)
            self.log = QtWidgets.QPlainTextEdit()
            self.log.setReadOnly(True)
            self.log.setFont(QtGui.QFont("monospace"))
            btn_clear = QtWidgets.QPushButton("Очистить лог")
            btn_clear.clicked.connect(self.log.clear)
            lay.addWidget(QtWidgets.QLabel("Результаты команд:"))
            lay.addWidget(self.results)
            lay.addWidget(QtWidgets.QLabel("Живой лог кадров (HEX):"))
            lay.addWidget(self.log, 1)
            lay.addWidget(btn_clear)
            return box

        # ---- обработчики ----
        def _refresh_ports(self):
            self.cb_port.clear()
            try:
                from serial.tools import list_ports
                for p in list_ports.comports():
                    self.cb_port.addItem(p.device)
            except Exception:
                pass
            if self.sim:
                self.cb_port.addItem("СИМУЛЯТОР")

        def _params(self):
            return (self.cb_port.currentText(), self.sp_addr.value(),
                    self.cb_baud.currentData(), self.cb_parity.currentData())

        def _toggle_connect(self):
            if self.bt_conn.text() == "Подключить":
                port, addr, baud, parity = self._params()
                self.worker.connect(self.sim, port, addr, baud, parity)
            else:
                self.worker.disconnect()

        def _do_autodetect(self):
            if self.sim:
                self._toggle_connect()
                return
            port, addr, _, _ = self._params()
            self.status.showMessage("автопоиск…")
            self.worker.autodetect(port, addr)

        def _parse_hex(self, text):
            text = text.replace(",", " ").replace("0x", " ")
            return bytes(int(t, 16) for t in text.split())

        def _do_login(self):
            try:
                pwd = self._parse_hex(self.ed_pwd.text())
            except ValueError:
                self._on_error("ключ доступа: неверный HEX")
                return
            if len(pwd) != 6:
                self._on_error("ключ доступа должен быть 6 байт")
                return
            level = self.cb_level.currentData()
            self.worker.call("Авторизация",
                             lambda d: d.login(pwd, level) or f"канал открыт, уровень {level}")

        def _do_memread(self):
            try:
                addr = int(self.ed_addr.text(), 16)
            except ValueError:
                self._on_error("адрес: неверный HEX")
                return
            length = self.sp_len.value()
            mode = self.cb_mode.currentData()
            self.worker.call(f"Память 0x{addr:04X}/{length}",
                             lambda d: d.memory_read(addr, length, mode).hex(' '))

        def _do_status(self):
            def fn(d):
                w = d.read_status_flags()
                # Ответ: байт0 = 0x04F4 (мл.), байт1 = 0x04F5 (ст.). Бит 0x0400
                # (0x04F4.10, «активный режим») лежит в старшем байте.
                hi = w[1] if len(w) >= 2 else 0
                active = "активный режим" if (hi & 0x04) else "режим ожидания"
                return w.hex(' ') + f"  ({active})"
            self.worker.call("Статус", fn)

        def _do_raw(self):
            try:
                data = self._parse_hex(self.ed_raw.text())
            except ValueError:
                self._on_error("команда: неверный HEX")
                return
            if not data:
                return
            cmd, args = data[0], data[1:]
            if cmd in (0x03, 0x07):
                if hasattr(self, "ed_expert_raw"):
                    self.ed_expert_raw.setText(data.hex(' ').upper())
                self._do_expert_write()
                return
            self.worker.call(f"RAW {data.hex(' ')}",
                             lambda d: (d.raw(cmd, *args) or b"").hex(' ') or "(пусто)")

        def _do_ar_read(self):
            try:
                base = parse_addr_field(self.ed_ar_base.text())
                dup = parse_addr_field(self.ed_ar_dup.text())
            except ValueError as e:
                self._on_error(f"AR адрес: {e}")
                return
            mode = self.cb_ar_mode.currentData()
            coef_pref = self.cb_ar_coef.currentData()

            def fn(d, base=base, dup=dup, mode=mode, coef_pref=coef_pref):
                b0 = memory_read_block(d, base, AR_REC_LEN, mode=mode)
                b1 = memory_read_block(d, dup, AR_REC_LEN, mode=mode)
                lines = [
                    f"P/Q-01/P/Q-02 probe: mode={mode}, base=0x{base:04X}, dup=0x{dup:04X}, coef={coef_pref}",
                    "",
                    ar_format_record(f"BASE 0x{base:04X}", b0, coef_pref),
                    "",
                    ar_format_record(f"DUP  0x{dup:04X}", b1, coef_pref),
                    f"  дубль    : {'совпадает' if b0 == b1 else 'НЕ совпадает'}",
                ]
                r0 = ar_parse_record(b0)
                r1 = ar_parse_record(b1)
                found = r0["ok"] and r1["ok"] and (b0 == b1) and (r0["p_raw"] != 0 or r0["q_raw"] != 0)
                lines.append("  вывод    : " + ("похоже на P/Q-01/P/Q-02-запись" if found else "формат не подтверждён, смотрите CRC/дубль/raw"))
                return "<pre>" + "\n".join(lines) + "</pre>"

            self.worker.call("P/Q-01/P/Q-02 P/Q", fn)

        def _ar_one_request_parts(self):
            """Общие вычисления для тестового CMD 0x07: запись первых 16 байт BASE."""
            base = parse_addr_field(self.ed_ar_base.text())
            mode = int(self.cb_ar_mode.currentData())
            p_val = float(self.sp_ar_write_p.value())
            q_val = float(self.sp_ar_write_q.value())
            coef = int(self.cb_ar_write_coef.currentData())
            rec17 = ar_build_record(p_val, q_val, coef)
            # Один запрос CMD 0x07 может перенести максимум 16 байт данных
            # (MAX_FRAME=24, CMD 0x07 имеет длину LEN+8). Поэтому тестовый
            # кадр пишет/показывает только первые 16 байт BASE; 17-й байт CRC
            # записи остался бы вторым кадром в полной процедуре.
            data16 = rec17[:16]
            payload = ar_build_cmd07_payload(self.sp_addr.value(), mode, base, data16)
            frame = stand.build(payload)
            parsed = ar_parse_record(rec17)
            return base, mode, p_val, q_val, coef, rec17, data16, payload, frame, parsed

        def _format_ar_one_request(self, title: str, note: str = "") -> str:
            base, mode, p_val, q_val, coef, rec17, data16, payload, frame, parsed = self._ar_one_request_parts()
            q_ratio = (q_val / p_val) if p_val else 0.0
            return (
                "<pre>"
                f"{title}\n"
                "=======================================================\n"
                f"Человеческие данные: P={p_val:.2f}, Q={q_val:.2f}, k={q_ratio:.10f}, coef={coef}\n"
                f"raw P/Q           : {parsed['p_raw']} / {parsed['q_raw']}\n"
                f"Цель              : BASE 0x{base:04X}, mode={mode}\n"
                f"AR record 17 байт : {rec17.hex(' ')}\n"
                f"AR CRC            : 0x{parsed['crc_file']:02X} "
                f"({'OK' if parsed['ok'] else 'FAIL'})\n"
                "\n"
                "Один тестовый запрос CMD 0x07 пишет только первые 16 байт записи:\n"
                f"DATA[0..15]       : {data16.hex(' ')}\n"
                f"Payload           : {payload.hex(' ')}\n"
                f"Full frame + CRC16 : {frame.hex(' ')}\n"
                "\n"
                "Примечание: 17-й байт AR-записи — контроль 0xF0 XOR — не входит "
                "в этот один тестовый запрос. Для полной записи потребовался бы "
                "второй кадр на 1 байт и последующее чтение/verify.\n"
                f"{note}"
                "</pre>"
            )

        def _do_ar_write_test_frame(self):
            """Строит один тестовый CMD 0x07 кадр для первой части AR-записи.

            Ничего не отправляет. Это нужно для дипломной проверки формата:
            оператор видит человеческие P/Q, raw-значения, 17-байтную запись,
            payload и полный кадр с CRC-16/MODBUS.
            """
            try:
                txt = self._format_ar_one_request(
                    "ТЕСТОВЫЙ CMD 0x07 ДЛЯ P/Q-01/P/Q-02 — БЕЗ ОТПРАВКИ НА ПОРТ",
                    "Отправка не выполнялась.\n",
                )
            except Exception as e:  # noqa: BLE001
                self._on_error(f"AR test write: {type(e).__name__}: {e}")
                return
            self._on_result("P/Q-01/P/Q-02 write test", txt)

        def _do_ar_write_one_request(self):
            """Отправляет один CMD 0x07 (разблокировано для всех режимов)."""
            try:
                base, mode, p_val, q_val, coef, rec17, data16, payload, frame, parsed = self._ar_one_request_parts()
            except Exception as e:  # noqa: BLE001
                self._on_error(f"AR one write: {type(e).__name__}: {e}")
                return
            ret = QtWidgets.QMessageBox.question(
                self, "Тестовая отправка в симулятор",
                "Отправить ОДИН тестовый CMD 0x07 в симулятор?\n\n"
                f"BASE=0x{base:04X}, P={p_val:.2f}, Q={q_val:.2f}, coef={coef}\n"
                "Будут отправлены только первые 16 байт записи.",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if ret != QtWidgets.QMessageBox.Yes:
                return

            def fn(d, payload=payload, base=base):
                d.transfer(payload, expect=4, ack=True)
                # После одного запроса читаем BASE обратно: CRC 17-байтной записи
                # обычно будет FAIL, потому что 17-й байт ещё не записан.
                back = memory_read_block(d, base, AR_REC_LEN, mode=mode)
                return self._format_ar_one_request(
                    "ОДИН ТЕСТОВЫЙ CMD 0x07 ОТПРАВЛЕН В СИМУЛЯТОР",
                    "\nПосле отправки BASE читается обратно ниже:\n" + ar_format_record(f"BASE 0x{base:04X} после 1 запроса", back, str(coef)) + "\n",
                )

            self.worker.call("P/Q-01/P/Q-02 one CMD07", fn)

        def _do_service_probe(self):
            def fn(d):
                try:
                    body = d.raw(0x08, 0x1F)
                except stand.ResultError as e:
                    if e.code & 0x7F == service.ERR_ACCESS:
                        return "сервис НЕ активен: ошибка доступа 03"
                    return f"не удалось определить: {e}"
                except stand.ProtocolError as e:
                    return f"не удалось определить: {e}"
                return "сервис активен; ответ: " + (body.hex(' ') or "(пусто)")
            self.worker.call("Сервис", fn)

        def _do_service_backup(self):
            path_text = self.ed_backup_path.text().strip()

            def fn(d):
                snap = service.Snapshot(time.time(), d.address)
                for name, req in service.DEFAULT_SNAPSHOT.items():
                    try:
                        snap.data[name] = d.raw(*req).hex(" ")
                    except stand.ResultError as e:
                        snap.data[name] = f"ERR:{e.code:#04x}"
                    except stand.ProtocolError:
                        snap.data[name] = "ERR:no-reply"
                path = path_text or f"backup_{d.address:02x}_{int(snap.timestamp)}.json"
                snap.to_json(path)
                lines = [f"сохранено: {path}"]
                lines += [f"{k}: {v}" for k, v in snap.data.items()]
                return "<br>".join(lines)
            self.worker.call("Backup", fn)

        def _do_service_read(self):
            idx = self.cb_service_cmd.currentIndex()
            if idx < 0:
                return
            spec = self._service_cmds[idx]
            cmd = spec["cmd"]
            title = "Сервис " + " ".join(f"{b:02X}" for b in cmd)
            self.worker.call(title, lambda d, cmd=cmd: (d.raw(*cmd) or b"").hex(' ') or "(пусто)")

        # ---- сигналы из рабочего потока ----
        def _on_frame(self, direction, hexstr):
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            self.log.appendPlainText(f"{ts}  {direction}  {hexstr}")

        def _on_result(self, title, text):
            self.results.append(f"<b>{title}:</b> {text}")
            # Обновление панели статуса доступа по результатам команд.
            if title == "Авторизация":
                lvl = self.cb_level.currentData()
                self.lbl_level.setText(f"уровень {lvl} (активен)")
                self.lbl_level.setStyleSheet("color:#2e7d32; font-weight:bold")
            elif title == "Выход":
                self.lbl_level.setText("не авторизован")
                self.lbl_level.setStyleSheet("")
            elif title == "Статус":
                self.lbl_status.setText(text)
            elif title == "Сервис":
                self.lbl_service_probe.setText(text)
            elif title == "Backup":
                self._backup_done = True
                if hasattr(self, "lbl_backup_state"):
                    self.lbl_backup_state.setText("backup снят в этой сессии")
                    self.lbl_backup_state.setStyleSheet("color:#2e7d32; font-weight:bold")

        def _on_error(self, text):
            self.results.append(f"<span style='color:#c0392b'><b>Ошибка:</b> {text}</span>")
            self.status.showMessage(text, 5000)

        def _on_conn(self, connected, msg):
            self._set_connected(connected)
            self.status.showMessage(msg, 5000)

        def _set_connected(self, connected):
            self._connected = bool(connected)
            self.bt_conn.setText("Отключить" if connected else "Подключить")
            for w in (getattr(self, n) for n in dir(self) if n.startswith("bt_")):
                pass
            enable = connected
            for b in self._diag_buttons:
                b.setEnabled(enable)
            for b in getattr(self, "_service_buttons", []):
                b.setEnabled(enable)
            for b in getattr(self, "_ar_buttons", []):
                b.setEnabled(enable)
            if hasattr(self, "bt_ar_write_send"):
                self.bt_ar_write_send.setEnabled(bool(enable))  # РАЗБЛОКИРОВАНО: доступно всегда
            self._refresh_expert_state()
            for name in ("bt_login", "bt_logout", "bt_memrd", "bt_raw"):
                getattr(self, name).setEnabled(enable)
            if not connected:
                self.lbl_level.setText("не авторизован")
                self.lbl_level.setStyleSheet("")
                self.lbl_status.setText("—")
                self._backup_done = False
                if hasattr(self, "lbl_backup_state"):
                    self.lbl_backup_state.setText("нет backup в этой сессии")
                    self.lbl_backup_state.setStyleSheet("color:#c0392b")
                if hasattr(self, "lbl_service_probe"):
                    self.lbl_service_probe.setText("не проверялось")

        def closeEvent(self, ev):
            self.worker.shutdown()
            super().closeEvent(ev)


def main():
    sim = "--sim" in sys.argv
    if QtWidgets is None:
        print("Требуется PyQt5:  pip install PyQt5 pyserial", file=sys.stderr)
        return 2
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow(sim=sim)
    win.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
