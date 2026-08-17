"""Программный эмулятор устройства для экспериментальной проверки протокола.

Эмулятор воспроизводит поведение прошивки на уровне кадра: принимает запрос,
проверяет адрес и CRC-16/Modbus, разбирает функцию и формирует ответ по тем
же правилам, что и обработчик sub_823E. Он служит для проверки корректности
восстановленных алгоритмов без физического устройства и как транспорт-заглушка
для host/device.py.

Эмулятор сознательно упрощён: он моделирует диспетчеризацию функций,
хранилище параметров и калибровок, а также подтверждает совпадение CRC —
то есть именно те свойства протокола, которые восстановлены из прошивки.
"""
from __future__ import annotations

from typing import Dict

from protocol import Frame, Func, crc16, BROADCAST


class DeviceEmulator:
    def __init__(self, address: int = 0x01):
        self.address = address
        # Модель энергонезависимой памяти параметров и калибровок.
        self.parameters: Dict[int, bytes] = {i: bytes([i, 0x00]) for i in range(16)}
        self.calibration: Dict[int, int] = {
            0x00: 0x0100,   # масштаб канала 1 (усл. коэффициент 1.0 в Q8)
            0x01: 0x0100,   # масштаб канала 2
            0x02: 0x0100,   # масштаб канала 3
            0x03: 0x0100,   # масштаб канала 4
            0x04: 0x0000,   # смещение нуля
        }
        self.mode = 0
        self._rx = bytearray()
        self._tx = bytearray()

    # -- интерфейс транспорта (совместим с host.device.Transport) ----------
    def send(self, data: bytes) -> None:
        self._tx = bytearray(self._handle(data) or b"")

    def recv(self, timeout: float = 1.0) -> bytes:
        out, self._tx = bytes(self._tx), bytearray()
        return out

    # -- ядро обработки кадра ----------------------------------------------
    def _handle(self, raw: bytes) -> bytes:
        try:
            frame = Frame.decode(raw)
        except ValueError:
            return b""  # плохой CRC — прошивка молча отбрасывает кадр
        if frame.addr not in (self.address, 0x00, BROADCAST):
            return b""  # чужой адрес
        handler = {
            Func.F3_ECHO: self._f_echo,
            Func.F4_READ: self._f_read,
            Func.F5_WRITE: self._f_write,
            Func.F8_PARAM: self._f_param,
            Func.F1_MODE: self._f_mode,
        }.get(frame.func)
        if handler is None:
            return self._reply(frame.func | 0x80, b"\x01")  # код ошибки функции
        return handler(frame)

    def _reply(self, func: int, data: bytes) -> bytes:
        return Frame(self.address, func, data).encode()

    # -- обработчики функций ------------------------------------------------
    def _f_echo(self, frame: Frame) -> bytes:
        return self._reply(Func.F3_ECHO, frame.data)

    def _f_read(self, frame: Frame) -> bytes:
        index = frame.data[0] if frame.data else 0
        length = frame.data[1] if len(frame.data) > 1 else 1
        value = self.parameters.get(index, b"\x00\x00")[:max(1, length)]
        return self._reply(Func.F4_READ, bytes([index]) + value)

    def _f_write(self, frame: Frame) -> bytes:
        index = frame.data[0]
        self.parameters[index] = bytes(frame.data[1:])
        return self._reply(Func.F5_WRITE, bytes([index, 0x00]))  # 0x00 = OK

    def _f_mode(self, frame: Frame) -> bytes:
        if frame.data:
            self.mode = frame.data[0]
        return self._reply(Func.F1_MODE, bytes([self.mode]))

    def _f_param(self, frame: Frame) -> bytes:
        sub = frame.data[0] if frame.data else 0
        if sub == 0x01:  # чтение калибровки
            param = frame.data[1]
            v = self.calibration.get(param, 0)
            return self._reply(Func.F8_PARAM,
                               bytes([0x01, param, v & 0xFF, (v >> 8) & 0xFF]))
        if sub == 0x12:  # запись калибровки
            param = frame.data[1]
            v = frame.data[2] | (frame.data[3] << 8)
            self.calibration[param] = v
            return self._reply(Func.F8_PARAM, bytes([0x12, param, 0x00]))
        return self._reply(Func.F8_PARAM | 0x80, b"\x02")
