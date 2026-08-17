"""Клиент обмена с устройством через последовательный порт (UART).

Параметры порта восстановлены из инициализации USCI прошивки:
  UCAxCTL1 = 0xE1 (UCSSEL=SMCLK, сброс), делители BR0/BR1 = {0xC4,0x09} и
  {0x71,0x02}, что при SMCLK ≈ 1 МГц даёт скорости обмена порядка 9600
  и стандартную кратную. По умолчанию используем 9600 8N1 — типовой
  режим прибора; при необходимости скорость задаётся аргументом.

Библиотека не требует физического устройства для отладки: если pyserial
недоступен или порт не задан, транспорт можно заменить эмулятором
(host/emulator.py) — это использовано в экспериментальной проверке.
"""
from __future__ import annotations

import time
from typing import Optional, Protocol

from protocol import Frame, Func, hexdump


class Transport(Protocol):
    """Абстракция канала: отправка кадра и приём ответа."""

    def send(self, data: bytes) -> None: ...

    def recv(self, timeout: float = 1.0) -> bytes: ...


class SerialTransport:
    """Транспорт поверх физического UART (pyserial)."""

    def __init__(self, port: str, baudrate: int = 9600, timeout: float = 1.0):
        import serial  # локальный импорт: зависимость нужна лишь для «железа»
        self.ser = serial.Serial(port, baudrate, timeout=timeout,
                                 bytesize=8, parity="N", stopbits=1)

    def send(self, data: bytes) -> None:
        self.ser.reset_input_buffer()
        self.ser.write(data)
        self.ser.flush()

    def recv(self, timeout: float = 1.0) -> bytes:
        self.ser.timeout = timeout
        # Кадр переменной длины: читаем всё, что пришло за паузу молчания.
        deadline = time.time() + timeout
        buf = bytearray()
        while time.time() < deadline:
            chunk = self.ser.read(64)
            if chunk:
                buf += chunk
                deadline = time.time() + 0.05  # межсимвольный тайм-аут (T3.5)
            elif buf:
                break
        return bytes(buf)


class Device:
    """Высокоуровневый интерфейс устройства."""

    def __init__(self, transport: Transport, address: int = 0x01,
                 verbose: bool = False):
        self.t = transport
        self.address = address
        self.verbose = verbose

    def _exchange(self, request: bytes, timeout: float = 1.0) -> Optional[Frame]:
        if self.verbose:
            print(f"  -> {hexdump(request)}")
        self.t.send(request)
        raw = self.t.recv(timeout)
        if not raw:
            if self.verbose:
                print("  <- (нет ответа)")
            return None
        if self.verbose:
            print(f"  <- {hexdump(raw)}")
        return Frame.decode(raw)

    # -- операции ----------------------------------------------------------
    def read_parameter(self, index: int, length: int = 1) -> Optional[Frame]:
        req = Frame(self.address, Func.F4_READ, bytes([index, length])).encode()
        return self._exchange(req)

    def write_parameter(self, index: int, value: bytes) -> Optional[Frame]:
        req = Frame(self.address, Func.F5_WRITE, bytes([index, *value])).encode()
        return self._exchange(req)

    def read_calibration(self, param: int) -> Optional[Frame]:
        req = Frame(self.address, Func.F8_PARAM, bytes([0x01, param])).encode()
        return self._exchange(req)

    def write_calibration(self, param: int, value16: int) -> Optional[Frame]:
        req = Frame(self.address, Func.F8_PARAM,
                    bytes([0x12, param, value16 & 0xFF, (value16 >> 8) & 0xFF])
                    ).encode()
        return self._exchange(req)

    def ping(self) -> bool:
        req = Frame(self.address, Func.F3_ECHO, b"\x00").encode()
        return self._exchange(req) is not None
