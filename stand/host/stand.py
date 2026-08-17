"""
Транспортное ядро для двустороннего обмена со стендом.

Кадрирование, CRC и коды ответов реконструированы из прошивки —
см. stand/docs/PROTOCOL.md. Всё, что здесь есть, подтверждено
дизассемблированием; прикладные команды будут добавляться сверху.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

# Скорости из таблиц flash 0xFB18/0xFB1E при SMCLK = 12 МГц.
# Индекс совпадает с полем 3:0 байта конфигурации 0x04E0.
BAUD_TABLE = {0: 19200, 1: 9600, 2: 4800, 3: 2400, 4: 1200, 5: 600}
BAUD_DEFAULT = 4800
PARITY_DEFAULT = "O"  # UCAxCTL0 = 0x80 в аварийной ветке 0x4936

# Межсимвольный тайм-аут в тех же условных единицах, что и таблица 0xFB24.
FRAME_TIMEOUT_UNITS = {0: 5, 1: 10, 2: 20, 3: 40, 4: 80, 5: 160}

ADDR_BROADCAST = 0x00
ADDR_SERVICE = 0xFE  # стенд обрабатывает, но НЕ отвечает

MAX_FRAME = 24  # размер буфера канала в прошивке

RESULT_OK = 0x00
RESULT_BAD_REQUEST = 0x01
RESULT_INTERNAL = 0x02

RESULT_TEXT = {
    RESULT_OK: "успех",
    RESULT_BAD_REQUEST: "неверная команда или параметр",
    RESULT_INTERNAL: "внутренняя ошибка",
}


def crc16(data: bytes) -> int:
    """CRC-16/MODBUS: полином 0xA001, init 0xFFFF, без финального XOR."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def build(payload: bytes) -> bytes:
    """Дописывает CRC младшим байтом вперёд, как это делает 0xB894."""
    crc = crc16(payload)
    return payload + bytes((crc & 0xFF, crc >> 8))


def check(frame: bytes) -> bool:
    """Кадр целостен, если CRC всего кадра вместе с контрольными байтами равен нулю."""
    return len(frame) >= 4 and crc16(frame) == 0


class StandError(Exception):
    pass


class ProtocolError(StandError):
    pass


class ResultError(StandError):
    def __init__(self, code: int):
        self.code = code
        text = RESULT_TEXT.get(code & 0x7F, f"код {code:#04x}")
        super().__init__(f"стенд вернул ошибку: {text}")


@dataclass
class Identity:
    serial: int
    day: int
    month: int
    year: int

    def __str__(self) -> str:
        return f"№{self.serial}, выпуск {self.day:02d}.{self.month:02d}.20{self.year:02d}"


class Stand:
    """Синхронный клиент стенда поверх pyserial."""

    def __init__(
        self,
        port: str,
        address: int = ADDR_BROADCAST,
        baudrate: int = BAUD_DEFAULT,
        parity: str = PARITY_DEFAULT,
        timeout: float = 0.5,
        retries: int = 3,
    ):
        import serial  # импорт здесь, чтобы модуль можно было использовать без железа

        if baudrate not in BAUD_TABLE.values():
            raise ValueError(f"стенд поддерживает только {sorted(BAUD_TABLE.values())}")

        self.address = address
        self.retries = retries
        self._timeout = timeout
        self._serial = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity={"N": serial.PARITY_NONE,
                    "O": serial.PARITY_ODD,
                    "E": serial.PARITY_EVEN}[parity],
            stopbits=serial.STOPBITS_ONE,
            timeout=timeout,
        )
        # Пауза между кадрами: стенд разделяет их межсимвольным тайм-аутом.
        self._gap = 40.0 / baudrate * 3

    def close(self) -> None:
        self._serial.close()

    def __enter__(self) -> "Stand":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---- транспорт -------------------------------------------------

    def transfer(self, payload: bytes, expect: int | None = None) -> bytes:
        """Отправляет кадр и возвращает тело ответа без адреса и CRC.

        `expect` — ожидаемая полная длина ответа; None означает «читать до
        межсимвольной паузы».
        """
        if len(payload) + 2 > MAX_FRAME:
            raise ValueError(f"кадр длиннее {MAX_FRAME} байт")

        frame = build(payload)
        last: Exception = ProtocolError("нет ответа")

        for _ in range(self.retries):
            time.sleep(self._gap)
            self._serial.reset_input_buffer()
            self._serial.write(frame)
            self._serial.flush()

            reply = self._read_reply(expect)
            if not reply:
                last = ProtocolError("нет ответа от стенда")
                continue
            if not check(reply):
                last = ProtocolError(f"ошибка CRC в ответе: {reply.hex(' ')}")
                continue
            if reply[0] != payload[0]:
                last = ProtocolError(
                    f"чужой адрес в ответе: {reply[0]:#04x} вместо {payload[0]:#04x}")
                continue

            body = reply[1:-2]
            # Квитанция: один байт кода результата.
            if len(body) == 1 and body[0] & 0x7F != RESULT_OK:
                raise ResultError(body[0])
            return body

        raise last

    def _read_reply(self, expect: int | None) -> bytes:
        if expect is not None:
            return self._serial.read(expect)
        # Кадр закончился, когда пауза превысила межсимвольный интервал.
        data = bytearray()
        deadline = time.monotonic() + self._timeout
        while time.monotonic() < deadline:
            chunk = self._serial.read(MAX_FRAME)
            if chunk:
                data += chunk
                deadline = time.monotonic() + self._gap
            elif data:
                break
        return bytes(data)

    # ---- команды, подтверждённые дизассемблированием ---------------

    def test_link(self) -> bool:
        """CMD 0x00 — тест канала связи (обработчик 0x8498, длина запроса 4)."""
        self.transfer(bytes((self.address, 0x00)), expect=4)
        return True

    def open_channel(self, password: bytes, level: int = 1) -> None:
        """CMD 0x01 — открытие канала (0x84F4, длина запроса 11)."""
        if level not in (1, 2):
            raise ValueError("уровень доступа: 1 или 2")
        if len(password) != 6:
            raise ValueError("пароль ровно 6 байт")
        self.transfer(bytes((self.address, 0x01, level)) + password, expect=4)

    def close_channel(self) -> None:
        """CMD 0x02 — закрытие канала (0x8590, длина запроса 4)."""
        self.transfer(bytes((self.address, 0x02)), expect=4)

    def read_identity(self) -> Identity:
        """CMD 0x08/0x00 — серийный номер и дата выпуска (0xAEC0, 7 байт из INFO 0x1080)."""
        body = self.transfer(bytes((self.address, 0x08, 0x00)), expect=10)
        if len(body) != 7:
            raise ProtocolError(f"ожидалось 7 байт, получено {len(body)}")
        return Identity(int.from_bytes(body[:4], "big"), body[4], body[5], body[6])

    def read_address(self) -> int:
        """CMD 0x08/0x05 — сетевой адрес узла (0xAF60)."""
        body = self.transfer(bytes((self.address, 0x08, 0x05)), expect=4)
        if len(body) != 1:
            raise ProtocolError(f"ожидался 1 байт, получено {len(body)}")
        return body[0]

    def raw(self, cmd: int, *args: int, expect: int | None = None) -> bytes:
        """Произвольная команда — для разбора ещё не описанных подкоманд."""
        return self.transfer(bytes((self.address, cmd, *args)), expect=expect)


def find_stand(port: str, address: int = ADDR_BROADCAST) -> tuple[int, str]:
    """Перебирает скорости и чётность, пока стенд не ответит на тест связи.

    Возвращает найденную пару (скорость, чётность).
    """
    for baud in sorted(BAUD_TABLE.values(), reverse=True):
        for parity in ("O", "E", "N"):
            try:
                with Stand(port, address, baud, parity, timeout=0.3, retries=1) as s:
                    s.test_link()
                    return baud, parity
            except StandError:
                continue
    raise StandError("стенд не отвечает ни на одной поддерживаемой скорости")
