# -*- coding: utf-8 -*-
# CRC_Storage_Writer — запись значений с CRC-16 CCITT
# Работает с бинарными файлами, содержащими структуры:
# 4 байта значение + 4 байта дубль + 32 байта паддинг + контрольная сумма
#
# Алгоритм: CRC-16 CCITT (poly=0x1021, init=0xFFFF)
# Представление: Fixed-Point (value * 100) в big-endian

import gc
import json
import os
import struct
import sys
import time
from datetime import datetime
from pathlib import Path

from PyQt5 import QtCore, QtGui, QtWidgets

# ═══════════════════════════════════════════════════════════════════════════
#  CRC-16 CCITT и кодирование значений
# ═══════════════════════════════════════════════════════════════════════════

SCALE = 100
BLOCK_SIZE = 0x28  # 40 байт: 4 + 4 + 32
CRC_SIZE = 2
VALUE_SIZE = 4

INIT_CRC = 0xFFFF
POLY_CRC = 0x1021


def crc16_ccitt(data, init=INIT_CRC, poly=POLY_CRC):
    """CRC-16 CCITT (полином 0x1021, инициализация 0xFFFF)"""
    crc = init
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc <<= 1
            if crc & 0x10000:
                crc ^= poly
            crc &= 0xFFFF
    return crc


def encode_value(value: float) -> bytes:
    """Кодирование значения в fixed-point big-endian (value * 100)"""
    raw = int(round(value * SCALE))
    if not 0 <= raw <= 0xFFFFFFFF:
        raise ValueError("Значение слишком большое (макс. 42949672.95).")
    return raw.to_bytes(4, "big", signed=False)


def decode_value(data: bytes) -> float:
    """Декодирование значения из fixed-point big-endian"""
    if len(data) != 4:
        raise ValueError("Неверная длина данных.")
    return int.from_bytes(data, "big", signed=False) / SCALE


def make_block(value: float) -> tuple:
    """Создаёт блок данных (40 байт) и вычисляет CRC"""
    val_bytes = encode_value(value)
    # Структура: значение + дубль + паддинг (32 байта нулей)
    block = val_bytes + val_bytes + b'\x00' * 32
    crc = crc16_ccitt(block)
    return block, crc


# ═══════════════════════════════════════════════════════════════════════════
#  Работа с файлами
# ═══════════════════════════════════════════════════════════════════════════

class StorageManager:
    def __init__(self, filepath):
        self.filepath = Path(filepath)
        self.data = None
        self.values = []  # список (позиция, значение)

    def load_file(self):
        """Загружает бинарный файл"""
        if not self.filepath.exists():
            raise FileNotFoundError(f"Файл не найден: {self.filepath}")

        with open(self.filepath, 'rb') as f:
            self.data = bytearray(f.read())

        self.scan_values()
        return len(self.data)

    def scan_values(self):
        """Сканирует файл на предмет структур значений с CRC"""
        self.values = []
        data = bytes(self.data)

        # Ищем структуры: дублированное значение + нули + CRC
        pos = 0
        while pos < len(data) - BLOCK_SIZE - CRC_SIZE:
            # Проверяем, является ли это структурой
            val1 = data[pos:pos+4]
            val2 = data[pos+4:pos+8]
            zeros = data[pos+8:pos+12]

            # Структура должна содержать дублированное значение и нули
            if val1 == val2 and zeros == b'\x00\x00\x00\x00':
                try:
                    # Проверяем CRC
                    block = data[pos:pos+BLOCK_SIZE]
                    crc_pos = pos + BLOCK_SIZE

                    if crc_pos + CRC_SIZE <= len(data):
                        stored_crc = struct.unpack('>H', data[crc_pos:crc_pos+2])[0]
                        calculated_crc = crc16_ccitt(block)

                        if stored_crc == calculated_crc:
                            value = decode_value(val1)
                            self.values.append((pos, value, stored_crc))
                            pos += BLOCK_SIZE + CRC_SIZE
                            continue
                except Exception:
                    pass

            pos += 1

    def write_value(self, position: int, new_value: float):
        """Записывает новое значение в указанную позицию"""
        if position < 0 or position + BLOCK_SIZE + CRC_SIZE > len(self.data):
            raise ValueError("Позиция выходит за пределы файла.")

        block, crc = make_block(new_value)

        # Записываем блок данных
        self.data[position:position+BLOCK_SIZE] = block

        # Записываем CRC
        crc_pos = position + BLOCK_SIZE
        self.data[crc_pos:crc_pos+CRC_SIZE] = struct.pack('>H', crc)

    def save_file(self):
        """Сохраняет файл"""
        backup = self.filepath.with_suffix('.bak')
        self.filepath.rename(backup)

        try:
            with open(self.filepath, 'wb') as f:
                f.write(self.data)
        except Exception as e:
            backup.rename(self.filepath)
            raise e

    def get_value(self, position: int) -> float:
        """Читает значение с позиции"""
        if position < 0 or position + VALUE_SIZE > len(self.data):
            raise ValueError("Позиция выходит за пределы файла.")

        val_bytes = self.data[position:position+VALUE_SIZE]
        return decode_value(val_bytes)


# ═══════════════════════════════════════════════════════════════════════════
#  Стиль
# ═══════════════════════════════════════════════════════════════════════════

APP_STYLE = """
QWidget { background:#10131a; color:#f2f4f8; font-family:'Segoe UI'; font-size:15px; }
QLineEdit {
    background:#181d27; border:2px solid #38445a; border-radius:14px;
    padding:14px 18px; font-size:28px; font-weight:700; color:#fff;
    selection-background-color:#4f7cff;
}
QLineEdit:focus { border-color:#6b8cff; }
QPushButton {
    background:#3f6df6; border:2px solid #6f91ff; border-radius:16px;
    padding:16px; font-size:22px; font-weight:800; color:white;
}
QPushButton:hover { background:#4e79ff; }
QPushButton:pressed { background:#345acb; }
QPushButton:disabled { background:#2b3240; border-color:#3a4352; color:#8d96a8; }
QPushButton#Ghost { background:#1a2230; border-color:#2b3648; color:#cdd6e6; font-size:14px; padding:10px; }
QPushButton#Ghost:hover { background:#222c3d; }
QLabel#TitleLabel { font-size:22px; font-weight:900; color:#fff; }
QLabel#HintLabel { font-size:14px; color:#aab3c5; }
QProgressBar {
    border:2px solid #3d4a60; border-radius:10px; background:#18202c;
    color:white; text-align:center; height:24px; font-weight:700;
}
QProgressBar::chunk { border-radius:8px; background:#3f6df6; }
QFrame#Card { background:#18202c; border:2px solid #3d4a60; border-radius:14px; }
QLabel#CounterValue { font-size:34px; font-weight:900; color:#7ff0ac; }
QLabel#CounterCaption { font-size:12px; font-weight:800; color:#8d96a8; }
QLabel#Footer { font-size:12px; color:#8d96a8; }
QTableWidget {
    background:#181d27; border:2px solid #3d4a60; border-radius:8px;
    gridline-color:#2a3346;
}
QTableWidget::item { padding:8px; }
QHeaderView::section {
    background:#2a3346; color:#aab3c5; padding:8px;
    border:none; font-weight:800;
}
"""


# ═══════════════════════════════════════════════════════════════════════════
#  Главное окно
# ═══════════════════════════════════════════════════════════════════════════

class MainWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.storage = None
        self.current_file = None
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("CRC Storage Writer — Fixed-Point CCITT")
        self.setFixedSize(800, 700)
        self.setStyleSheet(APP_STYLE)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        # ── Заголовок ────────────────────────────────────────────────────
        head = QtWidgets.QVBoxLayout()
        head.setSpacing(4)

        title = QtWidgets.QLabel("CRC-16 CCITT STORAGE WRITER")
        title.setObjectName("TitleLabel")
        head.addWidget(title)

        hint = QtWidgets.QLabel(
            "Запись значений в бинарные файлы с автоматическим вычислением CRC-16 CCITT.\n"
            "Формат: значение (×100, big-endian) + дубль + паддинг + CRC"
        )
        hint.setObjectName("HintLabel")
        hint.setWordWrap(True)
        head.addWidget(hint)
        root.addLayout(head)

        # ── Выбор файла ──────────────────────────────────────────────────
        file_box = QtWidgets.QHBoxLayout()
        file_box.setSpacing(8)

        self.file_input = QtWidgets.QLineEdit()
        self.file_input.setPlaceholderText("Выберите или перетащите файл...")
        self.file_input.setMinimumHeight(44)
        file_box.addWidget(self.file_input)

        browse_btn = QtWidgets.QPushButton("Обзор")
        browse_btn.setMaximumWidth(100)
        browse_btn.clicked.connect(self.browse_file)
        file_box.addWidget(browse_btn)

        root.addLayout(file_box)

        # ── Таблица значений ─────────────────────────────────────────────
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Позиция", "Значение", "CRC-16", "Статус"])
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.itemSelectionChanged.connect(self.on_value_selected)
        self.table.setMinimumHeight(200)
        root.addWidget(self.table)

        # ── Редактирование ───────────────────────────────────────────────
        edit_box = QtWidgets.QVBoxLayout()
        edit_box.setSpacing(8)

        edit_title = QtWidgets.QLabel("РЕДАКТИРОВАНИЕ")
        edit_title.setObjectName("CounterCaption")
        edit_box.addWidget(edit_title)

        edit_grid = QtWidgets.QGridLayout()
        edit_grid.setSpacing(12)

        edit_grid.addWidget(QtWidgets.QLabel("Новое значение:"), 0, 0)
        self.value_input = QtWidgets.QLineEdit()
        self.value_input.setPlaceholderText("Например: 9442.36")
        self.value_input.setAlignment(QtCore.Qt.AlignCenter)
        self.value_input.setMinimumHeight(44)
        validator = QtGui.QDoubleValidator(0.0, 42949672.95, 2, self)
        validator.setNotation(QtGui.QDoubleValidator.StandardNotation)
        self.value_input.setValidator(validator)
        edit_grid.addWidget(self.value_input, 0, 1)

        self.update_btn = QtWidgets.QPushButton("Обновить значение")
        self.update_btn.setMinimumHeight(44)
        self.update_btn.clicked.connect(self.update_value)
        self.update_btn.setEnabled(False)
        edit_grid.addWidget(self.update_btn, 1, 0, 1, 2)

        edit_box.addLayout(edit_grid)
        root.addLayout(edit_box)

        # ── Статус ───────────────────────────────────────────────────────
        self.status = QtWidgets.QLabel("Готово к работе")
        self.status.setWordWrap(True)
        self.status.setAlignment(QtCore.Qt.AlignCenter)
        self.status.setMinimumHeight(44)
        root.addWidget(self.status)

        # ── Кнопки ───────────────────────────────────────────────────────
        buttons = QtWidgets.QHBoxLayout()
        buttons.setSpacing(8)

        save_btn = QtWidgets.QPushButton("Сохранить файл")
        save_btn.clicked.connect(self.save_file)
        buttons.addWidget(save_btn)

        info_btn = QtWidgets.QPushButton("Информация")
        info_btn.setObjectName("Ghost")
        info_btn.clicked.connect(self.show_info)
        buttons.addWidget(info_btn)

        root.addLayout(buttons)
        root.addStretch()

        self.set_status("Загрузите файл для начала работы")

    def set_status(self, text, ok=None):
        self.status.setText(text)
        if ok is True:
            css = "background:#153c28;border:2px solid #2fc46f;color:#7ff0ac;"
        elif ok is False:
            css = "background:#471d25;border:2px solid #ff5a6f;color:#ff9cab;"
        else:
            css = "background:#18202c;border:2px solid #3d4a60;color:#d9dfeb;"
        self.status.setStyleSheet(
            f"QLabel{{background:{css.split('background:')[1].split(';')[0]};border:2px solid {css.split('border:')[1].split(';')[0]};color:{css.split('color:')[1].split(';')[0]};border-radius:14px;padding:16px;font-size:18px;font-weight:800;}}"
        )
        QtWidgets.QApplication.processEvents()

    def browse_file(self):
        filepath, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Выберите файл", "", "Binary files (*.bin);;All files (*)"
        )
        if filepath:
            self.file_input.setText(filepath)
            self.load_file()

    def load_file(self):
        filepath = self.file_input.text().strip()
        if not filepath:
            return

        try:
            self.storage = StorageManager(filepath)
            file_size = self.storage.load_file()
            self.current_file = filepath

            self.update_table()
            self.set_status(f"Файл загружен ({file_size} байт). Найдено {len(self.storage.values)} значений.", True)
        except Exception as e:
            self.set_status(f"Ошибка загрузки: {e}", False)
            self.storage = None
            self.current_file = None

    def update_table(self):
        self.table.setRowCount(len(self.storage.values))

        for row, (pos, value, crc) in enumerate(self.storage.values):
            pos_item = QtWidgets.QTableWidgetItem(f"0x{pos:04X}")
            pos_item.setFlags(pos_item.flags() & ~QtCore.Qt.ItemIsEditable)
            self.table.setItem(row, 0, pos_item)

            val_item = QtWidgets.QTableWidgetItem(f"{value:.2f}")
            val_item.setFlags(val_item.flags() & ~QtCore.Qt.ItemIsEditable)
            self.table.setItem(row, 1, val_item)

            crc_item = QtWidgets.QTableWidgetItem(f"0x{crc:04X}")
            crc_item.setFlags(crc_item.flags() & ~QtCore.Qt.ItemIsEditable)
            self.table.setItem(row, 2, crc_item)

            status_item = QtWidgets.QTableWidgetItem("✓ OK")
            status_item.setFlags(status_item.flags() & ~QtCore.Qt.ItemIsEditable)
            self.table.setItem(row, 3, status_item)

        self.table.resizeColumnsToContents()

    def on_value_selected(self):
        selected = self.table.selectedItems()
        if selected:
            row = self.table.row(selected[0])
            if row < len(self.storage.values):
                pos, value, crc = self.storage.values[row]
                self.value_input.setText(f"{value:.2f}")
                self.update_btn.setEnabled(True)

    def update_value(self):
        if not self.storage or not self.current_file:
            self.set_status("Загрузите файл сначала", False)
            return

        selected = self.table.selectedItems()
        if not selected:
            self.set_status("Выберите значение в таблице", False)
            return

        try:
            new_value = float(self.value_input.text().strip().replace(",", "."))
            row = self.table.row(selected[0])
            pos, old_value, old_crc = self.storage.values[row]

            self.storage.write_value(pos, new_value)
            self.storage.values[row] = (pos, new_value, crc16_ccitt(self.storage.data[pos:pos+BLOCK_SIZE]))

            self.update_table()
            self.table.selectRow(row)
            self.set_status(f"Значение обновлено: {old_value:.2f} → {new_value:.2f}", True)
        except Exception as e:
            self.set_status(f"Ошибка обновления: {e}", False)

    def save_file(self):
        if not self.storage or not self.current_file:
            self.set_status("Нечего сохранять", False)
            return

        try:
            self.storage.save_file()
            self.set_status(f"Файл сохранён: {self.current_file}", True)
        except Exception as e:
            self.set_status(f"Ошибка сохранения: {e}", False)

    def show_info(self):
        info = """
CRC-16 CCITT Storage Writer

Алгоритм:
  • CRC-16 CCITT (полином 0x1021, инициализация 0xFFFF)
  • Представление: Fixed-Point (value × 100)
  • Порядок байтов: Big-Endian

Структура блока (40 байт):
  • Байты 0–3:   Значение (4 байта, big-endian)
  • Байты 4–7:   Дубль значения (резервная копия)
  • Байты 8–39:  Паддинг нулями (32 байта)

CRC вычисляется для всего 40-байтового блока и хранится
после него в виде 2-байтового big-endian значения.

Примеры:
  9442.36 → 0x000E686C → CRC 0xAC55
  9440.38 → 0x000E67A6 → CRC 0x8748
        """
        dlg = QtWidgets.QMessageBox(self)
        dlg.setWindowTitle("О программе")
        dlg.setText(info)
        dlg.setFont(QtGui.QFont("Courier", 10))
        dlg.exec_()


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setStyleSheet(APP_STYLE)

    win = MainWindow()
    win.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
