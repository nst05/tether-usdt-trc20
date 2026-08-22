#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Работа с SPI FRAM напрямую через программатор CH341.

Транспорт отделён от протокола: SPIFram принимает любой объект с методом
transfer(bytes) -> bytes. В работе это CH341SPI, в тестах — эмулятор
микросхемы. Иначе протокол пришлось бы проверять только на живом железе.
"""

import ctypes
import os
import sys
import time

# ═══════════════════════════════════════════════════════════════════════════
#  Команды SPI FRAM
# ═══════════════════════════════════════════════════════════════════════════

CMD_WREN = 0x06     # разрешить запись
CMD_WRDI = 0x04     # запретить запись
CMD_RDSR = 0x05     # прочитать регистр состояния
CMD_WRSR = 0x01     # записать регистр состояния
CMD_READ = 0x03     # чтение
CMD_WRITE = 0x02    # запись
CMD_RDID = 0x9F     # идентификатор устройства

SR_WEL = 0x02       # бит «запись разрешена» в регистре состояния


# ═══════════════════════════════════════════════════════════════════════════
#  Профили микросхем
# ═══════════════════════════════════════════════════════════════════════════
#
# addr_bytes — сколько байт адреса уходит после команды.
# a8_in_opcode — девятый бит адреса едет в бит 3 самой команды, а не в
#   байт адреса. Так устроен FM25L04B: адресный байт всего один, а память
#   512 байт, и без этого бита вторая половина недоступна.
# has_rdid — отвечает ли микросхема на 0x9F.

CHIPS = {
    "MB85RS64":  {"size": 8192,  "addr_bytes": 2, "a8_in_opcode": False,
                  "has_rdid": True,  "title": "MB85RS64 · 64 Кбит · 8 КБ"},
    "MB85RS128": {"size": 16384, "addr_bytes": 2, "a8_in_opcode": False,
                  "has_rdid": True,  "title": "MB85RS128 · 128 Кбит · 16 КБ"},
    "MB85RS256": {"size": 32768, "addr_bytes": 2, "a8_in_opcode": False,
                  "has_rdid": True,  "title": "MB85RS256 · 256 Кбит · 32 КБ"},
    "FM25L04B":  {"size": 512,   "addr_bytes": 1, "a8_in_opcode": True,
                  "has_rdid": False, "title": "FM25L04B · 4 Кбит · 512 Б"},
    "FM25V02":   {"size": 32768, "addr_bytes": 2, "a8_in_opcode": False,
                  "has_rdid": True,  "title": "FM25V02 · 256 Кбит · 32 КБ"},
}

# Какие микросхемы предлагаются на каждой вкладке.
TAB_CHIPS = {
    "srt03": ["MB85RS256", "MB85RS128", "MB85RS64"],
    "ar":    ["FM25L04B"],
    "srt29": ["FM25V02"],
}


class SPIError(RuntimeError):
    """Ошибка обмена по SPI"""


# ═══════════════════════════════════════════════════════════════════════════
#  Транспорт: CH341 в режиме SPI
# ═══════════════════════════════════════════════════════════════════════════

class CH341SPI:
    """
    Полудуплексный обмен по SPI через CH341DLL.

    Используется CH341StreamSPI4 — четырёхпроводной SPI, полный дуплекс:
    буфер отдаётся на запись и им же возвращается принятое. Поэтому чтение
    выглядит как передача пустых байт нужной длины.
    """

    # Старший бит первым. Бит 7 в режиме потока отвечает за порядок бит:
    # 0 — младшим вперёд, 1 — старшим. SPI FRAM ждёт старший вперёд, и это
    # самая частая причина, по которой «читается мусор».
    STREAM_MODE_MSB = 0x80

    # Бит 7 — использовать сигнал выбора кристалла, младшие два бита
    # выбирают ножку: 0 = D0, 1 = D1, 2 = D2.
    CS_D0 = 0x80

    def __init__(self, index: int = 0, dll_path: str = None):
        self.index = index
        self.dll = None
        self._dll_path = dll_path
        self._opened = False

    # ── Загрузка библиотеки ───────────────────────────────────────────

    @staticmethod
    def default_dll_name() -> str:
        if sys.maxsize > 2147483647:
            return "CH341DLLA64.dll"
        return "CH341DLL.dll"

    def _load_dll(self):
        if self.dll is not None:
            return

        name = self._dll_path or os.environ.get("CH341DLL") or self.default_dll_name()

        try:
            self.dll = ctypes.windll.LoadLibrary(name)
        except AttributeError:
            # Не Windows: ctypes.windll отсутствует.
            raise SPIError(
                "Прямая работа с CH341 доступна только под Windows."
            )
        except OSError as exc:
            raise SPIError(
                f"Не удалось загрузить {name}: {exc}\n"
                "Положите библиотеку рядом с программой или укажите путь "
                "в переменной окружения CH341DLL."
            )

        self.dll.CH341OpenDevice.restype = ctypes.c_void_p
        self.dll.CH341OpenDevice.argtypes = [ctypes.c_ulong]
        self.dll.CH341CloseDevice.argtypes = [ctypes.c_ulong]
        self.dll.CH341SetStream.argtypes = [ctypes.c_ulong, ctypes.c_ulong]
        self.dll.CH341StreamSPI4.argtypes = [
            ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p]

    # ── Соединение ────────────────────────────────────────────────────

    def open(self):
        self._load_dll()

        handle = self.dll.CH341OpenDevice(self.index)
        # Библиотека возвращает INVALID_HANDLE_VALUE (-1) при неудаче.
        if handle in (None, 0) or ctypes.c_long(handle).value == -1:
            raise SPIError(
                f"Программатор CH341 №{self.index} не найден. "
                "Проверьте подключение и драйверы."
            )

        if not self.dll.CH341SetStream(self.index, self.STREAM_MODE_MSB):
            self.dll.CH341CloseDevice(self.index)
            raise SPIError("Не удалось перевести CH341 в режим SPI.")

        self._opened = True

    def close(self):
        if self._opened and self.dll is not None:
            try:
                self.dll.CH341CloseDevice(self.index)
            except Exception:
                pass
        self._opened = False

    def transfer(self, payload: bytes) -> bytes:
        """Отдать байты и вернуть принятые за ту же посылку"""
        if not self._opened:
            raise SPIError("Программатор не открыт.")

        buffer = ctypes.create_string_buffer(bytes(payload), len(payload))
        ok = self.dll.CH341StreamSPI4(
            self.index, self.CS_D0, len(payload), ctypes.byref(buffer))
        if not ok:
            raise SPIError("Обмен по SPI не удался (CH341StreamSPI4).")

        return bytes(buffer.raw[:len(payload)])


# ═══════════════════════════════════════════════════════════════════════════
#  Протокол SPI FRAM
# ═══════════════════════════════════════════════════════════════════════════

class SPIFram:
    """
    Чтение и запись SPI FRAM.

    FRAM пишется побайтово и без задержек: цикла стирания у неё нет, и
    страничных границ, о которые спотыкается EEPROM, — тоже. Единственное
    обязательное условие — WREN перед каждой командой записи.
    """

    # Обмен режется на куски: CH341 не любит гигантские посылки, а память
    # на 32 КБ иначе ушла бы одним буфером.
    CHUNK = 1024

    def __init__(self, chip: str, transport=None):
        if chip not in CHIPS:
            raise ValueError(f"Неизвестная микросхема: {chip}")

        self.chip = chip
        self.profile = CHIPS[chip]
        self.transport = transport

    # ── Свойства профиля ──────────────────────────────────────────────

    @property
    def size(self) -> int:
        return self.profile["size"]

    @property
    def addr_bytes(self) -> int:
        return self.profile["addr_bytes"]

    @property
    def title(self) -> str:
        return self.profile["title"]

    # ── Кадр команды ──────────────────────────────────────────────────

    def _frame(self, opcode: int, address: int) -> bytes:
        """
        Собрать команду с адресом.

        У FM25L04B адресный байт один, а памяти 512 байт: девятый бит
        адреса передаётся битом 3 в самой команде. Если этого не сделать,
        вся верхняя половина будет читаться и писаться поверх нижней.
        """
        if not 0 <= address < self.size:
            raise SPIError(
                f"Адрес 0x{address:04X} вне пределов {self.chip} "
                f"(0x0000-0x{self.size - 1:04X})."
            )

        if self.profile["a8_in_opcode"]:
            opcode |= ((address >> 8) & 0x01) << 3
            return bytes([opcode, address & 0xFF])

        return bytes([opcode]) + address.to_bytes(self.addr_bytes, "big")

    # ── Базовые операции ──────────────────────────────────────────────

    def _xfer(self, payload: bytes) -> bytes:
        if self.transport is None:
            raise SPIError("Транспорт не задан.")
        return self.transport.transfer(payload)

    def read_status(self) -> int:
        return self._xfer(bytes([CMD_RDSR, 0x00]))[1]

    def write_enable(self):
        self._xfer(bytes([CMD_WREN]))

    def write_disable(self):
        self._xfer(bytes([CMD_WRDI]))

    def read_id(self) -> bytes:
        """Идентификатор устройства; пусто, если микросхема его не имеет"""
        if not self.profile["has_rdid"]:
            return b""
        return self._xfer(bytes([CMD_RDID]) + b"\x00" * 9)[1:]

    # ── Чтение и запись ───────────────────────────────────────────────

    def read(self, address: int, length: int) -> bytes:
        """Прочитать length байт с адреса address"""
        if length < 0:
            raise SPIError("Отрицательная длина чтения.")
        if address + length > self.size:
            raise SPIError(
                f"Чтение 0x{address:04X}+{length} выходит за пределы "
                f"{self.chip}."
            )

        result = bytearray()
        position = address
        remaining = length

        while remaining > 0:
            piece = min(remaining, self.CHUNK)
            # У FM25L04B команда несёт девятый бит адреса, поэтому кусок
            # не должен пересекать границу 0x100 — иначе адрес завернётся
            # внутри той же половины.
            if self.profile["a8_in_opcode"]:
                piece = min(piece, 0x100 - (position & 0xFF))

            frame = self._frame(CMD_READ, position)
            answer = self._xfer(frame + b"\x00" * piece)
            result.extend(answer[len(frame):])

            position += piece
            remaining -= piece

        return bytes(result)

    def write(self, address: int, data: bytes):
        """Записать data по адресу address"""
        data = bytes(data)
        if address + len(data) > self.size:
            raise SPIError(
                f"Запись 0x{address:04X}+{len(data)} выходит за пределы "
                f"{self.chip}."
            )

        position = address
        offset = 0

        while offset < len(data):
            piece = min(self.CHUNK, len(data) - offset)
            if self.profile["a8_in_opcode"]:
                piece = min(piece, 0x100 - (position & 0xFF))

            # WREN обязателен перед КАЖДОЙ командой записи: бит разрешения
            # сбрасывается аппаратно по завершении предыдущей.
            self.write_enable()
            frame = self._frame(CMD_WRITE, position)
            self._xfer(frame + data[offset:offset + piece])

            position += piece
            offset += piece

    def read_all(self, progress=None) -> bytes:
        """Вычитать микросхему целиком"""
        result = bytearray()
        while len(result) < self.size:
            piece = min(self.CHUNK, self.size - len(result))
            result.extend(self.read(len(result), piece))
            if progress:
                progress(int(len(result) * 100 / self.size))
        return bytes(result)

    def changed_ranges(self, old: bytes, new: bytes) -> list:
        """
        Найти непрерывные участки, где байты действительно отличаются.

        Склейки соседних участков через неизменные байты здесь нет
        намеренно: всё, что не поменялось, записываться не должно вообще,
        даже тем же самым значением.
        """
        if len(old) != len(new):
            raise SPIError("Длины буферов не совпадают.")

        ranges = []
        index = 0
        total = len(new)

        while index < total:
            if old[index] == new[index]:
                index += 1
                continue
            start = index
            while index < total and old[index] != new[index]:
                index += 1
            ranges.append((start, index))

        return ranges

    def write_changed(self, old: bytes, new: bytes, progress=None) -> int:
        """
        Записать только те байты, которые отличаются.

        Возвращает число записанных байт. Ни один неизменившийся байт не
        попадает под команду записи — соседние участки не склеиваются.
        """
        ranges = self.changed_ranges(old, new)
        written = 0

        for number, (start, end) in enumerate(ranges, start=1):
            self.write(start, new[start:end])
            written += end - start
            if progress:
                progress(int(number * 100 / len(ranges)))

        return written

    def verify(self, expected: bytes, address: int = 0) -> tuple:
        """
        Сверить содержимое микросхемы с ожидаемым.

        Возвращает (совпало, список расхождений [(адрес, было, стало)]).
        """
        actual = self.read(address, len(expected))
        bad = [(address + i, expected[i], actual[i])
               for i in range(len(expected)) if expected[i] != actual[i]]
        return (not bad), bad


# ═══════════════════════════════════════════════════════════════════════════
#  Определение микросхемы
# ═══════════════════════════════════════════════════════════════════════════

def probe_size(fram: SPIFram) -> int:
    """
    Определить реальный объём микросхемы по завороту адреса.

    Память меньше заявленной заворачивает старшие адреса на начало. Пишем
    метку в нулевой адрес и ищем, с какого объёма она начинает повторяться.
    Содержимое восстанавливается.
    """
    saved = fram.read(0, 2)
    marker = bytes([saved[0] ^ 0xFF, saved[1] ^ 0xA5])

    try:
        fram.write(0, marker)
        for size in (512, 1024, 2048, 4096, 8192, 16384, 32768):
            if size >= fram.size:
                break
            if fram.read(size, 2) == marker:
                return size
        return fram.size
    finally:
        fram.write(0, saved)
