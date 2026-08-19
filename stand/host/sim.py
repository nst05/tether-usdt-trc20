"""Байтовый симулятор стенда для проверки GUI без реального железа.

Реализует интерфейс, совместимый с pyserial (read/write/…), и отвечает
на безопасные команды чтения корректными кадрами с CRC. Только чтение:
записи (CMD 0x03/0x07) не обрабатываются — на них симулятор отвечает
кодом ошибки, как и положено при отсутствии прав. Значения выдаются
условные, пригодные лишь для отладки интерфейса.
"""
from __future__ import annotations
import time
from stand import crc16, build, RESULT_BAD_REQUEST

# Условные данные «прибора» для отладки интерфейса.
SIM_SERIAL = 0x2E393D1C
SIM_DATE = (0x0C, 0x03, 0x16)      # день, месяц, год — как в INFO 0x1080
SIM_ADDR = 0x2A
SIM_CONFIG = bytes((0x02, 0x00, 0x2A, 0x00))  # 0x04E0..0x04E3: скорость 4800 и т.п.
SIM_PHASES = (0x0F1E, 0x0F20, 0x0F1D)


class SimSerial:
    """Мини-замена serial.Serial: принимает кадр запроса, кладёт ответ в очередь."""

    def __init__(self, *_, **kwargs):
        self.timeout = kwargs.get("timeout", 0.5)
        self._rx = bytearray()   # то, что «прибор» отправит хосту
        self._tx = bytearray()   # то, что хост отправил прибору
        self.is_open = True

    # --- API, используемый транспортом Stand ---
    def reset_input_buffer(self):
        self._rx.clear()

    def flush(self):
        pass

    def write(self, data: bytes):
        self._tx += data
        self._handle(bytes(data))
        return len(data)

    def read(self, n: int = 1) -> bytes:
        out = bytes(self._rx[:n])
        del self._rx[:n]
        return out

    def close(self):
        self.is_open = False

    # --- логика ответа ---
    def _reply(self, addr: int, body: bytes):
        self._rx += build(bytes((addr,)) + body)

    def _ack(self, addr: int, code: int = 0):
        self._rx += build(bytes((addr, code)))

    def _handle(self, frame: bytes):
        if len(frame) < 4 or crc16(frame) != 0:
            return
        addr, cmd = frame[0], frame[1]
        args = frame[2:-2]
        r = addr if addr else SIM_ADDR
        if cmd == 0x00:                       # тест связи
            self._ack(r)
        elif cmd == 0x01:                     # открытие канала (для симуляции — всегда OK)
            self._ack(r)
        elif cmd == 0x02:                     # закрытие канала
            self._ack(r)
        elif cmd == 0x08 and args:
            sub = args[0]
            if sub == 0x00:
                self._reply(r, SIM_SERIAL.to_bytes(4, "big") + bytes(SIM_DATE))
            elif sub in (0x04, 0x05):
                self._reply(r, bytes((SIM_ADDR,)))
            elif sub == 0x02:
                self._reply(r, SIM_CONFIG)
            elif sub == 0x09:
                self._reply(r, bytes((0x00, 0x04, 0x00, 0x00, 0x00, 0x00)))
            elif sub == 0x29:
                b = b"".join(v.to_bytes(2, "big") for v in SIM_PHASES)
                self._reply(r, b)
            elif sub == 0x07:                 # расширенная конфигурация
                self._reply(r, SIM_CONFIG + bytes((0x00, 0x00)))
            elif sub == 0x0A:
                self._reply(r, bytes((0x00, 0x00, 0x00, 0x00)))
            elif sub in (0x17, 0x1D):
                self._reply(r, bytes((SIM_ADDR,)))
            elif sub == 0x18:
                self._reply(r, bytes((0x00, 0x00)))
            elif sub == 0x19:
                self._reply(r, bytes((0x00, 0x00, 0x00)))
            elif sub == 0x1B:
                self._reply(r, bytes(8))
            elif sub == 0x1C:
                self._reply(r, bytes(4))
            elif sub == 0x1F:                 # служебная область (сервис активен в СИМ)
                self._reply(r, bytes(12))
            else:
                self._ack(r, RESULT_BAD_REQUEST)
        elif cmd == 0x06:                     # чтение памяти — вернём нули нужной длины
            length = args[3] if len(args) >= 4 else 1
            self._reply(r, bytes(length))
        else:
            self._ack(r, RESULT_BAD_REQUEST)


def make_sim_stand(address: int = 0x00):
    """Возвращает объект Stand, работающий поверх симулятора вместо COM-порта."""
    import stand as _s
    obj = _s.Stand.__new__(_s.Stand)
    obj.address = address
    obj.retries = 1
    obj._timeout = 0.2
    obj.on_frame = None
    obj._serial = SimSerial(timeout=0.2)
    obj._gap = 0.0
    return obj
