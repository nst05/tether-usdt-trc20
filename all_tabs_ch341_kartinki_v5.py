# -*- coding: utf-8 -*-
"""
ENERGOMERA — общий GUI с вкладками для 5 программаторов через CH341:
  1) 201_drob_random (24C16, целая + случайная дробная, патч дампа)
  2) c101            (24C04, GRAND STM8L052C6, патч дампа)
  3) new_1F          (AT24C1024, 1F, патч 0x0000..0x01FF)
  4) new_3F          (AT24C1024, 3F, патч 0x0000..0x01FF)
  5) ce6803b_p32     (24C04, патч дампа)

Картинки во вкладках при клике открываются в полном размере.

Оформление (цвета, размер окна, шрифт, заставка) настраивается кнопкой ⚙
в правом верхнем углу и применяется сразу, без перезапуска. Настройки
хранятся в settings_all_tabs.json рядом с программой.
"""

import os
import sys
import time
import random
from math import floor as floor_3F

from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import (
    Qt, QRectF, QPropertyAnimation, QEasingCurve,
    QParallelAnimationGroup, QSequentialAnimationGroup, pyqtSignal, pyqtProperty,
)
from PyQt5.QtGui import (
    QColor, QPainter, QPixmap, QIcon, QLinearGradient, QBrush, QFont,
)
from PyQt5.QtWidgets import QSizePolicy


# =====================================================================
#  Картинки во вкладках
# =====================================================================

IMG_201_IN_TAB    = "201.png"
IMG_C101_IN_TAB   = "c101_old2.jpg"
IMG_1F_IN_TAB     = "1F_NEW.png"
IMG_3F_IN_TAB     = "3F_NEW.png"
IMG_CE6803_IN_TAB = "3F_old.jpg"

TAB_ICON_201    = ""
TAB_ICON_C101   = ""
TAB_ICON_1F     = ""
TAB_ICON_3F     = ""
TAB_ICON_CE6803 = ""

IMG_HEIGHT = 150


# =====================================================================
#  Пути, ресурсы и драйвер CH341
# =====================================================================

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
    BUNDLE_DIR = getattr(sys, "_MEIPASS", BASE_DIR)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR = BASE_DIR


def resource_path(relative_path):
    """Путь к упакованному ресурсу (картинке) — в .exe и при запуске из исходника."""
    return os.path.join(BUNDLE_DIR, relative_path)


def _setup_ch341_dll():
    """Передать i2cpy абсолютный путь к CH341 DLL.

    Начиная с Python 3.8 ctypes ищет DLL по имени только в системных папках,
    в папке программы и в каталогах из os.add_dll_directory(); PATH больше не
    используется, поэтому одного добавления _MEIPASS в PATH для .exe мало.
    """
    os.environ["PATH"] = BUNDLE_DIR + os.pathsep + os.environ.get("PATH", "")
    if sys.platform != "win32":
        return
    dll_name = "CH341DLLA64.dll" if sys.maxsize > 2 ** 31 - 1 else "CH341DLL.dll"
    for folder in (BUNDLE_DIR, BASE_DIR):
        candidate = os.path.join(folder, dll_name)
        if os.path.isfile(candidate):
            os.environ.setdefault("CH341DLL", candidate)
            try:
                os.add_dll_directory(folder)
            except (AttributeError, OSError):
                pass
            return


_setup_ch341_dll()

try:
    from i2cpy import I2C
except ImportError:
    I2C = None


# =====================================================================
#  Настройки и тема (общие для всех вкладок)
# =====================================================================

import json

LIGHT_COLORS = {
    "bg": "#f4f6fb",
    "card": "#ffffff",
    "card_border": "#e2e6f0",
    "title": "#1f2430",
    "field_label": "#4a5170",
    "input_bg": "#f7f8fc",
    "input_border": "#d7dcec",
    "accent": "#4c6ef5",
    "accent_hover": "#5c7cfa",
    "accent_pressed": "#3b5bdb",
    "success": "#2f9e44",
    "error": "#e03131",
}

DARK_COLORS = {
    "bg": "#12141c",
    "card": "#1c1f2b",
    "card_border": "#2c3040",
    "title": "#eef1f8",
    "field_label": "#9aa3bf",
    "input_bg": "#252938",
    "input_border": "#39405a",
    "accent": "#4c6ef5",
    "accent_hover": "#5c7cfa",
    "accent_pressed": "#3b5bdb",
    "success": "#51cf66",
    "error": "#ff6b6b",
}

COLOR_FIELDS = [
    ("bg", "Фон окна"),
    ("card", "Фон панели"),
    ("card_border", "Рамки"),
    ("title", "Текст / заголовки"),
    ("field_label", "Подписи полей"),
    ("input_bg", "Фон полей ввода"),
    ("input_border", "Рамка полей ввода"),
    ("accent", "Акцент (кнопки, вкладки)"),
    ("accent_hover", "Акцент (наведение)"),
    ("accent_pressed", "Акцент (нажатие)"),
    ("success", "Текст успеха"),
    ("error", "Текст ошибки"),
]

DEFAULT_SETTINGS = {
    "colors": dict(LIGHT_COLORS),
    "window": {
        "width": 760,
        "height": 560,
        "font_scale": 100,
        "always_on_top": False,
        "splash": True,
    },
}

SETTINGS_PATH = os.path.join(BASE_DIR, "settings_all_tabs.json")
LAST_SAVE_ERROR = None


def copy_settings(settings):
    return json.loads(json.dumps(settings))


def load_settings():
    settings = copy_settings(DEFAULT_SETTINGS)
    if not os.path.isfile(SETTINGS_PATH):
        return settings
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        for section in ("colors", "window"):
            if isinstance(data.get(section), dict):
                settings[section].update(data[section])
    except Exception:
        pass
    return settings


def save_settings(settings):
    """Атомарная запись: .tmp + переименование, чтобы не остался обрезанный файл."""
    global LAST_SAVE_ERROR
    tmp_path = SETTINGS_PATH + ".tmp"
    try:
        folder = os.path.dirname(SETTINGS_PATH)
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, SETTINGS_PATH)
        LAST_SAVE_ERROR = None
        return True
    except Exception as e:
        LAST_SAVE_ERROR = "{}: {}".format(type(e).__name__, e)
        try:
            if os.path.isfile(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        return False


def readable_text_color(hex_color):
    c = QColor(hex_color)
    luma = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
    return "#000000" if luma > 140 else "#ffffff"


def build_qss(colors, font_scale):
    """Единый QSS для всего окна с вкладками.

    Правила адресованы конкретным типам/objectName и ставятся на само окно —
    ни одно не содержит слепого 'QWidget { background }', который протёк бы в
    диалоги и палитру выбора цвета.
    """
    def s(px):
        return max(1, round(px * font_scale / 100))

    c = colors
    return f"""
    QWidget#tabPage {{
        background-color: {c['bg']};
        font-family: 'Segoe UI', 'Arial';
        color: {c['title']};
    }}
    QLabel {{
        color: {c['title']};
        font-size: {s(13)}px;
    }}
    #titleLabel {{
        color: {c['title']};
        font-size: {s(14)}px;
        font-weight: 600;
    }}
    QLineEdit, QDoubleSpinBox, QSpinBox, QTextEdit {{
        background-color: {c['input_bg']};
        color: {c['title']};
        border: 1px solid {c['input_border']};
        border-radius: 8px;
        padding: 6px 8px;
        font-size: {s(14)}px;
        selection-background-color: {c['accent']};
        selection-color: #ffffff;
    }}
    QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QTextEdit:focus {{
        border: 1px solid {c['accent']};
    }}
    QPushButton {{
        background-color: {c['accent']};
        color: #ffffff;
        border: none;
        border-radius: 9px;
        padding: 8px 14px;
        font-size: {s(13)}px;
        font-weight: 600;
    }}
    QPushButton:hover  {{ background-color: {c['accent_hover']}; }}
    QPushButton:pressed {{ background-color: {c['accent_pressed']}; }}
    QPushButton:disabled {{ background-color: {c['input_border']}; color: {c['card']}; }}
    #settingsButton {{
        background-color: transparent;
        border: 1px solid {c['card_border']};
        border-radius: 9px;
        color: {c['field_label']};
        font-size: {s(16)}px;
        padding: 2px;
    }}
    #settingsButton:hover {{
        background-color: {c['input_bg']};
        border: 1px solid {c['accent']};
    }}
    QProgressBar {{
        background-color: {c['input_bg']};
        border: 1px solid {c['input_border']};
        border-radius: 8px;
        text-align: center;
        color: {c['title']};
        font-size: {s(12)}px;
        min-height: 22px;
    }}
    QProgressBar::chunk {{
        background-color: {c['accent']};
        border-radius: 7px;
    }}
    QTabWidget::pane {{
        border: 1px solid {c['card_border']};
        border-radius: 10px;
        background-color: {c['card']};
        top: -1px;
    }}
    QTabBar::tab {{
        background-color: {c['input_bg']};
        color: {c['field_label']};
        border: 1px solid {c['card_border']};
        border-bottom: none;
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
        padding: 8px 16px;
        margin-right: 2px;
        font-size: {s(13)}px;
        font-weight: 600;
    }}
    QTabBar::tab:selected {{
        background-color: {c['accent']};
        color: #ffffff;
    }}
    QTabBar::tab:hover:!selected {{
        background-color: {c['card']};
        color: {c['title']};
    }}
    """


def repolish(root):
    for widget in [root] + root.findChildren(QtWidgets.QWidget):
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)
        widget.update()


# =====================================================================
#  Логотип и заставка
# =====================================================================

LOGO_TOP = "#5c7cfa"
LOGO_BOTTOM = "#3b5bdb"


def paint_logo(painter, size):
    """Микросхема с точками как на игральной кости: память + случайность.
    Рисуется кодом, поэтому не зависит от внешних файлов и чёткая в любом размере."""
    sz = float(size)
    compact = size < 40
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(Qt.NoPen)

    gradient = QLinearGradient(0, 0, sz, sz)
    gradient.setColorAt(0.0, QColor(LOGO_TOP))
    gradient.setColorAt(1.0, QColor(LOGO_BOTTOM))
    painter.setBrush(QBrush(gradient))
    painter.drawRoundedRect(QRectF(0, 0, sz, sz), sz * 0.22, sz * 0.22)

    painter.setBrush(QColor("#ffffff"))
    if compact:
        margin, dot_r, dots = 0.21, 0.070, (0.355, 0.50, 0.645)
    else:
        margin, dot_r, dots = 0.26, 0.047, (0.385, 0.50, 0.615)
        pin_w, pin_h = sz * 0.11, sz * 0.055
        for center in (0.37, 0.50, 0.63):
            y = sz * center - pin_h / 2
            painter.drawRoundedRect(QRectF(sz * 0.17, y, pin_w, pin_h), pin_h / 2, pin_h / 2)
            painter.drawRoundedRect(QRectF(sz * 0.72, y, pin_w, pin_h), pin_h / 2, pin_h / 2)

    side = sz * (1 - 2 * margin)
    painter.drawRoundedRect(QRectF(sz * margin, sz * margin, side, side), sz * 0.08, sz * 0.08)

    painter.setBrush(QColor(LOGO_BOTTOM))
    r = sz * dot_r
    for center in dots:
        painter.drawEllipse(QRectF(center * sz - r, center * sz - r, 2 * r, 2 * r))


def logo_pixmap(size):
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    paint_logo(painter, size)
    painter.end()
    return pixmap


def app_icon():
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(logo_pixmap(size))
    return icon


class SplashScreen(QtWidgets.QWidget):
    """Заставка запуска: логотип проявляется, полоса заполняется, окно гаснет.
    Клик пропускает анимацию."""

    WIDTH = 460
    HEIGHT = 260

    def __init__(self, colors):
        super().__init__(None, Qt.FramelessWindowHint | Qt.SplashScreen)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.colors = colors
        self._progress = 0.0
        self._animation = None
        self._on_finished = None
        self._finished = False
        self._center_on_screen()

    def _center_on_screen(self):
        screen = QtWidgets.QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        self.move(area.center().x() - self.WIDTH // 2,
                  area.center().y() - self.HEIGHT // 2)

    def get_progress(self):
        return self._progress

    def set_progress(self, value):
        self._progress = value
        self.update()

    progress = pyqtProperty(float, fget=get_progress, fset=set_progress)

    def paintEvent(self, event):
        c = self.colors
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(c["card"]))
        painter.drawRoundedRect(QRectF(0, 0, self.WIDTH, self.HEIGHT), 18, 18)

        logo_size = 96
        scale = 0.86 + 0.14 * self._progress
        drawn = logo_size * scale
        painter.save()
        painter.translate((self.WIDTH - drawn) / 2, 30 + (logo_size - drawn) / 2)
        painter.scale(scale, scale)
        paint_logo(painter, logo_size)
        painter.restore()

        painter.setPen(QColor(c["title"]))
        painter.setFont(QFont("Segoe UI", 16, QFont.Bold))
        painter.drawText(QRectF(0, 140, self.WIDTH, 28), Qt.AlignCenter, "ENERGOMERA")

        painter.setPen(QColor(c["field_label"]))
        painter.setFont(QFont("Segoe UI", 9))
        painter.drawText(QRectF(0, 168, self.WIDTH, 22), Qt.AlignCenter,
                         "Программаторы CH341 · все вкладки")

        track = QRectF(80, 208, self.WIDTH - 160, 6)
        painter.setBrush(QColor(c["input_border"]))
        painter.drawRoundedRect(track, 3, 3)
        if self._progress > 0:
            fill = QRectF(track.x(), track.y(), track.width() * self._progress, track.height())
            painter.setBrush(QColor(c["accent"]))
            painter.drawRoundedRect(fill, 3, 3)
        painter.end()

    def start(self, on_finished):
        self._on_finished = on_finished
        self.setWindowOpacity(0.0)
        self.show()

        fade_in = QPropertyAnimation(self, b"windowOpacity", self)
        fade_in.setDuration(260)
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(1.0)

        sweep = QPropertyAnimation(self, b"progress", self)
        sweep.setDuration(950)
        sweep.setStartValue(0.0)
        sweep.setEndValue(1.0)
        sweep.setEasingCurve(QEasingCurve.OutCubic)

        appear = QParallelAnimationGroup()
        appear.addAnimation(fade_in)
        appear.addAnimation(sweep)

        fade_out = QPropertyAnimation(self, b"windowOpacity", self)
        fade_out.setDuration(280)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)
        fade_out.setEasingCurve(QEasingCurve.InCubic)

        sequence = QSequentialAnimationGroup(self)
        sequence.addAnimation(appear)
        sequence.addPause(200)
        sequence.addAnimation(fade_out)
        sequence.finished.connect(self.finish)
        self._animation = sequence
        sequence.start()

    def mousePressEvent(self, event):
        self.finish()

    def finish(self):
        if self._finished:
            return
        self._finished = True
        if self._animation is not None:
            self._animation.stop()
        self.close()
        if self._on_finished is not None:
            self._on_finished()


# =====================================================================
#  Картинки во вкладках (клик — просмотр в полном размере)
# =====================================================================

class ClickableImageLabel(QtWidgets.QLabel):
    def __init__(self, img_rel_path, parent=None):
        super().__init__(parent)
        self.rel_path = img_rel_path
        self.original_pixmap = None
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMaximumHeight(IMG_HEIGHT)

        if img_rel_path:
            pix = QtGui.QPixmap(resource_path(img_rel_path))
            if not pix.isNull():
                self.original_pixmap = pix
                self.setPixmap(pix.scaledToHeight(IMG_HEIGHT, QtCore.Qt.SmoothTransformation))
                self.setCursor(QtCore.Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        if self.original_pixmap is None:
            return
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Просмотр изображения")
        vbox = QtWidgets.QVBoxLayout(dlg)
        scroll = QtWidgets.QScrollArea(dlg)
        scroll.setWidgetResizable(True)
        vbox.addWidget(scroll)
        lbl = QtWidgets.QLabel()
        lbl.setAlignment(QtCore.Qt.AlignCenter)
        lbl.setPixmap(self.original_pixmap)
        scroll.setWidget(lbl)
        dlg.resize(min(self.original_pixmap.width() + 40, 1200),
                   min(self.original_pixmap.height() + 60, 800))
        dlg.exec_()


def make_tab_image_label(img_path):
    if not img_path:
        lbl = QtWidgets.QLabel()
        lbl.setFixedHeight(0)
        return lbl
    return ClickableImageLabel(img_path)


# =====================================================================
#  TAB 1: 201_drob_random (24C16, патч дампа)
# =====================================================================

def to_bcd_bytes_201(value):
    digits = list(str(value).rjust(6, '0'))
    d1 = int(digits[0]) * 16 + int(digits[1])
    d2 = int(digits[2]) * 16 + int(digits[3])
    d3 = int(digits[4]) * 16 + int(digits[5])
    return bytes([d1, d2, d3])


def crc16_ibm_201(data):
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def hund_to_bcd_201(hund):
    return ((hund // 10) << 4) | (hund % 10)


class Tab201Random(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.i2c = None
        self.program_counter = 0
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle('201 RANDOM')

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.addWidget(make_tab_image_label(IMG_201_IN_TAB))

        controls_layout = QtWidgets.QVBoxLayout()

        form = QtWidgets.QFormLayout()
        self.label_int = QtWidgets.QLabel("Целая часть (например, 575):", self)
        self.value_input = QtWidgets.QLineEdit(self)
        form.addRow(self.label_int, self.value_input)
        controls_layout.addLayout(form)

        self.btn_program_verify = QtWidgets.QPushButton(
            "Считать → изменить показания → записать → проверить", self)
        self.btn_program_verify.clicked.connect(self.on_program_and_verify)
        controls_layout.addWidget(self.btn_program_verify)

        self.progress = QtWidgets.QProgressBar(self)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        controls_layout.addWidget(self.progress)

        self.counter_label = QtWidgets.QLabel(f"Счётчик прошивок: {self.program_counter}", self)
        controls_layout.addWidget(self.counter_label)

        self.status_label = QtWidgets.QLabel("", self)
        self.status_label.setWordWrap(True)
        controls_layout.addWidget(self.status_label)

        controls_layout.addStretch(1)
        main_layout.addLayout(controls_layout)

    def _get_int_part(self):
        try:
            int_part = int(self.value_input.text())
        except ValueError:
            self.status_label.setText("Ошибка! Введите корректное целое число.")
            return None
        return int_part

    def blocks_match(self, golden, actual):
        if len(golden) < 0x56 or len(actual) < 0x56:
            return False
        for addr in range(0x30, 0x36):
            if golden[addr] != actual[addr]:
                return False
        for addr in range(0x50, 0x56):
            if golden[addr] != actual[addr]:
                return False
        return True

    def reset_i2c(self):
        if self.i2c is not None:
            try:
                if hasattr(self.i2c, "close"):
                    self.i2c.close()
            except Exception:
                pass
        self.i2c = None

    def on_program_and_verify(self):
        self.progress.setValue(0)
        self.status_label.setText("")
        self.reset_i2c()

        int_part = self._get_int_part()
        if int_part is None:
            return

        frac_hund = random.randint(0, 99)

        original = self.read_eeprom_with_ch341()
        if original is None:
            return
        if len(original) != 2048:
            self.status_label.setText("Ошибка: размер считанной 24C16 != 2048 байт.")
            return

        if all(b == 0xFF for b in original):
            self.status_label.setText("Ошибка: всё 0xFF — память не подключена/не отвечает.")
            return
        if all(b == 0x00 for b in original):
            self.status_label.setText("Ошибка: всё 0x00 — проблемы с подключением.")
            return

        patched = self.patch_eeprom(original, int_part, frac_hund)

        if not self.program_eeprom_with_ch341(patched):
            return

        read_back = self.read_eeprom_with_ch341()
        if read_back is None:
            return
        if len(read_back) != len(patched):
            self.status_label.setText("Ошибка: размер данных после записи не совпадает.")
            return

        if all(b == 0xFF for b in read_back):
            self.status_label.setText("Ошибка: всё 0xFF после записи — что-то не так.")
            return
        if all(b == 0x00 for b in read_back):
            self.status_label.setText("Ошибка: всё 0x00 после записи — что-то не так.")
            return

        if self.blocks_match(patched, read_back):
            self.program_counter += 1
            self.counter_label.setText(f"Счётчик прошивок: {self.program_counter}")
            self.status_label.setText(
                f"Успех: целая часть {int_part}, дробная {str(frac_hund).rjust(2,'0')} записана корректно.")
            self.progress.setValue(100)
        else:
            self.status_label.setText(
                "Ошибка: целая часть (BCD/инверсии) в блоках 0x30/0x50 не совпадает с ожидаемой.")

    def patch_eeprom(self, original, int_value, frac_hund):
        eeprom = bytearray(original)

        bcd = to_bcd_bytes_201(int_value)
        inv = bytes([0xFF - b for b in bcd])
        crc6 = crc16_ibm_201(bcd + inv)
        frame_int = bcd + inv + bytes([crc6 & 0xFF, (crc6 >> 8) & 0xFF])

        frac_bcd = hund_to_bcd_201(frac_hund)
        first6 = bytes([0x03, 0x00, frac_bcd, 0xFC, 0xFF, (0xFF - frac_bcd) & 0xFF])
        crc_frac = crc16_ibm_201(first6)
        frame_frac = first6 + bytes([crc_frac & 0xFF, (crc_frac >> 8) & 0xFF])

        eeprom[0x20:0x28] = frame_frac
        eeprom[0x33:0x36] = inv
        eeprom[0x30:0x38] = frame_int
        eeprom[0x50:0x58] = frame_int
        return bytes(eeprom)

    def ensure_i2c(self):
        if I2C is None:
            self.status_label.setText(
                "Ошибка: не установлена библиотека i2cpy.\nУстанови: pip install i2cpy")
            return None
        if self.i2c is None:
            try:
                self.i2c = I2C(driver="ch341")
            except Exception as e:
                self.status_label.setText(f"Ошибка инициализации CH341: {e}")
                return None
        return self.i2c

    def program_eeprom_with_ch341(self, eeprom):
        i2c = self.ensure_i2c()
        if i2c is None:
            return False
        page_size = 16
        total = len(eeprom)
        addr = 0
        try:
            for addr in range(0, total, page_size):
                chunk = bytes(eeprom[addr:addr + page_size])
                dev_addr = 0x50 | ((addr >> 8) & 0x07)
                i2c.writeto_mem(dev_addr, addr & 0xFF, chunk, addrsize=8)
                self.progress.setValue(min(int((addr + page_size) * 100 / total), 100))
                QtWidgets.QApplication.processEvents()
                time.sleep(0.01)
        except Exception as e:
            self.status_label.setText(f"Ошибка записи EEPROM через CH341 при адресе 0x{addr:04X}: {e}")
            self.reset_i2c()
            return False
        return True

    def read_eeprom_with_ch341(self):
        i2c = self.ensure_i2c()
        if i2c is None:
            return None
        page_size = 16
        total = 2048
        data = bytearray(total)
        addr = 0
        try:
            for addr in range(0, total, page_size):
                dev_addr = 0x50 | ((addr >> 8) & 0x07)
                data[addr:addr + page_size] = i2c.readfrom_mem(dev_addr, addr & 0xFF, page_size, addrsize=8)
                self.progress.setValue(min(int((addr + page_size) * 100 / total), 100))
                QtWidgets.QApplication.processEvents()
                time.sleep(0.001)
        except Exception as e:
            self.status_label.setText(f"Ошибка чтения EEPROM через CH341 при адресе 0x{addr:04X}: {e}")
            self.reset_i2c()
            return None
        return bytes(data)


# =====================================================================
#  TAB 2: c101 (24C04, патч кадров F8/FC)
# =====================================================================

POLY_C101 = 0xB5
INIT_C101 = 0xFF
SCALE_C101 = 2.56
FILE_SIZE_C101 = 0x200
HEAD1_C101 = 0x00F8
HEAD2_C101 = 0x00FC


def crc8_b5_c101(data):
    crc = INIT_C101
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ POLY_C101) & 0xFF if (crc & 0x80) else ((crc << 1) & 0xFF)
    return crc


def raw_to_3bytes_be_c101(raw):
    return bytes([(raw >> 16) & 0xFF, (raw >> 8) & 0xFF, raw & 0xFF])


def build_frame_c101(reading):
    raw = int(round(reading / SCALE_C101))
    if not (0 <= raw <= 0xFFFFFF):
        raise ValueError("RAW вне диапазона 0..0xFFFFFF")
    data3 = raw_to_3bytes_be_c101(raw)
    crc = crc8_b5_c101(data3)
    return data3 + bytes([crc]), raw


def patch_blob_c101(original, reading):
    frame, raw = build_frame_c101(reading)
    blob = bytearray(original)
    blob[HEAD1_C101:HEAD1_C101 + 4] = frame
    blob[HEAD2_C101:HEAD2_C101 + 4] = frame
    return bytes(blob), frame, raw


class TabC101(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("energomera c101")
        self.i2c = None
        self.program_counter = 0
        self.build_ui()

    def build_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.addWidget(make_tab_image_label(IMG_C101_IN_TAB))

        controls_layout = QtWidgets.QVBoxLayout()

        self.reading = QtWidgets.QDoubleSpinBox()
        self.reading.setDecimals(2)
        self.reading.setRange(0, 1_000_000_000)
        self.reading.setValue(3558.00)

        self.btn = QtWidgets.QPushButton("Считать → изменить кадры F8/FC → записать → проверить")
        self.btn.clicked.connect(self.make_and_program)

        self.info = QtWidgets.QTextEdit()
        self.info.setReadOnly(True)
        self.info.setFixedHeight(100)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)

        self.status = QtWidgets.QLabel("")
        self.status.setWordWrap(True)
        self.counter_label = QtWidgets.QLabel("Счётчик прошивок: 0")

        form = QtWidgets.QFormLayout()
        form.addRow("Показание:", self.reading)

        controls_layout.addLayout(form)
        controls_layout.addWidget(self.btn)
        controls_layout.addWidget(self.info)
        controls_layout.addWidget(self.progress)
        controls_layout.addWidget(self.status)
        controls_layout.addWidget(self.counter_label)
        controls_layout.addStretch(1)
        main_layout.addLayout(controls_layout)

    def reset_i2c(self):
        if self.i2c is not None:
            try:
                if hasattr(self.i2c, "close"):
                    self.i2c.close()
            except Exception:
                pass
        self.i2c = None

    def ensure_i2c(self):
        if I2C is None:
            self.status.setText("Ошибка: не установлена библиотека i2cpy (pip install i2cpy).")
        if self.i2c is None and I2C is not None:
            try:
                self.i2c = I2C(driver="ch341")
            except Exception as e:
                self.status.setText(f"Ошибка инициализации CH341: {e}")
                self.i2c = None
        return self.i2c

    def program_eeprom_with_ch341(self, blob):
        i2c = self.ensure_i2c()
        if i2c is None:
            return False
        page_size = 16
        total = FILE_SIZE_C101
        addr = 0
        try:
            for addr in range(0, total, page_size):
                chunk = bytes(blob[addr:addr + page_size])
                dev_addr = 0x50 | ((addr >> 8) & 0x01)
                i2c.writeto_mem(dev_addr, addr & 0xFF, chunk, addrsize=8)
                self.progress.setValue(min(int((addr + page_size) * 100 / total), 100))
                QtWidgets.QApplication.processEvents()
                time.sleep(0.01)
        except Exception as e:
            self.status.setText(f"Ошибка записи EEPROM: {e}")
            self.reset_i2c()
            return False
        return True

    def read_eeprom_with_ch341(self):
        i2c = self.ensure_i2c()
        if i2c is None:
            return None
        page_size = 16
        total = FILE_SIZE_C101
        data = bytearray(total)
        addr = 0
        try:
            for addr in range(0, total, page_size):
                dev_addr = 0x50 | ((addr >> 8) & 0x01)
                data[addr:addr + page_size] = i2c.readfrom_mem(dev_addr, addr & 0xFF, page_size, addrsize=8)
                self.progress.setValue(min(int((addr + page_size) * 100 / total), 100))
                QtWidgets.QApplication.processEvents()
                time.sleep(0.005)
        except Exception as e:
            self.status.setText(f"Ошибка чтения EEPROM: {e}")
            self.reset_i2c()
            return None
        return bytes(data)

    def make_and_program(self):
        self.progress.setValue(0)
        self.status.setText("")
        self.reset_i2c()

        try:
            reading = float(self.reading.value())
        except Exception:
            self.status.setText("Ошибка: некорректное показание.")
            return

        original = self.read_eeprom_with_ch341()
        if original is None:
            return
        if len(original) != FILE_SIZE_C101:
            self.status.setText("EEPROM: размер считанных данных не 512 байт.")
            return

        if all(b == 0xFF for b in original):
            self.status.setText("EEPROM: всё 0xFF (нет связи с микросхемой).")
            return
        if all(b == 0x00 for b in original):
            self.status.setText("EEPROM: всё 0x00 (проблемы с подключением).")
            return

        try:
            blob, frame, raw = patch_blob_c101(original, reading)
        except Exception as e:
            self.status.setText(f"Ошибка формирования кадра: {e}")
            return

        info_text = (
            "Дамп считан, подготовлен патч.\n"
            f"Размер: {len(blob)} (0x{len(blob):X})\n"
            f"Кадр @0x00F8/0x00FC: {' '.join(f'{b:02X}' for b in frame)}")

        if not self.program_eeprom_with_ch341(blob):
            self.info.setPlainText(info_text + "\n\nEEPROM: ошибка записи.")
            return

        read_back = self.read_eeprom_with_ch341()
        if read_back is None:
            self.info.setPlainText(info_text + "\n\nEEPROM: ошибка повторного чтения.")
            return

        if len(read_back) != FILE_SIZE_C101:
            self.status.setText("EEPROM: размер считанных данных после записи не 512 байт.")
            self.info.setPlainText(info_text + "\n\nEEPROM: размер не совпадает.")
            return

        if all(b == 0xFF for b in read_back):
            self.status.setText("EEPROM: всё 0xFF после записи.")
            self.info.setPlainText(info_text + "\n\nEEPROM: всё 0xFF.")
            return
        if all(b == 0x00 for b in read_back):
            self.status.setText("EEPROM: всё 0x00 после записи.")
            self.info.setPlainText(info_text + "\n\nEEPROM: всё 0x00.")
            return

        if read_back == blob:
            self.program_counter += 1
            self.counter_label.setText(f"Счётчик прошивок: {self.program_counter}")
            self.status.setText("EEPROM: запись подтверждена (весь дамп совпал).")
            self.progress.setValue(100)
            self.info.setPlainText(info_text + "\n\nEEPROM: запись подтверждена.")
        else:
            self.status.setText("EEPROM: данные отличаются (есть несовпадения).")
            self.info.setPlainText(info_text + "\n\nEEPROM: данные отличаются от дампа с патчем.")


# =====================================================================
#  TAB 3: new_1F (AT24C1024, патч первых 0x200)
# =====================================================================

PROGRAM_NAME_1F = "energomera_new_1F_NEW_CH341"
ADDRS_DATA_1F = [0x00F8, 0x00FC]
ADDRS_STATIC_1F = 0x01F0
STATIC_PATTERN_1F = [0x00, 0x00, 0x00, 0x00, 0x00]
IMAGE_SIZE_1F = 0x0200
POLY_1F = 0x1021
INIT_1F = 0xFFFF


def crc_low_ccitt_false_1F(d0, d1, d2):
    crc = INIT_1F
    for b in (d0 & 0xFF, d1 & 0xFF, d2 & 0xFF):
        crc ^= (b & 0xFF) << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ POLY_1F) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc & 0xFF


def build_frame_1F(value):
    N = int(round(value / 2.56))
    if not (0 <= N <= 0xFFFFFF):
        raise ValueError(f"N={N} вне 24-бит (0..0xFFFFFF)")
    d0 = (N >> 0) & 0xFF
    d1 = (N >> 8) & 0xFF
    d2 = (N >> 16) & 0xFF
    crc = crc_low_ccitt_false_1F(d0, d1, d2)
    return N, (d0, d1, d2, crc)


def patch_image_1F(original, value):
    if len(original) < IMAGE_SIZE_1F:
        raise ValueError("Размер дампа меньше 0x200 байт, нельзя патчить 1F.")
    N, frame = build_frame_1F(value)
    d0, d1, d2, crc = frame
    image = bytearray(original[:IMAGE_SIZE_1F])
    for a in ADDRS_DATA_1F:
        image[a + 0] = d0
        image[a + 1] = d1
        image[a + 2] = d2
        image[a + 3] = crc
    for i, b in enumerate(STATIC_PATTERN_1F):
        image[ADDRS_STATIC_1F + i] = b & 0xFF
    return bytes(image), N, frame


class Tab1F(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.i2c = None
        self.program_counter = 0
        self.setWindowTitle(PROGRAM_NAME_1F)
        self.build_ui()

    def build_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.addWidget(make_tab_image_label(IMG_1F_IN_TAB))

        controls_layout = QtWidgets.QVBoxLayout()

        title = QtWidgets.QLabel("AT24C1024 1F: считать 0x0000..0x01FF → патч кадра → записать → проверить")
        title.setObjectName("titleLabel")
        title.setWordWrap(True)
        title.setAlignment(QtCore.Qt.AlignCenter)
        controls_layout.addWidget(title)

        form = QtWidgets.QFormLayout()
        self.ed_value = QtWidgets.QLineEdit("2941.44")
        self.ed_value.setAlignment(QtCore.Qt.AlignCenter)
        self.ed_value.setPlaceholderText("например: 2941.44 (точка или запятая)")
        form.addRow("Показание:", self.ed_value)
        controls_layout.addLayout(form)

        self.btn = QtWidgets.QPushButton("Считать → изменить → записать → проверить")
        self.btn.clicked.connect(self.on_program_and_verify)
        controls_layout.addWidget(self.btn)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        controls_layout.addWidget(self.progress)

        self.counter_label = QtWidgets.QLabel("Счётчик прошивок: 0")
        controls_layout.addWidget(self.counter_label)

        self.status_label = QtWidgets.QLabel("")
        self.status_label.setWordWrap(True)
        controls_layout.addWidget(self.status_label)

        controls_layout.addStretch(1)
        main_layout.addLayout(controls_layout)

    def reset_i2c(self):
        if self.i2c is not None:
            try:
                if hasattr(self.i2c, "close"):
                    self.i2c.close()
            except Exception:
                pass
        self.i2c = None

    def ensure_i2c(self):
        if I2C is None:
            self.status_label.setText(
                "Ошибка: не установлена библиотека i2cpy.\nУстанови: pip install i2cpy")
            return None
        if self.i2c is None:
            try:
                self.i2c = I2C(driver="ch341")
            except Exception as e:
                self.status_label.setText(f"Ошибка инициализации CH341: {e}")
                return None
        return self.i2c

    def write_at24c1024_block(self, data):
        i2c = self.ensure_i2c()
        if i2c is None:
            return False
        dev_addr = 0x50
        page_size = 32
        total = len(data)
        addr = 0
        try:
            for addr in range(0, total, page_size):
                chunk = data[addr:addr + page_size]
                i2c.writeto_mem(dev_addr, addr, bytes(chunk), addrsize=16)
                self.progress.setValue(min(int((addr + page_size) * 100 / total), 100))
                QtWidgets.QApplication.processEvents()
                time.sleep(0.01)
        except Exception as e:
            self.status_label.setText(f"Ошибка записи AT24C1024 при адресе 0x{addr:04X}: {e}")
            self.reset_i2c()
            return False
        return True

    def read_at24c1024_block(self, size):
        i2c = self.ensure_i2c()
        if i2c is None:
            return None
        dev_addr = 0x50
        page_size = 32
        data = bytearray(size)
        addr = 0
        try:
            for addr in range(0, size, page_size):
                read_len = min(page_size, size - addr)
                data[addr:addr + read_len] = i2c.readfrom_mem(dev_addr, addr, read_len, addrsize=16)
                self.progress.setValue(min(int((addr + read_len) * 100 / size), 100))
                QtWidgets.QApplication.processEvents()
                time.sleep(0.001)
        except Exception as e:
            self.status_label.setText(f"Ошибка чтения AT24C1024 при адресе 0x{addr:04X}: {e}")
            self.reset_i2c()
            return None
        return bytes(data)

    def on_program_and_verify(self):
        self.progress.setValue(0)
        self.status_label.setText("")
        self.reset_i2c()

        raw = self.ed_value.text().strip().replace(",", ".")
        try:
            value = float(raw)
        except Exception:
            self.status_label.setText("Ошибка: введи число, например 2941.44")
            return
        if value < 0:
            self.status_label.setText("Ошибка: значение не может быть отрицательным.")
            return

        original = self.read_at24c1024_block(IMAGE_SIZE_1F)
        if original is None:
            return
        if len(original) != IMAGE_SIZE_1F:
            self.status_label.setText("Ошибка: прочитано меньше 0x200 байт.")
            return

        if all(b == 0xFF for b in original):
            self.status_label.setText("Ошибка: всё 0xFF — память не подключена или не отвечает.")
            return
        if all(b == 0x00 for b in original):
            self.status_label.setText("Ошибка: всё 0x00 — возможны проблемы с подключением памяти.")
            return

        try:
            image, N, frame = patch_image_1F(original, value)
        except Exception as e:
            self.status_label.setText(f"Ошибка генерации патча: {e}")
            return

        if not self.write_at24c1024_block(image):
            return

        read_back = self.read_at24c1024_block(IMAGE_SIZE_1F)
        if read_back is None:
            return
        if len(read_back) != len(image):
            self.status_label.setText("Ошибка: размер прочитанных данных не совпадает.")
            return

        if all(b == 0xFF for b in read_back):
            self.status_label.setText("Ошибка: всё 0xFF после записи.")
            return
        if all(b == 0x00 for b in read_back):
            self.status_label.setText("Ошибка: всё 0x00 после записи.")
            return

        if image == read_back:
            self.program_counter += 1
            self.counter_label.setText(f"Счётчик прошивок: {self.program_counter}")
            d0, d1, d2, crc = frame
            self.status_label.setText(
                f"Успех: value={value} (N={N})  D0 D1 D2 CRC = {d0:02X} {d1:02X} {d2:02X} {crc:02X}")
            self.progress.setValue(100)
        else:
            self.status_label.setText("Ошибка: байты 0x0000..0x01FF в EEPROM не совпадают с ожидаемыми.")


# =====================================================================
#  TAB 4: new_3F (AT24C1024, патч дампа)
# =====================================================================

PROGRAM_NAME_3F = "energomera_new_3F_CH341"
ADDRS_DATA_3F = [0x00F8, 0x00FC]
ADDR_9C_A_3F = 0x01FB
ADDR_9C_B_3F = 0x01FF
IMAGE_SIZE_3F = 0x0200
POLY_3F = 0x1021
INIT_3F = 0xFFFF


def crc_low_ccitt_false_3F(d0, d1, d2):
    crc = INIT_3F
    for b in (d0 & 0xFF, d1 & 0xFF, d2 & 0xFF):
        crc ^= (b & 0xFF) << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ POLY_3F) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc & 0xFF


def build_frame_3F(value):
    N = int(floor_3F(value / 2.56))
    if not (0 <= N <= 0xFFFFFF):
        raise ValueError(
            f"N={N} вне 24-бит (0..0xFFFFFF). "
            f"Допустимый диапазон value ~0..{0xFFFFFF * 2.56:.2f}")
    d0 = (N >> 0) & 0xFF
    d1 = (N >> 8) & 0xFF
    d2 = (N >> 16) & 0xFF
    crc = crc_low_ccitt_false_3F(d0, d1, d2)
    return N, (d0, d1, d2, crc)


def patch_image_3F(original, value):
    if len(original) < IMAGE_SIZE_3F:
        raise ValueError("Размер дампа меньше 0x200 байт, нельзя патчить 3F.")
    N, frame = build_frame_3F(value)
    d0, d1, d2, crc = frame
    image = bytearray(original[:IMAGE_SIZE_3F])
    for a in ADDRS_DATA_3F:
        image[a + 0] = d0
        image[a + 1] = d1
        image[a + 2] = d2
        image[a + 3] = crc
    image[ADDR_9C_A_3F] = 0x9C
    image[ADDR_9C_B_3F] = 0x9C
    return bytes(image), N, frame


class Tab3F(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.i2c = None
        self.program_counter = 0
        self.setWindowTitle(PROGRAM_NAME_3F)
        self.build_ui()

    def build_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.addWidget(make_tab_image_label(IMG_3F_IN_TAB))

        controls_layout = QtWidgets.QVBoxLayout()

        title = QtWidgets.QLabel("AT24C1024 3F: считать 0x0000..0x01FF → патч → записать → проверить")
        title.setObjectName("titleLabel")
        title.setAlignment(QtCore.Qt.AlignCenter)
        title.setWordWrap(True)
        controls_layout.addWidget(title)

        form = QtWidgets.QFormLayout()
        self.ed_value = QtWidgets.QLineEdit("2941.44")
        self.ed_value.setAlignment(QtCore.Qt.AlignCenter)
        self.ed_value.setPlaceholderText("например: 2941.44 (точка или запятая)")
        form.addRow("Показание:", self.ed_value)
        controls_layout.addLayout(form)

        self.btn = QtWidgets.QPushButton("Считать → изменить → записать → проверить")
        self.btn.clicked.connect(self.on_program_and_verify)
        controls_layout.addWidget(self.btn)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        controls_layout.addWidget(self.progress)

        self.counter_label = QtWidgets.QLabel("Счётчик прошивок: 0")
        controls_layout.addWidget(self.counter_label)

        self.status_label = QtWidgets.QLabel("")
        self.status_label.setWordWrap(True)
        controls_layout.addWidget(self.status_label)

        controls_layout.addStretch(1)
        main_layout.addLayout(controls_layout)

    def reset_i2c(self):
        if self.i2c is not None:
            try:
                if hasattr(self.i2c, "close"):
                    self.i2c.close()
            except Exception:
                pass
        self.i2c = None

    def ensure_i2c(self):
        if I2C is None:
            self.status_label.setText(
                "Ошибка: не установлена библиотека i2cpy.\nУстанови: pip install i2cpy")
            return None
        if self.i2c is None:
            try:
                self.i2c = I2C(driver="ch341")
            except Exception as e:
                self.status_label.setText(f"Ошибка инициализации CH341: {e}")
                self.i2c = None
        return self.i2c

    def write_at24c1024_block(self, data):
        i2c = self.ensure_i2c()
        if i2c is None:
            return False
        dev_addr = 0x50
        page_size = 32
        total = len(data)
        addr = 0
        try:
            for addr in range(0, total, page_size):
                chunk = data[addr:addr + page_size]
                i2c.writeto_mem(dev_addr, addr, bytes(chunk), addrsize=16)
                self.progress.setValue(min(int((addr + page_size) * 100 / total), 100))
                QtWidgets.QApplication.processEvents()
                time.sleep(0.01)
        except Exception as e:
            self.status_label.setText(f"Ошибка записи AT24C1024 при адресе 0x{addr:04X}: {e}")
            self.reset_i2c()
            return False
        return True

    def read_at24c1024_block(self, size):
        i2c = self.ensure_i2c()
        if i2c is None:
            return None
        dev_addr = 0x50
        page_size = 32
        data = bytearray(size)
        addr = 0
        try:
            for addr in range(0, size, page_size):
                read_len = min(page_size, size - addr)
                data[addr:addr + read_len] = i2c.readfrom_mem(dev_addr, addr, read_len, addrsize=16)
                self.progress.setValue(min(int((addr + read_len) * 100 / size), 100))
                QtWidgets.QApplication.processEvents()
                time.sleep(0.001)
        except Exception as e:
            self.status_label.setText(f"Ошибка чтения AT24C1024 при адресе 0x{addr:04X}: {e}")
            self.reset_i2c()
            return None
        return bytes(data)

    def on_program_and_verify(self):
        self.progress.setValue(0)
        self.status_label.setText("")
        self.reset_i2c()

        raw = self.ed_value.text().strip().replace(",", ".")
        try:
            value = float(raw)
        except Exception:
            self.status_label.setText("Ошибка: введи число, например 2941.44")
            return
        if value < 0:
            self.status_label.setText("Ошибка: значение не может быть отрицательным.")
            return

        original = self.read_at24c1024_block(IMAGE_SIZE_3F)
        if original is None:
            return
        if len(original) != IMAGE_SIZE_3F:
            self.status_label.setText("Ошибка: прочитано меньше 0x200 байт.")
            return

        if all(b == 0xFF for b in original):
            self.status_label.setText("Ошибка: всё 0xFF — память не подключена или не отвечает.")
            return
        if all(b == 0x00 for b in original):
            self.status_label.setText("Ошибка: всё 0x00 — возможны проблемы с подключением памяти.")
            return

        try:
            image, N, frame = patch_image_3F(original, value)
        except Exception as e:
            self.status_label.setText(f"Ошибка генерации патча: {e}")
            return

        if not self.write_at24c1024_block(image):
            return

        read_back = self.read_at24c1024_block(IMAGE_SIZE_3F)
        if read_back is None:
            return
        if len(read_back) != len(image):
            self.status_label.setText("Ошибка: размер прочитанных данных не совпадает.")
            return

        if all(b == 0xFF for b in read_back):
            self.status_label.setText("Ошибка: всё 0xFF — память не подключена или не отвечает.")
            return
        if all(b == 0x00 for b in read_back):
            self.status_label.setText("Ошибка: всё 0x00 — возможны проблемы с подключением памяти.")
            return

        if image == read_back:
            self.program_counter += 1
            self.counter_label.setText(f"Счётчик прошивок: {self.program_counter}")
            d0, d1, d2, crc = frame
            self.status_label.setText(
                f"Успех: value={value}  N={N}  "
                f"D0 D1 D2 CRC = {d0:02X} {d1:02X} {d2:02X} {crc:02X}, "
                f"0x9C @0x{ADDR_9C_A_3F:04X}/0x{ADDR_9C_B_3F:04X}")
            self.progress.setValue(100)
        else:
            self.status_label.setText("Ошибка: байты 0x0000..0x01FF в EEPROM не совпадают с ожидаемыми.")


# =====================================================================
#  TAB 5: ce6803b_p32 (24C04, патч дампа)
# =====================================================================

POLY_6803 = 0xB5
INIT_6803 = 0xFF
SCALE_6803 = 2.56
FILE_SIZE_6803 = 0x200
HEAD_OFFSETS_6803 = (0x00F8, 0x00FC)
TAIL_OFFSETS_6803 = (0x01F8, 0x01FC)
TAIL_STATIC_FRAME_6803 = bytes([0x00, 0x00, 0x00, 0x69])


def crc8_b5_6803(data):
    crc = INIT_6803
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ POLY_6803) & 0xFF if (crc & 0x80) else ((crc << 1) & 0xFF)
    return crc


def raw_to_3bytes_be_6803(raw):
    return bytes([(raw >> 16) & 0xFF, (raw >> 8) & 0xFF, raw & 0xFF])


def build_frame_6803(reading):
    raw = int(round(reading / SCALE_6803))
    if not (0 <= raw <= 0xFFFFFF):
        raise ValueError("RAW вне диапазона 0..0xFFFFFF")
    data3 = raw_to_3bytes_be_6803(raw)
    crc = crc8_b5_6803(data3)
    return data3 + bytes([crc]), raw


def patch_blob_6803(original, reading):
    frame, raw = build_frame_6803(reading)
    blob = bytearray(original)
    for off in HEAD_OFFSETS_6803:
        blob[off:off + 4] = frame
    for off in TAIL_OFFSETS_6803:
        blob[off:off + 4] = TAIL_STATIC_FRAME_6803
    return bytes(blob), frame, raw


class TabCE6803(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("energomera ce6803b e p32")
        self.i2c = None
        self.program_counter = 0
        self.build_ui()

    def build_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.addWidget(make_tab_image_label(IMG_CE6803_IN_TAB))

        controls_layout = QtWidgets.QVBoxLayout()

        self.reading = QtWidgets.QDoubleSpinBox()
        self.reading.setDecimals(2)
        self.reading.setRange(0, 1_000_000_000)
        self.reading.setValue(3558.00)

        self.btn = QtWidgets.QPushButton("Считать → изменить кадры F8/FC → записать → проверить")
        self.btn.clicked.connect(self.make_and_program)

        self.info = QtWidgets.QTextEdit()
        self.info.setReadOnly(True)
        self.info.setFixedHeight(100)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)

        self.status = QtWidgets.QLabel("")
        self.status.setWordWrap(True)
        self.counter_label = QtWidgets.QLabel("Счётчик прошивок: 0")

        form = QtWidgets.QFormLayout()
        form.addRow("Показание:", self.reading)

        controls_layout.addLayout(form)
        controls_layout.addWidget(self.btn)
        controls_layout.addWidget(self.info)
        controls_layout.addWidget(self.progress)
        controls_layout.addWidget(self.status)
        controls_layout.addWidget(self.counter_label)
        controls_layout.addStretch(1)
        main_layout.addLayout(controls_layout)

    def reset_i2c(self):
        if self.i2c is not None:
            try:
                if hasattr(self.i2c, "close"):
                    self.i2c.close()
            except Exception:
                pass
        self.i2c = None

    def ensure_i2c(self):
        if I2C is None:
            self.status.setText("Ошибка: не установлена библиотека i2cpy (pip install i2cpy).")
            return None
        if self.i2c is None:
            try:
                self.i2c = I2C(driver="ch341")
            except Exception as e:
                self.status.setText(f"Ошибка инициализации CH341: {e}")
                self.i2c = None
        return self.i2c

    def program_eeprom_with_ch341(self, blob):
        i2c = self.ensure_i2c()
        if i2c is None:
            return False
        page_size = 16
        total = FILE_SIZE_6803
        addr = 0
        try:
            for addr in range(0, total, page_size):
                chunk = bytes(blob[addr:addr + page_size])
                dev_addr = 0x50 | ((addr >> 8) & 0x01)
                i2c.writeto_mem(dev_addr, addr & 0xFF, chunk, addrsize=8)
                self.progress.setValue(min(int((addr + page_size) * 100 / total), 100))
                QtWidgets.QApplication.processEvents()
                time.sleep(0.01)
        except Exception as e:
            self.status.setText(f"Ошибка записи EEPROM: {e}")
            self.reset_i2c()
            return False
        return True

    def read_eeprom_with_ch341(self):
        i2c = self.ensure_i2c()
        if i2c is None:
            return None
        page_size = 16
        total = FILE_SIZE_6803
        data = bytearray(total)
        addr = 0
        try:
            for addr in range(0, total, page_size):
                dev_addr = 0x50 | ((addr >> 8) & 0x01)
                data[addr:addr + page_size] = i2c.readfrom_mem(dev_addr, addr & 0xFF, page_size, addrsize=8)
                self.progress.setValue(min(int((addr + page_size) * 100 / total), 100))
                QtWidgets.QApplication.processEvents()
                time.sleep(0.005)
        except Exception as e:
            self.status.setText(f"Ошибка чтения EEPROM: {e}")
            self.reset_i2c()
            return None
        return bytes(data)

    def make_and_program(self):
        self.progress.setValue(0)
        self.status.setText("")
        self.reset_i2c()

        try:
            reading = float(self.reading.value())
        except Exception:
            self.status.setText("Ошибка: некорректное показание.")
            return

        original = self.read_eeprom_with_ch341()
        if original is None:
            return
        if len(original) != FILE_SIZE_6803:
            self.status.setText("EEPROM: размер считанных данных не 512 байт.")
            return

        if all(b == 0xFF for b in original):
            self.status.setText("EEPROM: всё 0xFF (возможно, не подключена микросхема).")
            return
        if all(b == 0x00 for b in original):
            self.status.setText("EEPROM: всё 0x00 (возможно, проблемы с подключением памяти).")
            return

        try:
            blob, frame, raw = patch_blob_6803(original, reading)
        except Exception as e:
            self.status.setText(f"Ошибка формирования кадра: {e}")
            return

        info_text = (
            "Дамп считан, подготовлен патч.\n"
            f"Размер: {len(blob)} (0x{len(blob):X})\n"
            f"Кадр @0x00F8/0x00FC: {' '.join(f'{b:02X}' for b in frame)}\n"
            "Хвост @0x01F8/0x01FC: 00 00 00 69")

        if not self.program_eeprom_with_ch341(blob):
            self.info.setPlainText(info_text + "\n\nEEPROM: ошибка записи.")
            return

        read_back = self.read_eeprom_with_ch341()
        if read_back is None:
            self.info.setPlainText(info_text + "\n\nEEPROM: ошибка чтения.")
            return

        if len(read_back) != FILE_SIZE_6803:
            self.status.setText("EEPROM: размер считанных данных не 512 байт.")
            self.info.setPlainText(info_text + "\n\nEEPROM: размер не совпадает.")
            return

        if all(b == 0xFF for b in read_back):
            self.status.setText("EEPROM: всё 0xFF после записи.")
            self.info.setPlainText(info_text + "\n\nEEPROM: всё 0xFF.")
            return
        if all(b == 0x00 for b in read_back):
            self.status.setText("EEPROM: всё 0x00 после записи.")
            self.info.setPlainText(info_text + "\n\nEEPROM: всё 0x00.")
            return

        if read_back == blob:
            self.program_counter += 1
            self.counter_label.setText(f"Счётчик прошивок: {self.program_counter}")
            self.status.setText("EEPROM: запись подтверждена (весь дамп совпал).")
            self.progress.setValue(100)
            self.info.setPlainText(info_text + "\n\nEEPROM: запись подтверждена.")
        else:
            self.status.setText("EEPROM: данные отличаются от дампа с патчем.")
            self.info.setPlainText(info_text + "\n\nEEPROM: данные отличаются от эталона.")


# =====================================================================
#  Окно настроек (горизонтальное: цвета слева, окно справа)
# =====================================================================

class ColorSwatch(QtWidgets.QPushButton):
    colorChanged = pyqtSignal()

    def __init__(self, hex_color, parent=None):
        super().__init__(parent)
        self.hex_color = hex_color
        self.setObjectName("colorSwatch")
        self.setFixedSize(84, 28)
        self.setCursor(Qt.PointingHandCursor)
        self.refresh()
        self.clicked.connect(self.pick_color)

    def set_color(self, hex_color):
        self.hex_color = hex_color
        self.refresh()

    def refresh(self):
        # Селектор обязателен, иначе цвет протечёт в открытую отсюда палитру.
        self.setStyleSheet(
            f"QPushButton#colorSwatch {{ background-color: {self.hex_color};"
            f" color: {readable_text_color(self.hex_color)};"
            f" border: 1px solid #999999; border-radius: 6px; font-size: 11px; }}")
        self.setText(self.hex_color)

    def pick_color(self):
        color = QtWidgets.QColorDialog.getColor(QColor(self.hex_color), self.window(), "Выберите цвет")
        if color.isValid():
            self.set_color(color.name())
            self.colorChanged.emit()


class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, settings, main_window):
        super().__init__(main_window)
        self.setWindowTitle("Настройки оформления")
        self.main_window = main_window
        self.settings = copy_settings(settings)
        self.original = copy_settings(settings)
        self.swatches = {}

        root = QtWidgets.QVBoxLayout(self)
        root.setSpacing(12)

        columns = QtWidgets.QHBoxLayout()
        columns.setSpacing(16)
        columns.addWidget(self._colors_group(), 3)

        right = QtWidgets.QVBoxLayout()
        right.setSpacing(12)
        right.addWidget(self._window_group())
        right.addStretch(1)
        columns.addLayout(right, 2)
        root.addLayout(columns)
        root.addWidget(self._footer())

    def _colors_group(self):
        group = QtWidgets.QGroupBox("Цвета интерфейса", self)
        layout = QtWidgets.QVBoxLayout(group)
        layout.setSpacing(10)

        presets = QtWidgets.QHBoxLayout()
        presets.addWidget(QtWidgets.QLabel("Готовые темы:", group))
        btn_light = QtWidgets.QPushButton("Светлая", group)
        btn_light.clicked.connect(lambda: self.apply_preset(LIGHT_COLORS))
        presets.addWidget(btn_light)
        btn_dark = QtWidgets.QPushButton("Тёмная", group)
        btn_dark.clicked.connect(lambda: self.apply_preset(DARK_COLORS))
        presets.addWidget(btn_dark)
        presets.addStretch(1)
        layout.addLayout(presets)

        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(7)
        per_column = (len(COLOR_FIELDS) + 1) // 2
        for index, (key, label) in enumerate(COLOR_FIELDS):
            row = index % per_column
            col = (index // per_column) * 2
            swatch = ColorSwatch(self.settings["colors"].get(key, "#ffffff"), group)
            swatch.colorChanged.connect(self.preview)
            self.swatches[key] = swatch
            grid.addWidget(QtWidgets.QLabel(label, group), row, col)
            grid.addWidget(swatch, row, col + 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(2, 1)
        layout.addLayout(grid)
        layout.addStretch(1)
        return group

    def _window_group(self):
        group = QtWidgets.QGroupBox("Окно и шрифт", self)
        form = QtWidgets.QFormLayout(group)
        form.setSpacing(8)
        w = self.settings["window"]

        self.width_spin = QtWidgets.QSpinBox(group)
        self.width_spin.setRange(600, 1920)
        self.width_spin.setSingleStep(10)
        self.width_spin.setValue(int(w.get("width", 760)))
        form.addRow("Ширина окна (px):", self.width_spin)

        self.height_spin = QtWidgets.QSpinBox(group)
        self.height_spin.setRange(400, 1200)
        self.height_spin.setSingleStep(10)
        self.height_spin.setValue(int(w.get("height", 560)))
        form.addRow("Высота окна (px):", self.height_spin)

        self.font_scale = QtWidgets.QSpinBox(group)
        self.font_scale.setRange(80, 200)
        self.font_scale.setSingleStep(10)
        self.font_scale.setSuffix(" %")
        self.font_scale.setValue(int(w.get("font_scale", 100)))
        self.font_scale.valueChanged.connect(self.preview)
        form.addRow("Масштаб шрифта:", self.font_scale)

        self.always_on_top = QtWidgets.QCheckBox("Окно поверх остальных", group)
        self.always_on_top.setChecked(bool(w.get("always_on_top", False)))
        form.addRow(self.always_on_top)

        self.show_splash = QtWidgets.QCheckBox("Заставка при запуске", group)
        self.show_splash.setChecked(bool(w.get("splash", True)))
        form.addRow(self.show_splash)
        return group

    def _footer(self):
        frame = QtWidgets.QFrame(self)
        layout = QtWidgets.QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)

        path_label = QtWidgets.QLabel(f"Файл настроек: {SETTINGS_PATH}", frame)
        path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        path_label.setStyleSheet("color: #7b8199; font-size: 11px;")
        layout.addWidget(path_label, 1)

        if hasattr(os, "startfile"):
            btn_folder = QtWidgets.QPushButton("Открыть папку", frame)
            btn_folder.clicked.connect(self.open_settings_folder)
            layout.addWidget(btn_folder)

        btn_defaults = QtWidgets.QPushButton("По умолчанию", frame)
        btn_defaults.clicked.connect(self.reset_defaults)
        layout.addWidget(btn_defaults)

        btn_cancel = QtWidgets.QPushButton("Отмена", frame)
        btn_cancel.clicked.connect(self.reject)
        layout.addWidget(btn_cancel)

        btn_save = QtWidgets.QPushButton("Сохранить", frame)
        btn_save.setDefault(True)
        btn_save.clicked.connect(self.on_save)
        layout.addWidget(btn_save)
        return frame

    def current_colors(self):
        return {key: sw.hex_color for key, sw in self.swatches.items()}

    def preview(self):
        self.main_window.preview_theme(self.current_colors(), self.font_scale.value())

    def apply_preset(self, colors):
        for key, sw in self.swatches.items():
            sw.set_color(colors.get(key, "#ffffff"))
        self.preview()

    def reset_defaults(self):
        d = DEFAULT_SETTINGS
        self.apply_preset(d["colors"])
        self.width_spin.setValue(d["window"]["width"])
        self.height_spin.setValue(d["window"]["height"])
        self.font_scale.setValue(d["window"]["font_scale"])
        self.always_on_top.setChecked(d["window"]["always_on_top"])
        self.show_splash.setChecked(d["window"]["splash"])

    def open_settings_folder(self):
        folder = os.path.dirname(SETTINGS_PATH)
        try:
            os.makedirs(folder, exist_ok=True)
            os.startfile(folder)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Ошибка", f"Не удалось открыть папку:\n{folder}\n\n{e}")

    def reject(self):
        self.main_window.preview_theme(self.original["colors"], self.original["window"]["font_scale"])
        super().reject()

    def on_save(self):
        self.settings["colors"] = self.current_colors()
        self.settings["window"] = {
            "width": self.width_spin.value(),
            "height": self.height_spin.value(),
            "font_scale": self.font_scale.value(),
            "always_on_top": self.always_on_top.isChecked(),
            "splash": self.show_splash.isChecked(),
        }
        self.accept()


# =====================================================================
#  ГЛАВНОЕ ОКНО
# =====================================================================

class MainTabs(QtWidgets.QTabWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("mainTabs")
        self.setWindowTitle("ENERGOMERA — все программаторы")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(700, 460)

        self.settings = load_settings()
        if not os.path.isfile(SETTINGS_PATH):
            save_settings(self.settings)

        tabs = [
            (Tab201Random(), TAB_ICON_201, "201_drob_random"),
            (TabC101(),      TAB_ICON_C101, "c101"),
            (Tab1F(),        TAB_ICON_1F, "new_1F"),
            (Tab3F(),        TAB_ICON_3F, "new_3F"),
            (TabCE6803(),    TAB_ICON_CE6803, "ce6803b_p32"),
        ]
        for widget, icon_path, name in tabs:
            widget.setObjectName("tabPage")   # цель для QSS-фона вкладки
            if icon_path:
                self.addTab(widget, QtGui.QIcon(resource_path(icon_path)), name)
            else:
                self.addTab(widget, name)

        # шестерёнка настроек в правом верхнем углу панели вкладок
        self.btn_settings = QtWidgets.QPushButton("⚙", self)
        self.btn_settings.setObjectName("settingsButton")
        self.btn_settings.setFixedSize(34, 30)
        self.btn_settings.setCursor(Qt.PointingHandCursor)
        self.btn_settings.setToolTip("Настройки оформления")
        self.btn_settings.clicked.connect(self.open_settings)
        self.setCornerWidget(self.btn_settings, Qt.TopRightCorner)

        self.apply_settings(self.settings)

    def preview_theme(self, colors, font_scale):
        self.setStyleSheet(build_qss(colors, font_scale))
        repolish(self)

    def apply_settings(self, settings):
        self.settings = settings
        self.preview_theme(settings["colors"], settings["window"]["font_scale"])
        self.resize(int(settings["window"]["width"]), int(settings["window"]["height"]))
        self.set_always_on_top(settings["window"]["always_on_top"])

    def set_always_on_top(self, enabled):
        enabled = bool(enabled)
        if bool(self.windowFlags() & Qt.WindowStaysOnTopHint) == enabled:
            return
        geometry = self.geometry()
        was_visible = self.isVisible()
        flags = self.windowFlags()
        flags = flags | Qt.WindowStaysOnTopHint if enabled else flags & ~Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setGeometry(geometry)
        if was_visible:
            self.show()

    def open_settings(self):
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec_() != QtWidgets.QDialog.Accepted:
            return   # тему вернул сам диалог в reject()
        self.apply_settings(dialog.settings)
        if not save_settings(dialog.settings):
            QtWidgets.QMessageBox.warning(
                self, "Ошибка сохранения",
                f"Настройки применены, но файл записать не удалось:\n{SETTINGS_PATH}\n\n"
                f"Причина: {LAST_SAVE_ERROR}\n\n"
                "До перезапуска всё работает, но настройки не сохранятся.")


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")   # Fusion полностью подчиняется QSS, в отличие от родного стиля Windows
    app.setWindowIcon(app_icon())

    window = MainTabs()

    if window.settings["window"].get("splash", True):
        window.splash = SplashScreen(window.settings["colors"])
        window.splash.start(window.show)
    else:
        window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
