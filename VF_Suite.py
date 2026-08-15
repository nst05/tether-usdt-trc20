# -*- coding: utf-8 -*-
"""
VF Suite — объединённая программа с тремя вкладками:
  1. 200_MT — запись счётчика через CH341
  2. 310_MT — запись счётчика через CH341
  3. Синтетический журнал — чтение, пересчёт и запись журнала
     прямо в память 24AA256 через CH341

Сборка: pyinstaller --onefile --hidden-import=i2cpy VF_Suite.py
"""
import base64
import binascii
import csv
import gc
import hashlib
import hmac
import json
import math
import os
import platform
import random
import struct
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional

from PyQt5 import QtCore, QtGui, QtWidgets

if getattr(sys, "frozen", False):
    os.environ["PATH"] = sys._MEIPASS + os.pathsep + os.environ.get("PATH", "")


# ══════════════════════════════════════════════════════════════════════════════
# ЛИЦЕНЗИРОВАНИЕ (общее для всех вкладок)
# ══════════════════════════════════════════════════════════════════════════════

DEFAULT_SECRET = 'vf-gen-license-secret-change-me-2024'
SECRET = os.environ.get('VF_LICENSE_SECRET', DEFAULT_SECRET).encode('utf-8')

KEY_VERSION = 1
LICENSE_FILE = 'license.key'
_EPOCH = date(2020, 1, 1)
_SIG_LEN = 10
_CLOCK_TOLERANCE_DAYS = 2


def _win_machine_guid():
    try:
        import winreg
        for view in (getattr(winreg, 'KEY_WOW64_64KEY', 0), 0):
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                     r'SOFTWARE\Microsoft\Cryptography',
                                     0, winreg.KEY_READ | view)
                try:
                    value, _ = winreg.QueryValueEx(key, 'MachineGuid')
                finally:
                    winreg.CloseKey(key)
                if value:
                    return str(value).strip()
            except OSError:
                continue
    except Exception:
        pass
    return None


def _win_volume_serial():
    try:
        import ctypes
        root = os.environ.get('SystemDrive', 'C:') + '\\'
        serial = ctypes.c_ulong(0)
        ok = ctypes.windll.kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p(root), None, 0,
            ctypes.byref(serial), None, None, None, 0)
        if ok:
            return '%08X' % serial.value
    except Exception:
        pass
    return None


def _linux_machine_id():
    for path in ('/etc/machine-id', '/var/lib/dbus/machine-id'):
        try:
            with open(path, 'r') as fh:
                v = fh.read().strip()
            if v:
                return v
        except Exception:
            continue
    return None


def _linux_dmi_uuid():
    for path in ('/sys/class/dmi/id/product_uuid', '/sys/class/dmi/id/board_serial'):
        try:
            with open(path, 'r') as fh:
                v = fh.read().strip()
            if v and v.lower() not in ('none', 'unknown', '', '0'):
                return v
        except Exception:
            continue
    return None


def _mac_platform_uuid():
    try:
        import subprocess
        out = subprocess.run(['ioreg', '-rd1', '-c', 'IOPlatformExpertDevice'],
                             capture_output=True, text=True, timeout=10).stdout
        for line in out.splitlines():
            if 'IOPlatformUUID' in line:
                return line.split('=')[-1].strip().strip('"')
    except Exception:
        pass
    return None


def _mac_address():
    node = uuid.getnode()
    if node and not (node >> 40) & 0x01:
        return '%012X' % node
    return None


def _sources():
    system = platform.system()
    if system == 'Windows':
        return [_win_machine_guid, _win_volume_serial, _mac_address], ('win-guid', 'win-vol', 'mac')
    if system == 'Darwin':
        return [_mac_platform_uuid, _mac_address], ('mac-uuid', 'mac')
    return [_linux_machine_id, _linux_dmi_uuid, _mac_address], ('linux-id', 'linux-dmi', 'mac')


def _raw_fingerprint():
    getters, tags = _sources()
    for getter, tag in zip(getters, tags):
        try:
            v = getter()
        except Exception:
            v = None
        if v:
            return tag, v
    return None, None


def normalize(value):
    cleaned = ''.join(ch for ch in (value or '').upper() if ch.isalnum())
    return '-'.join(cleaned[i:i + 5] for i in range(0, len(cleaned), 5))


def _canonical(value):
    return ''.join(ch for ch in (value or '').upper() if ch.isalnum())


def get_machine_code():
    override = os.environ.get('VF_MACHINE_CODE')
    if override:
        return normalize(override)
    tag, value = _raw_fingerprint()
    if not value:
        tag, value = 'host', platform.node() or 'unknown-host'
    payload = ('%s:%s:%s' % (tag, value, platform.system())).encode('utf-8', 'replace')
    body = hashlib.sha256(payload).hexdigest()[:20].upper()
    return '-'.join(body[i:i + 5] for i in range(0, 20, 5))


def _signature(code, version, days):
    message = ('%s|%d|%d' % (_canonical(code), version, days)).encode('utf-8')
    return hmac.new(SECRET, message, hashlib.sha256).digest()[:_SIG_LEN]


def generate_key(code, valid_days=0):
    code = _canonical(code)
    if len(code) != 20:
        raise ValueError('Код компьютера должен содержать 20 символов (например A1B2C-D3E4F-6789A-BCDEF)')
    if valid_days and int(valid_days) > 0:
        expiry_days = (date.today() + timedelta(days=int(valid_days)) - _EPOCH).days
        if not 0 < expiry_days <= 0xFFFF:
            raise ValueError('Слишком большой срок действия')
    else:
        expiry_days = 0
    blob = struct.pack('>BH', KEY_VERSION, expiry_days)
    blob += _signature(code, KEY_VERSION, expiry_days)
    enc = base64.b32encode(blob).decode('ascii').rstrip('=')
    return '-'.join(enc[i:i + 7] for i in range(0, len(enc), 7))


def verify_key(key, code=None, today=None):
    code = code or get_machine_code()
    today = today or date.today()
    cleaned = _canonical(key)
    result = {'valid': False, 'reason': None, 'expires': None, 'perpetual': False}

    if not cleaned:
        result['reason'] = 'Ключ не введён'
        return result
    try:
        blob = base64.b32decode(cleaned + '=' * (-len(cleaned) % 8))
    except (binascii.Error, ValueError):
        result['reason'] = 'Ключ введён с ошибкой'
        return result
    if len(blob) != 3 + _SIG_LEN:
        result['reason'] = 'Неверная длина ключа'
        return result
    version, expiry_days = struct.unpack('>BH', blob[:3])
    if version != KEY_VERSION:
        result['reason'] = 'Ключ версии %d не поддерживается этой программой' % version
        return result
    if not hmac.compare_digest(_signature(code, version, expiry_days), blob[3:]):
        result['reason'] = 'Ключ не подходит к этому компьютеру'
        return result
    if expiry_days == 0:
        result.update(valid=True, perpetual=True)
        return result

    expires = _EPOCH + timedelta(days=expiry_days)
    result['expires'] = expires
    if today > expires:
        result['reason'] = 'Срок лицензии истёк %s' % expires.strftime('%d.%m.%Y')
        return result
    result['valid'] = True
    return result


def _guard(key, last_seen):
    message = ('%s|%s' % (_canonical(key), last_seen)).encode('utf-8')
    return hmac.new(SECRET, message, hashlib.sha256).hexdigest()[:32]


def _license_path():
    return os.path.join(app_data_dir(), LICENSE_FILE)


def _read_license():
    try:
        with open(_license_path(), encoding='utf-8') as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return None


def _write_license(data):
    try:
        with open(_license_path(), 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
    except Exception:
        pass


def check_license():
    code = get_machine_code()
    status = {'valid': False,
              'reason': 'Программа не активирована на этом компьютере',
              'machine_code': code, 'expires': None,
              'perpetual': False, 'days_left': None}

    data = _read_license()
    if not data or not data.get('key'):
        return status

    key = data.get('key', '')
    result = verify_key(key, code)
    if not result['valid']:
        status['reason'] = result['reason']
        return status

    # Защита от перевода системной даты назад.
    last_seen = data.get('last_seen')
    if last_seen and data.get('guard') == _guard(key, last_seen):
        try:
            seen = date.fromisoformat(last_seen)
            if date.today() < seen - timedelta(days=_CLOCK_TOLERANCE_DAYS):
                status['reason'] = ('Системная дата переведена назад. '
                                    'Установите правильную дату и запустите снова.')
                return status
        except ValueError:
            pass

    status.update(valid=True, reason=None,
                  expires=result['expires'], perpetual=result['perpetual'])
    if result['expires']:
        status['days_left'] = (result['expires'] - date.today()).days

    today = date.today().isoformat()
    if data.get('last_seen') != today:
        data['last_seen'] = today
        data['guard'] = _guard(key, today)
        _write_license(data)
    return status


def activate(key):
    """Ключ проверяется ДО сохранения — иначе активацией был бы любой текст."""
    code = get_machine_code()
    result = verify_key(key, code)
    if not result['valid']:
        return False, result['reason']

    last_seen = date.today().isoformat()
    _write_license({
        'key': normalize(key),
        'machine': code,
        'activated_at': datetime.now().isoformat(timespec='seconds'),
        'last_seen': last_seen,
        'guard': _guard(key, last_seen),
    })
    if result['perpetual']:
        return True, 'Программа активирована на этом компьютере (бессрочно).'
    return True, ('Программа активирована на этом компьютере до %s.'
                  % result['expires'].strftime('%d.%m.%Y'))


def license_line(status):
    if not status['valid']:
        return 'Лицензия: не активирована'
    if status['perpetual']:
        return 'Лицензия: бессрочная'
    return 'Лицензия: до %s (%d дн.)' % (
        status['expires'].strftime('%d.%m.%Y'), status['days_left'])


# ══════════════════════════════════════════════════════════════════════════════
# ХРАНИЛИЩЕ ДАННЫХ
# ══════════════════════════════════════════════════════════════════════════════

_APP_FOLDER = 'VF_Gen'
_cached_dir = None


def program_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _is_writable(path):
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, '.write_test')
        with open(probe, 'w'):
            pass
        os.remove(probe)
        return True
    except Exception:
        return False


def app_data_dir():
    global _cached_dir
    if _cached_dir:
        return _cached_dir

    override = os.environ.get('VF_DATA_DIR')
    if override and _is_writable(override):
        _cached_dir = os.path.abspath(override)
        return _cached_dir

    near_exe = program_dir()
    if _is_writable(near_exe):
        _cached_dir = near_exe
        return _cached_dir

    if os.name == 'nt':
        root = os.environ.get('APPDATA') or os.path.expanduser('~')
    else:
        root = (os.environ.get('XDG_DATA_HOME')
                or os.path.join(os.path.expanduser('~'), '.local', 'share'))

    fallback = os.path.join(root, _APP_FOLDER)
    os.makedirs(fallback, exist_ok=True)
    _cached_dir = fallback
    return _cached_dir


# ══════════════════════════════════════════════════════════════════════════════
# ВКЛ 0: MT WRITER (запись счётчиков 24C16 через CH341)
# ══════════════════════════════════════════════════════════════════════════════

try:
    from i2cpy import I2C
except ImportError:
    I2C = None

# В программе ДВЕ РАЗНЫЕ микросхемы, и путать их протоколы нельзя.
#
# Вкладки 200_MT / 310_MT — 24C16: 2 КБ, 8 блоков по 256 байт,
# номер блока едет в адресе устройства, адрес внутри блока однобайтный.
MT_EEPROM_SIZE = 2048
MT_BASE_I2C_ADDRESS = 0x50
VALUE_OFFSET = 0x0040
VALUE_SIZE = 4
SCALE = 100

# Синтетический журнал — 24AA256: 32 КБ, один адрес на шине,
# 16-битный адрес внутри памяти, страница записи 64 байта.
EEPROM_SIZE = 32768
EEPROM_PAGE_SIZE = 64
EEPROM_READ_CHUNK = 256
BASE_I2C_ADDRESS = 0x50


def encode_value(value: float) -> bytes:
    raw = int(round(value * SCALE))
    if not 0 <= raw <= 0xFFFFFFFF:
        raise ValueError("Значение слишком большое.")
    return raw.to_bytes(4, "little", signed=False)


def decode_value(data: bytes) -> float:
    if len(data) != 4:
        raise ValueError("Неверная длина данных.")
    return int.from_bytes(data, "little", signed=False) / SCALE


# ══════════════════════════════════════════════════════════════════════════════
# ВКЛ 1.5: MT WRITER TAB GUI
# ══════════════════════════════════════════════════════════════════════════════

class MTWriterTab(QtWidgets.QWidget):
    def __init__(self, name, counters):
        super().__init__()
        self.name = name
        self.counters = counters
        self.i2c = None
        self.init_ui()

    def init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        head = QtWidgets.QHBoxLayout()
        tbox = QtWidgets.QVBoxLayout()
        tbox.setSpacing(4)
        title = QtWidgets.QLabel("ЗАПИСЬ ЗНАЧЕНИЯ — " + self.name)
        font = title.font()
        font.setPointSize(16)
        font.setBold(True)
        title.setFont(font)
        tbox.addWidget(title)
        hint = QtWidgets.QLabel("Введите целую часть. Дробная часть 01–99 добавляется автоматически.")
        hint.setStyleSheet("color:#aab3c5;font-size:12px;")
        hint.setWordWrap(True)
        tbox.addWidget(hint)
        head.addLayout(tbox, 1)

        card = QtWidgets.QFrame()
        card.setStyleSheet("background:#18202c;border:2px solid #3d4a60;border-radius:14px;padding:8px;")
        card.setMinimumWidth(190)
        cc = QtWidgets.QVBoxLayout(card)
        cc.setContentsMargins(16, 8, 16, 8)
        cc.setSpacing(0)
        cap = QtWidgets.QLabel("ПРОШИВОК ВСЕГО")
        cap.setStyleSheet("font-size:12px;font-weight:800;color:#8d96a8;text-align:center;")
        self.counter_lbl = QtWidgets.QLabel(str(self.counters.get(self.name)))
        self.counter_lbl.setStyleSheet("font-size:34px;font-weight:900;color:#7ff0ac;text-align:center;")
        cc.addWidget(cap)
        cc.addWidget(self.counter_lbl)
        head.addWidget(card)
        layout.addLayout(head)

        self.value_input = QtWidgets.QLineEdit()
        self.value_input.setPlaceholderText("Например: 3456")
        self.value_input.setAlignment(QtCore.Qt.AlignCenter)
        self.value_input.setMinimumHeight(64)
        validator = QtGui.QDoubleValidator(0.0, 42949672.95, 2, self)
        self.value_input.setValidator(validator)
        self.value_input.returnPressed.connect(self.write_and_verify)
        layout.addWidget(self.value_input)

        self.write_button = QtWidgets.QPushButton("ЗАПИСАТЬ И ПРОВЕРИТЬ")
        self.write_button.setMinimumHeight(66)
        self.write_button.clicked.connect(self.write_and_verify)
        layout.addWidget(self.write_button)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        self.status = QtWidgets.QLabel("Готово к работе")
        self.status.setWordWrap(True)
        self.status.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.status)

        self.value_input.setFocus()
        self.set_status("Готово к работе")

    def set_status(self, text, ok=None):
        self.status.setText(text)
        if ok is True:
            css = "background:#153c28;border:2px solid #2fc46f;color:#7ff0ac;"
        elif ok is False:
            css = "background:#471d25;border:2px solid #ff5a6f;color:#ff9cab;"
        else:
            css = "background:#18202c;border:2px solid #3d4a60;color:#d9dfeb;"
        self.status.setStyleSheet("QLabel{%s border-radius:14px;padding:16px;font-size:18px;font-weight:800;}" % css)
        QtWidgets.QApplication.processEvents()

    def open_programmer(self):
        if I2C is None:
            raise RuntimeError("Не установлена библиотека i2cpy.")
        self.close_programmer()
        self.i2c = I2C(driver="ch341")

    def close_programmer(self):
        obj = self.i2c
        self.i2c = None
        if obj is not None:
            for method_name in ("close", "deinit", "disconnect"):
                method = getattr(obj, method_name, None)
                if callable(method):
                    try:
                        method()
                    except Exception:
                        pass
                    break
        del obj
        gc.collect()
        time.sleep(0.08)

    @staticmethod
    def split_address(address):
        """24C16: 2 КБ, 8 блоков по 256 байт. Номер блока едет в адресе
        устройства, внутри блока адрес однобайтный."""
        if not 0 <= address < MT_EEPROM_SIZE:
            raise ValueError("Адрес выходит за пределы 24C16.")
        block = (address >> 8) & 0x07
        device_address = MT_BASE_I2C_ADDRESS | block
        memory_address = address & 0xFF
        return device_address, memory_address

    def read_bytes(self, address, length):
        if self.i2c is None:
            raise RuntimeError("Программатор не инициализирован.")
        result = bytearray()
        current = address
        remaining = length
        while remaining > 0:
            dev_addr, mem_addr = self.split_address(current)
            chunk_len = min(remaining, 0x100 - mem_addr)
            chunk = self.i2c.readfrom_mem(dev_addr, mem_addr, chunk_len, addrsize=8)
            result.extend(bytes(chunk))
            current += chunk_len
            remaining -= chunk_len
        return bytes(result)

    def write_bytes(self, address, payload):
        if self.i2c is None:
            raise RuntimeError("Программатор не инициализирован.")
        dev_addr, mem_addr = self.split_address(address)
        self.i2c.writeto_mem(dev_addr, mem_addr, bytes(payload), addrsize=8)

    def parse_value(self):
        text = self.value_input.text().strip().replace(",", ".")
        if not text:
            raise ValueError("Введите целую часть.")
        base_value = float(text)
        if base_value < 0:
            raise ValueError("Значение не может быть отрицательным.")
        integer_part = int(base_value)
        fraction = random.randint(1, 99)
        value = integer_part + fraction / 100.0
        encode_value(value)
        return value

    def write_and_verify(self):
        status = check_license()
        if not status["valid"]:
            self.set_status(
                f"✗ Лицензия не активна: {status.get('reason', 'неизвестно')}", False
            )
            return

        self.write_button.setEnabled(False)
        self.progress.setValue(5)
        self.set_status("Запись...")

        try:
            value = self.parse_value()
            expected = encode_value(value)

            self.progress.setValue(20)
            self.open_programmer()

            before = self.read_bytes(VALUE_OFFSET, VALUE_SIZE)

            self.progress.setValue(45)
            self.write_bytes(VALUE_OFFSET, expected)

            self.close_programmer()

            self.progress.setValue(65)
            time.sleep(0.15)

            self.progress.setValue(80)
            self.open_programmer()

            actual = None
            for _ in range(10):
                try:
                    actual = self.read_bytes(VALUE_OFFSET, VALUE_SIZE)
                    if actual == expected:
                        break
                except Exception:
                    pass
                time.sleep(0.05)

            if actual != expected:
                raise RuntimeError("Проверка записи не пройдена.")

            verified = decode_value(actual)
            self.progress.setValue(100)
            self.value_input.clear()
            self.value_input.setFocus()

            total = self.counters.inc(self.name)
            self.counter_lbl.setText(str(total))

            self.set_status("✓ Успех: записано %.2f  ·  прошивка № %d" % (verified, total), True)

        except Exception as exc:
            self.progress.setValue(0)
            self.set_status("✗ Ошибка: %s" % exc, False)

        finally:
            self.close_programmer()
            self.write_button.setEnabled(True)

    def closeEvent(self, event):
        self.close_programmer()
        event.accept()


class MTCounters:
    def __init__(self, names):
        self.names = names
        self.data = {n: 0 for n in names}
        try:
            path = os.path.join(app_data_dir(), 'mt_counters.json')
            with open(path, encoding="utf-8") as fh:
                saved = json.load(fh)
            for n in names:
                self.data[n] = int(saved.get(n, 0))
        except Exception:
            pass

    def get(self, name):
        return self.data.get(name, 0)

    def inc(self, name):
        self.data[name] = self.get(name) + 1
        try:
            path = os.path.join(app_data_dir(), 'mt_counters.json')
            os.makedirs(app_data_dir(), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh)
        except Exception:
            pass
        return self.data[name]


# ══════════════════════════════════════════════════════════════════════════════
# ВКЛ 2: СИНТЕТИЧЕСКИЙ ЖУРНАЛ
# ══════════════════════════════════════════════════════════════════════════════

MONTHLY_START = 0x0000
MONTHLY_COUNT = 8
MONTHLY_STRIDE = 0x20
MONTHLY_VALUE_OFF = 0x0F
MONTHLY_VALID_OFF = 0x1F

DAILY_START = 0x2000
DAILY_END = 0x7C00
DAILY_STRIDE = 0x100
DAILY_VALUE_OFF = 0x10
PROFILE_OFF = 0x40
PROFILE_COUNT = 48

VALUE_SCALE = 100
MIN_DUMP_SIZE = 0x7D00


@dataclass
class DailyRecord:
    offset: int
    dt: date
    value: float
    profile: List[int]


@dataclass
class MonthlyRecord:
    offset: int
    month: int
    year: int
    value: float
    valid: int


def read_u24_le(buf: bytes, offset: int) -> int:
    return int.from_bytes(buf[offset:offset + 3], "little", signed=False)


def write_u24_le(buf: bytearray, offset: int, raw: int) -> None:
    if not 0 <= raw <= 0xFFFFFF:
        raise ValueError(f"Значение RAW {raw} не помещается в UInt24 (максимум {0xFFFFFF}).")
    buf[offset:offset + 3] = raw.to_bytes(3, "little", signed=False)


def valid_date(day: int, month: int, year_byte: int) -> Optional[date]:
    try:
        year = 2000 + year_byte
        if not 2000 <= year <= 2099:
            return None
        return date(year, month, day)
    except ValueError:
        return None


def parse_daily(data: bytes) -> List[DailyRecord]:
    records = []
    for offset in range(DAILY_START, DAILY_END + 1, DAILY_STRIDE):
        if offset + DAILY_STRIDE > len(data):
            break
        day, month, year_byte = data[offset:offset + 3]
        dt = valid_date(day, month, year_byte)
        if dt is None:
            continue
        raw = read_u24_le(data, offset + DAILY_VALUE_OFF)
        value = raw / VALUE_SCALE
        profile = [
            int.from_bytes(
                data[offset + PROFILE_OFF + i * 2:offset + PROFILE_OFF + i * 2 + 2],
                "little", signed=False,
            )
            for i in range(PROFILE_COUNT)
        ]
        records.append(DailyRecord(offset, dt, value, profile))
    records.sort(key=lambda item: (item.dt, item.offset))
    return records


def parse_monthly(data: bytes) -> List[MonthlyRecord]:
    result = []
    for index in range(MONTHLY_COUNT):
        offset = MONTHLY_START + index * MONTHLY_STRIDE
        if offset + MONTHLY_STRIDE > len(data):
            break
        month = data[offset]
        year_byte = data[offset + 1]
        valid = data[offset + MONTHLY_VALID_OFF]
        if not 1 <= month <= 12 or year_byte == 0xFF:
            continue
        year = 2000 + year_byte
        raw = read_u24_le(data, offset + MONTHLY_VALUE_OFF)
        result.append(MonthlyRecord(offset, month, year, raw / VALUE_SCALE, valid))
    return result


def make_template_weights(records):
    sums = [0.0] * PROFILE_COUNT
    count = 0
    for record in records:
        total = sum(record.profile)
        if total <= 0:
            continue
        for i, value in enumerate(record.profile):
            sums[i] += value / total
        count += 1
    if count == 0 or sum(sums) <= 0:
        return [1.0 / PROFILE_COUNT] * PROFILE_COUNT
    weights = [value / count for value in sums]
    total = sum(weights)
    return [value / total for value in weights]


def allocate_integer_total(total, base_weights, rng, noise):
    if total <= 0:
        return [0] * PROFILE_COUNT
    noisy = []
    for weight in base_weights:
        factor = max(0.05, 1.0 + rng.uniform(-noise, noise))
        noisy.append(max(0.0, weight * factor))
    weight_sum = sum(noisy)
    if weight_sum <= 0:
        noisy = [1.0] * PROFILE_COUNT
        weight_sum = PROFILE_COUNT
    exact = [total * value / weight_sum for value in noisy]
    integers = [int(math.floor(value)) for value in exact]
    remainder = total - sum(integers)
    fractions = sorted(range(PROFILE_COUNT), key=lambda i: exact[i] - integers[i], reverse=True)
    for i in fractions[:remainder]:
        integers[i] += 1
    return integers


def generate_increments(count, average, variation_percent, rng):
    if count <= 0:
        return []
    target_total = int(round(average * VALUE_SCALE * count))
    values = []
    for _ in range(count):
        factor = 1.0 + rng.uniform(-variation_percent / 100.0, variation_percent / 100.0)
        values.append(max(0.0, average * factor))
    current_total = sum(values)
    if current_total <= 0:
        raw = [0] * count
    else:
        exact = [value / current_total * target_total for value in values]
        raw = [int(math.floor(value)) for value in exact]
        remainder = target_total - sum(raw)
        order = sorted(range(count), key=lambda i: exact[i] - raw[i], reverse=True)
        for i in order[:remainder]:
            raw[i] += 1
    return raw


def synthetic_values(records, final_value, average_daily, variation_percent, seed):
    if len(records) < 2:
        raise ValueError("Недостаточно суточных записей для генерации.")
    rng = random.Random(seed)
    increment_count = len(records) - 1
    increments = generate_increments(increment_count, average_daily, variation_percent, rng)
    final_raw = int(round(final_value * VALUE_SCALE))
    total_increment = sum(increments)
    if total_increment > final_raw:
        if final_raw <= 0:
            increments = [0] * increment_count
        else:
            scale = final_raw / total_increment
            exact = [value * scale for value in increments]
            increments = [int(math.floor(value)) for value in exact]
            remainder = final_raw - sum(increments)
            order = sorted(range(increment_count), key=lambda i: exact[i] - increments[i], reverse=True)
            for i in order[:remainder]:
                increments[i] += 1
    start_raw = final_raw - sum(increments)
    if final_raw > 0xFFFFFF:
        raise ValueError("Конечное показание превышает максимум формата UInt24: 167772.15.")
    values = [start_raw]
    for increment in increments:
        values.append(values[-1] + increment)
    template = make_template_weights(records)
    profiles = []
    for increment in increments:
        profiles.append(
            allocate_integer_total(
                increment, template, rng,
                noise=min(0.95, variation_percent / 100.0 + 0.15),
            )
        )
    profiles.append(list(records[-1].profile))
    return values, profiles


def value_for_month(year, month, records, values_raw):
    target = date(year, month, 1)
    for record, raw in zip(records, values_raw):
        if record.dt >= target:
            return raw
    return values_raw[-1]


# ══════════════════════════════════════════════════════════════════════════════
# GUI СТИЛИ
# ══════════════════════════════════════════════════════════════════════════════

APP_STYLE = """
QWidget {
    background: #10131a;
    color: #eef2f8;
    font-family: Segoe UI;
    font-size: 14px;
}
QGroupBox {
    border: 1px solid #354157;
    border-radius: 12px;
    margin-top: 14px;
    padding: 14px;
    font-weight: 700;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 7px;
}
QLineEdit, QDoubleSpinBox, QSpinBox, QTextEdit {
    background: #181d27;
    border: 2px solid #38445a;
    border-radius: 10px;
    padding: 10px;
    color: white;
    font-size: 16px;
}
QPushButton {
    background: #3f6df6;
    border: 1px solid #7190ff;
    border-radius: 12px;
    padding: 13px;
    font-weight: 800;
    color: white;
}
QPushButton:disabled {
    background: #2b3240;
    color: #8d96a8;
}
QLabel#Status {
    background: #18202c;
    border: 1px solid #3d4a60;
    border-radius: 10px;
    padding: 12px;
}
QProgressBar {
    border: 1px solid #3d4a60;
    border-radius: 8px;
    background: #18202c;
    text-align: center;
}
QProgressBar::chunk {
    background: #3f6df6;
    border-radius: 7px;
}
QTabWidget::pane {
    border: 1px solid #354157;
}
QTabBar::tab {
    background: #1a1f2a;
    border: 1px solid #354157;
    padding: 8px 20px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background: #3f6df6;
    color: white;
}
QTableWidget {
    background: #121722;
    alternate-background-color: #171d29;
    gridline-color: #2d3748;
    border: 1px solid #354157;
    border-radius: 8px;
    color: #eef2f8;
}
QTableWidget::item {
    padding: 4px;
    color: #eef2f8;
}
QTableWidget::item:selected {
    background: #26344d;
    color: white;
}
QHeaderView::section {
    background: #26344d;
    color: white;
    padding: 6px;
    border: 1px solid #354157;
    font-weight: 700;
}
QScrollBar:vertical {
    background: #18202c;
    width: 12px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #3d4a60;
    border-radius: 6px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background: #4d5d78;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
"""


# ══════════════════════════════════════════════════════════════════════════════
# ВКЛ 2: СИНТЕТИЧЕСКИЙ ЖУРНАЛ GUI
# ══════════════════════════════════════════════════════════════════════════════

class JournalTab(QtWidgets.QWidget):
    """
    Синтетический журнал прямо в приборе (24AA256 через CH341).

    Порядок работы:
      1. «Прочитать журнал из прибора» — читает 32 КБ из EEPROM и разбирает
         месячные записи, суточные страницы и 48-интервальные профили;
      2. вводится конечное показание — пересчитывается вся хронология
         (суточные значения, профили нагрузки, месячные записи);
      3. «Записать в прибор» — изменённый образ пишется обратно в EEPROM
         постранично и проверяется обратным чтением.
    """

    sig_status = QtCore.pyqtSignal(str, object)
    sig_progress = QtCore.pyqtSignal(int)
    sig_loaded = QtCore.pyqtSignal()
    sig_busy = QtCore.pyqtSignal(bool)
    sig_busy_text = QtCore.pyqtSignal(str)
    sig_indeterminate = QtCore.pyqtSignal(bool)

    def __init__(self, mt_counters):
        super().__init__()
        self.path = None
        self.data = None
        self.daily = []
        self.monthly = []
        self.i2c = None
        self.mt_counters = mt_counters
        self.init_ui()

        # Анимация ожидания: крутится в главном потоке, пока обмен
        # с прибором идёт в фоновом.
        self._busy_text = ""
        self._busy_frame = 0
        self.busy_timer = QtCore.QTimer(self)
        self.busy_timer.setInterval(110)
        self.busy_timer.timeout.connect(self._tick_busy)

        self.sig_status.connect(self.set_status)
        self.sig_progress.connect(self.progress.setValue)
        self.sig_loaded.connect(self.on_journal_loaded)
        self.sig_busy.connect(self.set_busy)
        self.sig_busy_text.connect(self.set_busy_text)
        self.sig_indeterminate.connect(self.set_indeterminate)

    # ── работа с программатором ───────────────────────────────────────────

    def open_programmer(self):
        if I2C is None:
            raise RuntimeError("Не установлена библиотека i2cpy.")
        self.close_programmer()
        self.i2c = I2C(driver="ch341")

    def close_programmer(self):
        obj = self.i2c
        self.i2c = None
        if obj is not None:
            for method_name in ("close", "deinit", "disconnect"):
                method = getattr(obj, method_name, None)
                if callable(method):
                    try:
                        method()
                    except Exception:
                        pass
                    break
        del obj
        gc.collect()
        time.sleep(0.08)

    @staticmethod
    def check_address(address):
        """24AA256: один адрес на шине, 16-битный адрес внутри памяти."""
        if not 0 <= address < EEPROM_SIZE:
            raise ValueError(
                f"Адрес 0x{address:04X} выходит за пределы 24AA256 "
                f"(макс 0x{EEPROM_SIZE - 1:04X})."
            )
        return BASE_I2C_ADDRESS, address

    def read_from_eeprom(self, address, length, progress=None):
        if self.i2c is None:
            raise RuntimeError("Программатор не инициализирован.")
        result = bytearray()
        current = address
        remaining = length
        while remaining > 0:
            dev_addr, mem_addr = self.check_address(current)
            chunk_len = min(remaining, EEPROM_READ_CHUNK)
            chunk = self.i2c.readfrom_mem(dev_addr, mem_addr, chunk_len, addrsize=16)
            result.extend(bytes(chunk))
            current += chunk_len
            remaining -= chunk_len
            if progress is not None:
                progress(len(result), length)
        return bytes(result)

    def write_to_eeprom(self, address, payload):
        """Пишет постранично: у 24AA256 страница 64 байта, за её границу
        запись заворачивается в начало той же страницы."""
        if self.i2c is None:
            raise RuntimeError("Программатор не инициализирован.")
        offset = 0
        while offset < len(payload):
            current = address + offset
            dev_addr, mem_addr = self.check_address(current)
            space = EEPROM_PAGE_SIZE - (current % EEPROM_PAGE_SIZE)
            chunk = payload[offset:offset + space]
            self.i2c.writeto_mem(dev_addr, mem_addr, bytes(chunk), addrsize=16)
            time.sleep(0.006)  # tWC 24AA256 — 5 мс на страницу
            offset += len(chunk)

    # ── интерфейс ─────────────────────────────────────────────────────────

    def init_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        title = QtWidgets.QLabel("СИНТЕТИЧЕСКИЙ ЖУРНАЛ (24AA256 / CH341)")
        font = title.font()
        font.setPointSize(13)
        font.setBold(True)
        title.setFont(font)
        title.setAlignment(QtCore.Qt.AlignCenter)
        root.addWidget(title)

        device_box = QtWidgets.QGroupBox("Прибор")
        device_layout = QtWidgets.QHBoxLayout(device_box)
        device_layout.setContentsMargins(14, 12, 14, 12)
        self.read_btn = QtWidgets.QPushButton("ПРОЧИТАТЬ ЖУРНАЛ ИЗ ПРИБОРА")
        self.read_btn.setFixedHeight(40)
        self.read_btn.clicked.connect(self.start_read)
        device_layout.addWidget(self.read_btn)
        self.open_btn = QtWidgets.QPushButton("Открыть BIN")
        self.open_btn.setMaximumWidth(150)
        self.open_btn.setFixedHeight(40)
        self.open_btn.clicked.connect(self.open_file)
        device_layout.addWidget(self.open_btn)
        root.addWidget(device_box)

        self.tabs = QtWidgets.QTabWidget()
        root.addWidget(self.tabs, 1)

        # ── просмотр журнала ──
        viewer_tab = QtWidgets.QWidget()
        viewer_layout = QtWidgets.QVBoxLayout(viewer_tab)
        viewer_layout.setContentsMargins(12, 12, 12, 12)
        viewer_layout.setSpacing(10)

        self.summary_label = QtWidgets.QLabel("Журнал не загружен.")
        self.summary_label.setWordWrap(True)
        self.summary_label.setObjectName("Status")
        viewer_layout.addWidget(self.summary_label)

        self.journal_table = QtWidgets.QTableWidget()
        self.journal_table.setColumnCount(6)
        self.journal_table.setHorizontalHeaderLabels(
            ["№", "Дата", "Адрес", "Показание", "Прирост", "Сумма профиля"]
        )
        self.journal_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.journal_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.journal_table.setAlternatingRowColors(True)
        self.journal_table.verticalHeader().setVisible(False)
        header = self.journal_table.horizontalHeader()
        header.setStretchLastSection(False)
        for column in range(5):
            header.setSectionResizeMode(column, QtWidgets.QHeaderView.ResizeToContents)
        # Последняя колонка забирает остаток ширины, но не растягивается
        # на пол-экрана: заголовок остаётся рядом с данными.
        header.setSectionResizeMode(5, QtWidgets.QHeaderView.ResizeToContents)
        header.setDefaultAlignment(QtCore.Qt.AlignCenter)
        viewer_layout.addWidget(self.journal_table, 1)

        export_row = QtWidgets.QHBoxLayout()
        self.export_btn = QtWidgets.QPushButton("Экспорт просмотра в CSV")
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self.export_current_view)
        export_row.addStretch(1)
        export_row.addWidget(self.export_btn)
        viewer_layout.addLayout(export_row)

        self.tabs.addTab(viewer_tab, "Просмотр журнала")

        # ── генератор ──
        # Содержимое лежит в области прокрутки: на низких экранах вкладка
        # иначе сжимает группы и обрезает поля.
        generator_tab = QtWidgets.QScrollArea()
        generator_tab.setWidgetResizable(True)
        generator_tab.setFrameShape(QtWidgets.QFrame.NoFrame)
        generator_tab.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        generator_body = QtWidgets.QWidget()
        generator_tab.setWidget(generator_body)

        generator_layout = QtWidgets.QVBoxLayout(generator_body)
        generator_layout.setContentsMargins(12, 8, 12, 8)
        generator_layout.setSpacing(8)

        params = QtWidgets.QGroupBox("Параметры синтетической хронологии")
        form = QtWidgets.QGridLayout(params)
        form.setContentsMargins(16, 10, 16, 10)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(6)
        # Подпись и поле идут парой слева, свободное место уходит вправо.
        form.setColumnStretch(0, 0)
        form.setColumnStretch(1, 0)
        form.setColumnStretch(2, 1)

        self.final_value = QtWidgets.QDoubleSpinBox()
        self.final_value.setDecimals(2)
        self.final_value.setRange(0.0, 167772.15)
        self.final_value.setSingleStep(0.01)

        self.average = QtWidgets.QDoubleSpinBox()
        self.average.setDecimals(2)
        self.average.setRange(0.0, 9999.99)
        self.average.setValue(5.00)

        self.variation = QtWidgets.QDoubleSpinBox()
        self.variation.setDecimals(1)
        self.variation.setRange(0.0, 95.0)
        self.variation.setValue(25.0)
        self.variation.setSuffix(" %")

        self.seed = QtWidgets.QSpinBox()
        self.seed.setRange(0, 2_147_483_647)
        self.seed.setValue(2026)

        for widget in (self.final_value, self.average, self.variation, self.seed):
            widget.setMinimumWidth(220)
            widget.setFixedHeight(32)
            widget.setAlignment(QtCore.Qt.AlignCenter)
            widget.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
            widget.setStyleSheet("font-size:14px;min-height:0px;padding:2px 8px;")

        labels = [
            QtWidgets.QLabel("Конечное показание:"),
            QtWidgets.QLabel("Желаемый средний расход в сутки:"),
            QtWidgets.QLabel("Разброс расхода:"),
            QtWidgets.QLabel("Seed генератора:"),
        ]
        for label in labels:
            label.setFixedHeight(32)
            label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            label.setStyleSheet("font-size:13px;font-weight:700;color:#dce4f2;")

        for row, (label, widget) in enumerate(
            zip(labels, (self.final_value, self.average, self.variation, self.seed))
        ):
            form.addWidget(label, row, 0)
            form.addWidget(widget, row, 1)

        generator_layout.addWidget(params)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(10)
        self.generate_btn = QtWidgets.QPushButton("ПЕРЕСЧИТАТЬ ЖУРНАЛ")
        self.generate_btn.setEnabled(False)
        self.generate_btn.setFixedHeight(38)
        self.generate_btn.clicked.connect(self.generate)
        self.write_btn = QtWidgets.QPushButton("ЗАПИСАТЬ В ПРИБОР")
        self.write_btn.setEnabled(False)
        self.write_btn.setFixedHeight(38)
        self.write_btn.clicked.connect(self.start_write)
        btn_row.addWidget(self.generate_btn)
        btn_row.addWidget(self.write_btn)
        generator_layout.addLayout(btn_row)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFixedHeight(18)
        generator_layout.addWidget(self.progress)

        self.status_label = QtWidgets.QLabel(
            "Нажми «Прочитать журнал из прибора»."
        )
        self.status_label.setObjectName("Status")
        self.status_label.setWordWrap(True)
        generator_layout.addWidget(self.status_label)

        generator_layout.addStretch(1)

        self.tabs.addTab(generator_tab, "Генератор")

    def set_status(self, text, ok=None):
        self.status_label.setText(text)
        if ok is True:
            self.status_label.setStyleSheet(
                "background:#153c28;border:2px solid #2fc46f;"
                "border-radius:10px;padding:12px;color:#91f4b8;"
            )
        elif ok is False:
            self.status_label.setStyleSheet(
                "background:#471d25;border:2px solid #ff5a6f;"
                "border-radius:10px;padding:12px;color:#ffabb8;"
            )
        else:
            self.status_label.setStyleSheet(
                "background:#18202c;border:1px solid #3d4a60;"
                "border-radius:10px;padding:12px;"
            )

    # ── анимация ожидания ─────────────────────────────────────────────────

    BUSY_FRAMES = "⣾⣽⣻⢿⡿⣟⣯⣷"

    def start_busy(self, text):
        self._busy_text = text
        self._busy_frame = 0
        self.status_label.setStyleSheet(
            "background:#18202c;border:1px solid #3d4a60;"
            "border-radius:10px;padding:12px;color:#cfe0ff;"
        )
        self._tick_busy()
        if not self.busy_timer.isActive():
            self.busy_timer.start()

    def set_busy_text(self, text):
        self._busy_text = text

    def stop_busy(self):
        self.busy_timer.stop()

    def _tick_busy(self):
        frame = self.BUSY_FRAMES[self._busy_frame % len(self.BUSY_FRAMES)]
        self._busy_frame += 1
        self.status_label.setText(f"{frame}   {self._busy_text}")

    def set_indeterminate(self, on):
        """Бегущая полоса, пока длительность шага неизвестна."""
        if on:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 100)

    def set_summary(self, text):
        """Сводка над таблицей. Таблица растянута и иначе съедает у метки
        последние строки, поэтому высоту закрепляем по самому тексту."""
        self.summary_label.setText(text)
        lines = text.count("\n") + 1
        spacing = self.summary_label.fontMetrics().lineSpacing()
        self.summary_label.setMinimumHeight(lines * spacing + 26)

    def set_busy(self, busy):
        if not busy:
            self.stop_busy()
            self.set_indeterminate(False)
        self.read_btn.setEnabled(not busy)
        self.open_btn.setEnabled(not busy)
        has_data = self.data is not None and len(self.daily) >= 2
        self.generate_btn.setEnabled(not busy and has_data)
        self.write_btn.setEnabled(not busy and has_data)
        self.export_btn.setEnabled(not busy and has_data)

    # ── разбор и отображение ──────────────────────────────────────────────

    def load_image(self, data, source):
        """Разбирает 32-КБ образ и запоминает его как текущий журнал."""
        if len(data) < MIN_DUMP_SIZE:
            raise ValueError(
                f"Образ имеет размер {len(data)} байт; ожидается 32-КБ журнал."
            )
        daily = parse_daily(data)
        monthly = parse_monthly(data)
        if len(daily) < 2:
            raise ValueError("Суточный журнал не распознан.")

        self.data = bytes(data)
        self.daily = daily
        self.monthly = monthly
        self.source_name = source

    def on_journal_loaded(self):
        """Вызывается в GUI-потоке после успешного разбора образа."""
        self.populate_journal_table()
        self.final_value.setValue(self.daily[-1].value)

        diffs = [
            self.daily[i + 1].value - self.daily[i].value
            for i in range(len(self.daily) - 1)
            if self.daily[i + 1].value >= self.daily[i].value
        ]
        average = sum(diffs) / len(diffs) if diffs else 0.0
        if average > 0:
            self.average.setValue(average)

        self.set_busy(False)

    def populate_journal_table(self):
        self.journal_table.setRowCount(len(self.daily))

        for row, record in enumerate(self.daily):
            increment = ""
            if row + 1 < len(self.daily):
                increment = f"{self.daily[row + 1].value - record.value:.2f}"

            values = [
                str(row + 1),
                record.dt.strftime("%d.%m.%Y"),
                f"0x{record.offset:04X}",
                f"{record.value:.2f}",
                increment,
                f"{sum(record.profile) / VALUE_SCALE:.2f}",
            ]

            for column, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(value)
                item.setTextAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter)
                self.journal_table.setItem(row, column, item)

        if self.daily:
            diffs = [
                self.daily[i + 1].value - self.daily[i].value
                for i in range(len(self.daily) - 1)
            ]
            positive = [d for d in diffs if d >= 0]
            average = sum(positive) / len(positive) if positive else 0.0
            self.set_summary(
                f"Источник: {getattr(self, 'source_name', '—')}\n"
                f"Суточных записей: {len(self.daily)} | "
                f"Месячных записей: {len(self.monthly)}\n"
                f"Период: {self.daily[0].dt:%d.%m.%Y} — {self.daily[-1].dt:%d.%m.%Y}\n"
                f"Первое значение: {self.daily[0].value:.2f} | "
                f"Последнее значение: {self.daily[-1].value:.2f} | "
                f"Средний прирост: {average:.2f}"
            )

    # ── чтение из прибора ─────────────────────────────────────────────────

    def start_read(self):
        status = check_license()
        if not status["valid"]:
            self.set_status(
                f"✗ Лицензия не активна: {status.get('reason', 'неизвестно')}", False
            )
            return
        self.set_busy(True)
        self.start_busy("Подключение к программатору…")
        self.set_indeterminate(True)
        threading.Thread(target=self.read_from_device, daemon=True).start()

    def read_from_device(self):
        """Читает весь журнал (32 КБ) из 24AA256."""
        try:
            self.open_programmer()

            self.sig_indeterminate.emit(False)
            self.sig_busy_text.emit("Чтение журнала из прибора…")
            data = self.read_from_eeprom(
                0x0000, EEPROM_SIZE,
                progress=lambda done, total: self.sig_progress.emit(
                    int(done / total * 85)
                ),
            )
            self.close_programmer()

            self.sig_busy_text.emit("Разбор журнала…")
            self.load_image(data, "прибор (24AA256)")

            self.sig_progress.emit(100)
            self.sig_loaded.emit()
            self.sig_status.emit(
                f"✓ Прочитано из прибора: {len(self.daily)} суточных записей, "
                f"{len(self.monthly)} месячных.\n"
                f"Период: {self.daily[0].dt:%d.%m.%Y} — {self.daily[-1].dt:%d.%m.%Y}. "
                f"Последнее показание: {self.daily[-1].value:.2f}.",
                True,
            )
        except Exception as exc:
            self.sig_busy.emit(False)
            self.sig_progress.emit(0)
            self.sig_status.emit(f"✗ Ошибка чтения: {exc}", False)
        finally:
            self.close_programmer()

    # ── пересчёт хронологии ───────────────────────────────────────────────

    def generate(self):
        if self.data is None:
            self.set_status("Сначала прочитай журнал из прибора.", False)
            return

        self.set_busy(True)
        self.progress.setValue(5)
        try:
            values_raw, profiles = synthetic_values(
                self.daily,
                float(self.final_value.value()),
                float(self.average.value()),
                float(self.variation.value()),
                int(self.seed.value()),
            )

            output = bytearray(self.data)
            self.progress.setValue(35)

            for record, raw, profile in zip(self.daily, values_raw, profiles):
                write_u24_le(output, record.offset + DAILY_VALUE_OFF, raw)
                for i, interval_raw in enumerate(profile):
                    if not 0 <= interval_raw <= 0xFFFF:
                        raise ValueError(
                            "Интервальное значение не помещается в UInt16. "
                            "Уменьшите средний суточный расход."
                        )
                    pos = record.offset + PROFILE_OFF + i * 2
                    output[pos:pos + 2] = interval_raw.to_bytes(2, "little", signed=False)

            self.progress.setValue(70)

            for monthly in self.monthly:
                raw = value_for_month(monthly.year, monthly.month, self.daily, values_raw)
                write_u24_le(output, monthly.offset + MONTHLY_VALUE_OFF, raw)

            # Перечитываем собственный результат — таблица показывает то,
            # что реально уйдёт в прибор.
            self.load_image(bytes(output), "пересчитанный журнал")
            self.populate_journal_table()

            self.progress.setValue(100)
            self.set_status(
                f"✓ Журнал пересчитан: конечное показание "
                f"{self.daily[-1].value:.2f}, записей {len(self.daily)}.\n"
                f"Проверь таблицу на вкладке «Просмотр журнала», "
                f"затем нажми «ЗАПИСАТЬ В ПРИБОР».",
                True,
            )
        except Exception as exc:
            self.progress.setValue(0)
            self.set_status(f"✗ Ошибка пересчёта: {exc}", False)
        finally:
            self.set_busy(False)

    # ── запись в прибор ───────────────────────────────────────────────────

    def start_write(self):
        status = check_license()
        if not status["valid"]:
            self.set_status(
                f"✗ Лицензия не активна: {status.get('reason', 'неизвестно')}", False
            )
            return
        if self.data is None:
            self.set_status("✗ Сначала прочитай журнал из прибора", False)
            return
        self.set_busy(True)
        self.start_busy("Подключение к программатору…")
        self.set_indeterminate(True)
        threading.Thread(target=self.write_to_device, daemon=True).start()

    def write_to_device(self):
        """Пишет текущий образ журнала обратно в 24AA256 и проверяет запись."""
        try:
            payload = bytes(self.data)
            self.open_programmer()

            self.sig_indeterminate.emit(False)
            self.sig_busy_text.emit("Запись журнала в прибор…")
            total = len(payload)
            written = 0
            while written < total:
                chunk = payload[written:written + EEPROM_PAGE_SIZE]
                self.write_to_eeprom(written, chunk)
                written += len(chunk)
                self.sig_progress.emit(int(written / total * 75))

            self.sig_busy_text.emit("Проверка записи…")
            verify = self.read_from_eeprom(
                0x0000, total,
                progress=lambda done, tot: self.sig_progress.emit(
                    75 + int(done / tot * 20)
                ),
            )
            self.close_programmer()

            if verify != payload:
                mismatch = next(
                    (i for i in range(total) if verify[i] != payload[i]), -1
                )
                raise RuntimeError(
                    f"Проверка записи не пройдена: расхождение по адресу 0x{mismatch:04X}."
                )

            check_daily = parse_daily(verify)
            if not check_daily:
                raise RuntimeError("После записи журнал не распознаётся прибором.")
            actual_final = max(check_daily, key=lambda item: item.dt).value

            self.sig_progress.emit(100)
            self.sig_busy.emit(False)
            self.sig_status.emit(
                f"✓ Журнал записан в прибор и проверен.\n"
                f"Конечное показание в приборе: {actual_final:.2f}.",
                True,
            )
        except Exception as exc:
            self.sig_busy.emit(False)
            self.sig_progress.emit(0)
            self.sig_status.emit(f"✗ Ошибка записи: {exc}", False)
        finally:
            self.close_programmer()

    # ── офлайн-режим и экспорт ────────────────────────────────────────────

    def open_file(self):
        selected, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Открыть дамп журнала", "", "BIN (*.bin *.BIN);;Все файлы (*.*)",
        )
        if not selected:
            return
        path = Path(selected)
        try:
            self.load_image(path.read_bytes(), path.name)
            self.path = path
            self.on_journal_loaded()
            self.set_status(
                f"✓ Загружен файл: {len(self.daily)} суточных записей, "
                f"{len(self.monthly)} месячных.\n"
                f"Период: {self.daily[0].dt:%d.%m.%Y} — {self.daily[-1].dt:%d.%m.%Y}.",
                True,
            )
        except Exception as exc:
            self.data = None
            self.daily = []
            self.monthly = []
            self.journal_table.setRowCount(0)
            self.set_summary("Журнал не загружен.")
            self.set_busy(False)
            self.set_status(f"✗ Ошибка: {exc}", False)

    def export_current_view(self):
        if not self.daily:
            return
        default_name = "journal_view.csv"
        if self.path is not None:
            default_name = str(self.path.with_name(f"{self.path.stem}__journal_view.csv"))
        selected, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Экспорт журнала", default_name, "CSV (*.csv);;Все файлы (*.*)",
        )
        if not selected:
            return
        try:
            with Path(selected).open("w", newline="", encoding="utf-8-sig") as file:
                writer = csv.writer(file, delimiter=";")
                writer.writerow(
                    ["number", "date", "offset", "value", "increment", "profile_sum"]
                )
                for index, record in enumerate(self.daily):
                    increment = ""
                    if index + 1 < len(self.daily):
                        increment = f"{self.daily[index + 1].value - record.value:.2f}"
                    writer.writerow([
                        index + 1,
                        record.dt.isoformat(),
                        f"0x{record.offset:04X}",
                        f"{record.value:.2f}",
                        increment,
                        f"{sum(record.profile) / VALUE_SCALE:.2f}",
                    ])
            self.set_summary(
                self.summary_label.text() + f"\nЭкспортировано: {selected}"
            )
        except Exception as exc:
            QtWidgets.QMessageBox.critical(
                self, "Ошибка", f"Не удалось экспортировать CSV:\n{exc}"
            )


# ══════════════════════════════════════════════════════════════════════════════
# ГЛАВНОЕ ОКНО
# ══════════════════════════════════════════════════════════════════════════════

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, license_status):
        super().__init__()
        self.setWindowTitle("VF Suite — MT Writer + Синтетический журнал")
        self.setMinimumSize(1000, 700)

        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        self.license_label = QtWidgets.QLabel()
        self.license_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.license_label)

        tabs = QtWidgets.QTabWidget()

        mt_counters = MTCounters(["200_MT", "310_MT"])

        tabs.addTab(MTWriterTab("200_MT", mt_counters), "200_MT (24C16)")
        tabs.addTab(MTWriterTab("310_MT", mt_counters), "310_MT (24C16)")
        tabs.addTab(JournalTab(mt_counters), "Синтетический журнал (24AA256)")

        layout.addWidget(tabs)

        self.setCentralWidget(central)
        self.show_license(license_status)

    def show_license(self, status):
        self.license_label.setText(
            "%s   ·   ПК: %s" % (license_line(status), status["machine_code"])
        )
        if status["valid"]:
            self.license_label.setStyleSheet(
                "background:#153c28;border:2px solid #2fc46f;"
                "border-radius:10px;padding:10px;color:#91f4b8;font-weight:700;"
            )
        else:
            self.license_label.setStyleSheet(
                "background:#471d25;border:2px solid #ff5a6f;"
                "border-radius:10px;padding:10px;color:#ffabb8;font-weight:700;"
            )


class ActivationDialog(QtWidgets.QDialog):
    """Активация. Ключ проверяется здесь же — некорректный не сохраняется."""

    def __init__(self, status):
        super().__init__()
        self.status = status
        self.machine_code = status["machine_code"]
        self.setWindowTitle("Активация VF Suite")
        self.setFixedWidth(540)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)

        title = QtWidgets.QLabel("АКТИВАЦИЯ ПРОГРАММЫ")
        font = title.font()
        font.setPointSize(15)
        font.setBold(True)
        title.setFont(font)
        title.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(title)

        hint = QtWidgets.QLabel(
            "Программа работает только на одном компьютере.\n"
            "Отправьте код поставщику и введите полученный ключ."
        )
        hint.setAlignment(QtCore.Qt.AlignCenter)
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#aab3c5;")
        layout.addWidget(hint)

        cap = QtWidgets.QLabel("КОД ЭТОГО КОМПЬЮТЕРА")
        cap.setAlignment(QtCore.Qt.AlignCenter)
        cap.setStyleSheet("font-size:12px;font-weight:800;color:#8d96a8;")
        layout.addWidget(cap)

        self.code_input = QtWidgets.QLineEdit(self.machine_code)
        self.code_input.setReadOnly(True)
        self.code_input.setAlignment(QtCore.Qt.AlignCenter)
        self.code_input.setStyleSheet("color:#7ff0ac;font-size:18px;font-weight:700;")
        layout.addWidget(self.code_input)

        copy_btn = QtWidgets.QPushButton("Скопировать код")
        copy_btn.clicked.connect(self.copy_code)
        layout.addWidget(copy_btn)

        cap2 = QtWidgets.QLabel("КЛЮЧ АКТИВАЦИИ")
        cap2.setAlignment(QtCore.Qt.AlignCenter)
        cap2.setStyleSheet("font-size:12px;font-weight:800;color:#8d96a8;")
        layout.addWidget(cap2)

        self.key_input = QtWidgets.QLineEdit()
        self.key_input.setPlaceholderText("Вставь ключ от keygen_vf.py")
        self.key_input.setAlignment(QtCore.Qt.AlignCenter)
        self.key_input.returnPressed.connect(self.try_activate)
        layout.addWidget(self.key_input)

        self.message = QtWidgets.QLabel(status.get("reason") or "Введите ключ")
        self.message.setWordWrap(True)
        self.message.setAlignment(QtCore.Qt.AlignCenter)
        self.message.setMinimumHeight(44)
        self.message.setStyleSheet("color:#93a1b8;")
        layout.addWidget(self.message)

        row = QtWidgets.QHBoxLayout()
        ok_btn = QtWidgets.QPushButton("Активировать")
        ok_btn.clicked.connect(self.try_activate)
        row.addWidget(ok_btn, 2)
        quit_btn = QtWidgets.QPushButton("Выход")
        quit_btn.clicked.connect(self.reject)
        row.addWidget(quit_btn, 1)
        layout.addLayout(row)

        self.key_input.setFocus()

    def copy_code(self):
        QtWidgets.QApplication.clipboard().setText(self.machine_code)
        self.message.setStyleSheet("color:#7ff0ac;")
        self.message.setText("Код скопирован в буфер обмена.")

    def try_activate(self):
        ok, message = activate(self.key_input.text())
        self.message.setStyleSheet("color:#7ff0ac;" if ok else "color:#ff9cab;")
        self.message.setText(message)
        if ok:
            QtCore.QTimer.singleShot(500, self.accept)


# ══════════════════════════════════════════════════════════════════════════════
# ЗАСТАВКА
# ══════════════════════════════════════════════════════════════════════════════

class Splash(QtWidgets.QSplashScreen):
    """Заставка на время запуска. Крутится обычным таймером в главном
    потоке — никаких фоновых потоков, иначе окно остаётся чёрным."""

    FRAMES = "⣾⣽⣻⢿⡿⣟⣯⣷"

    def __init__(self):
        pixmap = QtGui.QPixmap(460, 210)
        pixmap.fill(QtGui.QColor("#10131a"))

        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        painter.setPen(QtGui.QPen(QtGui.QColor("#3f6df6"), 2))
        painter.drawRoundedRect(1, 1, 457, 207, 14, 14)

        painter.setPen(QtGui.QColor("#eef2f8"))
        font = painter.font()
        font.setPointSize(20)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(
            QtCore.QRect(0, 52, 460, 40), QtCore.Qt.AlignCenter, "VF SUITE"
        )

        painter.setPen(QtGui.QColor("#8ea3c8"))
        font.setPointSize(10)
        font.setBold(False)
        painter.setFont(font)
        painter.drawText(
            QtCore.QRect(0, 94, 460, 24),
            QtCore.Qt.AlignCenter,
            "MT Writer  •  Синтетический журнал",
        )
        painter.end()

        super().__init__(pixmap)
        self.setWindowFlags(
            QtCore.Qt.SplashScreen | QtCore.Qt.FramelessWindowHint
        )
        self._frame = 0
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(110)
        self._timer.timeout.connect(self._tick)

    def start(self):
        self.show()
        self._tick()
        self._timer.start()

    def _tick(self):
        frame = self.FRAMES[self._frame % len(self.FRAMES)]
        self._frame += 1
        self.showMessage(
            f"{frame}   Загрузка…",
            QtCore.Qt.AlignHCenter | QtCore.Qt.AlignBottom,
            QtGui.QColor("#cfe0ff"),
        )
        QtWidgets.QApplication.processEvents()

    def finish(self, window):
        self._timer.stop()
        super().finish(window)


# ══════════════════════════════════════════════════════════════════════════════
# ТОЧКА ВХОДА
# ══════════════════════════════════════════════════════════════════════════════

def main():
    if len(sys.argv) > 1 and sys.argv[1].lower() == "keygen":
        if len(sys.argv) < 3:
            print("Использование: VF_Suite.py keygen КОД [дней]")
            return 2
        code = sys.argv[2]
        days = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        try:
            key = generate_key(code, days)
            print(f"Компьютер: {normalize(code)}")
            print(f"Срок:      {'бессрочно' if days <= 0 else f'{days} дн.'}")
            print(f"Ключ:      {key}")
            return 0
        except ValueError as exc:
            print(f"Ошибка: {exc}")
            return 1

    app = QtWidgets.QApplication(sys.argv)
    app.setStyleSheet(APP_STYLE)

    status = check_license()
    if not status["valid"]:
        dlg = ActivationDialog(status)
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return 0
        status = check_license()
        if not status["valid"]:
            return 0

    splash = Splash()
    splash.start()

    win = MainWindow(status)
    win.show()
    splash.finish(win)

    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
