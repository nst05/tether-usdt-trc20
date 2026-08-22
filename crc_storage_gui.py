#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CRC Storage GUI — графическое приложение для работы с CRC-16 CCITT хранилищем
Рекомендуется собирать с pyinstaller:
    pyinstaller --onefile --windowed crc_storage_gui.py
"""

import struct
import sys
import os
from pathlib import Path
from datetime import datetime
import time

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread

try:
    from crc_storage_i2c import (
        I2CWriter, encode_bcd, decode_bcd, find_bcd_records,
        patch_bcd_record, find_records,
        BCD_RECORD_SIZE, BCD_VALUE_SIZE, BCD_COPY_OFFSETS,
    )
except ImportError:
    I2CWriter = None

try:
    from splash_screen import LoadingSplash
except ImportError:
    LoadingSplash = None

# ═══════════════════════════════════════════════════════════════════════════
#  Константы и ядро
# ═══════════════════════════════════════════════════════════════════════════

SCALE = 100
BLOCK_SIZE = 0x28
CRC_SIZE = 2
VALUE_SIZE = 4
INIT_CRC = 0xFFFF
POLY_CRC = 0x1021

# ── Два формата хранения, найденные в дампе ────────────────────────────────
#
# Поле T — value × 100 в BIG-ENDIAN. Блок 42 байта: значение, дубль,
#          32 байта нулей, CRC-16 CCITT. Целостность проверяется по CRC.
#          Пример: 9442.36 по 0x01C1.
#
# Поле S — упакованный BCD с обратным порядком байт. Запись 65 байт:
#          заголовок и ЧЕТЫРЕ копии значения. CRC у формата нет —
#          целостность держится на совпадении копий.
#          Пример: 9399.56 по 0x1446.
#
FORMAT_FIXED = "fixed"
FORMAT_BCD = "bcd"

FIELD_LABEL = {
    FORMAT_FIXED: "T",
    FORMAT_BCD: "S",
}

FIELD_DESCRIPTION = {
    FORMAT_FIXED: "fixed-point × 100, BIG-ENDIAN, 42 байта, CRC-16 CCITT",
    FORMAT_BCD: "BCD обратным порядком байт, 4 копии, без CRC",
}

# Записи, реально присутствующие в дампе: (смещение, значение, формат).
DEFAULT_SLOTS = [
    (0x01C1, 9442.36, FORMAT_FIXED),
    (0x0201, 9440.38, FORMAT_FIXED),
    (0x03E8, 9441.38, FORMAT_FIXED),
    (0x1446, 9399.56, FORMAT_BCD),
]


def crc16_ccitt(data):
    """CRC-16 CCITT"""
    crc = INIT_CRC
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc <<= 1
            if crc & 0x10000:
                crc ^= POLY_CRC
            crc &= 0xFFFF
    return crc


def encode_value(value: float) -> bytes:
    """Значение → fixed-point big-endian"""
    raw = int(round(value * SCALE))
    if not 0 <= raw <= 0xFFFFFFFF:
        raise ValueError(f"Диапазон: 0.00 – 42949672.95")
    return raw.to_bytes(4, "big", signed=False)


def decode_value(data: bytes) -> float:
    """Fixed-point big-endian → значение"""
    if len(data) != 4:
        raise ValueError("Неверная длина данных")
    return int.from_bytes(data, "big", signed=False) / SCALE


def parse_offset(text) -> int:
    """'0x1C1', '1C1h', '449' → int"""
    text = str(text).strip().lower().replace("_", "")
    if text.endswith("h"):
        return int(text[:-1], 16)
    if text.startswith("0x"):
        return int(text, 16)
    return int(text, 10)


def parse_hex_bytes(text: str) -> bytes:
    """'00 0E 68 6C', '000E686C' → bytes"""
    cleaned = "".join(c for c in text if c not in " \t\r\n,-:")
    if cleaned.lower().startswith("0x"):
        cleaned = cleaned[2:]
    if not cleaned:
        raise ValueError("Пустая последовательность байт")
    if len(cleaned) % 2:
        raise ValueError("Нечётное количество hex-символов")
    return bytes.fromhex(cleaned)


def hex_dump(data: bytes, start: int = 0, length: int = 256) -> str:
    """Классический hex-дамп по 16 байт в строке"""
    end = min(len(data), start + length)
    header = "Смещение  " + " ".join(f"{i:02X}" for i in range(16)) + "   ASCII"
    lines = [header, "-" * len(header)]

    for row in range(start - (start % 16), end, 16):
        hex_cells, ascii_cells = [], []
        for i in range(16):
            pos = row + i
            if pos < start or pos >= end:
                hex_cells.append("  ")
                ascii_cells.append(" ")
            else:
                b = data[pos]
                hex_cells.append(f"{b:02X}")
                ascii_cells.append(chr(b) if 32 <= b < 127 else ".")
        lines.append(f"{row:08X}  " + " ".join(hex_cells) + "   " + "".join(ascii_cells))

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
#  Слот записи — одно значение со своим смещением, HEX и CRC
# ═══════════════════════════════════════════════════════════════════════════

class RecordSlot(QtWidgets.QGroupBox):
    """
    Одна запись: смещение, значение, HEX и CRC-16.

    HEX и CRC пересчитываются при каждом изменении значения. Слоты
    независимы — правка одного не трогает остальные.
    """

    write_requested = pyqtSignal(object)   # сам слот
    read_requested = pyqtSignal(object)
    remove_requested = pyqtSignal(object)

    def __init__(self, title: str, offset: int = 0x0000,
                 value: float = None, fmt: str = None, parent=None):
        super().__init__(title, parent)

        fmt = fmt or FORMAT_FIXED

        self.setStyleSheet("""
            QGroupBox {
                border: 2px solid #30363d;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
                font-weight: bold;
                color: #58a6ff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
            }
        """)

        grid = QtWidgets.QGridLayout(self)
        grid.setSpacing(8)
        grid.setContentsMargins(12, 8, 12, 12)

        mono = "'Courier New', monospace"

        # ── Формат ────────────────────────────────────────────────────
        grid.addWidget(QtWidgets.QLabel("Формат:"), 0, 4)
        self.format_combo = QtWidgets.QComboBox()
        self.format_combo.addItem("T — fixed-point + CRC", FORMAT_FIXED)
        self.format_combo.addItem("S — BCD ×4 копии", FORMAT_BCD)
        self.format_combo.setMinimumWidth(180)
        self.format_combo.setToolTip(
            "Поле T — значение × 100 в BIG-ENDIAN, блок 42 байта,\n"
            "  в конце CRC-16 CCITT. Целостность проверяется по CRC.\n\n"
            "Поле S — упакованный BCD обратным порядком байт,\n"
            "  значение продублировано четыре раза. CRC у формата нет,\n"
            "  целостность держится на совпадении копий."
        )
        self.format_combo.currentIndexChanged.connect(self.on_format_changed)
        grid.addWidget(self.format_combo, 0, 5)

        # ── Смещение ──────────────────────────────────────────────────
        grid.addWidget(QtWidgets.QLabel("Смещение:"), 0, 0)
        self.offset_input = QtWidgets.QLineEdit(f"0x{offset:04X}")
        self.offset_input.setMaximumWidth(110)
        self.offset_input.setStyleSheet(f"font-family: {mono};")
        grid.addWidget(self.offset_input, 0, 1)

        # ── Значение ──────────────────────────────────────────────────
        grid.addWidget(QtWidgets.QLabel("Значение:"), 0, 2)
        self.value_input = QtWidgets.QLineEdit()
        self.value_input.setPlaceholderText("например 9399.56")
        self.value_input.setMinimumHeight(38)
        self.value_input.setStyleSheet("""
            QLineEdit {
                font-size: 15px;
                font-weight: bold;
                padding: 4px 8px;
                border: 2px solid #30363d;
                border-radius: 6px;
            }
            QLineEdit:focus { border: 2px solid #58a6ff; }
        """)
        validator = QtGui.QDoubleValidator(0.0, 42949672.95, 2, self)
        validator.setNotation(QtGui.QDoubleValidator.StandardNotation)
        self.value_input.setValidator(validator)
        self.value_input.textChanged.connect(self.recalculate)
        grid.addWidget(self.value_input, 0, 3)

        # ── HEX ───────────────────────────────────────────────────────
        grid.addWidget(QtWidgets.QLabel("HEX:"), 1, 0)
        self.hex_display = QtWidgets.QLineEdit()
        self.hex_display.setReadOnly(True)
        self.hex_display.setStyleSheet(f"""
            QLineEdit {{
                font-family: {mono};
                font-weight: bold;
                background-color: #0d1117;
                border: 2px solid #30363d;
                border-radius: 6px;
                padding: 4px 8px;
                color: #58a6ff;
            }}
        """)
        grid.addWidget(self.hex_display, 1, 1, 1, 1)

        # ── CRC ───────────────────────────────────────────────────────
        self.crc_label = QtWidgets.QLabel("CRC-16:")
        grid.addWidget(self.crc_label, 1, 2)
        self.crc_display = QtWidgets.QLineEdit()
        self.crc_display.setReadOnly(True)
        self.crc_display.setStyleSheet(f"""
            QLineEdit {{
                font-family: {mono};
                font-weight: bold;
                background-color: #0d1117;
                border: 2px solid #30363d;
                border-radius: 6px;
                padding: 4px 8px;
                color: #f85149;
            }}
        """)
        grid.addWidget(self.crc_display, 1, 3)

        # ── Кнопки ────────────────────────────────────────────────────
        buttons = QtWidgets.QHBoxLayout()

        # По умолчанию работает как MT_Writer: вводится целая часть, копейки
        # подставляются случайно. Галочка нужна, когда правится существующее
        # значение и его дробная часть значима (например 9399.56).
        self.exact_check = QtWidgets.QCheckBox("точное значение")
        self.exact_check.setChecked(False)
        self.exact_check.setToolTip(
            "Выключено (по умолчанию) — вводится целая часть, дробная 01–99\n"
            "  подставляется случайно при записи, как в MT_Writer.\n\n"
            "Включено — пишется ровно введённое число, вместе с копейками."
        )
        self.exact_check.setStyleSheet("color: #8b949e; font-weight: normal;")
        self.exact_check.stateChanged.connect(self.recalculate)
        buttons.addWidget(self.exact_check)
        buttons.addStretch()

        self.read_button = QtWidgets.QPushButton("Прочитать")
        self.read_button.clicked.connect(lambda: self.read_requested.emit(self))
        buttons.addWidget(self.read_button)

        self.write_button = QtWidgets.QPushButton("Записать")
        self.write_button.setStyleSheet("""
            QPushButton {
                font-weight: bold;
                background-color: #238636;
                border: 1px solid #2ea043;
                border-radius: 6px;
                color: white;
                padding: 6px 18px;
            }
            QPushButton:hover { background-color: #2ea043; }
            QPushButton:disabled {
                background-color: #21262d;
                border-color: #30363d;
                color: #6e7681;
            }
        """)
        self.write_button.clicked.connect(lambda: self.write_requested.emit(self))
        buttons.addWidget(self.write_button)

        self.remove_button = QtWidgets.QPushButton("✕")
        self.remove_button.setMaximumWidth(34)
        self.remove_button.setToolTip("Убрать слот")
        self.remove_button.clicked.connect(
            lambda: self.remove_requested.emit(self))
        buttons.addWidget(self.remove_button)

        grid.addLayout(buttons, 2, 0, 1, 6)

        index = self.format_combo.findData(fmt)
        if index >= 0:
            self.format_combo.setCurrentIndex(index)

        if value is not None:
            self.value_input.setText(f"{value:.2f}")

        self.on_format_changed()

    # ── Данные слота ──────────────────────────────────────────────────

    def format(self) -> str:
        return self.format_combo.currentData()

    def on_format_changed(self):
        """Подстроить подписи под выбранный формат и пересчитать поля"""
        if self.format() == FORMAT_BCD:
            self.crc_label.setText("Копии:")
            self.value_input.setPlaceholderText("например 9399.56")
        else:
            self.crc_label.setText("CRC-16:")
            self.value_input.setPlaceholderText("например 9442.36")
        self.recalculate()

    def offset(self) -> int:
        """Смещение слота. Бросает ValueError при неразборчивом вводе."""
        return parse_offset(self.offset_input.text())

    def value_text(self) -> str:
        return self.value_input.text().strip()

    def is_exact(self) -> bool:
        return self.exact_check.isChecked()

    def set_value(self, value: float):
        self.value_input.setText(f"{value:.2f}")

    def set_busy(self, busy: bool):
        self.write_button.setEnabled(not busy)
        self.read_button.setEnabled(not busy)

    def recalculate(self):
        """Пересчитать HEX и CRC (или число копий) из текущего значения"""
        text = self.value_text()
        if not text:
            self.hex_display.clear()
            self.crc_display.clear()
            return

        try:
            value = float(text.replace(",", "."))
            bcd = self.format() == FORMAT_BCD

            # В случайном режиме записано будет НЕ то, что введено: копейки
            # подставятся при записи. Показываем диапазон, а не одно значение,
            # чтобы превью не расходилось с тем, что реально ляжет в память.
            if not self.is_exact():
                whole = int(value)
                low, high = whole + 0.01, whole + 0.99

                if bcd:
                    self.hex_display.setText(
                        f"{encode_bcd(low).hex(' ').upper()} … "
                        f"{encode_bcd(high).hex(' ').upper()}")
                    self.crc_display.setText("4 × (нет CRC)")
                else:
                    self.hex_display.setText(
                        f"0x{self.encode_fixed(low).hex().upper()} … "
                        f"0x{self.encode_fixed(high).hex().upper()}")
                    self.crc_display.setText("рассчитается при записи")
                return

            if bcd:
                # BCD: значение × 100 упаковывается в цифры и кладётся
                # обратным порядком байт. CRC у формата нет — целостность
                # держится на четырёх одинаковых копиях.
                self.hex_display.setText(encode_bcd(value).hex(" ").upper())
                self.crc_display.setText("4 × (нет CRC)")
                return

            hex_bytes = self.encode_fixed(value)
            self.hex_display.setText(f"0x{hex_bytes.hex().upper()}")

            block = hex_bytes + hex_bytes + b"\x00" * 32
            self.crc_display.setText(f"0x{crc16_ccitt(block):04X}")

        except (ValueError, OverflowError, struct.error):
            self.hex_display.setText("✗ ошибка")
            self.crc_display.setText("✗ ошибка")

    @staticmethod
    def encode_fixed(value: float) -> bytes:
        """Значение → fixed-point BIG-ENDIAN, 4 байта"""
        raw = int(round(value * SCALE))
        if not 0 <= raw <= 0xFFFFFFFF:
            raise ValueError("вне диапазона")
        return raw.to_bytes(4, "big", signed=False)


# ═══════════════════════════════════════════════════════════════════════════
#  Работник (поток)
# ═══════════════════════════════════════════════════════════════════════════

class FileWorker(QThread):
    loaded = pyqtSignal(list, bytes)  # values, raw data
    error = pyqtSignal(str)

    def __init__(self, filepath):
        super().__init__()
        self.filepath = filepath

    def run(self):
        try:
            if not Path(self.filepath).exists():
                self.error.emit(f"Файл не найден: {self.filepath}")
                return

            with open(self.filepath, 'rb') as f:
                data = f.read()

            values = self._scan_values(data)
            self.loaded.emit(values, data)
        except Exception as e:
            self.error.emit(str(e))

    @staticmethod
    def _scan_values(data):
        values = []
        pos = 0

        while pos < len(data) - BLOCK_SIZE - CRC_SIZE:
            val1 = data[pos:pos+4]
            val2 = data[pos+4:pos+8]
            zeros = data[pos+8:pos+12]

            if val1 == val2 and zeros == b'\x00\x00\x00\x00':
                try:
                    block = data[pos:pos+BLOCK_SIZE]
                    crc_pos = pos + BLOCK_SIZE

                    if crc_pos + CRC_SIZE <= len(data):
                        stored_crc = struct.unpack('>H', data[crc_pos:crc_pos+2])[0]
                        calculated_crc = crc16_ccitt(block)

                        if stored_crc == calculated_crc:
                            value = decode_value(val1)
                            values.append({
                                'pos': pos,
                                'value': value,
                                'crc': stored_crc,
                                'valid': True
                            })
                            pos += BLOCK_SIZE + CRC_SIZE
                            continue
                except Exception:
                    pass

            pos += 1

        return values


# ═══════════════════════════════════════════════════════════════════════════
#  Стили
# ═══════════════════════════════════════════════════════════════════════════

DARK_STYLE = """
QWidget {
    background-color: #0d1117;
    color: #c9d1d9;
    font-family: 'Segoe UI', 'Ubuntu', 'Liberation Sans';
    font-size: 12px;
}

QMainWindow, QDialog {
    background-color: #0d1117;
}

QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 8px;
    color: #c9d1d9;
    selection-background-color: #388bfd;
}

QLineEdit:focus, QTextEdit:focus, QComboBox:focus {
    border: 1px solid #58a6ff;
    outline: none;
}

QPushButton {
    background-color: #238636;
    border: 1px solid #2ea043;
    border-radius: 6px;
    padding: 8px 16px;
    color: #ffffff;
    font-weight: bold;
    min-height: 32px;
}

QPushButton:hover {
    background-color: #2ea043;
}

QPushButton:pressed {
    background-color: #1f6feb;
}

QPushButton:disabled {
    background-color: #21262d;
    color: #6e7681;
    border-color: #30363d;
}

QPushButton#SecondaryButton {
    background-color: #21262d;
    border: 1px solid #30363d;
    color: #c9d1d9;
}

QPushButton#SecondaryButton:hover {
    background-color: #30363d;
    border-color: #58a6ff;
}

QPushButton#DangerButton {
    background-color: #da3633;
    border-color: #f85149;
}

QPushButton#DangerButton:hover {
    background-color: #f85149;
}

QLabel {
    color: #c9d1d9;
}

QLabel#Title {
    font-size: 18px;
    font-weight: bold;
    color: #58a6ff;
}

QLabel#Subtitle {
    font-size: 14px;
    font-weight: bold;
    color: #79c0ff;
}

QLabel#Status {
    font-size: 11px;
    color: #8b949e;
}

QTableWidget {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
    gridline-color: #30363d;
}

QTableWidget::item {
    padding: 4px;
    border: none;
}

QTableWidget::item:selected {
    background-color: #1f6feb;
}

QHeaderView::section {
    background-color: #161b22;
    color: #79c0ff;
    padding: 4px;
    border: none;
    border-right: 1px solid #30363d;
    border-bottom: 1px solid #30363d;
    font-weight: bold;
    text-align: left;
}

QProgressBar {
    border: 1px solid #30363d;
    border-radius: 4px;
    background-color: #161b22;
    height: 20px;
}

QProgressBar::chunk {
    background-color: #238636;
    border-radius: 3px;
}

QMenuBar {
    background-color: #0d1117;
    color: #c9d1d9;
    border-bottom: 1px solid #30363d;
}

QMenuBar::item:selected {
    background-color: #1f6feb;
}

QMenu {
    background-color: #161b22;
    color: #c9d1d9;
    border: 1px solid #30363d;
}

QMenu::item:selected {
    background-color: #1f6feb;
}

QFileDialog {
    background-color: #0d1117;
}

QMessageBox {
    background-color: #0d1117;
}

QMessageBox QLabel {
    color: #c9d1d9;
}

QDialog {
    background-color: #0d1117;
}

QSplitter::handle {
    background-color: #30363d;
}

QScrollBar:vertical {
    background-color: #161b22;
    width: 12px;
    border: none;
}

QScrollBar::handle:vertical {
    background-color: #30363d;
    border-radius: 6px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background-color: #484f58;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    border: none;
    background: none;
}
"""


# ═══════════════════════════════════════════════════════════════════════════
#  Главное окно
# ═══════════════════════════════════════════════════════════════════════════

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.filepath = None
        self.file_data = None       # bytearray — рабочая копия дампа
        self.original_data = None   # bytes — состояние на момент загрузки
        self.dump_writes = []
        self.worker = None
        self.values = []
        self.selected_row = -1
        self.updating_table = False  # Флаг: обновляем ли таблицу из кода
        self.init_ui()
        self.load_last_file()

    def init_ui(self):
        self.setWindowTitle("CRC Storage Editor — CRC-16 CCITT")
        self.setGeometry(100, 100, 1200, 700)
        self.setStyleSheet(DARK_STYLE)

        # ── Главный виджет ────────────────────────────────────────────
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        main_layout = QtWidgets.QVBoxLayout(central)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # ── Верхняя панель ────────────────────────────────────────────
        top = self.create_top_panel()
        main_layout.addLayout(top)

        # ── Вкладки: значения / дамп / i2c ────────────────────────────────────
        self.tabs = QtWidgets.QTabWidget()
        main_layout.addWidget(self.tabs)

        values_tab = QtWidgets.QWidget()
        values_layout = QtWidgets.QVBoxLayout(values_tab)
        values_layout.setContentsMargins(0, 8, 0, 0)
        self.tabs.addTab(values_tab, "Значения")
        self.tabs.addTab(self.create_dump_tab(), "Дамп (прямая запись)")
        self.tabs.addTab(self.create_i2c_tab(), "I2C/EEPROM 24C256")

        # ── Таблица значений ──────────────────────────────────────────
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Позиция", "Значение", "HEX", "CRC-16", "Статус"])
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setColumnWidth(0, 100)
        self.table.setColumnWidth(1, 120)
        self.table.setColumnWidth(2, 120)
        self.table.setColumnWidth(3, 100)
        self.table.setColumnWidth(4, 100)
        self.table.itemChanged.connect(self.on_value_edited)
        values_layout.addWidget(self.table)

        # ── Нижняя панель (редактирование) ────────────────────────────
        values_layout.addWidget(self.create_bottom_panel())

        # ── Строка состояния ──────────────────────────────────────────
        self.statusbar = self.statusBar()
        self.update_status("Готово")

    def create_top_panel(self):
        """Верхняя панель с файлом"""
        layout = QtWidgets.QHBoxLayout()
        layout.setSpacing(12)

        # Заголовок
        title = QtWidgets.QLabel("CRC Storage Editor")
        title.setObjectName("Title")
        layout.addWidget(title)

        layout.addSpacing(20)

        # Путь файла
        file_label = QtWidgets.QLabel("Файл:")
        layout.addWidget(file_label)

        self.file_path_label = QtWidgets.QLineEdit()
        self.file_path_label.setReadOnly(True)
        self.file_path_label.setMaximumWidth(400)
        layout.addWidget(self.file_path_label)

        # Кнопки файла
        open_btn = QtWidgets.QPushButton("Открыть")
        open_btn.setMaximumWidth(100)
        open_btn.clicked.connect(self.open_file)
        layout.addWidget(open_btn)

        reload_btn = QtWidgets.QPushButton("Перезагрузить")
        reload_btn.setMaximumWidth(120)
        reload_btn.clicked.connect(self.reload_file)
        layout.addWidget(reload_btn)

        save_btn = QtWidgets.QPushButton("Сохранить на диск")
        save_btn.setMaximumWidth(140)
        save_btn.clicked.connect(self.save_file_to_disk)
        save_btn.setToolTip("Сохранить все изменения из памяти на диск")
        layout.addWidget(save_btn)

        layout.addStretch()

        # Инфо
        self.info_label = QtWidgets.QLabel()
        self.info_label.setObjectName("Status")
        layout.addWidget(self.info_label)

        return layout

    def create_bottom_panel(self):
        """Нижняя панель редактирования"""
        layout = QtWidgets.QGroupBox("Редактирование")
        grid = QtWidgets.QGridLayout(layout)
        grid.setSpacing(12)

        # Позиция
        grid.addWidget(QtWidgets.QLabel("Позиция:"), 0, 0)
        self.pos_display = QtWidgets.QLineEdit()
        self.pos_display.setReadOnly(True)
        self.pos_display.setMaximumWidth(150)
        grid.addWidget(self.pos_display, 0, 1)

        # Текущее значение
        grid.addWidget(QtWidgets.QLabel("Текущее значение:"), 0, 2)
        self.current_value_display = QtWidgets.QLineEdit()
        self.current_value_display.setReadOnly(True)
        self.current_value_display.setMaximumWidth(150)
        grid.addWidget(self.current_value_display, 0, 3)

        # Новое значение
        grid.addWidget(QtWidgets.QLabel("Новое значение:"), 1, 0)
        self.new_value_input = QtWidgets.QLineEdit()
        self.new_value_input.setPlaceholderText("Например: 9442.36")
        self.new_value_input.setMaximumWidth(150)
        validator = QtGui.QDoubleValidator(0.0, 42949672.95, 2, self)
        validator.setNotation(QtGui.QDoubleValidator.StandardNotation)
        self.new_value_input.setValidator(validator)
        self.new_value_input.returnPressed.connect(self.update_value)
        grid.addWidget(self.new_value_input, 1, 1)

        # Новый CRC
        grid.addWidget(QtWidgets.QLabel("Новый CRC-16:"), 1, 2)
        self.new_crc_display = QtWidgets.QLineEdit()
        self.new_crc_display.setReadOnly(True)
        self.new_crc_display.setMaximumWidth(150)
        grid.addWidget(self.new_crc_display, 1, 3)

        # Кнопки
        update_btn = QtWidgets.QPushButton("Обновить значение")
        update_btn.setMinimumHeight(40)
        update_btn.clicked.connect(self.update_value)
        grid.addWidget(update_btn, 0, 4, 2, 1)
        grid.setColumnStretch(5, 1)

        return layout

    def create_dump_tab(self):
        """Вкладка дампа: hex-просмотр и прямая запись байт"""
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(12)

        # ── Навигация по дампу ────────────────────────────────────────
        nav = QtWidgets.QHBoxLayout()
        nav.addWidget(QtWidgets.QLabel("Смещение:"))
        self.dump_offset_input = QtWidgets.QLineEdit("0x0000")
        self.dump_offset_input.setMaximumWidth(120)
        self.dump_offset_input.returnPressed.connect(self.refresh_dump)
        nav.addWidget(self.dump_offset_input)

        nav.addWidget(QtWidgets.QLabel("Длина:"))
        self.dump_length_input = QtWidgets.QLineEdit("512")
        self.dump_length_input.setMaximumWidth(100)
        self.dump_length_input.returnPressed.connect(self.refresh_dump)
        nav.addWidget(self.dump_length_input)

        show_btn = QtWidgets.QPushButton("Показать")
        show_btn.setObjectName("SecondaryButton")
        show_btn.setMaximumWidth(110)
        show_btn.clicked.connect(self.refresh_dump)
        nav.addWidget(show_btn)

        prev_btn = QtWidgets.QPushButton("◀ Назад")
        prev_btn.setObjectName("SecondaryButton")
        prev_btn.setMaximumWidth(100)
        prev_btn.clicked.connect(lambda: self.page_dump(-1))
        nav.addWidget(prev_btn)

        next_btn = QtWidgets.QPushButton("Вперёд ▶")
        next_btn.setObjectName("SecondaryButton")
        next_btn.setMaximumWidth(100)
        next_btn.clicked.connect(lambda: self.page_dump(1))
        nav.addWidget(next_btn)

        nav.addSpacing(20)
        nav.addWidget(QtWidgets.QLabel("Найти байты:"))
        self.dump_find_input = QtWidgets.QLineEdit()
        self.dump_find_input.setPlaceholderText("00 0E 68 6C")
        self.dump_find_input.setMaximumWidth(180)
        self.dump_find_input.returnPressed.connect(self.find_in_dump)
        nav.addWidget(self.dump_find_input)

        find_btn = QtWidgets.QPushButton("Найти")
        find_btn.setObjectName("SecondaryButton")
        find_btn.setMaximumWidth(90)
        find_btn.clicked.connect(self.find_in_dump)
        nav.addWidget(find_btn)

        nav.addStretch()
        layout.addLayout(nav)

        # ── Сам дамп ──────────────────────────────────────────────────
        self.dump_view = QtWidgets.QPlainTextEdit()
        self.dump_view.setReadOnly(True)
        self.dump_view.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.dump_view.setFont(QtGui.QFont("Courier New", 10))
        layout.addWidget(self.dump_view)

        # ── Прямая запись ─────────────────────────────────────────────
        box = QtWidgets.QGroupBox("Прямая запись в дамп")
        grid = QtWidgets.QGridLayout(box)
        grid.setSpacing(12)

        grid.addWidget(QtWidgets.QLabel("Смещение:"), 0, 0)
        self.write_offset_input = QtWidgets.QLineEdit()
        self.write_offset_input.setPlaceholderText("0x01C1")
        self.write_offset_input.setMaximumWidth(140)
        grid.addWidget(self.write_offset_input, 0, 1)

        grid.addWidget(QtWidgets.QLabel("Байты (hex):"), 0, 2)
        self.write_hex_input = QtWidgets.QLineEdit()
        self.write_hex_input.setPlaceholderText("00 0E 68 6C")
        grid.addWidget(self.write_hex_input, 0, 3)

        write_bytes_btn = QtWidgets.QPushButton("Записать байты")
        write_bytes_btn.clicked.connect(self.write_raw_bytes)
        grid.addWidget(write_bytes_btn, 0, 4)

        grid.addWidget(QtWidgets.QLabel("Значение:"), 1, 2)
        self.write_value_input = QtWidgets.QLineEdit()
        self.write_value_input.setPlaceholderText("9442.36")
        grid.addWidget(self.write_value_input, 1, 3)

        write_value_btn = QtWidgets.QPushButton("Записать значение + CRC")
        write_value_btn.clicked.connect(self.write_value_block)
        grid.addWidget(write_value_btn, 1, 4)

        check_btn = QtWidgets.QPushButton("Проверить CRC блока")
        check_btn.setObjectName("SecondaryButton")
        check_btn.clicked.connect(self.check_dump_crc)
        grid.addWidget(check_btn, 1, 0, 1, 2)

        grid.setColumnStretch(3, 1)
        layout.addWidget(box)

        # ── Кнопки применения ─────────────────────────────────────────
        actions = QtWidgets.QHBoxLayout()
        self.dump_changes_label = QtWidgets.QLabel("Изменений нет")
        self.dump_changes_label.setObjectName("Status")
        actions.addWidget(self.dump_changes_label)
        actions.addStretch()

        undo_btn = QtWidgets.QPushButton("Отменить последнюю запись")
        undo_btn.setObjectName("SecondaryButton")
        undo_btn.clicked.connect(self.undo_dump_write)
        actions.addWidget(undo_btn)

        revert_btn = QtWidgets.QPushButton("Сбросить все изменения")
        revert_btn.setObjectName("DangerButton")
        revert_btn.clicked.connect(self.revert_dump)
        actions.addWidget(revert_btn)

        save_dump_btn = QtWidgets.QPushButton("Сохранить дамп")
        save_dump_btn.clicked.connect(self.save_dump)
        actions.addWidget(save_dump_btn)

        layout.addLayout(actions)

        return tab

    def create_i2c_tab(self):
        """Вкладка I2C: запись в EEPROM 24C256 с CH341 программатором"""
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        # ── Заголовок ─────────────────────────────────────────────────
        title = QtWidgets.QLabel("Запись значения в EEPROM 24C256")
        title.setObjectName("Title")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #58a6ff;")
        layout.addWidget(title)

        hint = QtWidgets.QLabel(
            "Каждая запись — отдельный слот со своим смещением. "
            "HEX и CRC-16 считаются на лету, слоты пишутся независимо друг "
            "от друга: правка одного не трогает остальные.\n"
            "По умолчанию вводится целая часть, а дробная 01–99 "
            "подставляется случайно при записи. Чтобы записать число ровно "
            "как введено, поставьте в слоте галочку «точное значение»."
        )
        hint.setStyleSheet("color: #8b949e; font-size: 13px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # ── Микросхема ────────────────────────────────────────────────
        offset_layout = QtWidgets.QHBoxLayout()
        offset_layout.addWidget(QtWidgets.QLabel("Микросхема:"))
        self.i2c_chip_combo = QtWidgets.QComboBox()
        self.i2c_chip_combo.addItems(["24C256", "24C128", "24C64",
                                      "24C32", "24C16", "24C08"])
        self.i2c_chip_combo.setMaximumWidth(140)
        offset_layout.addWidget(self.i2c_chip_combo)

        self.i2c_probe_button = QtWidgets.QPushButton("Определить чип")
        self.i2c_probe_button.clicked.connect(self.i2c_probe_chip)
        offset_layout.addWidget(self.i2c_probe_button)

        self.i2c_scan_button = QtWidgets.QPushButton("Найти записи")
        self.i2c_scan_button.setToolTip(
            "Вычитать микросхему целиком и создать слот для каждой найденной "
            "записи")
        self.i2c_scan_button.clicked.connect(self.i2c_scan_records)
        offset_layout.addWidget(self.i2c_scan_button)

        self.i2c_scan_file_button = QtWidgets.QPushButton("Найти в файле")
        self.i2c_scan_file_button.setToolTip(
            "Найти записи в открытом дампе, не обращаясь к железу")
        self.i2c_scan_file_button.clicked.connect(self.i2c_scan_file)
        offset_layout.addWidget(self.i2c_scan_file_button)

        self.i2c_add_button = QtWidgets.QPushButton("+ Слот")
        self.i2c_add_button.clicked.connect(lambda: self.add_i2c_slot())
        offset_layout.addWidget(self.i2c_add_button)

        offset_layout.addStretch()
        layout.addLayout(offset_layout)

        # ── Слоты записей ─────────────────────────────────────────────
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(260)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        container = QtWidgets.QWidget()
        self.i2c_slots_layout = QtWidgets.QVBoxLayout(container)
        self.i2c_slots_layout.setContentsMargins(0, 0, 0, 0)
        self.i2c_slots_layout.setSpacing(10)
        self.i2c_slots_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)

        self.i2c_slots = []

        # Слоты под записи, реально присутствующие в дампе.
        for offset, value, fmt in DEFAULT_SLOTS:
            self.add_i2c_slot(offset=offset, value=value, fmt=fmt)

        # ── Прогресс и статус ─────────────────────────────────────────
        self.i2c_progress = QtWidgets.QProgressBar()
        self.i2c_progress.setRange(0, 100)
        self.i2c_progress.setValue(0)
        self.i2c_progress.setVisible(False)
        self.i2c_progress.setStyleSheet("""
            QProgressBar {
                border: 2px solid #30363d;
                border-radius: 6px;
                background-color: #161b22;
                height: 28px;
            }
            QProgressBar::chunk {
                background-color: #238636;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.i2c_progress)

        self.i2c_status = QtWidgets.QTextEdit()
        self.i2c_status.setText("Готово к работе")
        self.i2c_status.setReadOnly(True)
        self.i2c_status.setMinimumHeight(100)
        self.i2c_status.setMaximumHeight(300)
        self.i2c_status.setStyleSheet("""
            QTextEdit {
                background-color: #0d1117;
                border: 2px solid #30363d;
                border-radius: 6px;
                padding: 12px;
                color: #c9d1d9;
                font-size: 12px;
                font-family: 'Courier New', monospace;
            }
        """)
        layout.addWidget(self.i2c_status)

        # ── Запись всех слотов ────────────────────────────────────────
        self.i2c_write_button = QtWidgets.QPushButton("ЗАПИСАТЬ ВСЕ СЛОТЫ")
        self.i2c_write_button.setMinimumHeight(56)
        self.i2c_write_button.setStyleSheet("""
            QPushButton {
                font-size: 16px;
                font-weight: bold;
                background-color: #238636;
                border: 2px solid #2ea043;
                border-radius: 6px;
                color: white;
                padding: 12px;
            }
            QPushButton:hover {
                background-color: #2ea043;
            }
            QPushButton:pressed {
                background-color: #1f6feb;
            }
            QPushButton:disabled {
                background-color: #21262d;
                border-color: #30363d;
                color: #6e7681;
            }
        """)
        self.i2c_write_button.clicked.connect(self.i2c_write_and_verify)
        layout.addWidget(self.i2c_write_button)

        # ── Информация о i2cpy ────────────────────────────────────────
        info_text = "✗ i2cpy не установлена" if I2CWriter is None else "✓ i2cpy установлена (CH341 программатор готов)"
        self.i2c_info = QtWidgets.QLabel(info_text)
        self.i2c_info.setStyleSheet("""
            QLabel {
                color: #f85149;
                font-size: 12px;
            }
        """)
        if I2CWriter is not None:
            self.i2c_info.setStyleSheet("""
                QLabel {
                    color: #7ee78c;
                    font-size: 12px;
                }
            """)
        self.i2c_info.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.i2c_info)

        layout.addStretch()

        return tab

    # ── Управление слотами ────────────────────────────────────────────

    def add_i2c_slot(self, offset: int = 0x0000, value: float = None,
                     fmt: str = None) -> 'RecordSlot':
        """Добавить слот записи на вкладку I2C"""
        slot = RecordSlot("", offset=offset, value=value, fmt=fmt)
        slot.format_combo.currentIndexChanged.connect(self.renumber_i2c_slots)
        slot.write_requested.connect(self.i2c_write_slot)
        slot.read_requested.connect(self.i2c_read_slot)
        slot.remove_requested.connect(self.remove_i2c_slot)

        # Перед распоркой, чтобы слоты прижимались кверху.
        self.i2c_slots_layout.insertWidget(
            self.i2c_slots_layout.count() - 1, slot)
        self.i2c_slots.append(slot)
        self.renumber_i2c_slots()
        return slot

    def remove_i2c_slot(self, slot: 'RecordSlot'):
        """Убрать слот"""
        if slot not in self.i2c_slots:
            return
        self.i2c_slots.remove(slot)
        self.i2c_slots_layout.removeWidget(slot)
        slot.setParent(None)
        slot.deleteLater()
        self.renumber_i2c_slots()

    def clear_i2c_slots(self):
        """Убрать все слоты"""
        for slot in list(self.i2c_slots):
            self.remove_i2c_slot(slot)

    def renumber_i2c_slots(self):
        """Обновить заголовки слотов: обозначение поля, номер, формат"""
        counters = {}
        for slot in self.i2c_slots:
            label = FIELD_LABEL[slot.format()]
            counters[label] = counters.get(label, 0) + 1
            number = counters[label]
            slot.setTitle(
                f"Поле {label}{number}  ·  {FIELD_DESCRIPTION[slot.format()]}")

    def populate_i2c_slots(self, fixed_records, bcd_records, source: str):
        """Пересобрать слоты по найденным записям"""
        total = len(fixed_records) + len(bcd_records)
        if not total:
            self.update_i2c_status(
                f"Записей не найдено ({source}). Слоты оставлены как есть.",
                "error")
            return

        self.clear_i2c_slots()

        for record in fixed_records:
            self.add_i2c_slot(offset=record['offset'], value=record['value'],
                              fmt=FORMAT_FIXED)
        for record in bcd_records:
            self.add_i2c_slot(offset=record['offset'], value=record['value'],
                              fmt=FORMAT_BCD)

        lines = [f"Найдено записей: {total} ({source})", ""]
        for record in fixed_records:
            lines.append(f"  fixed-point  0x{record['offset']:04X}  "
                         f"{record['value']:>12.2f}  CRC 0x{record['crc']:04X}")
        for record in bcd_records:
            lines.append(f"  BCD          0x{record['offset']:04X}  "
                         f"{record['value']:>12.2f}  "
                         f"копии {', '.join('0x%04X' % c for c in record['copies'])}")

        self.update_i2c_status("\n".join(lines), "success")

    def i2c_scan_file(self):
        """Найти записи в открытом дампе, не обращаясь к железу"""
        if not self.file_data:
            self.update_i2c_status(
                "Сначала откройте файл дампа на вкладке «Значения».", "error")
            return

        data = bytes(self.file_data)
        self.populate_i2c_slots(find_records(data),
                                find_bcd_records(data, 0.01, 999999.99),
                                f"файл, {len(data)} байт")

    def i2c_scan_records(self):
        """Вычитать микросхему целиком и создать слот на каждую запись"""
        if I2CWriter is None:
            self.update_i2c_status(
                "✗ i2cpy не установлена. Установите: pip install i2cpy", "error")
            return

        self.i2c_scan_button.setEnabled(False)
        self.i2c_progress.setVisible(True)
        self.i2c_progress.setValue(0)

        writer = I2CWriter(chip=self.i2c_chip_combo.currentText())

        try:
            writer.open_programmer()

            data = bytearray()
            while len(data) < writer.size:
                piece = min(256, writer.size - len(data))
                data.extend(writer.read_bytes(len(data), piece))
                self.i2c_progress.setValue(int(len(data) * 100 / writer.size))
                QtWidgets.QApplication.processEvents()

            data = bytes(data)
            self.populate_i2c_slots(find_records(data),
                                    find_bcd_records(data, 0.01, 999999.99),
                                    f"{writer.chip}, {len(data)} байт")

        except Exception as exc:
            self.update_i2c_status(f"✗ Ошибка чтения: {exc}", "error")

        finally:
            writer.close_programmer()
            self.i2c_progress.setVisible(False)
            self.i2c_scan_button.setEnabled(True)

    def i2c_read_slot(self, slot: 'RecordSlot'):
        """Прочитать значение слота из микросхемы"""
        if I2CWriter is None:
            self.update_i2c_status(
                "✗ i2cpy не установлена. Установите: pip install i2cpy", "error")
            return

        try:
            offset = slot.offset()
        except ValueError as exc:
            self.update_i2c_status(f"✗ Смещение: {exc}", "error")
            return

        slot.set_busy(True)
        writer = I2CWriter(offset=offset,
                           chip=self.i2c_chip_combo.currentText())

        try:
            writer.open_programmer()

            if slot.format() == FORMAT_BCD:
                raw = writer.read_bytes(offset, BCD_RECORD_SIZE)
                copies = [raw[c:c + BCD_VALUE_SIZE] for c in BCD_COPY_OFFSETS]
                value = decode_bcd(copies[0])

                if value is None:
                    self.update_i2c_status(
                        f"0x{offset:04X}: байты {copies[0].hex(' ').upper()} "
                        f"не являются корректным BCD.", "error")
                else:
                    slot.set_value(value)
                    agree = all(c == copies[0] for c in copies)
                    self.update_i2c_status(
                        f"0x{offset:04X}: прочитано {value:.2f} (BCD)\n"
                        f"  копии: "
                        f"{'  '.join(c.hex(' ').upper() for c in copies)}\n"
                        f"  {'✓ все четыре копии совпадают' if agree else '✗ КОПИИ РАСХОДЯТСЯ'}",
                        "success" if agree else "error")
            else:
                record = writer.read_record(offset)
                slot.set_value(record['value'])
                self.update_i2c_status(
                    f"0x{offset:04X}: прочитано {record['value']:.2f}\n"
                    f"  CRC сохранённый 0x{record['crc_stored']:04X}, "
                    f"расчётный 0x{record['crc']:04X}\n"
                    f"  {'✓ запись целая' if record['valid'] else '✗ CRC НЕ СОШЁЛСЯ'}",
                    "success" if record['valid'] else "error")

        except Exception as exc:
            self.update_i2c_status(f"✗ Ошибка чтения: {exc}", "error")

        finally:
            writer.close_programmer()
            slot.set_busy(False)

    def i2c_write_slot(self, slot: 'RecordSlot'):
        """Записать значение одного слота, не трогая остальные"""
        if I2CWriter is None:
            self.update_i2c_status(
                "✗ i2cpy не установлена. Установите: pip install i2cpy", "error")
            return

        text = slot.value_text()
        if not text:
            self.update_i2c_status("✗ Введите значение в слот", "error")
            return

        try:
            offset = slot.offset()
        except ValueError as exc:
            self.update_i2c_status(f"✗ Смещение: {exc}", "error")
            return

        slot.set_busy(True)
        self.i2c_progress.setVisible(True)
        self.i2c_progress.setValue(0)

        try:
            if slot.format() == FORMAT_BCD:
                self.write_bcd_slot(slot, offset, text)
            else:
                self.write_fixed_slot(slot, offset, text)

        except Exception as exc:
            self.update_i2c_status(f"✗ Ошибка: {exc}", "error")

        finally:
            slot.set_busy(False)
            self.i2c_progress.setValue(0)
            self.i2c_progress.setVisible(False)

    def write_fixed_slot(self, slot, offset, text):
        """Запись слота формата fixed-point: 42 байта с CRC"""
        writer = I2CWriter(offset=offset,
                           chip=self.i2c_chip_combo.currentText())

        def progress_callback(percent, message):
            self.i2c_progress.setValue(percent)
            if message:
                self.update_i2c_status(message, "info")
            QtWidgets.QApplication.processEvents()

        result = writer.write_and_verify(text, progress_callback, debug=True,
                                         offset=offset, exact=slot.is_exact())

        if result['success']:
            slot.set_value(result['after'])
            message = (f"✓ 0x{offset:04X}: записано {result['after']:.2f} "
                       f"| CRC 0x{result['crc']:04X} "
                       f"| было {result['before']:.2f}")
        else:
            message = f"✗ 0x{offset:04X}: {result['message']}"

        if result['debug']:
            message += f"\n\nДЕБАГ ЛОГИ:\n{result['debug']}"

        self.update_i2c_status(message, "success" if result['success'] else "error")

    def write_bcd_slot(self, slot, offset, text):
        """
        Запись слота формата BCD: четыре копии значения внутри записи.

        Правятся ровно 16 байт (4 копии × 4 байта). Заголовок, нули между
        копиями и хвост записи не трогаются.

        Галочка «точное значение» действует так же, как для поля T: когда
        она снята, дробная часть 01–99 подставляется случайно.
        """
        writer = I2CWriter(offset=offset,
                           chip=self.i2c_chip_combo.currentText())

        value = writer.parse_value(text, exact=slot.is_exact())
        payload = encode_bcd(value)

        log = [f"Значение {value:.2f} → BCD {payload.hex(' ').upper()}"]
        if not slot.is_exact():
            log.append(f"Введено {text}, дробная часть подставлена случайно")

        try:
            self.i2c_progress.setValue(10)
            writer.open_programmer()

            before_raw = writer.read_bytes(offset, BCD_RECORD_SIZE)
            before = decode_bcd(before_raw[BCD_COPY_OFFSETS[0]:
                                           BCD_COPY_OFFSETS[0] + BCD_VALUE_SIZE])
            log.append(f"Было: {before if before is not None else 'не BCD'}")

            self.i2c_progress.setValue(35)
            for index, copy_offset in enumerate(BCD_COPY_OFFSETS, start=1):
                position = offset + copy_offset
                writer.write_bytes(position, payload)
                log.append(f"Копия {index} записана по 0x{position:04X}")
                self.i2c_progress.setValue(35 + index * 10)
                QtWidgets.QApplication.processEvents()

            writer.close_programmer()
            time.sleep(0.15)
            writer.open_programmer()

            self.i2c_progress.setValue(85)
            after_raw = writer.read_bytes(offset, BCD_RECORD_SIZE)
            copies = [after_raw[c:c + BCD_VALUE_SIZE] for c in BCD_COPY_OFFSETS]
            ok = all(c == payload for c in copies)

            log.append(f"Проверка: "
                       f"{'  '.join(c.hex(' ').upper() for c in copies)}")

            if ok:
                slot.set_value(value)
                log.append("✓ Все четыре копии совпали")
                self.update_i2c_status(
                    f"✓ 0x{offset:04X}: записано {value:.2f} (BCD, 4 копии)"
                    f"\n\nДЕБАГ ЛОГИ:\n" + "\n".join(log), "success")
            else:
                log.append(f"✗ Ожидали во всех копиях {payload.hex(' ').upper()}")
                self.update_i2c_status(
                    f"✗ 0x{offset:04X}: проверка не пройдена"
                    f"\n\nДЕБАГ ЛОГИ:\n" + "\n".join(log), "error")

        finally:
            writer.close_programmer()

    def i2c_probe_chip(self):
        """Определить схему адресации микросхемы опросом шины"""
        if I2CWriter is None:
            self.update_i2c_status("✗ i2cpy не установлена. Установите: pip install i2cpy", "error")
            return

        # Опрашиваем по смещению первого слота — там заведомо есть данные,
        # а на содержательных байтах проверка стабильности точнее.
        offset = DEFAULT_SLOTS[0][0]
        if self.i2c_slots:
            try:
                offset = self.i2c_slots[0].offset()
            except ValueError:
                pass

        self.i2c_probe_button.setEnabled(False)
        writer = I2CWriter(offset=offset, chip=self.i2c_chip_combo.currentText())

        try:
            writer.open_programmer()
            report = writer.probe()

            lines = ["Опрос микросхемы по смещению 0x%04X:" % offset, ""]
            for bits in (8, 16):
                data = report[str(bits)]
                shown = data.hex(" ").upper() if data else "ошибка чтения"
                mark = "стабильно" if report[f"stable{bits}"] else "НЕСТАБИЛЬНО"
                lines.append(f"  адрес {bits:>2} бит: {shown}  [{mark}]")

            lines.append("")
            if report["recommend"]:
                lines.append(f"➜ Рекомендуется: {report['recommend']}")
                idx = self.i2c_chip_combo.findText(report["recommend"])
                if idx >= 0:
                    self.i2c_chip_combo.setCurrentIndex(idx)
                    lines.append("  (выбрано автоматически)")
                self.update_i2c_status("\n".join(lines), "success")
            else:
                lines.append("➜ Определить не удалось — обе схемы нестабильны.")
                lines.append("  Проверьте питание, подтяжки SDA/SCL и контакты.")
                self.update_i2c_status("\n".join(lines), "error")

        except Exception as e:
            self.update_i2c_status(f"✗ Ошибка опроса: {e}", "error")

        finally:
            writer.close_programmer()
            self.i2c_probe_button.setEnabled(True)

    def i2c_write_and_verify(self):
        """Записать по очереди все заполненные слоты"""
        if I2CWriter is None:
            self.update_i2c_status(
                "✗ i2cpy не установлена. Установите: pip install i2cpy", "error")
            return

        pending = [slot for slot in self.i2c_slots if slot.value_text()]
        if not pending:
            self.update_i2c_status("✗ Ни один слот не заполнен", "error")
            return

        self.i2c_write_button.setEnabled(False)
        try:
            for slot in pending:
                self.i2c_write_slot(slot)
                QtWidgets.QApplication.processEvents()
        finally:
            self.i2c_write_button.setEnabled(True)

    def update_i2c_status(self, text, status_type="info"):
        """Обновляет статус I2C"""
        self.i2c_status.setText(text)
        if status_type == "success":
            style = """
                QTextEdit {
                    background-color: #0d2818;
                    border: 2px solid #238636;
                    color: #7ee78c;
                }
            """
        elif status_type == "error":
            style = """
                QTextEdit {
                    background-color: #3d1f1a;
                    border: 2px solid #f85149;
                    color: #f85149;
                }
            """
        else:
            style = """
                QTextEdit {
                    background-color: #161b22;
                    border: 2px solid #30363d;
                    color: #c9d1d9;
                }
            """
        self.i2c_status.setStyleSheet(style + """
            border-radius: 6px;
            padding: 12px;
            font-size: 12px;
            font-family: 'Courier New', monospace;
        """)

    # ── Операции с дампом ─────────────────────────────────────────────

    def dump_ready(self):
        if self.file_data is None:
            self.update_status("✗ Файл не загружен")
            return False
        return True

    def refresh_dump(self):
        """Перерисовывает hex-дамп с текущего смещения"""
        if not self.dump_ready():
            return
        try:
            offset = parse_offset(self.dump_offset_input.text() or "0")
            length = parse_offset(self.dump_length_input.text() or "512")
        except ValueError:
            self.update_status("✗ Некорректное смещение или длина")
            return

        offset = max(0, min(offset, max(0, len(self.file_data) - 1)))
        self.dump_offset_input.setText(f"0x{offset:04X}")
        self.dump_view.setPlainText(hex_dump(bytes(self.file_data), offset, length))
        self.update_dump_changes_label()

    def page_dump(self, direction):
        """Листает дамп на страницу вперёд/назад"""
        if not self.dump_ready():
            return
        try:
            offset = parse_offset(self.dump_offset_input.text() or "0")
            length = parse_offset(self.dump_length_input.text() or "512")
        except ValueError:
            return
        self.dump_offset_input.setText(f"0x{max(0, offset + direction * length):04X}")
        self.refresh_dump()

    def find_in_dump(self):
        """Ищет последовательность байт и переходит к ней"""
        if not self.dump_ready():
            return
        try:
            pattern = parse_hex_bytes(self.dump_find_input.text())
        except ValueError as e:
            self.update_status(f"✗ {e}")
            return

        start = 0
        try:
            start = parse_offset(self.dump_offset_input.text() or "0") + 1
        except ValueError:
            pass

        pos = bytes(self.file_data).find(pattern, start)
        if pos == -1:
            pos = bytes(self.file_data).find(pattern)
        if pos == -1:
            self.update_status("✗ Последовательность не найдена")
            return

        self.dump_offset_input.setText(f"0x{pos:04X}")
        self.refresh_dump()
        self.update_status(f"✓ Найдено на 0x{pos:06X}")

    def write_raw_bytes(self):
        """Прямая запись произвольных байт по смещению"""
        if not self.dump_ready():
            return
        try:
            offset = parse_offset(self.write_offset_input.text())
            payload = parse_hex_bytes(self.write_hex_input.text())
        except ValueError as e:
            self.update_status(f"✗ {e}")
            return

        if offset < 0 or offset + len(payload) > len(self.file_data):
            self.update_status("✗ Запись выходит за пределы файла")
            return

        old = bytes(self.file_data[offset:offset + len(payload)])
        self.file_data[offset:offset + len(payload)] = payload
        self.dump_writes.append({'offset': offset, 'old': old})

        self.dump_offset_input.setText(f"0x{offset:04X}")
        self.refresh_dump()
        self.update_status(
            f"✓ 0x{offset:06X}: {old.hex(' ').upper()} → {payload.hex(' ').upper()} "
            f"({len(payload)} байт)"
        )

    def write_value_block(self):
        """Записывает значение как блок 40 байт + 2 байта CRC"""
        if not self.dump_ready():
            return
        try:
            offset = parse_offset(self.write_offset_input.text())
            value = float(self.write_value_input.text().replace(",", "."))
            val_bytes = encode_value(value)
        except ValueError as e:
            self.update_status(f"✗ {e}")
            return

        block = val_bytes + val_bytes + b'\x00' * 32
        crc = crc16_ccitt(block)
        payload = block + struct.pack('>H', crc)

        if offset < 0 or offset + len(payload) > len(self.file_data):
            self.update_status("✗ Запись выходит за пределы файла")
            return

        old = bytes(self.file_data[offset:offset + len(payload)])
        self.file_data[offset:offset + len(payload)] = payload
        self.dump_writes.append({'offset': offset, 'old': old})

        self.dump_offset_input.setText(f"0x{offset:04X}")
        self.refresh_dump()
        self.update_status(
            f"✓ 0x{offset:06X}: {value:.2f}, CRC 0x{crc:04X} "
            f"({BLOCK_SIZE + CRC_SIZE} байт)"
        )

    def check_dump_crc(self):
        """Сверяет сохранённый и вычисленный CRC блока по смещению"""
        if not self.dump_ready():
            return
        try:
            offset = parse_offset(self.write_offset_input.text())
        except ValueError as e:
            self.update_status(f"✗ {e}")
            return

        if offset < 0 or offset + BLOCK_SIZE + CRC_SIZE > len(self.file_data):
            self.update_status("✗ Блок выходит за пределы файла")
            return

        block = bytes(self.file_data[offset:offset + BLOCK_SIZE])
        stored = struct.unpack('>H', bytes(
            self.file_data[offset + BLOCK_SIZE:offset + BLOCK_SIZE + CRC_SIZE]))[0]
        calc = crc16_ccitt(block)
        value = decode_value(block[:4])

        verdict = "✓ совпадает" if stored == calc else "✗ НЕ совпадает"
        self.update_status(
            f"0x{offset:06X}: {value:.2f} | сохранён 0x{stored:04X} | "
            f"вычислен 0x{calc:04X} | {verdict}"
        )

    def undo_dump_write(self):
        """Откатывает последнюю прямую запись"""
        if not self.dump_writes:
            self.update_status("Нечего отменять")
            return
        last = self.dump_writes.pop()
        offset, old = last['offset'], last['old']
        self.file_data[offset:offset + len(old)] = old
        self.dump_offset_input.setText(f"0x{offset:04X}")
        self.refresh_dump()
        self.update_status(f"✓ Отменена запись на 0x{offset:06X}")

    def revert_dump(self):
        """Возвращает дамп к состоянию на момент загрузки"""
        if self.original_data is None:
            return
        answer = QtWidgets.QMessageBox.question(
            self, "Сброс", "Отменить все изменения дампа?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return
        self.file_data = bytearray(self.original_data)
        self.dump_writes = []
        self.refresh_dump()
        self.update_status("✓ Изменения дампа сброшены")

    def dump_diff(self):
        """Список изменённых байт относительно загруженного файла"""
        if self.original_data is None or self.file_data is None:
            return []
        return [i for i in range(min(len(self.original_data), len(self.file_data)))
                if self.original_data[i] != self.file_data[i]]

    def update_dump_changes_label(self):
        changed = len(self.dump_diff())
        self.dump_changes_label.setText(
            "Изменений нет" if not changed else f"Изменено байт: {changed}"
        )

    def save_dump(self):
        """Пишет дамп на диск как есть, с резервной копией"""
        if not self.dump_ready() or not self.filepath:
            return

        changed = self.dump_diff()
        if not changed:
            self.update_status("Изменений нет — сохранять нечего")
            return

        answer = QtWidgets.QMessageBox.question(
            self, "Сохранение дампа",
            f"Записать {len(changed)} изменённых байт в {Path(self.filepath).name}?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return

        try:
            backup = Path(self.filepath).with_suffix(Path(self.filepath).suffix + '.bak')
            backup.write_bytes(bytes(self.original_data))
            Path(self.filepath).write_bytes(bytes(self.file_data))

            self.original_data = bytes(self.file_data)
            self.dump_writes = []
            self.update_dump_changes_label()

            self.update_status(f"✓ Дамп сохранён | Резервная копия: {backup.name}")
            QtWidgets.QMessageBox.information(
                self, "Успех",
                f"Записано {len(changed)} байт\n\n"
                f"Файл: {self.filepath}\nРезервная копия: {backup}"
            )
        except Exception as e:
            self.update_status(f"✗ Ошибка сохранения дампа: {e}")
            QtWidgets.QMessageBox.critical(self, "Ошибка сохранения", str(e))

    def open_file(self):
        """Открывает диалог выбора файла"""
        filepath, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Выберите файл", "", "Binary files (*.bin);;All files (*)"
        )
        if filepath:
            self.load_file(filepath)

    def load_file(self, filepath):
        """Загружает файл в отдельном потоке"""
        self.filepath = filepath
        self.file_path_label.setText(filepath)

        if self.worker is not None and self.worker.isRunning():
            self.worker.wait()

        self.worker = FileWorker(filepath)
        self.worker.loaded.connect(self.on_file_loaded)
        self.worker.error.connect(self.on_file_error)
        self.worker.start()

        self.update_status("Загрузка файла...")

    def load_last_file(self):
        """Пытается загрузить последний открытый файл"""
        try:
            config_file = Path.home() / ".crc_storage_last"
            if config_file.exists():
                last_path = config_file.read_text().strip()
                if Path(last_path).exists():
                    self.load_file(last_path)
        except Exception:
            pass

    def on_file_loaded(self, values, data):
        """Файл загружен успешно"""
        self.values = values
        self.original_data = bytes(data)
        self.file_data = bytearray(data)
        self.dump_writes = []
        self.update_table()
        self.refresh_dump()
        self.info_label.setText(f"Файл: {len(data)} байт | Значений: {len(values)}")
        self.update_status(f"✓ Загруженo {len(values)} значений")

        # Сохраняем путь
        try:
            config_file = Path.home() / ".crc_storage_last"
            config_file.write_text(self.filepath)
        except Exception:
            pass

    def on_file_error(self, error):
        """Ошибка загрузки"""
        QtWidgets.QMessageBox.critical(self, "Ошибка", error)
        self.update_status(f"✗ Ошибка: {error}")

    def update_table(self):
        """Обновляет таблицу"""
        # Временно отключаем сигнал itemChanged чтобы избежать рекурсии
        self.table.itemChanged.disconnect()
        self.table.setRowCount(len(self.values))

        for row, item in enumerate(self.values):
            # Позиция (не редактируется)
            pos_cell = QtWidgets.QTableWidgetItem(f"0x{item['pos']:06X}")
            pos_cell.setFlags(pos_cell.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, pos_cell)

            # Значение (РЕДАКТИРУЕТСЯ — кликни и меняй)
            val_cell = QtWidgets.QTableWidgetItem(f"{item['value']:.2f}")
            val_cell.setFlags(val_cell.flags() | Qt.ItemIsEditable)
            self.table.setItem(row, 1, val_cell)

            # HEX (обновляется автоматически при редактировании)
            hex_val = int(item['value'] * SCALE)
            hex_cell = QtWidgets.QTableWidgetItem(f"0x{hex_val:08X}")
            hex_cell.setFlags(hex_cell.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 2, hex_cell)

            # CRC (обновляется автоматически)
            crc_cell = QtWidgets.QTableWidgetItem(f"0x{item['crc']:04X}")
            crc_cell.setFlags(crc_cell.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 3, crc_cell)

            # Статус
            status_cell = QtWidgets.QTableWidgetItem("✓ OK" if item['valid'] else "✗ ERROR")
            status_cell.setFlags(status_cell.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 4, status_cell)

        # Переподключаем сигнал после обновления таблицы
        self.table.itemChanged.connect(self.on_value_edited)

    def on_value_edited(self, table_item):
        """Значение отредактировано в таблице"""
        if self.updating_table or table_item is None:
            return

        # Безопасно получаем row/column (могут быть -1 если объект удален)
        try:
            row = table_item.row()
            col = table_item.column()
        except RuntimeError:
            # Объект был удален
            return

        if col != 1 or row < 0 or row >= len(self.values):
            return

        try:
            new_value = float(table_item.text().replace(",", "."))
            item = self.values[row]

            # Вычисляем новый CRC
            val_bytes = encode_value(new_value)
            block = val_bytes + val_bytes + b'\x00' * 32
            new_crc = crc16_ccitt(block)

            # Обновляем в памяти
            old_value = item['value']
            item['value'] = new_value
            item['crc'] = new_crc

            # Обновляем дамп
            pos = item['pos']
            self.file_data[pos:pos+BLOCK_SIZE] = block
            self.file_data[pos+BLOCK_SIZE:pos+BLOCK_SIZE+CRC_SIZE] = struct.pack('>H', new_crc)

            # Обновляем таблицу (с флагом чтобы избежать повторного вызова on_value_edited)
            self.updating_table = True
            self.update_table()
            self.updating_table = False

            self.refresh_dump()

            self.update_status(
                f"✓ В памяти: {old_value:.2f} → {new_value:.2f} | CRC 0x{new_crc:04X} | "
                f"Нажми Сохранить"
            )

        except ValueError:
            # Откатываем на старое значение если ввод неверный
            item = self.values[row]
            self.updating_table = True
            table_item.setText(f"{item['value']:.2f}")
            self.updating_table = False
            self.update_status(f"✗ Некорректное число")

    def update_value(self):
        """Обновляет значение в памяти и дампе (без записи на диск)"""
        if self.selected_row < 0:
            self.update_status("✗ Выберите значение в таблице")
            return

        if not self.new_value_input.text():
            self.update_status("✗ Введите новое значение")
            return

        try:
            new_value = float(self.new_value_input.text().replace(",", "."))
            item = self.values[self.selected_row]

            # Вычисляем новый CRC
            val_bytes = encode_value(new_value)
            block = val_bytes + val_bytes + b'\x00' * 32
            new_crc = crc16_ccitt(block)

            self.new_crc_display.setText(f"0x{new_crc:04X}")

            # Обновляем в памяти
            old_value = item['value']
            item['value'] = new_value
            item['crc'] = new_crc

            # Обновляем дамп (но не пишем на диск)
            pos = item['pos']
            self.file_data[pos:pos+BLOCK_SIZE] = block
            self.file_data[pos+BLOCK_SIZE:pos+BLOCK_SIZE+CRC_SIZE] = struct.pack('>H', new_crc)

            self.update_table()
            self.table.selectRow(self.selected_row)
            self.refresh_dump()

            self.update_status(
                f"✓ В памяти: {old_value:.2f} → {new_value:.2f} | CRC 0x{new_crc:04X} | "
                f"Нажми Сохранить"
            )

        except ValueError as e:
            self.update_status(f"✗ Ошибка: {e}")

    def reload_file(self):
        """Перезагружает файл"""
        if self.filepath:
            self.load_file(self.filepath)

    def save_file_to_disk(self):
        """Сохраняет все изменения из памяти на диск"""
        if not self.filepath:
            self.update_status("✗ Файл не загружен")
            return

        # Проверяем, есть ли изменения
        if bytes(self.file_data) == self.original_data:
            self.update_status("✗ Изменений нет")
            return

        try:
            path = Path(self.filepath)
            backup = path.with_suffix(path.suffix + '.bak')

            # Резервная копия исходного состояния
            backup.write_bytes(bytes(self.original_data))

            # Пишем на диск
            path.write_bytes(bytes(self.file_data))

            # Обновляем состояние
            self.original_data = bytes(self.file_data)
            self.dump_writes = []

            self.update_status(f"✓ Сохранено на диск | Резервная копия: {backup.name}")

        except Exception as e:
            self.update_status(f"✗ Ошибка сохранения: {e}")

    def update_status(self, text):
        """Обновляет строку состояния"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.statusbar.showMessage(f"[{timestamp}] {text}")

    def closeEvent(self, event):
        """При закрытии окна"""
        if self.worker is not None and self.worker.isRunning():
            self.worker.wait()
        event.accept()


# ═══════════════════════════════════════════════════════════════════════════
#  Главная функция
# ═══════════════════════════════════════════════════════════════════════════

def resource_path(name: str) -> str:
    """
    Путь к файлу рядом с программой.

    В сборке PyInstaller файлы распакованы во временную папку sys._MEIPASS,
    при обычном запуске лежат рядом со скриптом.
    """
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def load_app_icon() -> QtGui.QIcon:
    """Иконка приложения; пустая иконка, если файла нет"""
    for name in ("icon.ico", "icon.png"):
        path = resource_path(name)
        if os.path.isfile(path):
            return QtGui.QIcon(path)
    return QtGui.QIcon()


def close_pyinstaller_splash():
    """
    Убрать заставку PyInstaller.

    Она показывается ещё до старта Python и закрывает распаковку onefile.
    Модуль pyi_splash существует только внутри собранного exe.
    """
    try:
        import pyi_splash
    except ImportError:
        return
    try:
        pyi_splash.close()
    except Exception:
        pass


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle('Fusion')

    icon = load_app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)

    splash = None
    if LoadingSplash is not None:
        splash = LoadingSplash(icon)
        splash.start()
        splash.step("Загрузка модулей...", 20)

    # Заставку PyInstaller гасим только сейчас, когда уже есть что показать
    # вместо неё, — иначе между ними мигнёт пустой экран.
    close_pyinstaller_splash()

    if splash:
        splash.step("Проверка программатора...", 45)
    programmer_ready = I2CWriter is not None

    if splash:
        splash.step("Загрузка интерфейса...", 70)

    window = MainWindow()
    if not icon.isNull():
        window.setWindowIcon(icon)

    if splash:
        splash.step("Готово" if programmer_ready else "i2cpy не установлена", 100)
        splash.finish(window)
    else:
        window.show()

    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
