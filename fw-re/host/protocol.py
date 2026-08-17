"""Протокол обмена с исследуемым устройством (MSP430F249).

Восстановлен реверс-инжинирингом прошивки. Кадр строится по образцу
Modbus RTU, контрольная сумма — CRC-16/Modbus (полином 0xA001, init 0xFFFF,
порядок байтов в кадре — младший вперёд), что подтверждено сравнением с
табличной реализацией прошивки (таблицы auchCRCHi@0xFB3C, auchCRCLo@0xFC3C)
и обработчиком приёма sub_823E / расчётом sub_BBF6.

Структура кадра (восстановлено из sub_823E):
    +--------+--------+------------------+---------+---------+
    | addr   | func   |   данные...      | CRC_lo  | CRC_hi  |
    +--------+--------+------------------+---------+---------+
      byte0    byte1        N байт          CRC-16/Modbus

  * addr  — адрес устройства; собственный адрес хранится в ОЗУ по 0x04FE,
            0x00 и 0xFE трактуются как широковещательные (см. 0x833A..0x834E);
  * func  — код функции 0x00..0x08; диспетчеризация — таблица переходов
            по адресу 0x8474 (index*4 + PC);
  * данные — зависят от функции; байт данных [0] (смещение 2 в кадре)
            обычно задаёт подкоманду/номер параметра.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

# --- Таблицы CRC-16/Modbus, эквивалентные зашитым в прошивку ---------------
# В прошивке лежат две таблицы: auchCRClo @0xFB3C и auchCRChi @0xFC3C
# (полином 0xA001). Здесь они восстановлены расчётом и используются для
# проверки эквивалентности (см. host/tests/test_protocol.py).

def _build_tables():
    hi = [0] * 256
    lo = [0] * 256
    for i in range(256):
        crc = i
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
        hi[i] = (crc >> 8) & 0xFF
        lo[i] = crc & 0xFF
    return hi, lo


_CRC_HI, _CRC_LO = _build_tables()


def crc16(data: Sequence[int], init: int = 0xFFFF) -> int:
    """CRC-16/Modbus (полином 0xA001, init 0xFFFF).

    Возвращает стандартное значение свёртки. В кадре оно передаётся младшим
    байтом вперёд (см. Frame.encode), что совпадает с порядком сравнения в
    приёмнике прошивки (sub_83A2). Внутренний регистр прошивки (sub_BC22)
    хранит байт-инвертированное значение — эквивалентность проверяется тестом
    test_firmware_algorithm_bytewise.
    """
    crc = init & 0xFFFF
    for b in data:
        crc ^= b & 0xFF
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


# --- Контрольная сумма коротких служебных пакетов -------------------------
# Используется для внутренних 3-словных структур (sub_4A72 / 0x7C58):
#   csum = 0xF0F0 XOR w0 XOR w1 XOR w2

def xor_checksum(words: Sequence[int], seed: int = 0xF0F0) -> int:
    acc = seed & 0xFFFF
    for w in words:
        acc ^= w & 0xFFFF
    return acc


# --- Функциональные коды устройства ---------------------------------------

class Func:
    """Коды функций (byte1 кадра). Назначение по анализу обработчиков."""
    F0_CONFIG_BITS = 0x00   # 0x8498  установка битовой конфигурации (0x07D0/0x07D7)
    F1_MODE = 0x01          # 0x84F4  выбор режима/сохранение (подкоманда в byte2)
    F2_RESET_FLAG = 0x02    # 0x8590  сброс служебного флага 0x02A1
    F3_ECHO = 0x03          # 0x85B2  проверка адреса / служебная
    F4_READ = 0x04          # 0xA0FE  чтение параметра/области
    F5_WRITE = 0x05         # 0xA3B6  запись параметра
    F6_BLOCK = 0x06         # 0xA7C6  блочная операция (byte5 — длина/индекс)
    F7_EXT = 0x07           # 0xAAEC  расширенная операция (byte5 + 8 = длина)
    F8_PARAM = 0x08         # 0xAD98  доступ к калибровочным параметрам


BROADCAST = 0xFE


@dataclass
class Frame:
    addr: int
    func: int
    data: bytes = b""

    def encode(self) -> bytes:
        """Собрать кадр с CRC-16/Modbus (младший байт CRC вперёд)."""
        body = bytes([self.addr & 0xFF, self.func & 0xFF]) + bytes(self.data)
        crc = crc16(body)
        return body + bytes([crc & 0xFF, (crc >> 8) & 0xFF])

    @classmethod
    def decode(cls, raw: bytes) -> "Frame":
        """Разобрать кадр, проверить CRC. Бросает ValueError при ошибке."""
        if len(raw) < 4:
            raise ValueError("кадр короче 4 байт")
        body, crc_lo, crc_hi = raw[:-2], raw[-2], raw[-1]
        want = crc16(body)
        got = crc_lo | (crc_hi << 8)
        if want != got:
            raise ValueError(f"неверный CRC: получен 0x{got:04X}, ожидался 0x{want:04X}")
        return cls(addr=body[0], func=body[1], data=bytes(body[2:]))

    def __repr__(self) -> str:
        return (f"Frame(addr=0x{self.addr:02X}, func=0x{self.func:02X}, "
                f"data={self.data.hex()})")


# --- Высокоуровневые построители команд -----------------------------------

def read_param(addr: int, index: int, length: int = 1) -> bytes:
    """Команда чтения параметра/области (func 0x04)."""
    return Frame(addr, Func.F4_READ, bytes([index & 0xFF, length & 0xFF])).encode()


def write_param(addr: int, index: int, value: Sequence[int]) -> bytes:
    """Команда записи параметра (func 0x05)."""
    return Frame(addr, Func.F5_WRITE, bytes([index & 0xFF, *value])).encode()


def read_calibration(addr: int, param: int) -> bytes:
    """Чтение калибровочного коэффициента (func 0x08, подкоманда 0x01)."""
    return Frame(addr, Func.F8_PARAM, bytes([0x01, param & 0xFF])).encode()


def write_calibration(addr: int, param: int, value16: int) -> bytes:
    """Запись калибровочного коэффициента (func 0x08, подкоманда 0x12)."""
    return Frame(addr, Func.F8_PARAM,
                 bytes([0x12, param & 0xFF, value16 & 0xFF, (value16 >> 8) & 0xFF])
                 ).encode()


def hexdump(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)
