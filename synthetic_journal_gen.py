# -*- coding: utf-8 -*-
"""
Офлайн-генератор СИНТЕТИЧЕСКОГО журнала с активацией по коду компьютера.
Работает только с копией BIN-файла, сохраняет отдельный файл __SYNTHETIC.

Запуск:
  python synthetic_journal_gen.py                    (GUI с активацией)
  pyinstaller --onefile synthetic_journal_gen.py    (собрать exe)
"""

import base64
import binascii
import csv
import hashlib
import hmac
import math
import os
import platform
import random
import struct
import sys
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

from PyQt5 import QtCore, QtGui, QtWidgets


# ══════════════════════════════════════════════════════════════════════════
# ЛИЦЕНЗИРОВАНИЕ (идентично VF_Gen.py, MT_Writer.py)
# ══════════════════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════════════════
# ДАННЫЕ ЖУРНАЛА
# ══════════════════════════════════════════════════════════════════════════

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
        raise ValueError(
            f"Значение RAW {raw} не помещается в UInt24 "
            f"(максимум {0xFFFFFF})."
        )
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
    records: List[DailyRecord] = []

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
                data[
                    offset + PROFILE_OFF + i * 2:
                    offset + PROFILE_OFF + i * 2 + 2
                ],
                "little",
                signed=False,
            )
            for i in range(PROFILE_COUNT)
        ]

        records.append(DailyRecord(offset, dt, value, profile))

    records.sort(key=lambda item: (item.dt, item.offset))
    return records


def parse_monthly(data: bytes) -> List[MonthlyRecord]:
    result: List[MonthlyRecord] = []

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
        result.append(
            MonthlyRecord(offset, month, year, raw / VALUE_SCALE, valid)
        )

    return result


def make_template_weights(records: List[DailyRecord]) -> List[float]:
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


def allocate_integer_total(
    total: int,
    base_weights: List[float],
    rng: random.Random,
    noise: float,
) -> List[int]:
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

    fractions = sorted(
        range(PROFILE_COUNT),
        key=lambda i: exact[i] - integers[i],
        reverse=True,
    )
    for i in fractions[:remainder]:
        integers[i] += 1

    return integers


def generate_increments(
    count: int,
    average: float,
    variation_percent: float,
    rng: random.Random,
) -> List[int]:
    if count <= 0:
        return []

    target_total = int(round(average * VALUE_SCALE * count))
    values = []

    for _ in range(count):
        factor = 1.0 + rng.uniform(
            -variation_percent / 100.0,
            variation_percent / 100.0,
        )
        values.append(max(0.0, average * factor))

    current_total = sum(values)
    if current_total <= 0:
        raw = [0] * count
    else:
        exact = [value / current_total * target_total for value in values]
        raw = [int(math.floor(value)) for value in exact]
        remainder = target_total - sum(raw)
        order = sorted(
            range(count),
            key=lambda i: exact[i] - raw[i],
            reverse=True,
        )
        for i in order[:remainder]:
            raw[i] += 1

    return raw


def synthetic_values(
    records: List[DailyRecord],
    final_value: float,
    average_daily: float,
    variation_percent: float,
    seed: int,
) -> Tuple[List[int], List[List[int]]]:
    if len(records) < 2:
        raise ValueError("Недостаточно суточных записей для генерации.")

    rng = random.Random(seed)
    increment_count = len(records) - 1
    increments = generate_increments(
        increment_count,
        average_daily,
        variation_percent,
        rng,
    )

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
            order = sorted(
                range(increment_count),
                key=lambda i: exact[i] - increments[i],
                reverse=True,
            )
            for i in order[:remainder]:
                increments[i] += 1

    start_raw = final_raw - sum(increments)
    if final_raw > 0xFFFFFF:
        raise ValueError(
            "Конечное показание превышает максимум формата UInt24: "
            "167772.15."
        )

    values = [start_raw]
    for increment in increments:
        values.append(values[-1] + increment)

    template = make_template_weights(records)
    profiles: List[List[int]] = []

    for increment in increments:
        profiles.append(
            allocate_integer_total(
                increment,
                template,
                rng,
                noise=min(0.95, variation_percent / 100.0 + 0.15),
            )
        )

    profiles.append(list(records[-1].profile))

    return values, profiles


def value_for_month(
    year: int,
    month: int,
    records: List[DailyRecord],
    values_raw: List[int],
) -> int:
    target = date(year, month, 1)

    for record, raw in zip(records, values_raw):
        if record.dt >= target:
            return raw

    return values_raw[-1]


# ══════════════════════════════════════════════════════════════════════════
# GUI
# ══════════════════════════════════════════════════════════════════════════

class JournalTool(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.path: Optional[Path] = None
        self.data: Optional[bytes] = None
        self.daily: List[DailyRecord] = []
        self.monthly: List[MonthlyRecord] = []
        self.license_ok = False
        self.init_ui()
        self.check_license()

    def init_ui(self):
        self.setWindowTitle("Синтетический журнал BIN")
        self.setMinimumSize(760, 580)

        self.setStyleSheet("""
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
        """)

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

        # Лицензия
        self.license_status = QtWidgets.QLabel()
        self.license_status.setObjectName("Status")
        self.license_status.setWordWrap(True)
        root.addWidget(self.license_status)

        warning = QtWidgets.QLabel(
            "Работает только с копией BIN и сохраняет отдельный файл "
            "__SYNTHETIC. Прямая запись в устройство отсутствует."
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

        self.generate_btn = QtWidgets.QPushButton(
            "СФОРМИРОВАТЬ СИНТЕТИЧЕСКУЮ КОПИЮ"
        )
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

    def check_license(self):
        machine_code = get_machine_code()
        self.license_status.setText(
            f"Код компьютера: {machine_code}\n"
            f"Для активации используйте keygen_vf.py"
        )
        self.license_status.setStyleSheet(
            "background:#2d3340;border:1px solid #5d6a80;"
            "border-radius:10px;padding:12px;color:#b0b8c8;"
        )

        key_file = Path(os.path.expanduser("~")) / ".vf_license"
        if not key_file.exists():
            self.license_ok = False
            self.open_btn.setEnabled(False)
            self.generate_btn.setEnabled(False)
            self.status.setText("❌ Лицензия не найдена. Используйте keygen_vf.py для создания ключа.")
            self.status.setStyleSheet(
                "background:#471d25;border:2px solid #ff5a6f;"
                "border-radius:10px;padding:12px;color:#ffabb8;"
            )
            return

        try:
            key = key_file.read_text().strip()
            ok, msg = verify_key(key, machine_code)
            if ok:
                self.license_ok = True
                self.license_status.setText(f"✓ Лицензия активна: {msg}")
                self.license_status.setStyleSheet(
                    "background:#153c28;border:2px solid #2fc46f;"
                    "border-radius:10px;padding:12px;color:#91f4b8;"
                )
                self.open_btn.setEnabled(True)
            else:
                self.license_ok = False
                self.open_btn.setEnabled(False)
                self.generate_btn.setEnabled(False)
                self.status.setText(f"❌ Ошибка лицензии: {msg}")
                self.status.setStyleSheet(
                    "background:#471d25;border:2px solid #ff5a6f;"
                    "border-radius:10px;padding:12px;color:#ffabb8;"
                )
        except Exception as exc:
            self.license_ok = False
            self.open_btn.setEnabled(False)
            self.generate_btn.setEnabled(False)
            self.status.setText(f"❌ Ошибка проверки лицензии: {exc}")
            self.status.setStyleSheet(
                "background:#471d25;border:2px solid #ff5a6f;"
                "border-radius:10px;padding:12px;color:#ffabb8;"
            )

    def set_status(self, text: str, ok: Optional[bool] = None):
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
        if not self.license_ok:
            self.set_status("Требуется активная лицензия.", False)
            return

        selected, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Открыть дамп журнала",
            "",
            "BIN (*.bin *.BIN);;Все файлы (*.*)",
        )
        if not selected:
            return

        path = Path(selected)
        try:
            data = path.read_bytes()
            if len(data) < MIN_DUMP_SIZE:
                raise ValueError(
                    f"Файл имеет размер {len(data)} байт; "
                    f"ожидается 32-КБ дамп."
                )

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
                f"Распознано: {len(daily)} суточных страниц и "
                f"{len(monthly)} месячных записей.\n"
                f"Период: {daily[0].dt:%d.%m.%Y} — "
                f"{daily[-1].dt:%d.%m.%Y}. "
                f"Последнее архивное значение: {daily[-1].value:.2f}.",
                True,
            )
        except Exception as exc:
            self.path = None
            self.data = None
            self.daily = []
            self.monthly = []
            self.generate_btn.setEnabled(False)
            self.set_status(f"Ошибка: {exc}", False)

    def generate(self):
        if not self.license_ok:
            self.set_status("Требуется активная лицензия.", False)
            return

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
            for index, (record, raw, profile) in enumerate(
                zip(self.daily, values_raw, profiles)
            ):
                write_u24_le(
                    output,
                    record.offset + DAILY_VALUE_OFF,
                    raw,
                )

                for i, interval_raw in enumerate(profile):
                    if not 0 <= interval_raw <= 0xFFFF:
                        raise ValueError(
                            "Интервальное значение не помещается в UInt16. "
                            "Уменьшите средний суточный расход."
                        )
                    pos = record.offset + PROFILE_OFF + i * 2
                    output[pos:pos + 2] = interval_raw.to_bytes(
                        2, "little", signed=False
                    )

                next_increment = (
                    values_raw[index + 1] - raw
                    if index + 1 < len(values_raw)
                    else None
                )
                rows.append([
                    f"0x{record.offset:04X}",
                    record.dt.isoformat(),
                    f"{raw / VALUE_SCALE:.2f}",
                    "" if next_increment is None else f"{next_increment / 100:.2f}",
                    sum(profile),
                ])

            self.progress.setValue(65)

            for monthly in self.monthly:
                raw = value_for_month(
                    monthly.year,
                    monthly.month,
                    self.daily,
                    values_raw,
                )
                write_u24_le(
                    output,
                    monthly.offset + MONTHLY_VALUE_OFF,
                    raw,
                )

            out_path = self.path.with_name(
                f"{self.path.stem}__SYNTHETIC"
                f"_final_{self.final_value.value():.2f}"
                f"{self.path.suffix or '.bin'}"
            )
            csv_path = out_path.with_suffix(".csv")

            out_path.write_bytes(output)

            with csv_path.open(
                "w",
                newline="",
                encoding="utf-8-sig",
            ) as file:
                writer = csv.writer(file, delimiter=";")
                writer.writerow([
                    "offset",
                    "date",
                    "cumulative_value",
                    "increment_to_next",
                    "profile_sum_raw",
                ])
                writer.writerows(rows)

            verify = out_path.read_bytes()
            if verify != bytes(output):
                raise RuntimeError(
                    "Проверка сохранённого файла не пройдена."
                )

            check_daily = parse_daily(verify)
            if not check_daily:
                raise RuntimeError(
                    "После сохранения журнал не распознаётся."
                )

            actual_final = max(
                check_daily,
                key=lambda item: item.dt,
            ).value

            if abs(actual_final - self.final_value.value()) > 0.011:
                raise RuntimeError(
                    "Конечное значение после проверки не совпало."
                )

            self.progress.setValue(100)
            self.set_status(
                f"✓ Готово: создана синтетическая копия.\n"
                f"{out_path}\n"
                f"Таблица хронологии: {csv_path}",
                True,
            )

        except Exception as exc:
            self.progress.setValue(0)
            self.set_status(f"✗ Ошибка: {exc}", False)
        finally:
            self.generate_btn.setEnabled(True)


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = JournalTool()
    window.show()
    sys.exit(app.exec_())
