# -*- coding: utf-8 -*-
"""
VF Suite — объединённая программа с двумя табами:
  1. Генератор частоты (VF Gen) — для PIC16F1934 через PICkit 3
  2. Синтетический журнал — генератор данных счётчика из BIN-дампов

Сборка: pyinstaller --onefile VF_Suite.py
"""
import base64
import binascii
import csv
import gc
import glob
import hashlib
import hmac
import json
import math
import os
import platform
import random
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

from PyQt5 import QtCore, QtGui, QtWidgets

if getattr(sys, "frozen", False):
    os.environ["PATH"] = sys._MEIPASS + os.pathsep + os.environ.get("PATH", "")


# ══════════════════════════════════════════════════════════════════════════════
# ЛИЦЕНЗИРОВАНИЕ (общее для обоих табов)
# ══════════════════════════════════════════════════════════════════════════════

DEFAULT_SECRET = 'vf-gen-license-secret-change-me-2024'
SECRET = os.environ.get('VF_LICENSE_SECRET', DEFAULT_SECRET).encode('utf-8')

KEY_VERSION = 1
_EPOCH = date(2020, 1, 1)
_SIG_LEN = 10


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


def verify_key(key, code):
    cleaned = _canonical(key)
    try:
        blob = base64.b32decode(cleaned + '=' * (-len(cleaned) % 8))
    except (binascii.Error, ValueError):
        return False, 'Ключ введён с ошибкой'
    if len(blob) != 3 + _SIG_LEN:
        return False, 'Неверная длина ключа'
    version, expiry_days = struct.unpack('>BH', blob[:3])
    if version != KEY_VERSION:
        return False, 'Другая версия ключа'
    if not hmac.compare_digest(_signature(code, version, expiry_days), blob[3:]):
        return False, 'Ключ не подходит к этому компьютеру'
    if expiry_days == 0:
        return True, 'действителен (бессрочно)'
    expires = _EPOCH + timedelta(days=expiry_days)
    if date.today() > expires:
        return False, 'срок истёк ' + expires.strftime('%d.%m.%Y')
    return True, 'действителен до ' + expires.strftime('%d.%m.%Y')


def check_license():
    machine_code = get_machine_code()
    license_file = os.path.expanduser("~/.vf_license")

    if not os.path.exists(license_file):
        return {"valid": False, "machine_code": machine_code, "reason": "not_found"}

    try:
        key = open(license_file, 'r').read().strip()
        ok, msg = verify_key(key, machine_code)
        return {"valid": ok, "machine_code": machine_code, "message": msg, "reason": None if ok else "invalid"}
    except Exception as exc:
        return {"valid": False, "machine_code": machine_code, "reason": str(exc)}


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


def data_path(filename):
    return os.path.join(app_data_dir(), filename)


def read_json(filename, default=None):
    try:
        with open(data_path(filename), 'r', encoding='utf-8') as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return default


def write_json(filename, data):
    path = data_path(filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass
        raise


class Counters:
    def __init__(self, filename='counters.json'):
        self.filename = filename
        self.data = read_json(filename, {})

    def get(self, name, default=0):
        return self.data.get(name, default)

    def increment(self, name, value=None):
        if value is not None:
            self.data[name] = (self.data.get(name, 0) + 1, value)
        else:
            count, _ = self.data.get(name, (0, None))
            self.data[name] = (count + 1, None)
        write_json(self.filename, self.data)
        count, _ = self.data.get(name, (0, None))
        return count

    def get_count_and_value(self, name):
        return self.data.get(name, (0, None))


# ══════════════════════════════════════════════════════════════════════════════
# ВКЛ 0: MT WRITER (запись счётчиков 24C16 через CH341)
# ══════════════════════════════════════════════════════════════════════════════

try:
    from i2cpy import I2C
except ImportError:
    I2C = None

EEPROM_SIZE = 2048
VALUE_OFFSET = 0x0040
VALUE_SIZE = 4
SCALE = 100
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
# ВКЛ 1: VF_GEN (частотный генератор)
# ══════════════════════════════════════════════════════════════════════════════

PIC_DEVICE = "16F1934"
PIC_TOOL = "PPK3"
EEPROM_ONLY = True
NO_ERASE = True
POWER_FROM_TOOL = True
PRESERVE_PROGRAM = False

BASE_ADDR = 0x1E000
FRAC_ADDR = 0x1E200
FRAC_LEN = 256

COUNTER_NAME = "vf_gen_writes"


@dataclass
class Candidate:
    b1: int
    b2: int
    b3: int
    n_frac: int
    value: float
    exact: bool
    error: float


def solve(target_freq):
    best = None
    best_error = float('inf')

    for b1 in range(256):
        for b2 in range(256):
            for b3 in range(256):
                mid = (1 + b2 / 256) * (b1 + 38) if b1 else 37
                freq = 37000000 / (4 * mid * (b3 + 1) * 64)
                error = abs(freq - target_freq)

                if error < best_error:
                    best_error = error
                    best = Candidate(b1, b2, b3, 0, freq, error < 0.01, error)

    return best


def make_base_block(b1, b2, b3):
    data = bytearray(512)
    data[0] = b1
    data[1] = b2
    data[2] = b3
    return bytes(data)


def make_frac_block(n_frac):
    return bytes(bytearray(256))


def build_ihex(blocks):
    lines = []
    current_ela = None

    for addr_base, data in blocks:
        ela = (addr_base >> 16) & 0xFFFF
        if ela != current_ela:
            lines.append(':02000004%04X%02X' % (ela, (256 - (ela + ela >> 8)) & 0xFF))
            current_ela = ela
        base16 = addr_base & 0xFFFF
        for off in range(0, len(data), 16):
            chunk = data[off:off + 16]
            checksum = (256 - (len(chunk) + (base16 + off >> 8) + (base16 + off & 0xFF) + sum(chunk))) & 0xFF
            line = ':%02X%04X00%s%02X' % (len(chunk), base16 + off, chunk.hex().upper(), checksum)
            lines.append(line)

    lines.append(':00000001FF')
    return '\n'.join(lines) + '\n'


def build_hex_for(candidate):
    blocks = [(BASE_ADDR, make_base_block(candidate.b1, candidate.b2, candidate.b3))]
    if candidate.n_frac > 0:
        blocks.append((FRAC_ADDR, make_frac_block(candidate.n_frac)))
    return build_ihex(blocks)


def format_value(value):
    return '%.2f кГц' % (value / 1000)


def _microchip_glob(name):
    pf = os.environ.get('ProgramFiles', 'C:\\Program Files')
    pf86 = os.environ.get('ProgramFiles(x86)', 'C:\\Program Files (x86)')
    paths = [
        os.path.join(pf, 'Microchip', '**', name),
        os.path.join(pf86, 'Microchip', '**', name),
        os.path.join(pf, 'MPLABX', '**', name),
        os.path.join(pf86, 'MPLABX', '**', name),
    ]
    for pattern in paths:
        matches = glob.glob(pattern, recursive=True)
        if matches:
            return sorted(matches, key=lambda x: -os.path.getmtime(x))[0]
    return None


def find_ipecmd():
    if os.path.exists('ipecmd_path.txt'):
        try:
            return open('ipecmd_path.txt').read().strip()
        except Exception:
            pass

    override = os.environ.get('IPECMD')
    if override and os.path.exists(override):
        return override

    if shutil.which('ipecmd.exe'):
        return 'ipecmd.exe'
    if shutil.which('ipecmd'):
        return 'ipecmd'

    found = _microchip_glob('ipecmd.exe')
    if found:
        return found

    return None


def build_flash_args(ipecmd, hex_path):
    args = list(ipecmd if isinstance(ipecmd, (list, tuple)) else [ipecmd])
    args += ["-P" + PIC_DEVICE, "-T" + PIC_TOOL, "-F" + hex_path]
    args.append("-ME" if EEPROM_ONLY else "-M")
    if NO_ERASE:
        args.append("-OH")
    if PRESERVE_PROGRAM:
        args.append("-OP0-1FFF")
    if POWER_FROM_TOOL:
        args.append("-W")
    args.append("-OL")
    return args


class FlashWorker(QtCore.QThread):
    line = QtCore.pyqtSignal(str)
    done = QtCore.pyqtSignal(int)

    def __init__(self, ipecmd, hex_path):
        super().__init__()
        self.ipecmd = ipecmd
        self.hex_path = hex_path

    def run(self):
        try:
            cmd = build_flash_args(self.ipecmd, self.hex_path)
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.stdout:
                for line in result.stdout.splitlines():
                    self.line.emit(line)
            if result.stderr:
                for line in result.stderr.splitlines():
                    self.line.emit("[stderr] " + line)
            self.done.emit(result.returncode)
        except Exception as exc:
            self.line.emit(f"✗ Ошибка: {exc}")
            self.done.emit(1)


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
        if not 0 <= address < EEPROM_SIZE:
            raise ValueError("Адрес выходит за пределы 24C16.")
        block = (address >> 8) & 0x07
        device_address = BASE_I2C_ADDRESS | block
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
"""


# ══════════════════════════════════════════════════════════════════════════════
# ВКЛ 1: VF_GEN GUI
# ══════════════════════════════════════════════════════════════════════════════

class VFGenTab(QtWidgets.QWidget):
    def __init__(self, status):
        super().__init__()
        self.status = status
        self.counters = Counters('counters.json')
        self.worker = None
        self.flash_worker = None
        self._flash_value = None
        self.init_ui()
        self._refresh_counter()

    def init_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        title = QtWidgets.QLabel("ГЕНЕРАТОР ЧАСТОТЫ PIC16F1934")
        font = title.font()
        font.setPointSize(16)
        font.setBold(True)
        title.setFont(font)
        title.setAlignment(QtCore.Qt.AlignCenter)
        root.addWidget(title)

        inp_group = QtWidgets.QGroupBox("Целевая частота")
        inp_layout = QtWidgets.QHBoxLayout(inp_group)
        self.inp = QtWidgets.QLineEdit()
        self.inp.setPlaceholderText("Введите частоту в кГц (например: 3332.85)")
        self.inp.returnPressed.connect(self.on_solve)
        inp_layout.addWidget(self.inp)
        root.addWidget(inp_group)

        btn_layout = QtWidgets.QHBoxLayout()
        self.solve_btn = QtWidgets.QPushButton("ПОДОБРАТЬ ПАРАМЕТРЫ")
        self.solve_btn.clicked.connect(self.on_solve)
        self.auto_btn = QtWidgets.QPushButton("ЗАПИСАТЬ В ПРИБОР")
        self.auto_btn.clicked.connect(self.on_write_auto)
        self.auto_btn.setEnabled(False)
        btn_layout.addWidget(self.solve_btn)
        btn_layout.addWidget(self.auto_btn)
        root.addLayout(btn_layout)

        counter_group = QtWidgets.QGroupBox("Счётчик прошивок")
        counter_layout = QtWidgets.QHBoxLayout(counter_group)
        self.counter_label = QtWidgets.QLabel()
        counter_layout.addWidget(self.counter_label)
        root.addWidget(counter_group)

        self.log = QtWidgets.QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(300)
        root.addWidget(self.log)

    def _refresh_counter(self):
        count, value = self.counters.get_count_and_value(COUNTER_NAME)
        if value is None:
            self.counter_label.setText(f"Всего прошивок: {count}")
        else:
            self.counter_label.setText(f"Всего прошивок: {count} (последняя: {format_value(value)})")

    def on_solve(self):
        try:
            freq_str = self.inp.text().strip()
            if not freq_str:
                self.log.setText("Введите частоту")
                return
            freq = float(freq_str.replace(',', '.')) * 1000

            self.log.append("Подбираю параметры...")

            def solve_async():
                cand = solve(freq)
                self.log.append(f"Подобрано: {format_value(cand.value)} "
                              f"({('точно' if cand.exact else f'±{cand.error:.2f} кГц')}) "
                              f"B1={cand.b1} B2={cand.b2} B3={cand.b3}")
                self.auto_btn.setEnabled(True)

            self.worker = threading.Thread(target=solve_async, daemon=True)
            self.worker.start()
        except ValueError:
            self.log.setText("Ошибка: введите корректную частоту")

    def on_write_auto(self):
        try:
            freq_str = self.inp.text().strip()
            freq = float(freq_str.replace(',', '.')) * 1000
            cand = solve(freq)

            ipecmd = find_ipecmd()
            if not ipecmd:
                self.log.setText("Ошибка: ipecmd.exe не найден. Установите MPLAB X.")
                return

            hex_text = build_hex_for(cand)
            with tempfile.NamedTemporaryFile(mode='w', suffix='.hex', delete=False) as tmp:
                tmp.write(hex_text)
                hex_path = tmp.name

            self._flash_value = cand.value
            self.log.append(f"Подобрано {format_value(cand.value)} ({('точно' if cand.exact else f'±{cand.error:.2f} кГц')}, базовый блок) → прошиваю EEPROM в PIC{PIC_DEVICE}…")
            self.auto_btn.setEnabled(False)
            self.auto_btn.setText("ПРОШИВКА…")
            self.solve_btn.setEnabled(False)

            self.flash_worker = FlashWorker(ipecmd, hex_path)
            self.flash_worker.line.connect(self.log.append)
            self.flash_worker.done.connect(self.on_flash_done)
            self.flash_worker.start()
        except Exception as exc:
            self.log.setText(f"Ошибка: {exc}")

    def on_flash_done(self, rc):
        self.auto_btn.setEnabled(True)
        self.auto_btn.setText("ЗАПИСАТЬ В ПРИБОР")
        self.solve_btn.setEnabled(True)
        if rc == 0:
            total = self.counters.increment(COUNTER_NAME, getattr(self, "_flash_value", 0))
            self._refresh_counter()
            self.log.append(f"✓ EEPROM записан (№ {total}). Основная прошивка не тронута.")
            self.inp.selectAll()
            self.inp.setFocus()
        else:
            self.log.append(f"✗ Ошибка прошивки (код {rc}). См. сообщения выше.")


# ══════════════════════════════════════════════════════════════════════════════
# ВКЛ 2: СИНТЕТИЧЕСКИЙ ЖУРНАЛ GUI
# ══════════════════════════════════════════════════════════════════════════════

class JournalTab(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.path = None
        self.data = None
        self.daily = []
        self.monthly = []
        self.init_ui()

    def init_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        title = QtWidgets.QLabel("ГЕНЕРАТОР СИНТЕТИЧЕСКОГО ЖУРНАЛА")
        font = title.font()
        font.setPointSize(17)
        font.setBold(True)
        title.setFont(font)
        title.setAlignment(QtCore.Qt.AlignCenter)
        root.addWidget(title)

        warning = QtWidgets.QLabel(
            "Работает только с копией BIN и сохраняет отдельный файл __SYNTHETIC. "
            "Прямая запись в устройство отсутствует."
        )
        warning.setWordWrap(True)
        warning.setAlignment(QtCore.Qt.AlignCenter)
        warning.setStyleSheet("color:#ffcf70;")
        root.addWidget(warning)

        file_box = QtWidgets.QGroupBox("Исходный дамп")
        file_layout = QtWidgets.QHBoxLayout(file_box)
        self.open_btn = QtWidgets.QPushButton("Открыть BIN")
        self.open_btn.clicked.connect(self.open_file)
        self.path_edit = QtWidgets.QLineEdit()
        self.path_edit.setReadOnly(True)
        file_layout.addWidget(self.open_btn)
        file_layout.addWidget(self.path_edit, 1)
        root.addWidget(file_box)

        params = QtWidgets.QGroupBox("Параметры синтетической хронологии")
        form = QtWidgets.QGridLayout(params)

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

        form.addWidget(QtWidgets.QLabel("Конечное показание:"), 0, 0)
        form.addWidget(self.final_value, 0, 1)
        form.addWidget(QtWidgets.QLabel("Желаемый средний расход в сутки:"), 1, 0)
        form.addWidget(self.average, 1, 1)
        form.addWidget(QtWidgets.QLabel("Разброс расхода:"), 2, 0)
        form.addWidget(self.variation, 2, 1)
        form.addWidget(QtWidgets.QLabel("Seed генератора:"), 3, 0)
        form.addWidget(self.seed, 3, 1)

        root.addWidget(params)

        self.generate_btn = QtWidgets.QPushButton("СФОРМИРОВАТЬ СИНТЕТИЧЕСКУЮ КОПИЮ")
        self.generate_btn.setEnabled(False)
        self.generate_btn.clicked.connect(self.generate)
        root.addWidget(self.generate_btn)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        root.addWidget(self.progress)

        self.status = QtWidgets.QLabel("Откройте 32-КБ BIN-дамп.")
        self.status.setObjectName("Status")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

    def set_status(self, text, ok=None):
        self.status.setText(text)
        if ok is True:
            self.status.setStyleSheet(
                "background:#153c28;border:2px solid #2fc46f;"
                "border-radius:10px;padding:12px;color:#91f4b8;"
            )
        elif ok is False:
            self.status.setStyleSheet(
                "background:#471d25;border:2px solid #ff5a6f;"
                "border-radius:10px;padding:12px;color:#ffabb8;"
            )
        else:
            self.status.setStyleSheet(
                "background:#18202c;border:1px solid #3d4a60;"
                "border-radius:10px;padding:12px;"
            )

    def open_file(self):
        selected, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Открыть дамп журнала", "", "BIN (*.bin *.BIN);;Все файлы (*.*)",
        )
        if not selected:
            return
        path = Path(selected)
        try:
            data = path.read_bytes()
            if len(data) < MIN_DUMP_SIZE:
                raise ValueError(f"Файл имеет размер {len(data)} байт; ожидается 32-КБ дамп.")
            daily = parse_daily(data)
            monthly = parse_monthly(data)
            if len(daily) < 2:
                raise ValueError("Суточный журнал не распознан.")
            self.path = path
            self.data = data
            self.daily = daily
            self.monthly = monthly
            self.path_edit.setText(str(path))
            self.final_value.setValue(daily[-1].value)
            self.generate_btn.setEnabled(True)
            diffs = [
                daily[i + 1].value - daily[i].value
                for i in range(len(daily) - 1)
                if daily[i + 1].value >= daily[i].value
            ]
            average = sum(diffs) / len(diffs) if diffs else 0.0
            if average > 0:
                self.average.setValue(average)
            self.set_status(
                f"✓ Распознано: {len(daily)} суточных страниц и {len(monthly)} месячных записей.\n"
                f"Период: {daily[0].dt:%d.%m.%Y} — {daily[-1].dt:%d.%m.%Y}. "
                f"Последнее архивное значение: {daily[-1].value:.2f}.",
                True,
            )
        except Exception as exc:
            self.path = None
            self.data = None
            self.daily = []
            self.monthly = []
            self.generate_btn.setEnabled(False)
            self.set_status(f"✗ Ошибка: {exc}", False)

    def generate(self):
        if self.path is None or self.data is None:
            self.set_status("Сначала откройте дамп.", False)
            return
        self.generate_btn.setEnabled(False)
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
            self.progress.setValue(30)
            rows = []
            for index, (record, raw, profile) in enumerate(zip(self.daily, values_raw, profiles)):
                write_u24_le(output, record.offset + DAILY_VALUE_OFF, raw)
                for i, interval_raw in enumerate(profile):
                    if not 0 <= interval_raw <= 0xFFFF:
                        raise ValueError("Интервальное значение не помещается в UInt16. Уменьшите средний суточный расход.")
                    pos = record.offset + PROFILE_OFF + i * 2
                    output[pos:pos + 2] = interval_raw.to_bytes(2, "little", signed=False)
                next_increment = values_raw[index + 1] - raw if index + 1 < len(values_raw) else None
                rows.append([
                    f"0x{record.offset:04X}",
                    record.dt.isoformat(),
                    f"{raw / VALUE_SCALE:.2f}",
                    "" if next_increment is None else f"{next_increment / 100:.2f}",
                    sum(profile),
                ])
            self.progress.setValue(65)
            for monthly in self.monthly:
                raw = value_for_month(monthly.year, monthly.month, self.daily, values_raw)
                write_u24_le(output, monthly.offset + MONTHLY_VALUE_OFF, raw)
            out_path = self.path.with_name(
                f"{self.path.stem}__SYNTHETIC_final_{self.final_value.value():.2f}{self.path.suffix or '.bin'}"
            )
            csv_path = out_path.with_suffix(".csv")
            out_path.write_bytes(output)
            with csv_path.open("w", newline="", encoding="utf-8-sig") as file:
                writer = csv.writer(file, delimiter=";")
                writer.writerow(["offset", "date", "cumulative_value", "increment_to_next", "profile_sum_raw"])
                writer.writerows(rows)
            verify = out_path.read_bytes()
            if verify != bytes(output):
                raise RuntimeError("Проверка сохранённого файла не пройдена.")
            check_daily = parse_daily(verify)
            if not check_daily:
                raise RuntimeError("После сохранения журнал не распознаётся.")
            actual_final = max(check_daily, key=lambda item: item.dt).value
            if abs(actual_final - self.final_value.value()) > 0.011:
                raise RuntimeError("Конечное значение после проверки не совпало.")
            self.progress.setValue(100)
            self.set_status(
                f"✓ Готово: создана синтетическая копия.\n{out_path}\nТаблица хронологии: {csv_path}",
                True,
            )
        except Exception as exc:
            self.progress.setValue(0)
            self.set_status(f"✗ Ошибка: {exc}", False)
        finally:
            self.generate_btn.setEnabled(True)


# ══════════════════════════════════════════════════════════════════════════════
# ГЛАВНОЕ ОКНО
# ══════════════════════════════════════════════════════════════════════════════

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, license_status):
        super().__init__()
        self.setWindowTitle("VF Suite — MT Writer + VF Gen + Синтетический журнал")
        self.setMinimumSize(1000, 750)

        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        license_label = QtWidgets.QLabel()
        if license_status["valid"]:
            license_label.setText(f"✓ Лицензия активна: {license_status.get('message', '')}")
            license_label.setStyleSheet("background:#153c28;border:2px solid #2fc46f;border-radius:10px;padding:12px;color:#91f4b8;")
        else:
            license_label.setText(f"Код компьютера: {license_status['machine_code']}")
            license_label.setStyleSheet("background:#2d3340;border:1px solid #5d6a80;border-radius:10px;padding:12px;color:#b0b8c8;")
        layout.addWidget(license_label)

        tabs = QtWidgets.QTabWidget()

        mt_counters = MTCounters(["200_MT", "310_MT"])
        tabs.addTab(MTWriterTab("200_MT", mt_counters), "200_MT (CH341)")
        tabs.addTab(MTWriterTab("310_MT", mt_counters), "310_MT (CH341)")
        tabs.addTab(VFGenTab(license_status), "Генератор частоты (PIC)")
        tabs.addTab(JournalTab(), "Синтетический журнал")

        layout.addWidget(tabs)

        self.setCentralWidget(central)


class ActivationDialog(QtWidgets.QDialog):
    def __init__(self, license_status):
        super().__init__()
        self.setWindowTitle("Активация")
        self.setMinimumWidth(400)
        layout = QtWidgets.QVBoxLayout(self)

        layout.addWidget(QtWidgets.QLabel(
            f"Требуется активация.\n\nКод компьютера:\n{license_status['machine_code']}"
        ))

        key_layout = QtWidgets.QHBoxLayout()
        key_layout.addWidget(QtWidgets.QLabel("Ключ:"))
        self.key_input = QtWidgets.QLineEdit()
        key_layout.addWidget(self.key_input)
        layout.addLayout(key_layout)

        btn_layout = QtWidgets.QHBoxLayout()
        ok_btn = QtWidgets.QPushButton("OK")
        cancel_btn = QtWidgets.QPushButton("Отмена")
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def exec_(self):
        if super().exec_() == QtWidgets.QDialog.Accepted:
            key = self.key_input.text().strip()
            if key:
                key_file = os.path.expanduser("~/.vf_license")
                with open(key_file, 'w') as fh:
                    fh.write(key)
            return QtWidgets.QDialog.Accepted
        return QtWidgets.QDialog.Rejected




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

    win = MainWindow(status)
    win.show()

    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
