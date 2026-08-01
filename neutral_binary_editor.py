# -*- coding: utf-8 -*-
"""
Редактор бинарных дампов с прямой записью в SPI-память (адаптер CH341A).

Вкладки:
    1. MB85RS256  (Формат A — два канала и итог)
    2. FM25V04B   (Формат B — итоговая запись)
    3. FM25L02    (Формат C — два канала и итог, 4 копии)

На каждой вкладке доступна прямая работа с микросхемой SPI-FRAM через
USB-адаптер CH341A: чтение чипа в файл, запись файла или текущего буфера
редактора в чип, проверка (verify) и чтение ID/статуса.
"""

import os
import sys
import math
import ctypes
from dataclasses import dataclass
from typing import Tuple, Optional, Callable

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtWidgets import QSizePolicy

# -------------------------------------------------------------------
# SETTINGS: optional images/icons (leave empty to disable)
# -------------------------------------------------------------------
IMG_HEIGHT = 150

IMG_FORMAT_A_IN_TAB   = ""   # например: "img/format_a.png"
IMG_FORMAT_B_IN_TAB      = ""   # например: "img/format_b.png"

TAB_ICON_FORMAT_A     = ""   # например: "img/format_a_icon.png"
TAB_ICON_FORMAT_B        = ""   # например: "img/format_b_icon.png"

# -------------------------------------------------------------------
# PyInstaller support for bundled resources
# -------------------------------------------------------------------
if getattr(sys, "frozen", False):
    os.environ["PATH"] = sys._MEIPASS + os.pathsep + os.environ.get("PATH", "")

def resource_path(relative_path: str) -> str:
    """Resolve resource paths in source and bundled builds."""
    if getattr(sys, "frozen", False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

# -------------------------------------------------------------------
# User interface styling — светлая тема
# -------------------------------------------------------------------
def apply_pretty_ui(app: QtWidgets.QApplication) -> None:
    app.setStyle("Fusion")

    # Светлая палитра для стандартных виджетов (диалоги, спинбоксы и т.д.)
    pal = QtGui.QPalette()
    pal.setColor(QtGui.QPalette.Window,          QtGui.QColor("#eef2f9"))
    pal.setColor(QtGui.QPalette.WindowText,      QtGui.QColor("#1f2733"))
    pal.setColor(QtGui.QPalette.Base,            QtGui.QColor("#ffffff"))
    pal.setColor(QtGui.QPalette.AlternateBase,   QtGui.QColor("#f4f7fc"))
    pal.setColor(QtGui.QPalette.Text,            QtGui.QColor("#1f2733"))
    pal.setColor(QtGui.QPalette.Button,          QtGui.QColor("#ffffff"))
    pal.setColor(QtGui.QPalette.ButtonText,      QtGui.QColor("#1f2733"))
    pal.setColor(QtGui.QPalette.Highlight,       QtGui.QColor("#3b6ef5"))
    pal.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor("#ffffff"))
    pal.setColor(QtGui.QPalette.ToolTipBase,     QtGui.QColor("#ffffff"))
    pal.setColor(QtGui.QPalette.ToolTipText,     QtGui.QColor("#1f2733"))
    pal.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.Text,       QtGui.QColor("#9aa3b2"))
    pal.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.ButtonText, QtGui.QColor("#9aa3b2"))
    app.setPalette(pal)

    font = QtGui.QFont("Segoe UI", 10)
    app.setFont(font)

    qss = """
    QWidget {
        background: #eef2f9;
        color: #1f2733;
        font-size: 10pt;
    }

    QTabWidget::pane {
        border: 1px solid #dbe2ee;
        border-radius: 16px;
        top: -1px;
        background: #f7f9fd;
    }
    QTabBar::tab {
        background: #e7edf7;
        border: 1px solid #dbe2ee;
        border-bottom: none;
        padding: 10px 18px;
        margin-right: 6px;
        border-top-left-radius: 12px;
        border-top-right-radius: 12px;
        color: #5b6675;
    }
    QTabBar::tab:selected {
        background: #ffffff;
        color: #1a2f7a;
        border-color: #c3d2f0;
        font-weight: 600;
    }
    QTabBar::tab:hover {
        background: #f1f5fc;
        color: #2a3a63;
    }

    QGroupBox {
        border: 1px solid #dbe2ee;
        border-radius: 16px;
        margin-top: 16px;
        padding: 14px;
        background: #ffffff;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 16px;
        padding: 2px 10px;
        color: #2b3a67;
        font-weight: 700;
        background: transparent;
    }

    QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox {
        background: #ffffff;
        border: 1px solid #d3dbe9;
        border-radius: 10px;
        padding: 8px 10px;
        selection-background-color: #3b6ef5;
        selection-color: #ffffff;
    }
    QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus {
        border: 1px solid #3b6ef5;
    }
    QLineEdit:read-only {
        background: #f2f5fb;
        color: #445067;
    }
    QLineEdit:disabled, QComboBox:disabled, QDoubleSpinBox:disabled, QSpinBox:disabled {
        color: #9aa3b2;
        background: #f0f2f7;
    }
    QComboBox::drop-down {
        border: none;
        width: 24px;
    }
    QComboBox QAbstractItemView {
        background: #ffffff;
        border: 1px solid #d3dbe9;
        selection-background-color: #e7edfb;
        selection-color: #1f2733;
        outline: none;
    }

    QPushButton {
        background: #ffffff;
        border: 1px solid #cdd6e6;
        border-radius: 12px;
        padding: 9px 16px;
        color: #2b3a67;
        font-weight: 600;
    }
    QPushButton:hover {
        border-color: #3b6ef5;
        background: #f3f7ff;
    }
    QPushButton:pressed {
        background: #e7eefc;
    }
    QPushButton:disabled {
        color: #a9b1c1;
        background: #f2f4f9;
        border-color: #e1e6f0;
    }

    QPushButton#PrimaryButton {
        background: #3b6ef5;
        border: 1px solid #3b6ef5;
        color: #ffffff;
    }
    QPushButton#PrimaryButton:hover {
        background: #2f60e0;
        border-color: #2f60e0;
    }
    QPushButton#PrimaryButton:pressed {
        background: #2953c9;
    }
    QPushButton#PrimaryButton:disabled {
        background: #b9c8f4;
        border-color: #b9c8f4;
        color: #eef2fb;
    }

    QLabel#HeaderTitle {
        font-size: 16pt;
        font-weight: 800;
        color: #17244a;
    }
    QLabel#HeaderSub {
        color: #6b7688;
    }

    QLabel#StatusLabel {
        background: #f4f7fd;
        border: 1px solid #dbe2ee;
        border-radius: 12px;
        padding: 10px 12px;
        color: #3d4a60;
    }

    QLabel#Pill {
        border-radius: 11px;
        padding: 5px 12px;
        font-weight: 600;
    }
    QLabel#PillOff {
        background: #f0f2f7;
        border: 1px solid #dbe2ee;
        color: #7b869a;
        border-radius: 11px;
        padding: 5px 12px;
        font-weight: 600;
    }
    QLabel#PillOn {
        background: #e6f6ec;
        border: 1px solid #b7e3c6;
        color: #1f8a4c;
        border-radius: 11px;
        padding: 5px 12px;
        font-weight: 600;
    }

    QProgressBar {
        border: 1px solid #d3dbe9;
        border-radius: 9px;
        background: #f2f5fb;
        text-align: center;
        color: #3d4a60;
        height: 18px;
    }
    QProgressBar::chunk {
        border-radius: 8px;
        background: #3b6ef5;
    }

    QScrollArea {
        border: none;
        background: transparent;
    }
    QScrollBar:vertical {
        background: transparent;
        width: 12px;
        margin: 4px;
    }
    QScrollBar::handle:vertical {
        background: #c7d0e0;
        border-radius: 6px;
        min-height: 30px;
    }
    QScrollBar::handle:vertical:hover { background: #adb9d0; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    """
    app.setStyleSheet(qss)

# -------------------------------------------------------------------
# Optional clickable image
# -------------------------------------------------------------------
class ClickableImageLabel(QtWidgets.QLabel):
    def __init__(self, img_rel_path: str, parent=None):
        super().__init__(parent)
        self.original_pixmap = None
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMaximumHeight(IMG_HEIGHT)

        if img_rel_path:
            full = resource_path(img_rel_path)
            pix = QtGui.QPixmap(full)
            if not pix.isNull():
                self.original_pixmap = pix
                scaled = pix.scaledToHeight(IMG_HEIGHT, QtCore.Qt.SmoothTransformation)
                self.setPixmap(scaled)

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        if self.original_pixmap is None:
            return
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Просмотр изображения")
        dlg.setModal(True)

        vbox = QtWidgets.QVBoxLayout(dlg)
        vbox.setContentsMargins(12, 12, 12, 12)

        scroll = QtWidgets.QScrollArea(dlg)
        scroll.setWidgetResizable(True)
        vbox.addWidget(scroll)

        lbl = QtWidgets.QLabel()
        lbl.setAlignment(QtCore.Qt.AlignCenter)
        lbl.setPixmap(self.original_pixmap)
        scroll.setWidget(lbl)

        w = min(self.original_pixmap.width() + 60, 1200)
        h = min(self.original_pixmap.height() + 90, 800)
        dlg.resize(w, h)
        dlg.exec_()

def make_tab_image_label(img_path: str) -> QtWidgets.QLabel:
    if not img_path:
        lbl = QtWidgets.QLabel()
        lbl.setFixedHeight(0)
        return lbl
    return ClickableImageLabel(img_path)

# =============================
# Shared binary-record helpers
# =============================
REC_LEN = 17
OFF_X = 0
OFF_Y = 8
OFF_CRC = 16

def encode_raw_u32_weird(raw: int) -> bytes:
    tmp = raw & 0xFFFFFFFF
    b2 = tmp & 0xFF; tmp >>= 8
    b3 = tmp & 0xFF; tmp >>= 8
    b0 = tmp & 0xFF; tmp >>= 8
    b1 = tmp & 0xFF
    return bytes([b0, b1, b2, b3])

def decode_raw_u32_weird(b4: bytes) -> int:
    b0, b1, b2, b3 = b4
    return ((b1 << 24) | (b0 << 16) | (b3 << 8) | b2) & 0xFFFFFFFF

def crc_xor_16(buf16: bytes) -> int:
    crc = 0xF0
    for x in buf16:
        crc ^= x
    return crc & 0xFF

def read_record_raw(data: bytes, offset: int) -> Tuple[int, int, bool]:
    rec = data[offset:offset+REC_LEN]
    if len(rec) != REC_LEN:
        return (0, 0, False)
    x_raw = decode_raw_u32_weird(rec[OFF_X:OFF_X+4])
    y_raw = decode_raw_u32_weird(rec[OFF_Y:OFF_Y+4])
    ok = (crc_xor_16(rec[0:16]) == rec[OFF_CRC])
    return (x_raw, y_raw, ok)

def read_record(data: bytes, offset: int, factor: int) -> Tuple[float, float, bool]:
    x_raw, y_raw, ok = read_record_raw(data, offset)
    return (x_raw / factor, y_raw / factor, ok)

def write_record(data: bytearray, offset: int, x: float, y: float, factor: int) -> None:
    x_raw = int(round(x * factor))
    y_raw = int(round(y * factor))
    data[offset+OFF_X:offset+OFF_X+4] = encode_raw_u32_weird(x_raw)
    data[offset+OFF_Y:offset+OFF_Y+4] = encode_raw_u32_weird(y_raw)
    data[offset+OFF_CRC] = crc_xor_16(bytes(data[offset:offset+16]))

# Ratio profiles
RATIO_PROFILE_A = 4490.54 / 18987.70
RATIO_PROFILE_B    = 1445.71 / 6384.36

# =============================================================================
# CH341A SPI backend (SPI FRAM: MB85RS256 / FM25V04B / FM25L02 …)
# =============================================================================
# Прямая работа с SPI-памятью через USB-адаптер CH341A. Используется штатная
# библиотека CH341DLL(.dll) от производителя (только Windows). Библиотека
# загружается «лениво» — при первом подключении, поэтому модуль импортируется
# на любой платформе.
CH341_DLL_NAMES = [
    "CH341DLLA64.dll",  # 64-bit (новые сборки)
    "CH341DLLA.dll",
    "CH341DLL.dll",     # 32-bit
    "CH341DLL",
]


class Ch341Error(Exception):
    pass


class Ch341Spi:
    """Тонкая обёртка над CH341DLL для полнодуплексного обмена по SPI.

    Микросхемы SPI-FRAM (MB85RS256, FM25V04B, FM25L02) используют одинаковый
    набор команд; отличаются только объёмом и разрядностью адреса.
    """

    # Команды SPI-FRAM
    CMD_WREN  = 0x06  # разрешить запись
    CMD_WRDI  = 0x04  # запретить запись
    CMD_RDSR  = 0x05  # прочитать регистр статуса
    CMD_WRSR  = 0x01  # записать регистр статуса
    CMD_READ  = 0x03  # чтение памяти
    CMD_WRITE = 0x02  # запись памяти
    CMD_RDID  = 0x9F  # идентификатор устройства

    # Предельный размер одного потока CH341StreamSPI4 (вместе с командой/адресом)
    MAX_XFER = 4096
    # CS на линии D0, старший бит первым (стандартный SPI)
    _CS = 0x80
    _STREAM_MODE = 0x80  # bit7=1 -> MSB first, одиночный ввод/вывод

    def __init__(self, index: int = 0):
        self.index = index
        self._dll = None
        self._open = False

    # ---- низкий уровень ----------------------------------------------------
    def _load(self):
        if self._dll is not None:
            return
        if os.name != "nt":
            raise Ch341Error("Прямая запись через CH341 доступна только в Windows "
                              "(требуется CH341DLL.dll).")
        last_err = None
        for name in CH341_DLL_NAMES:
            try:
                self._dll = ctypes.WinDLL(name)
                break
            except OSError as e:
                last_err = e
        if self._dll is None:
            raise Ch341Error("Не найдена библиотека CH341DLL. Установите драйвер "
                             f"CH341 и положите CH341DLL.dll рядом с программой. ({last_err})")

        self._dll.CH341OpenDevice.restype = ctypes.c_void_p
        self._dll.CH341OpenDevice.argtypes = [ctypes.c_ulong]
        self._dll.CH341CloseDevice.argtypes = [ctypes.c_ulong]
        self._dll.CH341SetStream.restype = ctypes.c_int
        self._dll.CH341SetStream.argtypes = [ctypes.c_ulong, ctypes.c_ulong]
        self._dll.CH341StreamSPI4.restype = ctypes.c_int
        self._dll.CH341StreamSPI4.argtypes = [
            ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p
        ]

    @property
    def is_open(self) -> bool:
        return self._open

    def open(self):
        self._load()
        handle = self._dll.CH341OpenDevice(self.index)
        invalid = (None, 0, -1, 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF)
        if handle in invalid:
            raise Ch341Error(f"Не удалось открыть CH341 (устройство {self.index}). "
                             "Проверьте подключение адаптера и драйвер.")
        # Настроить SPI: старший бит первым, одиночный ввод/вывод.
        self._dll.CH341SetStream(self.index, self._STREAM_MODE)
        self._open = True

    def close(self):
        if self._open and self._dll is not None:
            try:
                self._dll.CH341CloseDevice(self.index)
            except Exception:
                pass
        self._open = False

    def _xfer(self, out_bytes: bytes) -> bytearray:
        """Полнодуплексная передача: возвращает принятые байты той же длины."""
        n = len(out_bytes)
        buf = ctypes.create_string_buffer(bytes(out_bytes), n)
        ok = self._dll.CH341StreamSPI4(self.index, self._CS, n, buf)
        if not ok:
            raise Ch341Error("Ошибка обмена по SPI (CH341StreamSPI4).")
        return bytearray(buf.raw[:n])

    @staticmethod
    def _addr(a: int, nbytes: int) -> bytes:
        return bytes((a >> (8 * (nbytes - 1 - i))) & 0xFF for i in range(nbytes))

    # ---- высокий уровень ---------------------------------------------------
    def read_status(self) -> int:
        return self._xfer(bytes([self.CMD_RDSR, 0x00]))[1]

    def read_id(self) -> bytes:
        # 9 «холостых» байт достаточно для manufacturer/continuation/product id
        return bytes(self._xfer(bytes([self.CMD_RDID]) + bytes(9))[1:])

    def read(self, size: int, addr_bytes: int,
             progress: Optional[Callable[[int, int], None]] = None,
             should_stop: Optional[Callable[[], bool]] = None) -> bytearray:
        out = bytearray()
        chunk_max = self.MAX_XFER - (1 + addr_bytes)
        a = 0
        while a < size:
            n = min(chunk_max, size - a)
            cmd = bytes([self.CMD_READ]) + self._addr(a, addr_bytes) + bytes(n)
            r = self._xfer(cmd)
            out += r[1 + addr_bytes:1 + addr_bytes + n]
            a += n
            if progress:
                progress(a, size)
            if should_stop and should_stop():
                break
        return out

    def write(self, data: bytes, addr_bytes: int,
              progress: Optional[Callable[[int, int], None]] = None,
              should_stop: Optional[Callable[[], bool]] = None) -> int:
        size = len(data)
        chunk_max = self.MAX_XFER - (1 + addr_bytes)
        a = 0
        while a < size:
            n = min(chunk_max, size - a)
            # WREN обязателен перед каждой командой записи (WEL сбрасывается).
            self._xfer(bytes([self.CMD_WREN]))
            cmd = bytes([self.CMD_WRITE]) + self._addr(a, addr_bytes) + bytes(data[a:a + n])
            self._xfer(cmd)
            a += n
            if progress:
                progress(a, size)
            if should_stop and should_stop():
                break
        return a

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


class SpiWorker(QtCore.QThread):
    """Выполняет операцию SPI в отдельном потоке, не блокируя интерфейс."""
    progress = QtCore.pyqtSignal(int, int)
    done = QtCore.pyqtSignal(bool, str, object)

    def __init__(self, fn: Callable):
        super().__init__()
        self._fn = fn
        self._stop = False

    def request_stop(self):
        self._stop = True

    def run(self):
        try:
            res = self._fn(
                lambda a, b: self.progress.emit(a, b),
                lambda: self._stop,
            )
            self.done.emit(True, "", res)
        except Exception as e:  # noqa: BLE001 — сообщаем текст пользователю
            self.done.emit(False, str(e), None)


# Каталог распространённых SPI-FRAM: (короткое имя, объём КБ, байт адреса).
# Значения FM25V04B/FM25L02 — типовые, при необходимости правьте вручную.
CHIP_CATALOG = [
    ("MB85RS64",   8,   2),
    ("MB85RS128B", 16,  2),
    ("MB85RS256",  32,  2),
    ("MB85RS512",  64,  2),
    ("MB85RS1MT",  128, 3),
    ("MB85RS2MTA", 256, 3),
    ("FM25V01",    16,  2),
    ("FM25V02",    32,  2),
    ("FM25V04B",   64,  2),
    ("FM25V05",    64,  2),
    ("FM25V10",    128, 3),
    ("FM25V20A",   256, 3),
    ("FM25W256",   32,  2),
    ("FM25L16B",   2,   2),
    ("FM25L02",    32,  2),
]
MANUAL_CHIP = "Другая (вручную)"


class SpiPanel(QtWidgets.QGroupBox):
    """Панель прямой записи в SPI-память (через CH341A).

    Основное действие — одна кнопка «Записать в память»: она сама подключает
    адаптер, пишет текущий буфер редактора в выбранную микросхему и сразу
    проверяет результат. Дополнительно есть чтение микросхемы в файл.
    """

    def __init__(self, chip_name: str, default_size_kb: int, default_addr_bytes: int,
                 editor_provider: Optional[Callable[[], Optional[bytearray]]] = None,
                 parent=None):
        super().__init__(f"Прямая запись в SPI · {chip_name}", parent)
        self.chip_name = chip_name
        self.editor_provider = editor_provider
        self._chip_map = {name: (kb, ab) for name, kb, ab in CHIP_CATALOG}
        self.spi = Ch341Spi(0)
        self.worker: Optional[SpiWorker] = None

        g = QtWidgets.QGridLayout(self)
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(10)

        # --- выбор микросхемы + индикатор подключения ---
        self.combo_chip = QtWidgets.QComboBox()
        for name, kb, ab in CHIP_CATALOG:
            self.combo_chip.addItem(f"{name} · {kb} КБ · {ab} б", name)
        self.combo_chip.addItem(MANUAL_CHIP, None)
        idx = self.combo_chip.findData(chip_name)
        self.combo_chip.setCurrentIndex(max(0, idx))
        self.combo_chip.currentIndexChanged.connect(self.on_chip_changed)

        self.lbl_conn = QtWidgets.QLabel("Не подключено")
        self.lbl_conn.setObjectName("PillOff")
        self.lbl_conn.setAlignment(QtCore.Qt.AlignCenter)

        g.addWidget(QtWidgets.QLabel("Микросхема:"), 0, 0)
        g.addWidget(self.combo_chip, 0, 1)
        g.addWidget(self.lbl_conn, 0, 2)
        g.setColumnStretch(1, 1)

        # --- ручные параметры (видны только для «Другая (вручную)») ---
        self.manual_row = QtWidgets.QWidget()
        m = QtWidgets.QHBoxLayout(self.manual_row)
        m.setContentsMargins(0, 0, 0, 0)
        m.setSpacing(10)
        self.spin_size = QtWidgets.QSpinBox()
        self.spin_size.setRange(1, 4096)
        self.spin_size.setSuffix(" КБ")
        self.spin_size.setValue(default_size_kb)
        self.combo_addr = QtWidgets.QComboBox()
        self.combo_addr.addItems(["1", "2", "3"])
        self.combo_addr.setCurrentText(str(default_addr_bytes))
        self.spin_index = QtWidgets.QSpinBox()
        self.spin_index.setRange(0, 15)
        self.spin_index.setPrefix("устр. ")
        m.addWidget(QtWidgets.QLabel("Объём:"))
        m.addWidget(self.spin_size)
        m.addWidget(QtWidgets.QLabel("Адрес, байт:"))
        m.addWidget(self.combo_addr)
        m.addWidget(self.spin_index)
        m.addStretch(1)
        self.manual_row.setVisible(False)
        g.addWidget(self.manual_row, 1, 0, 1, 3)

        # --- главное действие + чтение ---
        self.btn_write = QtWidgets.QPushButton("⤓  Записать в память")
        self.btn_write.setObjectName("PrimaryButton")
        self.btn_write.setMinimumHeight(46)
        self.btn_write.clicked.connect(self.write_to_memory)
        self.btn_read = QtWidgets.QPushButton("Считать в файл")
        self.btn_read.clicked.connect(self.read_to_file)
        g.addWidget(self.btn_write, 2, 0, 1, 2)
        g.addWidget(self.btn_read, 2, 2)

        # --- прогресс + статус ---
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        g.addWidget(self.progress, 3, 0, 1, 3)

        self.status = QtWidgets.QLabel(
            "Готово к работе. Подключите CH341 и нажмите «Записать в память» — "
            "адаптер подключится автоматически."
        )
        self.status.setObjectName("StatusLabel")
        self.status.setWordWrap(True)
        g.addWidget(self.status, 4, 0, 1, 3)

        if editor_provider is None:
            self.btn_write.setVisible(False)

        self._update_conn_ui()

    # ---- параметры ----
    def size_bytes(self) -> int:
        return int(self.spin_size.value()) * 1024

    def addr_bytes(self) -> int:
        return int(self.combo_addr.currentText())

    def on_chip_changed(self):
        """Подставить объём/адрес выбранной микросхемы; показать ручные поля."""
        name = self.combo_chip.currentData()
        manual = name is None
        self.manual_row.setVisible(manual)
        if manual:
            self.setTitle("Прямая запись в SPI · вручную")
            return
        self.chip_name = name
        self.setTitle(f"Прямая запись в SPI · {name}")
        kb, ab = self._chip_map[name]
        self.spin_size.setValue(kb)
        self.combo_addr.setCurrentText(str(ab))

    # ---- подключение ----
    def _ensure_open(self) -> bool:
        """Открыть CH341 при необходимости. Возвращает True, если подключено."""
        if self.spi.is_open:
            return True
        self.spi.index = int(self.spin_index.value())
        try:
            self.spi.open()
        except Ch341Error as e:
            self.status.setText("Ошибка подключения: " + str(e))
            self._update_conn_ui()
            return False
        self._update_conn_ui()
        return True

    def _update_conn_ui(self):
        on = self.spi.is_open
        self.lbl_conn.setText("Подключено" if on else "Не подключено")
        self.lbl_conn.setObjectName("PillOn" if on else "PillOff")
        self.lbl_conn.style().unpolish(self.lbl_conn)
        self.lbl_conn.style().polish(self.lbl_conn)

    # ---- вспомогательное ----
    def _busy(self, busy: bool):
        for w in (self.btn_write, self.btn_read, self.combo_chip,
                  self.manual_row):
            w.setEnabled(not busy)

    def _on_progress(self, cur: int, total: int):
        self.progress.setValue(int(cur * 100 / total) if total else 0)

    def _run(self, fn: Callable, busy_label: str, on_success: Callable):
        self._busy(True)
        self.progress.setValue(0)
        self.status.setText(busy_label)
        self.worker = SpiWorker(fn)
        self.worker.progress.connect(self._on_progress)

        def _finished(ok: bool, err: str, res):
            self._busy(False)
            if not ok:
                self.status.setText("Ошибка: " + err)
            else:
                on_success(res)
            self.worker = None

        self.worker.done.connect(_finished)
        self.worker.start()

    def _fit_to_chip(self, data: bytearray) -> bytearray:
        size = self.size_bytes()
        if len(data) > size:
            QtWidgets.QMessageBox.warning(
                self, "Внимание",
                f"Данные ({len(data)} байт) больше объёма {self.chip_name} "
                f"({size} байт). Будут записаны первые {size} байт."
            )
            return data[:size]
        return data

    # ---- основное действие: запись буфера + автопроверка ----
    def write_to_memory(self):
        if self.editor_provider is None:
            return
        data = self.editor_provider()
        if not data:
            self.status.setText("Нет данных: откройте файл и задайте значения "
                                "на этой вкладке, затем нажмите «Записать в память».")
            return
        data = self._fit_to_chip(bytearray(data))

        r = QtWidgets.QMessageBox.question(
            self, "Запись в память",
            f"Записать {len(data)} байт в {self.chip_name}?\n"
            "Текущее содержимое микросхемы будет перезаписано.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if r != QtWidgets.QMessageBox.Yes:
            return
        if not self._ensure_open():
            return

        ab = self.addr_bytes()
        payload = bytes(data)
        n = len(payload)

        def fn(progress, stop):
            # фаза 1 — запись (0..50%), фаза 2 — проверка (50..100%)
            self.spi.write(payload, ab,
                           progress=lambda c, t: progress(c, t * 2), should_stop=stop)
            back = self.spi.read(n, ab,
                                 progress=lambda c, t: progress(t + c, t * 2),
                                 should_stop=stop)
            diff = next((i for i in range(n) if back[i] != payload[i]), None)
            return diff

        def ok(diff):
            if diff is None:
                self.status.setText(f"Записано и проверено: {n} байт в "
                                    f"{self.chip_name} — совпадение OK.")
            else:
                self.status.setText(
                    f"Записано {n} байт, но проверка не прошла: расхождение по "
                    f"адресу 0x{diff:06X}. Проверьте контакт и питание чипа."
                )

        self._run(fn, f"Запись и проверка {n} байт в {self.chip_name}…", ok)

    # ---- чтение микросхемы в файл ----
    def read_to_file(self):
        if not self._ensure_open():
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, f"Сохранить дамп {self.chip_name}", f"{self.chip_name}_dump.bin",
            "BIN (*.bin);;All files (*.*)")
        if not path:
            return
        size = self.size_bytes()
        ab = self.addr_bytes()

        def fn(progress, stop):
            return self.spi.read(size, ab, progress=progress, should_stop=stop)

        def ok(res):
            try:
                with open(path, "wb") as f:
                    f.write(res)
            except Exception as e:  # noqa: BLE001
                self.status.setText(f"Ошибка записи файла: {e}")
                return
            self.status.setText(f"Считано {len(res)} байт из {self.chip_name} → {path}")

        self._run(fn, f"Чтение {size} байт из {self.chip_name}…", ok)

    def shutdown(self):
        if self.worker is not None and self.worker.isRunning():
            self.worker.request_stop()
            self.worker.wait(2000)
        self.spi.close()

# =============================
# TAB 1: MB85RS256 — Формат A (two channels + total)
# =============================
CHANNEL_A_RECORD_OFFSETS = [0x0000, 0x0100]
CHANNEL_B_RECORD_OFFSETS = [0x0011, 0x0111]
TOTAL_RECORD_OFFSETS = [0x0200]

def _close(a: float, b: float, tol: float = 0.02) -> bool:
    return abs(a - b) <= tol

def choose_total_values(a_x: float, a_y: float, b_x: float, b_y: float, total_x_file: float, total_y_file: float) -> Tuple[float, float, str]:
    sum_x = a_x + b_x
    sum_y = a_y + b_y
    if _close(total_x_file, sum_x, tol=0.02) and _close(total_y_file, sum_y, tol=0.02):
        return total_x_file, total_y_file, "FILE"
    return sum_x, sum_y, "SUM"

@dataclass
class FormatAValues:
    channel_a_x: float
    channel_b_x: float
    channel_a_y: float
    channel_b_y: float
    total_x: float
    total_y: float

def safe_output_name_a(in_path: str, values: FormatAValues, factor: int) -> str:
    base = os.path.basename(in_path)
    root, ext = os.path.splitext(base)
    tag = f"X{values.total_x:.2f}_Y{values.total_y:.2f}_scale{factor}"
    return os.path.join(os.path.dirname(in_path), f"{root}__format_a__updated__{tag}{ext or '.bin'}")

class FormatATab(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self._current_path = None
        self._file_ratio = None
        self._sum_ratio = None
        self._total_source = "FILE"

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        header = QtWidgets.QHBoxLayout()
        titles = QtWidgets.QVBoxLayout()
        self.h1 = QtWidgets.QLabel("MB85RS256 — Формат A (два канала и итог)")
        self.h1.setObjectName("HeaderTitle")
        self.h2 = QtWidgets.QLabel("Задайте итоговое X и X канала A — канал B и значения Y рассчитываются автоматически.")
        self.h2.setObjectName("HeaderSub")
        titles.addWidget(self.h1)
        titles.addWidget(self.h2)
        header.addLayout(titles)
        header.addStretch(1)
        root.addLayout(header)

        root.addWidget(make_tab_image_label(IMG_FORMAT_A_IN_TAB))

        file_box = QtWidgets.QGroupBox("Файл")
        file_l = QtWidgets.QGridLayout(file_box)
        file_l.setHorizontalSpacing(10)
        file_l.setVerticalSpacing(10)

        self.btn_open = QtWidgets.QPushButton("Открыть файл формата A")
        self.btn_open.clicked.connect(self.open_file)
        self.path_edit = QtWidgets.QLineEdit(); self.path_edit.setReadOnly(True)

        file_l.addWidget(self.btn_open, 0, 0, 1, 1)
        file_l.addWidget(self.path_edit, 0, 1, 1, 5)

        self.factor_box = QtWidgets.QComboBox()
        self.factor_box.addItems(["1000", "2000"])
        self.factor_box.setCurrentIndex(0)

        self.ratio_mode = QtWidgets.QComboBox()
        self.ratio_mode.addItems([
            "Профиль A (4490.54/18987.70)",
            "Профиль B (1445.71/6384.36)",
            "Из итоговой записи 0x0200 (Y/X)",
            "Из суммы каналов",
            "Ручной коэффициент",
        ])
        self.ratio_mode.setCurrentIndex(0)

        self.ed_ratio = QtWidgets.QLineEdit()
        dvk = QtGui.QDoubleValidator(0.0, 9999.0, 10, self)
        dvk.setNotation(QtGui.QDoubleValidator.StandardNotation)
        self.ed_ratio.setValidator(dvk)
        self.ed_ratio.setText(f"{RATIO_PROFILE_A:.10f}")
        self.ed_ratio.setToolTip("коэффициент = Y/X")


        file_l.addWidget(QtWidgets.QLabel("Масштаб:"), 1, 0)
        file_l.addWidget(self.factor_box, 1, 1)
        file_l.addWidget(QtWidgets.QLabel("Режим коэффициента:"), 1, 2)
        file_l.addWidget(self.ratio_mode, 1, 3, 1, 2)
        file_l.addWidget(QtWidgets.QLabel("Коэффициент:"), 1, 5)
        file_l.addWidget(self.ed_ratio, 1, 6)

        root.addWidget(file_box)

        calc_box = QtWidgets.QGroupBox("Расчёт / замена")
        form = QtWidgets.QGridLayout(calc_box)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(10)

        self.out_total_x = QtWidgets.QDoubleSpinBox(); self._setup_spin(self.out_total_x)
        self.out_total_y = QtWidgets.QLineEdit(); self.out_total_y.setReadOnly(True)

        self.in_a_x = QtWidgets.QDoubleSpinBox(); self._setup_spin(self.in_a_x)
        self.in_b_x = QtWidgets.QDoubleSpinBox(); self._setup_spin(self.in_b_x); self.in_b_x.setEnabled(False)
        self.in_a_y = QtWidgets.QDoubleSpinBox(); self._setup_spin(self.in_a_y); self.in_a_y.setEnabled(False)
        self.in_b_y = QtWidgets.QDoubleSpinBox(); self._setup_spin(self.in_b_y); self.in_b_y.setEnabled(False)

        r = 0
        form.addWidget(QtWidgets.QLabel("Итог X:"), r, 0); form.addWidget(self.out_total_x, r, 1)
        form.addWidget(QtWidgets.QLabel("Итог Y (авто):"), r, 2); form.addWidget(self.out_total_y, r, 3, 1, 3)
        r += 1
        form.addWidget(QtWidgets.QLabel("Канал A — X:"), r, 0); form.addWidget(self.in_a_x, r, 1)
        form.addWidget(QtWidgets.QLabel("Канал B — X (итог − A):"), r, 2); form.addWidget(self.in_b_x, r, 3, 1, 3)
        r += 1
        form.addWidget(QtWidgets.QLabel("Канал A — Y (авто):"), r, 0); form.addWidget(self.in_a_y, r, 1)
        form.addWidget(QtWidgets.QLabel("Канал B — Y (авто):"), r, 2); form.addWidget(self.in_b_y, r, 3, 1, 3)

        root.addWidget(calc_box)

        self.lbl_status = QtWidgets.QLabel("Файл не выбран")
        self.lbl_status.setObjectName("StatusLabel")
        self.lbl_status.setWordWrap(True)
        root.addWidget(self.lbl_status)

        self.btn_apply = QtWidgets.QPushButton("Сформировать изменённую копию")
        self.btn_apply.setObjectName("PrimaryButton")
        self.btn_apply.clicked.connect(self.apply_patch)
        root.addWidget(self.btn_apply)

        # Прямая запись в SPI (MB85RS256, 32 КБ, 2 байта адреса)
        self.spi_panel = SpiPanel("MB85RS256", 32, 2, editor_provider=self.build_patched_bytes)
        root.addWidget(self.spi_panel)

        root.addStretch(1)

        self.in_a_x.valueChanged.connect(self.refresh_values)
        self.out_total_x.valueChanged.connect(self.refresh_values)
        self.factor_box.currentIndexChanged.connect(self.reload_from_file)
        self.ratio_mode.currentIndexChanged.connect(self.on_ratio_mode_changed)
        self.ed_ratio.textChanged.connect(self.refresh_values)

        self.on_ratio_mode_changed()

    def _setup_spin(self, w: QtWidgets.QDoubleSpinBox):
        w.setDecimals(2)
        w.setRange(0, 999999999.99)
        w.setSingleStep(0.01)

    def factor(self) -> int:
        return int(self.factor_box.currentText())

    def open_file(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Выберите файл формата A", "", "BIN (*.bin *.BIN);;All files (*.*)")
        if not path:
            return
        self._current_path = path
        self.path_edit.setText(path)
        self.reload_from_file()

    def reload_from_file(self):
        if not self._current_path:
            return
        try:
            data = open(self._current_path, "rb").read()
        except Exception as e:
            self.lbl_status.setText(f"Ошибка чтения: {e}")
            return

        factor = self.factor()
        a_x, a_y, ok1 = read_record(data, CHANNEL_A_RECORD_OFFSETS[0], factor)
        b_x, b_y, ok2 = read_record(data, CHANNEL_B_RECORD_OFFSETS[0], factor)
        total_x_f, total_y_f, ok3 = read_record(data, TOTAL_RECORD_OFFSETS[0], factor)

        self._file_ratio = (total_y_f / total_x_f) if total_x_f > 0 else None
        sum_x = a_x + b_x
        sum_y = a_y + b_y
        self._sum_ratio = (sum_y / sum_x) if sum_x > 0 else None

        total_x_use, total_y_use, src = choose_total_values(a_x, a_y, b_x, b_y, total_x_f, total_y_f)
        self._total_source = src

        self.out_total_x.blockSignals(True)
        self.in_a_x.blockSignals(True)
        self.out_total_x.setValue(total_x_use)
        self.in_a_x.setValue(a_x)
        self.out_total_x.blockSignals(False)
        self.in_a_x.blockSignals(False)

        self.on_ratio_mode_changed()
        self.refresh_values()

        fk = self._file_ratio if self._file_ratio is not None else float("nan")
        sk = self._sum_ratio if self._sum_ratio is not None else float("nan")
        self.lbl_status.setText(
            f"Контроль: A={'OK' if ok1 else 'BAD'} | B={'OK' if ok2 else 'BAD'} | TOTAL@0x0200={'OK' if ok3 else 'BAD'}\n"
            f"TOTAL@0x0200: X={total_x_f:.2f} Y={total_y_f:.2f} (ratio_file={fk:.10f})\n"
            f"TOTAL(sum): X={sum_x:.2f} Y={sum_y:.2f} (ratio_sum={sk:.10f})\n"
            f"Источник итога: {self._total_source}"
        )

    def on_ratio_mode_changed(self):
        mode = self.ratio_mode.currentIndex()
        if mode == 0:
            self.ed_ratio.setText(f"{RATIO_PROFILE_A:.10f}")
            self.ed_ratio.setEnabled(False)
        elif mode == 1:
            self.ed_ratio.setText(f"{RATIO_PROFILE_B:.10f}")
            self.ed_ratio.setEnabled(False)
        elif mode == 2:
            if self._file_ratio is not None and self._file_ratio > 0:
                self.ed_ratio.setText(f"{self._file_ratio:.10f}")
            else:
                self.ed_ratio.setText(f"{RATIO_PROFILE_A:.10f}")
            self.ed_ratio.setEnabled(False)
        elif mode == 3:
            if self._sum_ratio is not None and self._sum_ratio > 0:
                self.ed_ratio.setText(f"{self._sum_ratio:.10f}")
            else:
                self.ed_ratio.setText(f"{RATIO_PROFILE_A:.10f}")
            self.ed_ratio.setEnabled(False)
        else:
            if not self.ed_ratio.text().strip():
                self.ed_ratio.setText(f"{RATIO_PROFILE_A:.10f}")
            self.ed_ratio.setEnabled(True)
        self.refresh_values()

    def _parse_ratio(self) -> float:
        s = self.ed_ratio.text().strip().replace(',', '.')
        try:
            ratio = float(s)
        except Exception:
            ratio = RATIO_PROFILE_A
        if ratio <= 0:
            ratio = RATIO_PROFILE_A
        return ratio

    def refresh_values(self):
        totp = float(self.out_total_x.value())
        a_x = float(self.in_a_x.value())
        b_x = totp - a_x
        if b_x < 0:
            b_x = 0.0

        ratio = self._parse_ratio()
        a_y = a_x * ratio
        b_y = b_x * ratio
        totq = a_y + b_y

        for w, v in ((self.in_b_x, b_x), (self.in_a_y, a_y), (self.in_b_y, b_y)):
            w.blockSignals(True)
            w.setValue(v)
            w.blockSignals(False)

        self.out_total_y.setText(f"{totq:.2f}")

    def build_patched_bytes(self) -> Optional[bytearray]:
        """Собрать пропатченный буфер по текущим значениям (для записи в SPI)."""
        if not self._current_path:
            return None
        try:
            data = bytearray(open(self._current_path, "rb").read())
        except Exception:
            return None

        factor = self.factor()
        totp = float(self.out_total_x.value())
        a_x = float(self.in_a_x.value())
        b_x = totp - a_x
        if b_x < 0:
            b_x = 0.0
        ratio = self._parse_ratio()
        a_y = a_x * ratio
        b_y = b_x * ratio
        totq = a_y + b_y

        for s in CHANNEL_A_RECORD_OFFSETS:
            write_record(data, s, a_x, a_y, factor)
        for s in CHANNEL_B_RECORD_OFFSETS:
            write_record(data, s, b_x, b_y, factor)
        for s in TOTAL_RECORD_OFFSETS:
            write_record(data, s, totp, totq, factor)
        return data

    def apply_patch(self):
        if not self._current_path:
            self.lbl_status.setText("Сначала выбери файл")
            return
        data = self.build_patched_bytes()
        if data is None:
            self.lbl_status.setText("Ошибка чтения файла")
            return

        factor = self.factor()
        totp = float(self.out_total_x.value())
        a_x = float(self.in_a_x.value())
        b_x = totp - a_x
        if b_x < 0:
            b_x = 0.0
        ratio = self._parse_ratio()
        a_y = a_x * ratio
        b_y = b_x * ratio
        totq = a_y + b_y

        values = FormatAValues(channel_a_x=a_x, channel_b_x=b_x, channel_a_y=a_y, channel_b_y=b_y, total_x=totp, total_y=totq)

        out_path = safe_output_name_a(self._current_path, values, factor)
        try:
            with open(out_path, "wb") as f:
                f.write(data)
        except Exception as e:
            self.lbl_status.setText(f"Ошибка записи: {e}")
            return

        self.lbl_status.setText(f"Готово: {out_path}")

# =============================
# TAB 2: FM25V04B — Формат B (single total record)
# =============================
BASE_OFF = 0x0000
DUP_OFF  = 0x0100

@dataclass
class DecodedRecord:
    ok: bool
    x_raw: int
    y_raw: int
    crc_file: int
    crc_calc: int

def parse_record(buf: bytes, base_off: int) -> DecodedRecord:
    if len(buf) < base_off + REC_LEN:
        return DecodedRecord(False, 0, 0, 0, 0)
    rec = buf[base_off: base_off + REC_LEN]
    data16 = rec[:16]
    crc_file = rec[OFF_CRC]
    crc_calc = crc_xor_16(data16)
    x_raw = decode_raw_u32_weird(rec[OFF_X:OFF_X+4])
    y_raw = decode_raw_u32_weird(rec[OFF_Y:OFF_Y+4])
    return DecodedRecord(crc_file == crc_calc, x_raw, y_raw, crc_file, crc_calc)

def detect_factor_from_raw(x_raw: int, y_raw: int) -> int:
    step10_ok = (x_raw % 10 == 0) and (y_raw % 10 == 0)
    step20_ok = (x_raw % 20 == 0) and (y_raw % 20 == 0)
    if step20_ok:
        return 2000
    if step10_ok:
        return 1000
    return 1000

def patch_total_record(buf: bytearray, x_value: float, y_value: float, factor: int) -> None:
    x_raw = int(round(x_value * factor))
    y_raw = int(round(y_value * factor))
    buf[BASE_OFF+OFF_X:BASE_OFF+OFF_X+4] = encode_raw_u32_weird(x_raw)
    buf[BASE_OFF+OFF_Y:BASE_OFF+OFF_Y+4] = encode_raw_u32_weird(y_raw)
    buf[BASE_OFF+OFF_CRC] = crc_xor_16(bytes(buf[BASE_OFF:BASE_OFF+16]))
    buf[DUP_OFF:DUP_OFF+REC_LEN] = buf[BASE_OFF:BASE_OFF+REC_LEN]

class FormatBTab(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.buf = None
        self.path_in = None
        self._file_ratio = None

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        header = QtWidgets.QHBoxLayout()
        titles = QtWidgets.QVBoxLayout()
        h1 = QtWidgets.QLabel("FM25V04B — Формат B (итоговая запись)")
        h1.setObjectName("HeaderTitle")
        h2 = QtWidgets.QLabel("Задайте X — значение Y будет рассчитано автоматически по коэффициенту.")
        h2.setObjectName("HeaderSub")
        titles.addWidget(h1)
        titles.addWidget(h2)
        header.addLayout(titles)
        header.addStretch(1)
        root.addLayout(header)

        root.addWidget(make_tab_image_label(IMG_FORMAT_B_IN_TAB))

        file_box = QtWidgets.QGroupBox("Файл")
        file_l = QtWidgets.QHBoxLayout(file_box)
        file_l.setSpacing(10)

        self.btn_open = QtWidgets.QPushButton("Открыть BIN")
        self.btn_save = QtWidgets.QPushButton("Сохранить копию")
        self.btn_save.setObjectName("PrimaryButton")
        self.btn_save.setEnabled(False)

        file_l.addWidget(self.btn_open)
        file_l.addWidget(self.btn_save)
        file_l.addStretch(1)

        root.addWidget(file_box)

        settings_box = QtWidgets.QGroupBox("Настройки")
        s = QtWidgets.QGridLayout(settings_box)
        s.setHorizontalSpacing(10)
        s.setVerticalSpacing(10)

        self.rb_auto = QtWidgets.QRadioButton("Авто (по содержимому файла)")
        self.rb_1000 = QtWidgets.QRadioButton("Профиль 1 = 1000")
        self.rb_2000 = QtWidgets.QRadioButton("Профиль 2 = 2000")
        self.rb_auto.setChecked(True)

        coef_row = QtWidgets.QHBoxLayout()
        coef_row.addWidget(self.rb_auto)
        coef_row.addWidget(self.rb_1000)
        coef_row.addWidget(self.rb_2000)
        coef_row.addStretch(1)

        self.ratio_mode = QtWidgets.QComboBox()
        self.ratio_mode.addItems(["Профиль B (1445.71/6384.36)", "Из файла (Y/X)", "Ручной коэффициент"])
        self.ratio_mode.setCurrentIndex(0)

        self.ed_ratio = QtWidgets.QLineEdit()
        dv = QtGui.QDoubleValidator(0.0, 9999.0, 10, self)
        dv.setNotation(QtGui.QDoubleValidator.StandardNotation)
        self.ed_ratio.setValidator(dv)
        self.ed_ratio.setText(f"{RATIO_PROFILE_B:.10f}")
        self.ed_ratio.setEnabled(False)

        s.addWidget(QtWidgets.QLabel("Масштаб:"), 0, 0)
        s.addLayout(coef_row, 0, 1, 1, 4)
        s.addWidget(QtWidgets.QLabel("Режим коэффициента:"), 1, 0)
        s.addWidget(self.ratio_mode, 1, 1, 1, 2)
        s.addWidget(QtWidgets.QLabel("Коэффициент:"), 1, 3)
        s.addWidget(self.ed_ratio, 1, 4)

        root.addWidget(settings_box)

        cur = QtWidgets.QGroupBox("Текущие значения (0x0000)")
        cur_l = QtWidgets.QGridLayout(cur)
        cur_l.setHorizontalSpacing(10); cur_l.setVerticalSpacing(10)

        self.ed_cur_x = QtWidgets.QLineEdit(); self.ed_cur_x.setReadOnly(True)
        self.ed_cur_y = QtWidgets.QLineEdit(); self.ed_cur_y.setReadOnly(True)
        cur_l.addWidget(QtWidgets.QLabel("X:"), 0, 0); cur_l.addWidget(self.ed_cur_x, 0, 1)
        cur_l.addWidget(QtWidgets.QLabel("Y:"), 0, 2); cur_l.addWidget(self.ed_cur_y, 0, 3)

        root.addWidget(cur)

        new = QtWidgets.QGroupBox("Новые значения (запись в 0x0000 и 0x0100)")
        new_l = QtWidgets.QGridLayout(new)
        new_l.setHorizontalSpacing(10); new_l.setVerticalSpacing(10)

        self.ed_new_x = QtWidgets.QLineEdit()
        self.ed_new_y = QtWidgets.QLineEdit(); self.ed_new_y.setReadOnly(True)

        dv2 = QtGui.QDoubleValidator(0.0, 999999999.99, 2, self)
        dv2.setNotation(QtGui.QDoubleValidator.StandardNotation)
        self.ed_new_x.setValidator(dv2)
        self.ed_new_y.setValidator(dv2)

        self.ed_new_x.setPlaceholderText("например, 6384.36")
        self.ed_new_y.setPlaceholderText("авто")

        new_l.addWidget(QtWidgets.QLabel("X:"), 0, 0); new_l.addWidget(self.ed_new_x, 0, 1)
        new_l.addWidget(QtWidgets.QLabel("Y (авто):"), 0, 2); new_l.addWidget(self.ed_new_y, 0, 3)

        root.addWidget(new)

        self.lbl_status = QtWidgets.QLabel("Файл не открыт")
        self.lbl_status.setObjectName("StatusLabel")
        self.lbl_status.setWordWrap(True)
        root.addWidget(self.lbl_status)

        hint = QtWidgets.QLabel("Структура: X 0..3, Y 8..11, контрольный байт 16, копия +0x100.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#6b7688;")
        root.addWidget(hint)

        # Прямая запись в SPI (FM25V04B, 64 КБ, 2 байта адреса — уточните при необходимости)
        self.spi_panel = SpiPanel("FM25V04B", 64, 2, editor_provider=self.build_patched_bytes)
        root.addWidget(self.spi_panel)

        root.addStretch(1)

        self.btn_open.clicked.connect(self.open_file)
        self.btn_save.clicked.connect(self.save_copy)
        self.ed_new_x.textChanged.connect(self.update_auto_y)
        self.ed_ratio.textChanged.connect(self.update_auto_y)
        self.ratio_mode.currentIndexChanged.connect(self.on_ratio_mode_changed)

        self.rb_auto.toggled.connect(self.refresh_view)
        self.rb_1000.toggled.connect(self.refresh_view)
        self.rb_2000.toggled.connect(self.refresh_view)

        self.on_ratio_mode_changed()

    def _parse_float(self, s, default=float('nan')):
        s = ("" if s is None else str(s)).strip().replace(',', '.')
        if not s:
            return default
        try:
            return float(s)
        except ValueError:
            return default

    def chosen_factor(self, parsed: DecodedRecord) -> int:
        if self.rb_1000.isChecked():
            return 1000
        if self.rb_2000.isChecked():
            return 2000
        return detect_factor_from_raw(parsed.x_raw, parsed.y_raw)

    def on_ratio_mode_changed(self):
        mode = self.ratio_mode.currentIndex()
        if mode == 0:
            self.ed_ratio.setText(f"{RATIO_PROFILE_B:.10f}")
            self.ed_ratio.setEnabled(False)
        elif mode == 1:
            if self._file_ratio is not None and self._file_ratio > 0:
                self.ed_ratio.setText(f"{self._file_ratio:.10f}")
            else:
                self.ed_ratio.setText(f"{RATIO_PROFILE_B:.10f}")
            self.ed_ratio.setEnabled(False)
        else:
            if not self.ed_ratio.text().strip():
                self.ed_ratio.setText(f"{RATIO_PROFILE_B:.10f}")
            self.ed_ratio.setEnabled(True)
        self.update_auto_y()

    def _parse_ratio(self) -> float:
        ratio = self._parse_float(self.ed_ratio.text(), default=RATIO_PROFILE_B)
        if math.isnan(ratio) or ratio <= 0:
            ratio = RATIO_PROFILE_B
        return ratio

    def update_auto_y(self):
        x = self._parse_float(self.ed_new_x.text(), default=float('nan'))
        ratio = self._parse_ratio()
        if math.isnan(x):
            self.ed_new_y.clear()
            return
        self.ed_new_y.setText(f"{(x*ratio):.2f}")

    def open_file(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Открыть BIN", "", "BIN files (*.bin *.BIN);;All files (*.*)")
        if not path:
            return
        with open(path, "rb") as f:
            buf = f.read()
        if len(buf) < (DUP_OFF + REC_LEN):
            QtWidgets.QMessageBox.warning(self, "Ошибка", f"Файл слишком маленький: {len(buf)} байт. Нужно минимум {DUP_OFF + REC_LEN}.")
            return
        self.buf = bytearray(buf)
        self.path_in = path

        parsed = parse_record(self.buf, BASE_OFF)
        factor = self.chosen_factor(parsed)
        self._file_ratio = None
        if parsed.x_raw > 0:
            x = parsed.x_raw / float(factor)
            y = parsed.y_raw / float(factor)
            self._file_ratio = y / x if x > 0 else None

        self.btn_save.setEnabled(True)
        self.on_ratio_mode_changed()
        self.refresh_view()

    def refresh_view(self):
        if self.buf is None:
            self.lbl_status.setText("Файл не открыт")
            self.ed_cur_x.clear()
            self.ed_cur_y.clear()
            return

        parsed = parse_record(self.buf, BASE_OFF)
        factor = self.chosen_factor(parsed)
        x = parsed.x_raw / float(factor) if factor else 0.0
        y = parsed.y_raw / float(factor) if factor else 0.0

        self.ed_cur_x.setText(f"{x:.2f}")
        self.ed_cur_y.setText(f"{y:.2f}")

        parsed_dup = parse_record(self.buf, DUP_OFF)
        same = self.buf[BASE_OFF:BASE_OFF+REC_LEN] == self.buf[DUP_OFF:DUP_OFF+REC_LEN]

        fk = self._file_ratio if self._file_ratio is not None else float("nan")
        self.lbl_status.setText(
            f"Файл: {os.path.basename(self.path_in)} ({len(self.buf)} байт)\n"
            f"Контроль(0x0000): {'OK' if parsed.ok else 'FAIL'} (file=0x{parsed.crc_file:02X}, calc=0x{parsed.crc_calc:02X})\n"
            f"Масштаб: {factor} | Контроль(0x0100): {'OK' if parsed_dup.ok else 'FAIL'}; копия {'совпадает' if same else 'НЕ совпадает'}\n"
            f"ratio_file={fk:.10f}"
        )
        self.update_auto_y()

    def build_patched_bytes(self) -> Optional[bytearray]:
        """Собрать пропатченный буфер по текущему X (для записи в SPI)."""
        if self.buf is None:
            return None
        new_x = self._parse_float(self.ed_new_x.text(), default=float('nan'))
        if math.isnan(new_x):
            return None
        ratio = self._parse_ratio()
        new_y = new_x * ratio
        parsed = parse_record(self.buf, BASE_OFF)
        factor = self.chosen_factor(parsed)
        out_buf = bytearray(self.buf)
        patch_total_record(out_buf, new_x, new_y, factor)
        return out_buf

    def save_copy(self):
        if self.buf is None or self.path_in is None:
            return

        new_x = self._parse_float(self.ed_new_x.text(), default=float('nan'))
        if math.isnan(new_x):
            QtWidgets.QMessageBox.warning(self, 'Ошибка', 'Введите корректное значение X.')
            return

        ratio = self._parse_ratio()
        new_y = new_x * ratio
        self.ed_new_y.setText(f"{new_y:.2f}")

        parsed = parse_record(self.buf, BASE_OFF)
        factor = self.chosen_factor(parsed)

        out_buf = bytearray(self.buf)
        patch_total_record(out_buf, new_x, new_y, factor)

        base_dir = os.path.dirname(self.path_in)
        base_name = os.path.splitext(os.path.basename(self.path_in))[0]
        out_name = f"{base_name}__format_b__X{new_x:.2f}_Y{new_y:.2f}_scale{factor}.bin"
        out_path = os.path.join(base_dir, out_name)

        if os.path.abspath(out_path) == os.path.abspath(self.path_in):
            out_path = os.path.join(base_dir, f"{base_name}__format_b__updated_scale{factor}.bin")

        with open(out_path, "wb") as f:
            f.write(out_buf)

        QtWidgets.QMessageBox.information(self, "Готово", f"Сохранено:\n{out_path}")

# =============================
# TAB 3: FM25L02 — Формат C (two channels + total, four copies)
# =============================
# Binary layout for this format:
#   factor = 2000
#   Within one copy (0x2000-byte block):
#     Channel A     -> 0x0000, 0x0100
#     Channel B     -> 0x0011, 0x0111
#     Summary block -> 0x06A6 (duplicate at 0x06FB), order: TOTAL, A, B
#         TOTAL: +0x00 (0x06A6 / 0x06FB)
#         A:     +0x11 (0x06B7 / 0x070C)
#         B:     +0x22 (0x06C8 / 0x071D)
#   A 32 KiB file stores four copies at 0x0000, 0x2000, 0x4000, and 0x6000.
COPY_STRIDE = 0x2000
COPY_COUNT  = 4

# Offsets within one copy
FORMAT_C_CHANNEL_A_OFFSETS  = [0x0000, 0x0100]
FORMAT_C_CHANNEL_B_OFFSETS  = [0x0011, 0x0111]
FORMAT_C_TOTAL_OFFSETS = [0x06A6, 0x06FB]          # start of the summary block (TOTAL record)
FORMAT_C_BLOCK_CHANNEL_A   = 0x11                       # channel A offset inside the summary block
FORMAT_C_BLOCK_CHANNEL_B   = 0x22                       # channel B offset inside the summary block

FORMAT_C_FACTOR = 2000


def format_c_all_offsets(rec_off: int) -> list:
    """Return all physical addresses for rec_off across the four copies."""
    return [rec_off + m * COPY_STRIDE for m in range(COPY_COUNT)]


def format_c_set_x_keep_y(data: bytearray, offset: int, x: float, factor: int) -> bool:
    """Update only X while preserving the original Y and recalculating the checksum.
    If the displayed value (precision 0.01) is unchanged, leave the bytes untouched.
    Return True when the record was modified."""
    x_old_raw, y_old_raw, _ = read_record_raw(data, offset)
    # Compare at display precision (0.01): the file stores X more precisely (1/factor),
    # so compare rounded values instead of raw integers.
    if round(x_old_raw / factor, 2) == round(x, 2):
        return False  # displayed value is unchanged — leave the bytes untouched
    x_new_raw = int(round(x * factor))
    data[offset+OFF_X:offset+OFF_X+4] = encode_raw_u32_weird(x_new_raw)
    data[offset+OFF_Y:offset+OFF_Y+4] = encode_raw_u32_weird(y_old_raw)  # preserve Y
    data[offset+OFF_CRC] = crc_xor_16(bytes(data[offset:offset+16]))
    return True


class FormatCTab(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self._current_path = None

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        header = QtWidgets.QHBoxLayout()
        titles = QtWidgets.QVBoxLayout()
        h1 = QtWidgets.QLabel("FM25L02 — Формат C (два канала и итог, 4 копии)")
        h1.setObjectName("HeaderTitle")
        h2 = QtWidgets.QLabel("Задайте значения каналов A и B — итог рассчитывается автоматически и записывается во все копии.")
        h2.setObjectName("HeaderSub")
        titles.addWidget(h1)
        titles.addWidget(h2)
        header.addLayout(titles)
        header.addStretch(1)
        root.addLayout(header)

        file_box = QtWidgets.QGroupBox("Файл")
        file_l = QtWidgets.QGridLayout(file_box)
        file_l.setHorizontalSpacing(10)
        file_l.setVerticalSpacing(10)

        self.btn_open = QtWidgets.QPushButton("Открыть файл формата C")
        self.btn_open.clicked.connect(self.open_file)
        self.path_edit = QtWidgets.QLineEdit(); self.path_edit.setReadOnly(True)
        file_l.addWidget(self.btn_open, 0, 0)
        file_l.addWidget(self.path_edit, 0, 1, 1, 5)

        self.factor_box = QtWidgets.QComboBox()
        self.factor_box.addItems(["2000", "1000"])
        self.factor_box.setCurrentIndex(0)
        file_l.addWidget(QtWidgets.QLabel("Масштаб:"), 1, 0)
        file_l.addWidget(self.factor_box, 1, 1)
        root.addWidget(file_box)

        calc_box = QtWidgets.QGroupBox("Значения")
        form = QtWidgets.QGridLayout(calc_box)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(10)

        self.in_channel_a = QtWidgets.QDoubleSpinBox(); self._setup_spin(self.in_channel_a)
        self.in_channel_b = QtWidgets.QDoubleSpinBox(); self._setup_spin(self.in_channel_b)
        self.out_total = QtWidgets.QLineEdit(); self.out_total.setReadOnly(True)

        r = 0
        form.addWidget(QtWidgets.QLabel("Канал A:"), r, 0); form.addWidget(self.in_channel_a, r, 1)
        form.addWidget(QtWidgets.QLabel("Канал B:"), r, 2); form.addWidget(self.in_channel_b, r, 3)
        r += 1
        form.addWidget(QtWidgets.QLabel("Итог (A+B, авто):"), r, 0); form.addWidget(self.out_total, r, 1, 1, 3)
        root.addWidget(calc_box)

        self.lbl_status = QtWidgets.QLabel("Файл не выбран")
        self.lbl_status.setObjectName("StatusLabel")
        self.lbl_status.setWordWrap(True)
        root.addWidget(self.lbl_status)

        self.btn_apply = QtWidgets.QPushButton("Сформировать изменённую копию")
        self.btn_apply.setObjectName("PrimaryButton")
        self.btn_apply.clicked.connect(self.apply_patch)
        root.addWidget(self.btn_apply)

        # Прямая запись в SPI (FM25L02, 32 КБ, 2 байта адреса — уточните при необходимости)
        self.spi_panel = SpiPanel("FM25L02", 32, 2, editor_provider=self.build_patched_bytes)
        root.addWidget(self.spi_panel)

        root.addStretch(1)

        self.in_channel_a.valueChanged.connect(self.refresh_sum)
        self.in_channel_b.valueChanged.connect(self.refresh_sum)
        self.factor_box.currentIndexChanged.connect(self.reload_from_file)

    def _setup_spin(self, w: QtWidgets.QDoubleSpinBox):
        w.setDecimals(2)
        w.setRange(0, 999999999.99)
        w.setSingleStep(0.01)

    def factor(self) -> int:
        return int(self.factor_box.currentText())

    def refresh_sum(self):
        s = float(self.in_channel_a.value()) + float(self.in_channel_b.value())
        self.out_total.setText(f"{s:.2f}")

    def open_file(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Выберите файл формата C", "", "BIN (*.bin *.BIN);;All files (*.*)")
        if not path:
            return
        self._current_path = path
        self.path_edit.setText(path)
        self.reload_from_file()

    def reload_from_file(self):
        if not self._current_path:
            return
        try:
            data = open(self._current_path, "rb").read()
        except Exception as e:
            self.lbl_status.setText(f"Ошибка чтения: {e}")
            return

        factor = self.factor()
        channel_a_x, _, ok_a = read_record(data, FORMAT_C_CHANNEL_A_OFFSETS[0], factor)
        channel_b_x, _, ok_b = read_record(data, FORMAT_C_CHANNEL_B_OFFSETS[0], factor)
        sum_x, _, ok_total = read_record(data, FORMAT_C_TOTAL_OFFSETS[0], factor)

        self.in_channel_a.blockSignals(True); self.in_channel_b.blockSignals(True)
        self.in_channel_a.setValue(channel_a_x)
        self.in_channel_b.setValue(channel_b_x)
        self.in_channel_a.blockSignals(False); self.in_channel_b.blockSignals(False)
        self.refresh_sum()

        # Check that all copies match the base block
        copies_ok = all(
            data[m:m + COPY_STRIDE] == data[0:COPY_STRIDE]
            for m in (0x2000, 0x4000, 0x6000)
            if len(data) >= m + COPY_STRIDE
        )

        self.lbl_status.setText(
            f"Контроль: A={'OK' if ok_a else 'BAD'} | B={'OK' if ok_b else 'BAD'} | TOTAL={'OK' if ok_total else 'BAD'}\n"
            f"Из файла: A={channel_a_x:.2f}  B={channel_b_x:.2f}  TOTAL={sum_x:.2f}\n"
            f"Копии (0x2000/0x4000/0x6000) совпадают с базой: {'да' if copies_ok else 'НЕТ'}"
        )

    def build_patched_bytes(self) -> Optional[bytearray]:
        """Собрать пропатченный буфер по текущим A/B (для записи в SPI)."""
        if not self._current_path:
            return None
        try:
            data = bytearray(open(self._current_path, "rb").read())
        except Exception:
            return None

        factor = self.factor()
        channel_a = float(self.in_channel_a.value())
        channel_b = float(self.in_channel_b.value())
        s = channel_a + channel_b

        for m in range(COPY_COUNT):
            base = m * COPY_STRIDE
            if base + COPY_STRIDE > len(data):
                continue
            for off in FORMAT_C_CHANNEL_A_OFFSETS:
                format_c_set_x_keep_y(data, base + off, channel_a, factor)
            for off in FORMAT_C_CHANNEL_B_OFFSETS:
                format_c_set_x_keep_y(data, base + off, channel_b, factor)
            for blk in FORMAT_C_TOTAL_OFFSETS:
                format_c_set_x_keep_y(data, base + blk, s, factor)
                format_c_set_x_keep_y(data, base + blk + FORMAT_C_BLOCK_CHANNEL_A, channel_a, factor)
                format_c_set_x_keep_y(data, base + blk + FORMAT_C_BLOCK_CHANNEL_B, channel_b, factor)
        return data

    def apply_patch(self):
        if not self._current_path:
            self.lbl_status.setText("Сначала выбери файл")
            return
        try:
            data = bytearray(open(self._current_path, "rb").read())
        except Exception as e:
            self.lbl_status.setText(f"Ошибка чтения: {e}")
            return

        factor = self.factor()
        channel_a = float(self.in_channel_a.value())
        channel_b = float(self.in_channel_b.value())
        s  = channel_a + channel_b

        # Update only X, preserve Y, and leave unchanged records untouched.
        points = 0
        for m in range(COPY_COUNT):
            base = m * COPY_STRIDE
            if base + COPY_STRIDE > len(data):
                continue
            # Separate channel records
            for off in FORMAT_C_CHANNEL_A_OFFSETS:
                points += format_c_set_x_keep_y(data, base + off, channel_a, factor)
            for off in FORMAT_C_CHANNEL_B_OFFSETS:
                points += format_c_set_x_keep_y(data, base + off, channel_b, factor)
            # Summary blocks (TOTAL, A, B)
            for blk in FORMAT_C_TOTAL_OFFSETS:
                points += format_c_set_x_keep_y(data, base + blk,                s,  factor)
                points += format_c_set_x_keep_y(data, base + blk + FORMAT_C_BLOCK_CHANNEL_A, channel_a, factor)
                points += format_c_set_x_keep_y(data, base + blk + FORMAT_C_BLOCK_CHANNEL_B, channel_b, factor)

        base_dir = os.path.dirname(self._current_path)
        base_name = os.path.splitext(os.path.basename(self._current_path))[0]
        out_name = f"{base_name}__format_c__A_{channel_a:.2f}_B_{channel_b:.2f}_total_{s:.2f}_scale{factor}.bin"
        out_path = os.path.join(base_dir, out_name)
        try:
            with open(out_path, "wb") as f:
                f.write(data)
        except Exception as e:
            self.lbl_status.setText(f"Ошибка записи: {e}")
            return

        self.lbl_status.setText(f"Готово ({points} записей изменено): {out_path}")


# =============================
# Main window
# =============================
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Редактор дампов и прямая запись SPI")
        self.setMinimumSize(1060, 720)

        central = QtWidgets.QWidget()
        central_l = QtWidgets.QVBoxLayout(central)
        central_l.setContentsMargins(14, 14, 14, 14)
        central_l.setSpacing(10)

        tabs = QtWidgets.QTabWidget()
        tabs.setDocumentMode(True)

        self.tab_a = FormatATab()
        self.tab_b = FormatBTab()
        self.tab_c = FormatCTab()

        if TAB_ICON_FORMAT_A:
            tabs.addTab(self._scroll(self.tab_a), QtGui.QIcon(resource_path(TAB_ICON_FORMAT_A)), "MB85RS256")
        else:
            tabs.addTab(self._scroll(self.tab_a), "MB85RS256")

        if TAB_ICON_FORMAT_B:
            tabs.addTab(self._scroll(self.tab_b), QtGui.QIcon(resource_path(TAB_ICON_FORMAT_B)), "FM25V04B")
        else:
            tabs.addTab(self._scroll(self.tab_b), "FM25V04B")

        tabs.addTab(self._scroll(self.tab_c), "FM25L02")

        central_l.addWidget(tabs)
        self.setCentralWidget(central)

    def _scroll(self, widget: QtWidgets.QWidget) -> QtWidgets.QScrollArea:
        area = QtWidgets.QScrollArea()
        area.setWidgetResizable(True)
        area.setWidget(widget)
        return area

    def closeEvent(self, event: QtGui.QCloseEvent):
        for tab in (self.tab_a, self.tab_b, self.tab_c):
            panel = getattr(tab, "spi_panel", None)
            if panel is not None:
                panel.shutdown()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    apply_pretty_ui(app)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
