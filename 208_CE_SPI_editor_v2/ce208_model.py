"""CE208 V8530P SPI-state model recovered from MCU firmware.

The firmware uses two logical access paths, but their addresses are regions of
one 512-KiB 25DF041B image.  ``small`` is a writable view of SPI 0x0000..0x1FFF.
This module never talks to hardware.
"""

from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable


SMALL_SIZE = 0x2000
AT25_SIZE = 0x80000
AT25_PAGE = 0x100
AT25_SECTOR = 0x1000

CRC_POLY = 0x04C11DB7
CRC_INIT = 0xFFFFFFFF

CLOCK_PRIMARY = 0x0000
CLOCK_BACKUP = 0x19E0
CLOCK_RECORD_SIZE = 0x0A

CONTROL_PRIMARY = 0x000A
CONTROL_BACKUP = 0x19EA
CONTROL_RECORD_SIZE = 0x16

ENERGY_RECORD_SIZE = 0x44
ENERGY_BODY_SIZE = 0x42
ENERGY_CELL_COUNT = 13
ENERGY_CELL_SIZE = 5
ENERGY_BANK_COUNT = 4
CURRENT_ENERGY_PRIMARY = 0x0020
CURRENT_ENERGY_BACKUP = 0x1A00

ENERGY_ARCHIVES = {
    0: (0x03A38, 0x0080, "archive_type_0"),
    1: (0x10638, 0x0028, "archive_type_1"),
    2: (0x130B8, 0x000A, "archive_type_2"),
    5: (0x13B58, 0x0014, "archive_type_5"),
}

EVENT_HEADER_PRIMARY = 0x0308
EVENT_HEADER_BACKUP = 0x1CE8
EVENT_HEADER_SIZE = 0x08
EVENT_INDEX_PRIMARY = 0x0310
EVENT_INDEX_BACKUP = 0x1CF0
EVENT_INDEX_SIZE = 0x24
EVENT_INDEX_GROUPS = 9
EVENT_EPOCH = datetime(2000, 1, 1)
TIME_COUNTER_PRIMARY = 0x0EE0
TIME_COUNTER_RECORD_SIZE = 0x44
TIME_COUNTER_BLOCKS = 2
TIME_COUNTER_PAIRS = 8


@dataclass(frozen=True)
class EventLog:
    event_id: int
    display_code: int
    body_length: int
    capacity: int
    base: int

    @property
    def group(self) -> int:
        return self.event_id >> 3

    @property
    def sub(self) -> int:
        return self.event_id & 7

    @property
    def record_length(self) -> int:
        return self.body_length + 2


# Exact 70-entry table at MCU Flash 0x6F64C.  Function 0x4358A copies one
# eight-byte entry to RAM 0x2000BD10; 0x2E80C then builds the dynamic AT25
# descriptor from body_length, capacity and base.
_EVENT_LOG_ROWS = [
    (101, 12, 20, 0x47E70), (102, 8, 20, 0x47F88), (103, 8, 4, 0x48050),
    (104, 8, 4, 0x48078), (105, 8, 4, 0x480A0), (106, 8, 4, 0x480C8),
    (107, 8, 4, 0x480F0), (108, 8, 4, 0x48118), (109, 8, 12, 0x48140),
    (110, 8, 4, 0x481B8), (111, 8, 4, 0x481E0), (112, 8, 4, 0x48208),
    (113, 8, 4, 0x48230), (114, 8, 12, 0x48258), (115, 8, 12, 0x482D0),
    (116, 8, 12, 0x48348), (117, 8, 20, 0x483C0), (118, 8, 12, 0x48488),
    (119, 8, 12, 0x48500), (120, 12, 12, 0x48578), (121, 8, 12, 0x48620),
    (122, 8, 4, 0x48698), (123, 8, 4, 0x486C0), (124, 8, 4, 0x486E8),
    (125, 8, 12, 0x48710), (126, 8, 12, 0x48788), (127, 8, 12, 0x48800),
    (128, 8, 12, 0x48878), (129, 8, 12, 0x488F0), (130, 8, 12, 0x48968),
    (131, 8, 12, 0x489E0), (132, 8, 12, 0x48A58), (133, 8, 12, 0x48AD0),
    (134, 8, 4, 0x48B48), (1, 8, 20, 0x48B70), (2, 8, 12, 0x48C38),
    (3, 8, 4, 0x48CB0), (4, 8, 20, 0x48CD8), (5, 8, 4, 0x48DA0),
    (6, 8, 12, 0x48DC8), (7, 8, 4, 0x48E40), (8, 8, 20, 0x48E68),
    (9, 8, 20, 0x48F30), (10, 8, 20, 0x48FF8), (11, 12, 12, 0x490C0),
    (12, 12, 12, 0x49168), (13, 12, 12, 0x49210), (14, 8, 20, 0x492B8),
    (15, 8, 20, 0x49380), (16, 8, 20, 0x49448), (17, 8, 4, 0x49510),
    (18, 8, 12, 0x49538), (19, 8, 12, 0x495B0), (20, 8, 12, 0x49628),
    (21, 8, 12, 0x496A0), (22, 8, 4, 0x49718), (23, 8, 4, 0x49740),
    (24, 8, 12, 0x49768), (25, 8, 12, 0x497E0), (26, 8, 12, 0x49858),
    (27, 8, 12, 0x498D0), (28, 12, 4, 0x49948), (29, 12, 4, 0x49980),
    (30, 8, 12, 0x499B8), (31, 8, 12, 0x49A30), (32, 8, 12, 0x49AA8),
    (33, 8, 12, 0x49B20), (34, 8, 4, 0x49B98), (35, 12, 20, 0x49BC0),
    (36, 12, 20, 0x49CD8),
]
EVENT_LOGS = {
    event_id: EventLog(event_id, display_code, body_length, capacity, base)
    for event_id, (display_code, body_length, capacity, base) in enumerate(_EVENT_LOG_ROWS)
}


def pack_event_timestamp(value: datetime) -> int:
    """Firmware 0x30BDE: seconds since 2000-01-01, using whole days."""
    if not 2000 <= value.year <= 2050:
        raise ValueError("Прошивка принимает год события 2000..2050")
    seconds = int((value.replace(microsecond=0) - EVENT_EPOCH).total_seconds())
    if not 0 <= seconds <= 0xFFFFFFFF:
        raise ValueError("Время события не помещается в uint32")
    return seconds


def unpack_event_timestamp(value: int) -> datetime:
    if not 0 <= value <= 0xFFFFFFFF:
        raise ValueError("Упакованное время должно помещаться в uint32")
    return EVENT_EPOCH + timedelta(seconds=value)


def sha256(data: bytes | bytearray) -> str:
    return hashlib.sha256(bytes(data)).hexdigest().upper()


def crc32_msb(data: bytes | bytearray, initial: int = CRC_INIT) -> int:
    """Firmware function 0x304CC: MSB-first CRC32, no final XOR."""
    crc = initial & 0xFFFFFFFF
    for value in data:
        crc ^= value << 24
        for _ in range(8):
            crc = ((crc << 1) ^ CRC_POLY) & 0xFFFFFFFF if crc & 0x80000000 else (crc << 1) & 0xFFFFFFFF
    return crc


# ── Схемы контрольной суммы записи ─────────────────────────────────────────
# Приборы этой серии встречаются с двумя прошивками, которые считают CRC записи
# по-разному. Раскладка памяти у них одинаковая, отличается только алгоритм.
#
#   "ce208"   — функция прошивки 0x3B8EC: младшие 16 бит CRC-32 MSB-first
#               (poly 0x04C11DB7, init 0xFFFFFFFF, без финального XOR);
#   "msp430"  — CRC-16 CCITT (poly 0x1021) с обратным порядком бит на входе и
#               начальным значением 0x68D3 — так считает аппаратный модуль CRC
#               MSP430 в дампах вида «24C64_MKMSP430».
#
# Схема определяется при загрузке образа и используется как для проверки, так и
# для записи, чтобы прибор принял изменённый дамп.

MSP430_CRC_POLY = 0x1021
MSP430_CRC_INIT = 0x68D3

_BIT_REVERSED = bytes(int(f"{value:08b}"[::-1], 2) for value in range(256))


def crc16_msp430(data: bytes | bytearray, initial: int = MSP430_CRC_INIT) -> int:
    """CRC-16 CCITT с обратным порядком бит на входе (модуль CRC MSP430)."""
    reg = initial & 0xFFFF
    for value in data:
        reg ^= _BIT_REVERSED[value] << 8
        for _ in range(8):
            reg = ((reg << 1) ^ MSP430_CRC_POLY) & 0xFFFF if reg & 0x8000 else (reg << 1) & 0xFFFF
    return reg


CRC_SCHEMES = {
    "ce208": ("CE208 · CRC-32 MSB 0x04C11DB7", lambda data: crc32_msb(data) & 0xFFFF),
    "msp430": ("MSP430 · CRC-16 CCITT 0x1021", crc16_msp430),
}
DEFAULT_CRC_SCHEME = "ce208"
_active_crc_scheme = DEFAULT_CRC_SCHEME


def crc_scheme() -> str:
    """Текущая схема контрольной суммы записи."""
    return _active_crc_scheme


def crc_scheme_title(name: str | None = None) -> str:
    return CRC_SCHEMES[name or _active_crc_scheme][0]


def set_crc_scheme(name: str) -> None:
    global _active_crc_scheme
    if name not in CRC_SCHEMES:
        raise ValueError(f"Неизвестная схема CRC: {name}")
    _active_crc_scheme = name


def record_crc(data: bytes | bytearray) -> int:
    """Контрольная сумма записи по активной схеме."""
    return CRC_SCHEMES[_active_crc_scheme][1](data)


def build_record(body: bytes | bytearray, total_size: int) -> bytes:
    if total_size < 2 or len(body) > total_size - 2:
        raise ValueError("Неверная длина записи")
    padded = bytes(body).ljust(total_size - 2, b"\x00")
    return padded + struct.pack("<H", record_crc(padded))


def verify_record(record: bytes | bytearray) -> tuple[bool, int, int]:
    if len(record) < 2:
        raise ValueError("Запись короче двух байт")
    stored = struct.unpack_from("<H", record, len(record) - 2)[0]
    calculated = record_crc(record[:-2])
    return stored == calculated, stored, calculated


def parse_decimal(value: str | int | Decimal) -> Decimal:
    try:
        return Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Неверное число: {value}") from exc


def decode_energy(raw: int, divisor: int, decimals: int) -> Decimal:
    """Exact display path of 0x2EE96 + 0x2FE20, before LCD windowing."""
    if divisor <= 0:
        raise ValueError("Делитель энергии должен быть положительным")
    if not 0 <= decimals <= 12:
        raise ValueError("Знаков после точки должно быть от 0 до 12")
    quotient = raw // divisor
    return Decimal(quotient).scaleb(-decimals)


def encode_energy(value: str | int | Decimal, divisor: int, decimals: int) -> int:
    """Choose the smallest raw value that the firmware displays exactly as value."""
    if divisor <= 0:
        raise ValueError("Делитель энергии должен быть положительным")
    scaled = parse_decimal(value).scaleb(decimals)
    integer = scaled.to_integral_value()
    if scaled != integer:
        raise ValueError(f"Значение имеет больше {decimals} знаков после точки")
    raw = int(integer) * divisor
    if not 0 <= raw < 10**12:
        raise ValueError("Энергия выходит за штатный диапазон 0..10^12-1 raw")
    return raw


@dataclass(frozen=True)
class Descriptor:
    name: str
    path: str
    length: int
    primary: int
    backup_path: str | None = None
    backup: int | None = None
    ram: int | None = None
    template: int | None = None
    note: str = ""


# Fixed descriptors recovered from 24-byte templates in the MCU image.  Dynamic
# templates (whose addresses are filled by code) are represented separately by
# the clock/current-energy/archive APIs below.
FIXED_DESCRIPTORS = [
    Descriptor("cfg_C660", "small", 0x30, 0x0130, "small", 0x1B10, 0x2000C660, 0x6D150),
    Descriptor("cfg_C6F0", "small", 0x14, 0x023C, "small", 0x1C1C, 0x2000C6F0, 0x6D168),
    Descriptor("counter_C718", "small", 0x10, 0x0620, "at25", 0x5E7C8, 0x2000C718, 0x6D1B0),
    Descriptor("cfg_C690", "small", 0x28, 0x0160, "small", 0x1B40, 0x2000C690, 0x6D1E0),
    Descriptor("event_index_group0", "small", 0x24, 0x0310, "small", 0x1CF0, 0x2000A91C, 0x6D210, note="8 счётчиков журналов ID 0..7"),
    Descriptor("event_sequence_header", "small", 0x08, 0x0308, "small", 0x1CE8, 0x2000A914, 0x6D228, note="глобальная последовательность событий"),
    Descriptor("time_counters_0", "small", 0x44, 0x0EE0, None, None, 0x20009928, 0x6D240, note="8 пар timestamp/counter"),
    Descriptor("cfg_BBA0", "small", 0x10, 0x0250, "small", 0x1C30, 0x2000BBA0, 0x6D258),
    Descriptor("clock_snapshot", "small", CLOCK_RECORD_SIZE, CLOCK_PRIMARY, "small", CLOCK_BACKUP, 0x2000C734, 0x6D270),
    Descriptor("tariff_control", "small", CONTROL_RECORD_SIZE, CONTROL_PRIMARY, "small", CONTROL_BACKUP, 0x2000C6D8, 0x6D288),
    Descriptor("cfg_BB7C", "small", 0x20, 0x0188, "small", 0x1B68, 0x2000BB7C, 0x6D2A0),
    Descriptor("cfg_BD90", "at25", 0xE8, 0x0EB8, "at25", 0x5FB40, 0x2000BD90, 0x6D2B8),
    Descriptor("cfg_BE78", "at25", 0xE8, 0x0DD0, "at25", 0x5FA58, 0x2000BE78, 0x6D2D0),
    Descriptor("record_02A0", "at25", 0x22, 0x02A0, "at25", 0x5EF28, 0x20009928, 0x6D2E8),
    Descriptor("record_06E0", "at25", 0x6E, 0x06E0, "at25", 0x5F368, 0x20009928, 0x6D300),
    Descriptor("record_0750", "at25", 0xC4, 0x0750, "at25", 0x5F3D8, 0x20009928, 0x6D318),
    Descriptor("record_2258", "at25", 0xD4, 0x2258, None, None, 0x20009928, 0x6D330),
    Descriptor("record_0D88", "at25", 0x24, 0x0D88, "at25", 0x5FA10, 0x20009928, 0x6D348),
    Descriptor("record_2750", "at25", 0x68, 0x2750, None, None, 0x20009928, 0x6D360),
    Descriptor("record_5FEE0", "at25", 0x80, 0x5FEE0, None, None, 0x20009928, 0x6D378),
    Descriptor("record_5FF60", "at25", 0x80, 0x5FF60, None, None, 0x20009928, 0x6D390),
    Descriptor("cfg_C26C", "at25", 0xE8, 0x0FA0, "at25", 0x5FC28, 0x2000C26C, 0x6F07C),
    Descriptor("cfg_C354", "at25", 0xE8, 0x1088, "at25", 0x5FD10, 0x2000C354, 0x6F094),
    Descriptor("cfg_C43C", "at25", 0xE8, 0x1170, "at25", 0x5FDF8, 0x2000C43C, 0x6F0AC),
    Descriptor("record_0AE0", "small", 0x100, 0x0AE0, "at25", 0x5E6C8, 0x20009928, 0x6F0C4),
    Descriptor("cfg_B5B4", "small", 0x80, 0x0260, "small", 0x1C40, 0x2000B5B4, 0x6F0DC),
    Descriptor("cfg_AB84", "small", 0x50, 0x0478, "small", 0x1E58, 0x2000AB84, 0x6F10C),
    Descriptor("cfg_AA84", "small", 0x80, 0x04C8, "small", 0x1EA8, 0x2000AA84, 0x6F124),
    Descriptor("cfg_AD0C", "at25", 0x110, 0x3928, None, None, 0x2000AD0C, 0x6F13C),
    Descriptor("cfg_AB04", "small", 0x80, 0x05A0, "small", 0x1F80, 0x2000AB04, 0x6F154),
]

# 0x2E758/0x2E794 construct eight more group-index descriptors dynamically.
# Each 0x24-byte record holds eight uint32 write counters plus CRC/padding.
FIXED_DESCRIPTORS.extend(
    Descriptor(
        f"event_index_group{group}",
        "small",
        EVENT_INDEX_SIZE,
        EVENT_INDEX_PRIMARY + group * EVENT_INDEX_SIZE,
        "small",
        EVENT_INDEX_BACKUP + group * EVENT_INDEX_SIZE,
        0x2000A91C + group * EVENT_INDEX_SIZE,
        0x6D210,
        note=f"8 счётчиков журналов ID {group * 8}..{group * 8 + 7}",
    )
    for group in range(1, EVENT_INDEX_GROUPS)
)
FIXED_DESCRIPTORS.append(
    Descriptor(
        "time_counters_1",
        "small",
        TIME_COUNTER_RECORD_SIZE,
        TIME_COUNTER_PRIMARY + TIME_COUNTER_RECORD_SIZE,
        None,
        None,
        0x20009928,
        0x6D240,
        note="динамический блок 1: 8 пар timestamp/counter",
    )
)


@dataclass
class ClockValue:
    hour: int
    minute: int
    second: int
    weekday: int
    day: int
    month: int
    year: int
    flags: int = 0

    @classmethod
    def from_body(cls, body: bytes) -> "ClockValue":
        if len(body) < 8:
            raise ValueError("Тело времени короче 8 байт")
        value = cls(body[0], body[1], body[2], body[3], body[4], body[5], 2000 + body[6], body[7])
        value.validate()
        return value

    @classmethod
    def from_datetime(cls, value: datetime) -> "ClockValue":
        # Firmware weekday is 0..6; Python Monday is 0.  Preserve that convention.
        return cls(value.hour, value.minute, value.second, value.weekday(), value.day, value.month, value.year, 0)

    def validate(self) -> None:
        if not 2000 <= self.year <= 2050:
            raise ValueError("Прошивка принимает год 2000..2050")
        datetime(self.year, self.month, self.day, self.hour, self.minute, self.second)
        if not 0 <= self.weekday <= 6:
            raise ValueError("День недели должен быть 0..6")
        if not 0 <= self.flags <= 0xFF:
            raise ValueError("Флаги времени должны помещаться в байт")

    def body(self) -> bytes:
        self.validate()
        return bytes((self.hour, self.minute, self.second, self.weekday, self.day, self.month, self.year - 2000, self.flags))


@dataclass
class EnergyBank:
    cells: list[int]
    marker: int = 0

    @classmethod
    def empty(cls) -> "EnergyBank":
        return cls([0] * ENERGY_CELL_COUNT, 0)

    @classmethod
    def from_record(cls, record: bytes) -> "EnergyBank":
        if len(record) != ENERGY_RECORD_SIZE:
            raise ValueError("Энергетическая запись должна иметь 0x44 байта")
        valid, stored, calculated = verify_record(record)
        if not valid:
            raise ValueError(f"CRC записи неверна: {stored:04X} != {calculated:04X}")
        cells = [int.from_bytes(record[index * 5:index * 5 + 5], "little") for index in range(ENERGY_CELL_COUNT)]
        return cls(cells, record[65])

    def to_record(self) -> bytes:
        if len(self.cells) != ENERGY_CELL_COUNT:
            raise ValueError("Нужно ровно 13 энергетических ячеек")
        body = bytearray()
        for value in self.cells:
            if not 0 <= value < 10**12:
                raise ValueError("Энергетическая ячейка выходит за диапазон 0..10^12-1")
            body.extend(value.to_bytes(5, "little"))
        body.append(self.marker & 0xFF)
        return build_record(body, ENERGY_RECORD_SIZE)

    @property
    def tariffs(self) -> list[int]:
        return self.cells[3:11]

    @property
    def total(self) -> int:
        # Exact 0x2EE96 path for tariff selector 0.
        return sum(self.tariffs) % (10**12)

    def set_tariffs(self, tariffs: Iterable[int]) -> None:
        values = list(tariffs)
        if len(values) != 8:
            raise ValueError("Нужно восемь тарифов")
        if any(value < 0 or value >= 10**12 for value in values):
            raise ValueError("Тарифная ячейка выходит за штатный диапазон")
        self.cells[3:11] = values
        # Ячейки итога c0 и c2 = сумма тарифов (как в заводских записях),
        # чтобы прибор не читал устаревший итог. c1 и прочие сохраняются.
        total = sum(values) % (10**12)
        self.cells[0] = total
        self.cells[2] = total


@dataclass
class EventRecord:
    timestamp: datetime
    sequence: int
    status: int = 0
    value: int | None = None

    @classmethod
    def from_record(cls, log: EventLog, record: bytes) -> "EventRecord":
        if len(record) != log.record_length:
            raise ValueError("Неверная длина записи события")
        valid, stored, calculated = verify_record(record)
        if not valid:
            raise ValueError(f"CRC события неверна: {stored:04X} != {calculated:04X}")
        timestamp, sequence_status = struct.unpack_from("<II", record)
        value = struct.unpack_from("<I", record, 8)[0] if log.body_length == 12 else None
        return cls(
            unpack_event_timestamp(timestamp),
            sequence_status & 0x00FFFFFF,
            sequence_status >> 24,
            value,
        )

    def to_record(self, log: EventLog) -> bytes:
        if not 0 <= self.sequence <= 0xFFFFFF:
            raise ValueError("Порядковый номер события должен помещаться в 24 бита")
        if not 0 <= self.status <= 0xFF:
            raise ValueError("Статус события должен помещаться в байт")
        body = bytearray(struct.pack(
            "<II",
            pack_event_timestamp(self.timestamp),
            self.sequence | (self.status << 24),
        ))
        if log.body_length == 12:
            value = 0 if self.value is None else self.value
            if not 0 <= value <= 0xFFFFFFFF:
                raise ValueError("Значение события должно помещаться в uint32")
            body.extend(struct.pack("<I", value))
        return build_record(body, log.record_length)


@dataclass
class TimeCounterBlock:
    pairs: list[tuple[datetime, int]]

    @classmethod
    def initialized(cls, timestamp: datetime) -> "TimeCounterBlock":
        value = timestamp.replace(microsecond=0)
        return cls([(value, 0) for _ in range(TIME_COUNTER_PAIRS)])

    @classmethod
    def from_record(cls, record: bytes) -> "TimeCounterBlock":
        if len(record) != TIME_COUNTER_RECORD_SIZE:
            raise ValueError("Блок временных счётчиков должен иметь 0x44 байта")
        valid, stored, calculated = verify_record(record)
        if not valid:
            raise ValueError(f"CRC временных счётчиков неверна: {stored:04X} != {calculated:04X}")
        pairs = []
        for index in range(TIME_COUNTER_PAIRS):
            timestamp, counter = struct.unpack_from("<II", record, index * 8)
            pairs.append((unpack_event_timestamp(timestamp), counter))
        return cls(pairs)

    def to_record(self) -> bytes:
        if len(self.pairs) != TIME_COUNTER_PAIRS:
            raise ValueError("Нужно ровно восемь пар timestamp/counter")
        body = bytearray()
        for timestamp, counter in self.pairs:
            if not 0 <= counter <= 0xFFFFFFFF:
                raise ValueError("Счётчик должен помещаться в uint32")
            body.extend(struct.pack("<II", pack_event_timestamp(timestamp), counter))
        return build_record(body, TIME_COUNTER_RECORD_SIZE)


@dataclass(frozen=True)
class RecordResult:
    source: str
    address: int
    record: bytes
    valid: bool
    stored_crc: int
    calculated_crc: int


class CE208State:
    def __init__(self, small: bytes | bytearray | None = None, at25: bytes | bytearray | None = None):
        self.at25 = bytearray(b"\xFF" * AT25_SIZE if at25 is None else at25)
        if len(self.at25) != AT25_SIZE:
            raise ValueError(f"AT25 должна иметь 0x{AT25_SIZE:X} байт")
        if small is not None:
            if len(small) != SMALL_SIZE:
                raise ValueError(f"Нижняя область SPI должна иметь 0x{SMALL_SIZE:X} байт")
            self.at25[:SMALL_SIZE] = small
        # Logical firmware path 0x06A0 is not a second output image: it maps to
        # the first 8 KiB of this same SPI dump.  memoryview keeps writes shared.
        self.small = memoryview(self.at25)[:SMALL_SIZE]
        self.original_at25 = bytes(self.at25)
        self.original_small = self.original_at25[:SMALL_SIZE]
        # Схема CRC определяется по самому образу: у прошивок этой серии
        # раскладка одна, а алгоритм контрольной суммы разный.
        self.crc_scheme, self.crc_scheme_hits = self.detect_crc_scheme()
        set_crc_scheme(self.crc_scheme)

    def detect_crc_scheme(self) -> tuple[str, dict[str, int]]:
        """Подбирает схему CRC: побеждает та, по которой сходится больше записей.

        Если не сходится ни одна (пустой или чужой образ), остаётся схема
        по умолчанию — поведение для родных дампов CE208 не меняется.
        """
        hits: dict[str, int] = {}
        for name, (_title, function) in CRC_SCHEMES.items():
            count = 0
            for descriptor in FIXED_DESCRIPTORS:
                for path, address in (
                    (descriptor.path, descriptor.primary),
                    (descriptor.backup_path, descriptor.backup),
                ):
                    if address is None:
                        continue
                    store = self.at25 if path == "at25" else self.small
                    if address + descriptor.length > len(store):
                        continue
                    record = bytes(store[address:address + descriptor.length])
                    stored = struct.unpack("<H", record[-2:])[0]
                    if function(record[:-2]) == stored:
                        count += 1
            hits[name] = count
        best = max(hits, key=lambda name: hits[name])
        return (best if hits[best] else DEFAULT_CRC_SCHEME), hits

    @classmethod
    def load_spi(cls, at25_path: str | Path) -> "CE208State":
        return cls(at25=Path(at25_path).read_bytes())

    def storage(self, path: str) -> bytearray | memoryview:
        if path == "small":
            return self.small
        if path == "at25":
            return self.at25
        raise ValueError(f"Неизвестная память {path}")

    def inspect_record(self, path: str, address: int, length: int) -> RecordResult:
        store = self.storage(path)
        if address < 0 or address + length > len(store):
            raise ValueError("Запись выходит за границы памяти")
        record = bytes(store[address:address + length])
        valid, stored, calculated = verify_record(record)
        return RecordResult(path, address, record, valid, stored, calculated)

    def read_descriptor(self, descriptor: Descriptor) -> RecordResult:
        primary = self.inspect_record(descriptor.path, descriptor.primary, descriptor.length)
        if primary.valid:
            return primary
        if descriptor.backup_path is None or descriptor.backup is None:
            return primary
        return self.inspect_record(descriptor.backup_path, descriptor.backup, descriptor.length)

    def write_descriptor_body(self, descriptor: Descriptor, body: bytes | bytearray, write_backup: bool = True) -> bytes:
        record = build_record(body, descriptor.length)
        primary = self.storage(descriptor.path)
        primary[descriptor.primary:descriptor.primary + descriptor.length] = record
        if write_backup and descriptor.backup_path is not None and descriptor.backup is not None:
            backup = self.storage(descriptor.backup_path)
            backup[descriptor.backup:descriptor.backup + descriptor.length] = record
        return record

    def read_clock(self) -> tuple[ClockValue, RecordResult]:
        descriptor = next(item for item in FIXED_DESCRIPTORS if item.name == "clock_snapshot")
        result = self.read_descriptor(descriptor)
        if not result.valid:
            raise ValueError("Обе копии времени имеют неверную CRC")
        return ClockValue.from_body(result.record[:-2]), result

    def write_clock(self, value: ClockValue) -> bytes:
        descriptor = next(item for item in FIXED_DESCRIPTORS if item.name == "clock_snapshot")
        return self.write_descriptor_body(descriptor, value.body())

    def read_active_tariff(self) -> tuple[int, RecordResult]:
        descriptor = next(item for item in FIXED_DESCRIPTORS if item.name == "tariff_control")
        result = self.read_descriptor(descriptor)
        if not result.valid:
            raise ValueError("Обе копии tariff_control имеют неверную CRC")
        tariff = result.record[0] & 0x0F
        if not 1 <= tariff <= 8:
            raise ValueError(f"В записи находится недопустимый активный тариф {tariff}")
        return tariff, result

    def write_active_tariff(self, tariff: int) -> bytes:
        if not 1 <= tariff <= 8:
            raise ValueError("Активный тариф должен быть 1..8")
        descriptor = next(item for item in FIXED_DESCRIPTORS if item.name == "tariff_control")
        body = self._descriptor_body_or_zero(descriptor)
        body[0] = (body[0] & 0xF0) | tariff
        return self.write_descriptor_body(descriptor, body)

    def time_counter_address(self, block: int) -> int:
        if not 0 <= block < TIME_COUNTER_BLOCKS:
            raise ValueError("Штатный блок временных счётчиков должен быть 0 или 1")
        return TIME_COUNTER_PRIMARY + block * TIME_COUNTER_RECORD_SIZE

    def read_time_counters(self, block: int) -> tuple[TimeCounterBlock, RecordResult]:
        address = self.time_counter_address(block)
        result = self.inspect_record("small", address, TIME_COUNTER_RECORD_SIZE)
        if not result.valid:
            raise ValueError(f"Блок временных счётчиков {block} имеет неверную CRC")
        return TimeCounterBlock.from_record(result.record), result

    def write_time_counters(self, block: int, value: TimeCounterBlock) -> bytes:
        record = value.to_record()
        address = self.time_counter_address(block)
        self.small[address:address + TIME_COUNTER_RECORD_SIZE] = record
        return record

    def current_energy_address(self, bank: int, backup: bool = False) -> int:
        if not 0 <= bank < ENERGY_BANK_COUNT:
            raise ValueError("Банк энергии должен быть 0..3")
        return (CURRENT_ENERGY_BACKUP if backup else CURRENT_ENERGY_PRIMARY) + bank * ENERGY_RECORD_SIZE

    def read_current_energy(self, bank: int) -> tuple[EnergyBank, RecordResult]:
        primary = self.inspect_record("small", self.current_energy_address(bank), ENERGY_RECORD_SIZE)
        result = primary if primary.valid else self.inspect_record("small", self.current_energy_address(bank, True), ENERGY_RECORD_SIZE)
        if not result.valid:
            raise ValueError(f"Обе копии текущего энергетического банка {bank} имеют неверную CRC")
        return EnergyBank.from_record(result.record), result

    def write_current_energy(self, bank: int, value: EnergyBank) -> bytes:
        record = value.to_record()
        for backup in (False, True):
            address = self.current_energy_address(bank, backup)
            self.small[address:address + ENERGY_RECORD_SIZE] = record
        return record

    def synchronize_current_tariffs(self, bank: int, tariffs: Iterable[int]) -> EnergyBank:
        """Set T1..Tn and synchronize all dependent persistent fields."""
        values = list(tariffs)
        if not 1 <= len(values) <= 8:
            raise ValueError("Количество тарифов должно быть 1..8")
        try:
            energy, _ = self.read_current_energy(bank)
        except ValueError:
            energy = EnergyBank.empty()
        energy.set_tariffs(values + [0] * (8 - len(values)))
        self.write_current_energy(bank, energy)
        try:
            active_tariff, _ = self.read_active_tariff()
        except ValueError:
            active_tariff = 1
        if active_tariff > len(values):
            active_tariff = 1
        self.write_active_tariff(active_tariff)
        return energy

    def synchronize_energy_everywhere(
        self,
        banks: Iterable[int],
        tariffs: Iterable[int],
        archive_marker: int = 0,
    ) -> dict:
        """Rewrite current values and every archive slot for selected banks."""
        selected_banks = list(dict.fromkeys(banks))
        values = list(tariffs)
        if not selected_banks or any(bank < 0 or bank >= ENERGY_BANK_COUNT for bank in selected_banks):
            raise ValueError("Нужно выбрать энергетический банк 0..3")
        if not 1 <= len(values) <= 8:
            raise ValueError("Количество тарифов должно быть 1..8")
        if not 0 <= archive_marker <= 0xFF:
            raise ValueError("Маркер архива должен помещаться в байт")
        padded = values + [0] * (8 - len(values))
        current_records = 0
        archive_records = 0
        per_type: dict[int, int] = {}
        for bank in selected_banks:
            self.synchronize_current_tariffs(bank, values)
            current_records += 2  # primary + backup
            for archive_type, (_base, count, _name) in ENERGY_ARCHIVES.items():
                written = 0
                for slot in range(count):
                    try:
                        archived, _ = self.read_archive_energy(archive_type, slot, bank)
                    except ValueError:
                        archived = EnergyBank.empty()
                        archived.marker = archive_marker
                    archived.set_tariffs(padded)
                    self.write_archive_energy(archive_type, slot, bank, archived)
                    written += 1
                per_type[archive_type] = per_type.get(archive_type, 0) + written
                archive_records += written
        return {
            "banks": selected_banks,
            "tariff_count": len(values),
            "current_physical_records": current_records,
            "archive_records": archive_records,
            "archive_records_by_type": per_type,
        }

    def archive_address(self, archive_type: int, slot: int, bank: int) -> int:
        try:
            base, count, _ = ENERGY_ARCHIVES[archive_type]
        except KeyError as exc:
            raise ValueError("Штатный архив энергии имеет тип 0, 1, 2 или 5") from exc
        if not 0 <= bank < ENERGY_BANK_COUNT:
            raise ValueError("Банк энергии должен быть 0..3")
        # 0x2DDA8 applies slot modulo archive count.
        normalized = slot % count
        return base + normalized * 0x110 + bank * ENERGY_RECORD_SIZE

    def read_archive_energy(self, archive_type: int, slot: int, bank: int) -> tuple[EnergyBank, RecordResult]:
        address = self.archive_address(archive_type, slot, bank)
        result = self.inspect_record("at25", address, ENERGY_RECORD_SIZE)
        if not result.valid:
            raise ValueError(f"Архивная запись @0x{address:05X} имеет неверную CRC")
        return EnergyBank.from_record(result.record), result

    def write_archive_energy(self, archive_type: int, slot: int, bank: int, value: EnergyBank, marker: int | None = None) -> bytes:
        if marker is not None:
            value.marker = marker & 0xFF
        record = value.to_record()
        address = self.archive_address(archive_type, slot, bank)
        self.at25[address:address + ENERGY_RECORD_SIZE] = record
        return record

    def _descriptor_body_or_zero(self, descriptor: Descriptor) -> bytearray:
        result = self.read_descriptor(descriptor)
        if result.valid:
            return bytearray(result.record[:-2])
        return bytearray(descriptor.length - 2)

    def event_log(self, event_id: int) -> EventLog:
        try:
            return EVENT_LOGS[event_id]
        except KeyError as exc:
            raise ValueError("ID журнала события должен быть 0..69") from exc

    def event_index_descriptor(self, group: int) -> Descriptor:
        if not 0 <= group < EVENT_INDEX_GROUPS:
            raise ValueError("Группа журнала должна быть 0..8")
        return next(item for item in FIXED_DESCRIPTORS if item.name == f"event_index_group{group}")

    def event_global_counter(self) -> int:
        descriptor = next(item for item in FIXED_DESCRIPTORS if item.name == "event_sequence_header")
        body = self._descriptor_body_or_zero(descriptor)
        return struct.unpack_from("<I", body)[0]

    def event_count(self, event_id: int) -> int:
        log = self.event_log(event_id)
        body = self._descriptor_body_or_zero(self.event_index_descriptor(log.group))
        return struct.unpack_from("<I", body, log.sub * 4)[0]

    def event_address(self, event_id: int, counter: int) -> int:
        log = self.event_log(event_id)
        return log.base + (counter % log.capacity) * log.record_length

    def read_event(self, event_id: int, history_offset: int = 0) -> tuple[EventRecord, RecordResult, int]:
        log = self.event_log(event_id)
        counter = self.event_count(event_id)
        available = min(counter, log.capacity)
        if history_offset < 0 or history_offset >= available:
            raise ValueError(f"В журнале доступно записей: {available}")
        record_counter = (counter - history_offset) & 0xFFFFFFFF
        address = self.event_address(event_id, record_counter)
        result = self.inspect_record("at25", address, log.record_length)
        if not result.valid:
            raise ValueError(f"Событие @0x{address:05X} имеет неверную CRC")
        return EventRecord.from_record(log, result.record), result, record_counter

    def append_event(
        self,
        event_id: int,
        timestamp: datetime,
        status: int = 0,
        value: int | None = None,
    ) -> tuple[EventRecord, int, int]:
        """Reproduce 0x4364C + 0x4366C + 0x2E876 for one event."""
        log = self.event_log(event_id)

        header = next(item for item in FIXED_DESCRIPTORS if item.name == "event_sequence_header")
        header_body = self._descriptor_body_or_zero(header)
        global_counter = (struct.unpack_from("<I", header_body)[0] + 1) & 0xFFFFFFFF
        struct.pack_into("<I", header_body, 0, global_counter)
        self.write_descriptor_body(header, header_body)

        index_descriptor = self.event_index_descriptor(log.group)
        index_body = self._descriptor_body_or_zero(index_descriptor)
        event_counter = (struct.unpack_from("<I", index_body, log.sub * 4)[0] + 1) & 0xFFFFFFFF
        struct.pack_into("<I", index_body, log.sub * 4, event_counter)
        self.write_descriptor_body(index_descriptor, index_body)

        event = EventRecord(timestamp.replace(microsecond=0), global_counter & 0xFFFFFF, status, value)
        record = event.to_record(log)
        address = self.event_address(event_id, event_counter)
        self.at25[address:address + log.record_length] = record
        return event, address, event_counter

    def changed_counts(self) -> tuple[int, int]:
        small = sum(a != b for a, b in zip(self.original_small, self.small))
        at25 = sum(a != b for a, b in zip(self.original_at25, self.at25))
        return small, at25

    def save_spi(self, at25_path: str | Path) -> None:
        Path(at25_path).write_bytes(self.at25)

    def audit(self) -> dict:
        small_changed, at25_changed = self.changed_counts()
        descriptors = []
        for descriptor in FIXED_DESCRIPTORS:
            try:
                result = self.read_descriptor(descriptor)
                status = {
                    "selected_source": result.source,
                    "selected_address": f"0x{result.address:05X}",
                    "valid": result.valid,
                    "stored_crc": f"0x{result.stored_crc:04X}",
                    "calculated_crc": f"0x{result.calculated_crc:04X}",
                }
            except ValueError as exc:
                status = {"valid": False, "error": str(exc)}
            descriptors.append({"name": descriptor.name, **status})
        return {
            "logical_low_8k_inside_spi": {
                "size": SMALL_SIZE,
                "original_sha256": sha256(self.original_small),
                "current_sha256": sha256(self.small),
                "changed_bytes": small_changed,
            },
            "spi_25df041b": {
                "size": AT25_SIZE,
                "original_sha256": sha256(self.original_at25),
                "current_sha256": sha256(self.at25),
                "changed_bytes": at25_changed,
            },
            "event_logs": {
                "catalog_entries": len(EVENT_LOGS),
                "range": "0x47E70..0x49DEF",
                "global_sequence": self.event_global_counter(),
                "nonempty": [
                    {"event_id": event_id, "count": count}
                    for event_id in EVENT_LOGS
                    if (count := self.event_count(event_id)) != 0
                ],
            },
            "descriptors": descriptors,
        }

    def save_audit(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.audit(), ensure_ascii=False, indent=2), encoding="utf-8")


def at25_program_sectors(original: bytes, target: bytes) -> list[dict]:
    """Build sector/page operations respecting NOR 1->0 programming."""
    if len(original) != AT25_SIZE or len(target) != AT25_SIZE:
        raise ValueError("План AT25 требует два полных 512-КиБ образа")
    operations: list[dict] = []
    for sector in range(0, AT25_SIZE, AT25_SECTOR):
        old_sector = original[sector:sector + AT25_SECTOR]
        new_sector = target[sector:sector + AT25_SECTOR]
        if old_sector == new_sector:
            continue
        erase = any((new & ~old) != 0 for old, new in zip(old_sector, new_sector))
        operations.append({"op": "ERASE_4K" if erase else "NO_ERASE", "address": f"0x{sector:06X}"})
        reference = b"\xFF" * AT25_SECTOR if erase else old_sector
        for page in range(0, AT25_SECTOR, AT25_PAGE):
            address = sector + page
            old_page = reference[page:page + AT25_PAGE]
            new_page = new_sector[page:page + AT25_PAGE]
            changed = [index for index, pair in enumerate(zip(old_page, new_page)) if pair[0] != pair[1]]
            if changed:
                first, last = changed[0], changed[-1]
                operations.append({
                    "op": "PAGE_PROGRAM",
                    "address": f"0x{address + first:06X}",
                    "length": last - first + 1,
                    "data": new_page[first:last + 1].hex().upper(),
                })
    return operations
