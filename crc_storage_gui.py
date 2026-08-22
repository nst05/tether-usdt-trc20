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

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread

# ═══════════════════════════════════════════════════════════════════════════
#  Константы и ядро
# ═══════════════════════════════════════════════════════════════════════════

SCALE = 100
BLOCK_SIZE = 0x28
CRC_SIZE = 2
VALUE_SIZE = 4
INIT_CRC = 0xFFFF
POLY_CRC = 0x1021


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

        # ── Вкладки: значения / дамп ──────────────────────────────────
        self.tabs = QtWidgets.QTabWidget()
        main_layout.addWidget(self.tabs)

        values_tab = QtWidgets.QWidget()
        values_layout = QtWidgets.QVBoxLayout(values_tab)
        values_layout.setContentsMargins(0, 8, 0, 0)
        self.tabs.addTab(values_tab, "Значения")
        self.tabs.addTab(self.create_dump_tab(), "Дамп (прямая запись)")

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
        self.table.itemSelectionChanged.connect(self.on_value_selected)
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
        self.table.setRowCount(len(self.values))

        for row, item in enumerate(self.values):
            pos_cell = QtWidgets.QTableWidgetItem(f"0x{item['pos']:06X}")
            pos_cell.setFlags(pos_cell.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, pos_cell)

            val_cell = QtWidgets.QTableWidgetItem(f"{item['value']:.2f}")
            val_cell.setFlags(val_cell.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 1, val_cell)

            # HEX представление
            hex_val = int(item['value'] * SCALE)
            hex_cell = QtWidgets.QTableWidgetItem(f"0x{hex_val:08X}")
            hex_cell.setFlags(hex_cell.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 2, hex_cell)

            crc_cell = QtWidgets.QTableWidgetItem(f"0x{item['crc']:04X}")
            crc_cell.setFlags(crc_cell.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 3, crc_cell)

            status_cell = QtWidgets.QTableWidgetItem("✓ OK" if item['valid'] else "✗ ERROR")
            status_cell.setFlags(status_cell.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 4, status_cell)

    def on_value_selected(self):
        """Выбрано значение в таблице"""
        selected = self.table.selectedItems()
        if not selected:
            return

        row = self.table.row(selected[0])
        if 0 <= row < len(self.values):
            item = self.values[row]
            self.selected_row = row

            self.pos_display.setText(f"0x{item['pos']:06X}")
            self.current_value_display.setText(f"{item['value']:.2f}")
            self.new_value_input.clear()
            self.new_crc_display.clear()
            self.new_value_input.setFocus()

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

def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle('Fusion')

    window = MainWindow()
    window.show()

    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
