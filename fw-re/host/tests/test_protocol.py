"""Экспериментальная проверка восстановленных алгоритмов и протокола.

Тесты подтверждают:
  1. соответствие CRC-16 табличной реализации прошивки и стандарту Modbus;
  2. корректность сборки/разбора кадров и обнаружение искажений по CRC;
  3. работу команд чтения/записи параметров и калибровок через эмулятор,
     воспроизводящий обработчик sub_823E.

Запуск:  python3 -m pytest host/tests/  (или host/tests/test_protocol.py)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tools"))

import ihex
import protocol as P
from device import Device
from emulator import DeviceEmulator

HEX = os.path.join(os.path.dirname(__file__), "..", "..", "razbor.hex")


# --------------------------------------------------------------------------
# 1. CRC-16/Modbus против таблиц, реально зашитых в прошивку
# --------------------------------------------------------------------------

def _firmware_tables():
    """Возвращает (tabA@0xFB3C, tabB@0xFC3C) — как они лежат в прошивке."""
    img = ihex.load(HEX)
    tabA = list(img.read(0xFB3C, 256))  # старший результат (auchCRClo)
    tabB = list(img.read(0xFC3C, 256))  # младший результат  (auchCRChi)
    return tabA, tabB


def _reference_modbus(data, init=0xFFFF):
    crc = init
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def test_tables_match_firmware():
    """Таблицы прошивки совпадают с восстановленными: FB3C=lo, FC3C=hi."""
    tabA, tabB = _firmware_tables()
    assert tabA == P._CRC_LO, "таблица @0xFB3C != auchCRClo"
    assert tabB == P._CRC_HI, "таблица @0xFC3C != auchCRChi"


def test_crc_equivalent_to_modbus():
    for msg in [b"\x01\x03\x00\x00\x00\x01",
                b"\x11\x03\x00\x6B\x00\x03",
                bytes(range(20)),
                b"\xFE\x04\x00\x01"]:
        assert P.crc16(msg) == _reference_modbus(msg), \
            f"CRC не совпадает со стандартом Modbus для {msg.hex()}"


def test_firmware_algorithm_bytewise():
    """Прямая эмуляция цикла sub_BC22.

    Внутренний регистр прошивки хранит байт-инвертированное значение:
        R = (((R_lo ^ tabA[idx]) << 8) | tabB[idx]),  idx = b ^ (R>>8)
    и равен swap(crc16). В кадр (sub_83A2) уходит crc16 младшим байтом вперёд.
    """
    tabA, tabB = _firmware_tables()

    def fw_loop(data, init=0xFFFF):
        R = init
        for b in data:
            idx = (b ^ (R >> 8)) & 0xFF
            R = (((R & 0xFF) ^ tabA[idx]) << 8 | tabB[idx]) & 0xFFFF
        return R

    for msg in [b"hello-device", b"\x01\x08\x01\x00", bytes([0xAA] * 33)]:
        std = P.crc16(msg)
        swapped = ((std & 0xFF) << 8) | (std >> 8)
        assert fw_loop(msg) == swapped, f"внутр. регистр != swap(crc16) для {msg!r}"


# --------------------------------------------------------------------------
# 2. Кадр: сборка, разбор, контроль искажений
# --------------------------------------------------------------------------

def test_frame_roundtrip():
    f = P.Frame(0x01, P.Func.F4_READ, b"\x05\x02")
    raw = f.encode()
    back = P.Frame.decode(raw)
    assert back.addr == 0x01 and back.func == 0x04 and back.data == b"\x05\x02"


def test_frame_detects_corruption():
    raw = bytearray(P.Frame(0x01, P.Func.F4_READ, b"\x05\x02").encode())
    raw[3] ^= 0xFF  # искажаем байт данных
    try:
        P.Frame.decode(bytes(raw))
        assert False, "искажение не обнаружено"
    except ValueError:
        pass


def test_xor_checksum():
    # sub_4A72: csum = 0xF0F0 ^ w0 ^ w1 ^ w2
    assert P.xor_checksum([0x1234, 0x5678, 0x9ABC]) == \
        (0xF0F0 ^ 0x1234 ^ 0x5678 ^ 0x9ABC)


# --------------------------------------------------------------------------
# 3. Обмен через эмулятор устройства
# --------------------------------------------------------------------------

def test_read_write_parameter():
    emu = DeviceEmulator(address=0x01)
    dev = Device(emu, address=0x01)
    resp = dev.write_parameter(0x05, b"\xDE\xAD")
    assert resp is not None and resp.data[0] == 0x05
    resp = dev.read_parameter(0x05, length=2)
    assert resp is not None and resp.data[1:3] == b"\xDE\xAD"


def test_read_write_calibration():
    emu = DeviceEmulator(address=0x01)
    dev = Device(emu, address=0x01)
    resp = dev.read_calibration(0x00)
    assert resp is not None
    value = resp.data[2] | (resp.data[3] << 8)
    assert value == 0x0100  # исходный коэффициент масштаба канала 1

    dev.write_calibration(0x00, 0x0180)
    resp = dev.read_calibration(0x00)
    value = resp.data[2] | (resp.data[3] << 8)
    assert value == 0x0180  # коэффициент изменён


def test_wrong_address_ignored():
    emu = DeviceEmulator(address=0x01)
    dev = Device(emu, address=0x02)  # обращаемся к другому адресу
    assert dev.read_parameter(0x00) is None


def test_broadcast_accepted():
    emu = DeviceEmulator(address=0x01)
    dev = Device(emu, address=P.BROADCAST)
    assert dev.ping() is True


if __name__ == "__main__":
    import traceback
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    ok = 0
    for t in tests:
        try:
            t()
            print(f"  [OK]   {t.__name__}")
            ok += 1
        except Exception:
            print(f"  [FAIL] {t.__name__}")
            traceback.print_exc()
    print(f"\nПройдено {ok}/{len(tests)} тестов")
    sys.exit(0 if ok == len(tests) else 1)
