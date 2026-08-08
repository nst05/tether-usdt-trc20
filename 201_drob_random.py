# -*- coding: utf-8 -*-
"""
201 RANDOM — прошивка EEPROM 24C16 через CH341 со случайной дробной частью.

Целая часть вводится вручную, дробная (сотые) берётся случайно из заданного
диапазона или фиксируется в настройках. После записи образ читается обратно
и сверяется.
"""

import json
import os
import random
import sys
import time

from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QPushButton, QLineEdit, QLabel, QProgressBar, QGroupBox, QFrame,
    QGraphicsOpacityEffect, QDialog, QColorDialog, QSpinBox, QCheckBox,
    QMessageBox,
)


# ============================================================================
#  Пути и драйвер CH341
# ============================================================================

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)           # папка рядом с .exe
    BUNDLE_DIR = getattr(sys, "_MEIPASS", BASE_DIR)      # ресурсы внутри .exe
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR = BASE_DIR


def _setup_ch341_dll():
    """Передать i2cpy абсолютный путь к CH341 DLL.

    Начиная с Python 3.8 ctypes ищет DLL по имени только в системных папках,
    в папке программы и в каталогах из os.add_dll_directory(); PATH больше
    не используется. Поэтому одного добавления _MEIPASS в PATH для .exe мало.
    Имя зависит от разрядности Python — так его ищет сам i2cpy.
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


# ============================================================================
#  Настройки
# ============================================================================

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
    "counter": "#7b8199",
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
    "counter": "#7b8199",
    "success": "#51cf66",
    "error": "#ff6b6b",
}

# порядок важен — в таком виде поля выводятся в окне настроек
COLOR_FIELDS = [
    ("bg", "Фон окна"),
    ("card", "Фон карточки"),
    ("card_border", "Рамка карточки"),
    ("title", "Заголовок"),
    ("field_label", "Подпись поля"),
    ("input_bg", "Фон поля ввода"),
    ("input_border", "Рамка поля ввода"),
    ("accent", "Акцент (кнопка)"),
    ("accent_hover", "Акцент (наведение)"),
    ("accent_pressed", "Акцент (нажатие)"),
    ("counter", "Текст счётчика"),
    ("success", "Текст успеха"),
    ("error", "Текст ошибки"),
]

DEFAULT_SETTINGS = {
    "colors": dict(LIGHT_COLORS),
    "random": {
        "frac_min": 0,           # диапазон случайных сотых, 0..99
        "frac_max": 99,
        "use_fixed_frac": False,
        "fixed_frac_value": 50,
    },
    "window": {
        "width": 620,
        "height": 420,
        "font_scale": 100,       # проценты, 100 = обычный размер
        "always_on_top": False,
    },
    "counter": {
        "persist": False,        # помнить счётчик между запусками
        "value": 0,
    },
}

SECTIONS = ("colors", "random", "window", "counter")


def _dir_writable(path):
    """Реальная проверка записи: создаём и удаляем тестовый файл."""
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".write_test_tmp")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("test")
        os.remove(probe)
        return True
    except Exception:
        return False


def _resolve_settings_path():
    """settings.json рядом с программой; если туда нельзя писать —
    в %APPDATA%\\201_drob_random (программа может лежать в Program Files)."""
    if _dir_writable(BASE_DIR):
        return os.path.join(BASE_DIR, "settings.json")

    appdata = os.environ.get("APPDATA")
    folder = (os.path.join(appdata, "201_drob_random") if appdata
              else os.path.join(os.path.expanduser("~"), ".201_drob_random"))
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "settings.json")


SETTINGS_PATH = _resolve_settings_path()

# текст последней ошибки записи — показываем причину, а не «не удалось»
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
        for section in SECTIONS:
            if isinstance(data.get(section), dict):
                settings[section].update(data[section])
    except Exception:
        pass  # битый файл — молча работаем на значениях по умолчанию
    return settings


def save_settings(settings):
    """Атомарная запись: сначала .tmp, потом переименование, чтобы при сбое
    не остался обрезанный settings.json."""
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


# ============================================================================
#  Тема оформления
# ============================================================================

def build_qss(colors, font_scale):
    """QSS для главного окна.

    Все правила адресные (#objectName). Правило вида QWidget { ... } без имени
    наследуется всеми дочерними окнами — диалоги и выбор цвета красились бы
    вместе с главным окном.
    """
    def s(px):
        return max(1, round(px * font_scale / 100))

    c = colors
    return f"""
    QWidget#mainWindow {{
        background-color: {c['bg']};
    }}
    #titleLabel {{
        color: {c['title']};
        font-family: 'Segoe UI', 'Arial';
        font-size: {s(20)}px;
        font-weight: 600;
        padding: 4px 0 2px 0;
    }}
    #settingsButton {{
        background-color: transparent;
        border: 1px solid {c['card_border']};
        border-radius: 10px;
        font-size: {s(18)}px;
        color: {c['field_label']};
    }}
    #settingsButton:hover {{
        background-color: {c['input_bg']};
        border: 1px solid {c['accent']};
    }}
    #card {{
        background-color: {c['card']};
        border-radius: 16px;
        border: 1px solid {c['card_border']};
    }}
    #fieldLabel {{
        color: {c['field_label']};
        font-family: 'Segoe UI', 'Arial';
        font-size: {s(15)}px;
        font-weight: 500;
    }}
    #valueInput {{
        background-color: {c['input_bg']};
        color: {c['title']};
        border: 2px solid {c['input_border']};
        border-radius: 10px;
        font-family: 'Segoe UI', 'Arial';
        font-size: {s(22)}px;
        font-weight: 600;
        padding: 6px 10px;
        selection-background-color: {c['accent']};
        selection-color: #ffffff;
    }}
    #valueInput:focus {{
        border: 2px solid {c['accent']};
        background-color: {c['card']};
    }}
    #mainButton {{
        background-color: {c['accent']};
        color: #ffffff;
        border: none;
        border-radius: 12px;
        font-family: 'Segoe UI', 'Arial';
        font-size: {s(17)}px;
        font-weight: 600;
    }}
    #mainButton:hover  {{ background-color: {c['accent_hover']}; }}
    #mainButton:pressed {{ background-color: {c['accent_pressed']}; }}
    #mainButton:disabled {{
        background-color: {c['input_border']};
        color: {c['card']};
    }}
    #progressBar {{
        background-color: {c['input_bg']};
        border: 1px solid {c['input_border']};
        border-radius: 10px;
        text-align: center;
        color: {c['title']};
        font-size: {s(13)}px;
        font-weight: 600;
    }}
    #progressBar::chunk {{
        background-color: {c['accent']};
        border-radius: 9px;
    }}
    #counterLabel {{
        color: {c['counter']};
        font-family: 'Segoe UI', 'Arial';
        font-size: {s(14)}px;
        font-weight: 500;
    }}
    """


def status_qss(color, font_scale):
    size = max(1, round(15 * font_scale / 100))
    return (f"#statusLabel {{ color: {color}; font-family: 'Segoe UI','Arial';"
            f" font-size: {size}px; font-weight: 600; padding: 6px; }}")


def repolish(root):
    """Пересчитать стиль у уже созданных виджетов. Без этого часть оформления
    (рамки, фон полей) остаётся от прежней темы."""
    for widget in [root] + root.findChildren(QWidget):
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)
        widget.update()


def readable_text_color(hex_color):
    """Чёрная или белая подпись — по яркости фона."""
    c = QColor(hex_color)
    luma = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
    return "#000000" if luma > 140 else "#ffffff"


# ============================================================================
#  EEPROM: математика образа
# ============================================================================

def to_bcd_bytes(value):
    """Целая часть -> 3 BCD-байта (6 цифр)."""
    digits = list(str(value).rjust(6, "0"))
    d1 = int(digits[0]) * 16 + int(digits[1])
    d2 = int(digits[2]) * 16 + int(digits[3])
    d3 = int(digits[4]) * 16 + int(digits[5])
    return bytes([d1, d2, d3])


def crc16_ibm(data):
    """CRC-16 IBM: полином 0xA001, init 0xFFFF."""
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def hund_to_bcd(hund):
    """0..99 -> один BCD-байт."""
    return ((hund // 10) << 4) | (hund % 10)


def build_eeprom(int_value, frac_hund):
    """Образ 2 КБ.

    Целая часть: BCD(3) + инверсии(3) + CRC16 -> 0x30..0x37 и 0x50..0x57.
    Дробная:     [0x03, 0x00, BCD(сотые), 0xFC, 0xFF, 0xFF-BCD] + CRC16
                 -> 0x20..0x27.
    """
    bcd = to_bcd_bytes(int_value)
    inv = bytes([0xFF - b for b in bcd])
    crc = crc16_ibm(bcd + inv)
    frame_int = bcd + inv + bytes([crc & 0xFF, (crc >> 8) & 0xFF])

    frac_bcd = hund_to_bcd(frac_hund)
    first6 = bytes([0x03, 0x00, frac_bcd, 0xFC, 0xFF, (0xFF - frac_bcd) & 0xFF])
    crc_frac = crc16_ibm(first6)
    frame_frac = first6 + bytes([crc_frac & 0xFF, (crc_frac >> 8) & 0xFF])

    eeprom = bytearray([0xFF] * 2048)
    eeprom[0x20:0x28] = frame_frac
    eeprom[0x33:0x36] = inv
    eeprom[0x30:0x38] = frame_int
    eeprom[0x50:0x58] = frame_int
    return bytes(eeprom)


def blocks_match(golden, actual):
    """Сверка кадров целой части 0x30..0x35 и 0x50..0x55 (CRC не проверяем)."""
    if len(golden) < 0x56 or len(actual) < 0x56:
        return False
    for addr in list(range(0x30, 0x36)) + list(range(0x50, 0x56)):
        if golden[addr] != actual[addr]:
            return False
    return True


# ============================================================================
#  Окно настроек
# ============================================================================

class ColorSwatch(QPushButton):
    """Кнопка-образец цвета; клик открывает палитру."""

    colorChanged = pyqtSignal()

    def __init__(self, hex_color, parent=None):
        super().__init__(parent)
        self.hex_color = hex_color
        self.setObjectName("colorSwatch")
        self.setFixedSize(84, 30)
        self.setCursor(Qt.PointingHandCursor)
        self.refresh()
        self.clicked.connect(self.pick_color)

    def set_color(self, hex_color):
        self.hex_color = hex_color
        self.refresh()

    def refresh(self):
        # Селектор обязателен: стиль без него достаётся всем дочерним
        # виджетам, включая открытую отсюда палитру.
        self.setStyleSheet(
            f"QPushButton#colorSwatch {{"
            f" background-color: {self.hex_color};"
            f" color: {readable_text_color(self.hex_color)};"
            f" border: 1px solid #999999; border-radius: 6px;"
            f" font-size: 11px; }}"
        )
        self.setText(self.hex_color)

    def pick_color(self):
        # Родитель — окно настроек, а не сама кнопка, иначе палитра
        # унаследует её цвет.
        color = QColorDialog.getColor(QColor(self.hex_color), self.window(),
                                      "Выберите цвет")
        if color.isValid():
            self.set_color(color.name())
            self.colorChanged.emit()


class SettingsDialog(QDialog):
    """Настройки в две колонки: слева цвета, справа всё остальное.

    Цвета применяются к главному окну сразу при выборе — «Отмена» возвращает
    прежнюю тему.
    """

    def __init__(self, settings, counter, main_window):
        super().__init__(main_window)
        self.setWindowTitle("Настройки")

        self.main_window = main_window
        self.settings = copy_settings(settings)
        self.original = copy_settings(settings)
        self.counter = counter
        self.counter_reset_requested = False
        self.swatches = {}

        root = QVBoxLayout(self)
        root.setSpacing(12)

        columns = QHBoxLayout()
        columns.setSpacing(16)
        columns.addWidget(self._colors_group(), 3)

        right = QVBoxLayout()
        right.setSpacing(12)
        right.addWidget(self._random_group())
        right.addWidget(self._window_group())
        right.addWidget(self._counter_group())
        right.addStretch(1)
        columns.addLayout(right, 2)

        root.addLayout(columns)
        root.addWidget(self._footer())

    # ---------- левая колонка ----------

    def _colors_group(self):
        group = QGroupBox("Цвета интерфейса", self)
        layout = QVBoxLayout(group)
        layout.setSpacing(10)

        presets = QHBoxLayout()
        presets.addWidget(QLabel("Готовые темы:", group))
        btn_light = QPushButton("Светлая", group)
        btn_light.clicked.connect(lambda: self.apply_preset(LIGHT_COLORS))
        presets.addWidget(btn_light)
        btn_dark = QPushButton("Тёмная", group)
        btn_dark.clicked.connect(lambda: self.apply_preset(DARK_COLORS))
        presets.addWidget(btn_dark)
        presets.addStretch(1)
        layout.addLayout(presets)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(7)
        # две пары «подпись + образец» в строке — окно растёт вширь, не вниз
        per_column = (len(COLOR_FIELDS) + 1) // 2
        for index, (key, label) in enumerate(COLOR_FIELDS):
            row = index % per_column
            col = (index // per_column) * 2
            swatch = ColorSwatch(self.settings["colors"].get(key, "#ffffff"), group)
            swatch.colorChanged.connect(self.preview_colors)
            self.swatches[key] = swatch
            grid.addWidget(QLabel(label, group), row, col)
            grid.addWidget(swatch, row, col + 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(2, 1)
        layout.addLayout(grid)
        layout.addStretch(1)
        return group

    # ---------- правая колонка ----------

    def _random_group(self):
        group = QGroupBox("Логика случайной дробной части", self)
        form = QFormLayout(group)
        form.setSpacing(8)

        r = self.settings["random"]

        self.frac_min = QSpinBox(group)
        self.frac_min.setRange(0, 99)
        self.frac_min.setValue(int(r.get("frac_min", 0)))
        form.addRow("Мин. сотые (0..99):", self.frac_min)

        self.frac_max = QSpinBox(group)
        self.frac_max.setRange(0, 99)
        self.frac_max.setValue(int(r.get("frac_max", 99)))
        form.addRow("Макс. сотые (0..99):", self.frac_max)

        self.use_fixed = QCheckBox("Фиксированное значение вместо случайного", group)
        self.use_fixed.setChecked(bool(r.get("use_fixed_frac", False)))
        form.addRow(self.use_fixed)

        self.fixed_value = QSpinBox(group)
        self.fixed_value.setRange(0, 99)
        self.fixed_value.setValue(int(r.get("fixed_frac_value", 50)))
        form.addRow("Фиксированные сотые:", self.fixed_value)

        self.use_fixed.toggled.connect(self._sync_random_enabled)
        self._sync_random_enabled(self.use_fixed.isChecked())
        return group

    def _sync_random_enabled(self, fixed):
        """Не даём крутить неработающие поля."""
        self.frac_min.setEnabled(not fixed)
        self.frac_max.setEnabled(not fixed)
        self.fixed_value.setEnabled(fixed)

    def _window_group(self):
        group = QGroupBox("Окно и шрифт", self)
        form = QFormLayout(group)
        form.setSpacing(8)

        w = self.settings["window"]

        self.width_spin = QSpinBox(group)
        self.width_spin.setRange(400, 1600)
        self.width_spin.setSingleStep(10)
        self.width_spin.setValue(int(w.get("width", 620)))
        form.addRow("Ширина окна (px):", self.width_spin)

        self.height_spin = QSpinBox(group)
        self.height_spin.setRange(300, 1200)
        self.height_spin.setSingleStep(10)
        self.height_spin.setValue(int(w.get("height", 420)))
        form.addRow("Высота окна (px):", self.height_spin)

        self.font_scale = QSpinBox(group)
        self.font_scale.setRange(80, 200)
        self.font_scale.setSingleStep(10)
        self.font_scale.setSuffix(" %")
        self.font_scale.setValue(int(w.get("font_scale", 100)))
        self.font_scale.valueChanged.connect(self.preview_colors)
        form.addRow("Масштаб шрифта:", self.font_scale)

        self.always_on_top = QCheckBox("Окно поверх остальных", group)
        self.always_on_top.setChecked(bool(w.get("always_on_top", False)))
        form.addRow(self.always_on_top)
        return group

    def _counter_group(self):
        group = QGroupBox("Счётчик прошивок", self)
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        self.persist_counter = QCheckBox("Помнить счётчик между запусками", group)
        self.persist_counter.setChecked(bool(self.settings["counter"].get("persist", False)))
        layout.addWidget(self.persist_counter)

        row = QHBoxLayout()
        self.counter_label = QLabel(f"Текущее значение: {self.counter}", group)
        row.addWidget(self.counter_label, 1)
        btn_reset = QPushButton("Сбросить на 0", group)
        btn_reset.clicked.connect(self.reset_counter)
        row.addWidget(btn_reset, 0)
        layout.addLayout(row)
        return group

    # ---------- низ окна ----------

    def _footer(self):
        frame = QFrame(self)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)

        path_label = QLabel(f"Файл настроек: {SETTINGS_PATH}", frame)
        path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        path_label.setStyleSheet("color: #7b8199; font-size: 11px;")
        layout.addWidget(path_label, 1)

        if hasattr(os, "startfile"):  # Windows
            btn_folder = QPushButton("Открыть папку", frame)
            btn_folder.clicked.connect(self.open_settings_folder)
            layout.addWidget(btn_folder)

        btn_defaults = QPushButton("По умолчанию", frame)
        btn_defaults.clicked.connect(self.reset_defaults)
        layout.addWidget(btn_defaults)

        btn_cancel = QPushButton("Отмена", frame)
        btn_cancel.clicked.connect(self.reject)
        layout.addWidget(btn_cancel)

        btn_save = QPushButton("Сохранить", frame)
        btn_save.setDefault(True)
        btn_save.clicked.connect(self.on_save)
        layout.addWidget(btn_save)
        return frame

    # ---------- действия ----------

    def current_colors(self):
        return {key: swatch.hex_color for key, swatch in self.swatches.items()}

    def preview_colors(self):
        """Показать тему на главном окне сразу, не дожидаясь «Сохранить»."""
        self.main_window.preview_theme(self.current_colors(), self.font_scale.value())

    def apply_preset(self, colors):
        for key, swatch in self.swatches.items():
            swatch.set_color(colors.get(key, "#ffffff"))
        self.preview_colors()

    def reset_defaults(self):
        d = DEFAULT_SETTINGS
        self.apply_preset(d["colors"])
        self.frac_min.setValue(d["random"]["frac_min"])
        self.frac_max.setValue(d["random"]["frac_max"])
        self.use_fixed.setChecked(d["random"]["use_fixed_frac"])
        self.fixed_value.setValue(d["random"]["fixed_frac_value"])
        self.width_spin.setValue(d["window"]["width"])
        self.height_spin.setValue(d["window"]["height"])
        self.font_scale.setValue(d["window"]["font_scale"])
        self.always_on_top.setChecked(d["window"]["always_on_top"])
        self.persist_counter.setChecked(d["counter"]["persist"])

    def reset_counter(self):
        answer = QMessageBox.question(
            self, "Сбросить счётчик",
            "Сбросить счётчик прошивок на 0?\nПрименится после сохранения настроек.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self.counter_reset_requested = True
            self.counter = 0
            self.counter_label.setText("Текущее значение: 0 (будет сброшено)")

    def open_settings_folder(self):
        folder = os.path.dirname(SETTINGS_PATH)
        try:
            os.makedirs(folder, exist_ok=True)
            os.startfile(folder)
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось открыть папку:\n{folder}\n\n{e}")

    def reject(self):
        # вернуть тему, которая была до открытия настроек
        self.main_window.preview_theme(self.original["colors"],
                                       self.original["window"]["font_scale"])
        super().reject()

    def on_save(self):
        if self.frac_min.value() > self.frac_max.value():
            QMessageBox.warning(self, "Ошибка",
                                "Минимальные сотые не могут быть больше максимальных.")
            return

        self.settings["colors"] = self.current_colors()
        self.settings["random"] = {
            "frac_min": self.frac_min.value(),
            "frac_max": self.frac_max.value(),
            "use_fixed_frac": self.use_fixed.isChecked(),
            "fixed_frac_value": self.fixed_value.value(),
        }
        self.settings["window"] = {
            "width": self.width_spin.value(),
            "height": self.height_spin.value(),
            "font_scale": self.font_scale.value(),
            "always_on_top": self.always_on_top.isChecked(),
        }
        self.settings["counter"] = {
            "persist": self.persist_counter.isChecked(),
            "value": self.counter,
        }
        self.accept()


# ============================================================================
#  Главное окно
# ============================================================================

class EEPROMTool(QWidget):

    def __init__(self):
        super().__init__()

        self.i2c = None
        self._progress_anim = None
        self._status_anim = None
        self._status_kind = "info"

        self.settings = load_settings()
        if not os.path.isfile(SETTINGS_PATH):
            save_settings(self.settings)   # файл виден сразу после первого запуска

        counter = self.settings["counter"]
        self.program_counter = int(counter.get("value", 0)) if counter.get("persist") else 0

        self.build_ui()
        self.apply_settings(self.settings)

    # ---------- интерфейс ----------

    def build_ui(self):
        self.setObjectName("mainWindow")
        self.setWindowTitle("201 RANDOM")
        self.setMinimumSize(420, 320)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 26, 28, 26)
        outer.setSpacing(18)

        title = QLabel("EEPROM · Прошивка со случайной дробной частью", self)
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(True)

        self.btn_settings = QPushButton("⚙", self)
        self.btn_settings.setObjectName("settingsButton")
        self.btn_settings.setFixedSize(40, 40)
        self.btn_settings.setCursor(Qt.PointingHandCursor)
        self.btn_settings.setToolTip("Настройки: цвета, окно, логика случайных чисел")
        self.btn_settings.clicked.connect(self.open_settings)

        header = QHBoxLayout()
        header.addWidget(title, 1)
        header.addWidget(self.btn_settings, 0)
        outer.addLayout(header)

        card = QFrame(self)
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(16)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignLeft)

        label = QLabel("Целая часть (например, 575):", self)
        label.setObjectName("fieldLabel")

        self.value_input = QLineEdit(self)
        self.value_input.setObjectName("valueInput")
        self.value_input.setPlaceholderText("575")
        self.value_input.setAlignment(Qt.AlignCenter)
        self.value_input.setMinimumHeight(52)
        self.value_input.returnPressed.connect(self.on_program_and_verify)

        form.addRow(label, self.value_input)
        card_layout.addLayout(form)

        self.btn_program = QPushButton("⚡  Записать и проверить", self)
        self.btn_program.setObjectName("mainButton")
        self.btn_program.setMinimumHeight(56)
        self.btn_program.setCursor(Qt.PointingHandCursor)
        self.btn_program.clicked.connect(self.on_program_and_verify)
        card_layout.addWidget(self.btn_program)

        self.progress = QProgressBar(self)
        self.progress.setObjectName("progressBar")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setMinimumHeight(28)
        card_layout.addWidget(self.progress)

        self.counter_label = QLabel(self)
        self.counter_label.setObjectName("counterLabel")
        self.counter_label.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(self.counter_label)

        self.status_label = QLabel("", self)
        self.status_label.setObjectName("statusLabel")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumHeight(44)
        self._status_effect = QGraphicsOpacityEffect(self.status_label)
        self._status_effect.setOpacity(0.0)
        self.status_label.setGraphicsEffect(self._status_effect)
        card_layout.addWidget(self.status_label)

        outer.addWidget(card)

    # ---------- применение настроек ----------

    def preview_theme(self, colors, font_scale):
        """Только внешний вид — используется живым предпросмотром настроек."""
        self.setStyleSheet(build_qss(colors, font_scale))
        self.status_label.setStyleSheet(
            status_qss(colors.get(self._status_kind, colors["title"]), font_scale))
        repolish(self)

    def apply_settings(self, settings):
        """Применить настройки целиком, без перезапуска программы."""
        self.settings = settings

        self.preview_theme(settings["colors"], settings["window"]["font_scale"])

        self.resize(int(settings["window"]["width"]), int(settings["window"]["height"]))
        self.set_always_on_top(settings["window"]["always_on_top"])
        self.counter_label.setText(f"Счётчик прошивок: {self.program_counter}")

    def set_always_on_top(self, enabled):
        enabled = bool(enabled)
        if bool(self.windowFlags() & Qt.WindowStaysOnTopHint) == enabled:
            return  # не трогаем флаги зря: окно мигает и теряет позицию

        geometry = self.geometry()
        was_visible = self.isVisible()
        flags = self.windowFlags()
        flags = flags | Qt.WindowStaysOnTopHint if enabled else flags & ~Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setGeometry(geometry)
        if was_visible:
            self.show()

    def open_settings(self):
        dialog = SettingsDialog(self.settings, self.program_counter, self)
        if dialog.exec_() != QDialog.Accepted:
            return   # тему вернул сам диалог в reject()

        new_settings = dialog.settings
        if dialog.counter_reset_requested:
            self.program_counter = 0
        new_settings["counter"]["value"] = self.program_counter

        self.apply_settings(new_settings)

        if not save_settings(new_settings):
            QMessageBox.warning(
                self, "Ошибка сохранения",
                f"Настройки применены, но файл записать не удалось:\n{SETTINGS_PATH}\n\n"
                f"Причина: {LAST_SAVE_ERROR}\n\n"
                "До перезапуска всё работает, но настройки не сохранятся."
            )

    # ---------- статус и прогресс ----------

    def animate_progress_to(self, value):
        target = max(0, min(100, int(value)))
        if self._progress_anim is not None:
            self._progress_anim.stop()
        anim = QPropertyAnimation(self.progress, b"value", self)
        anim.setDuration(220)
        anim.setStartValue(self.progress.value())
        anim.setEndValue(target)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()
        self._progress_anim = anim

    def show_status(self, text, kind="info"):
        """kind: success | error | info."""
        self._status_kind = {"success": "success", "error": "error"}.get(kind, "title")
        colors = self.settings["colors"]
        self.status_label.setStyleSheet(
            status_qss(colors[self._status_kind], self.settings["window"]["font_scale"]))
        self.status_label.setText(text)

        if self._status_anim is not None:
            self._status_anim.stop()
        self._status_effect.setOpacity(0.0)
        anim = QPropertyAnimation(self._status_effect, b"opacity", self)
        anim.setDuration(350)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()
        self._status_anim = anim

    # ---------- логика ----------

    def read_int_part(self):
        text = self.value_input.text().strip()
        if not text.isdigit():
            self.show_status("Ошибка! Введите целое число без знака.", "error")
            return None
        value = int(text)
        if value > 999999:
            self.show_status("Ошибка! Целая часть не должна превышать 999999.", "error")
            return None
        return value

    def generate_frac_hund(self):
        """Сотые (0..99) по текущим настройкам."""
        r = self.settings["random"]
        if r.get("use_fixed_frac"):
            return max(0, min(99, int(r.get("fixed_frac_value", 50))))

        lo = max(0, min(99, int(r.get("frac_min", 0))))
        hi = max(0, min(99, int(r.get("frac_max", 99))))
        if lo > hi:
            lo, hi = hi, lo
        return random.randint(lo, hi)

    def on_program_and_verify(self):
        self.progress.setValue(0)
        self.status_label.setText("")
        self._status_effect.setOpacity(0.0)
        self.reset_i2c()

        int_part = self.read_int_part()
        if int_part is None:
            return

        frac_hund = self.generate_frac_hund()

        try:
            eeprom = build_eeprom(int_part, frac_hund)
        except Exception as e:
            self.show_status(f"Ошибка генерации образа EEPROM: {e}", "error")
            return

        self.btn_program.setEnabled(False)
        try:
            if not self.program_eeprom(eeprom):
                return
            read_back = self.read_eeprom()
        finally:
            self.btn_program.setEnabled(True)

        if read_back is None:
            return
        if len(read_back) != len(eeprom):
            self.show_status("Ошибка: размер прочитанных данных не совпадает.", "error")
            return
        if all(b == 0xFF for b in read_back):
            self.show_status("Ошибка: всё 0xFF — память не подключена или не отвечает.", "error")
            return
        if all(b == 0x00 for b in read_back):
            self.show_status("Ошибка: всё 0x00 — проблемы с подключением памяти.", "error")
            return

        if not blocks_match(eeprom, read_back):
            self.show_status(
                "Ошибка: целая часть в EEPROM не совпадает с ожидаемой (BCD/инверсии).",
                "error")
            return

        self.program_counter += 1
        self.counter_label.setText(f"Счётчик прошивок: {self.program_counter}")
        if self.settings["counter"].get("persist"):
            self.settings["counter"]["value"] = self.program_counter
            save_settings(self.settings)   # тихо, без диалогов

        source = "фиксирована" if self.settings["random"].get("use_fixed_frac") else "случайна"
        self.show_status(
            f"✓ Успех: записано {int_part}.{str(frac_hund).rjust(2, '0')} "
            f"(дробная часть {source}).",
            "success")
        self.animate_progress_to(100)

    # ---------- CH341 / 24C16 ----------

    def ensure_i2c(self):
        if I2C is None:
            self.show_status("Ошибка: не установлена библиотека i2cpy.\n"
                             "Установите: pip install i2cpy", "error")
            return None
        if self.i2c is None:
            try:
                self.i2c = I2C(driver="ch341")
            except Exception as e:
                self.show_status(f"Ошибка инициализации CH341: {e}", "error")
                return None
        return self.i2c

    def reset_i2c(self):
        if self.i2c is not None:
            try:
                if hasattr(self.i2c, "close"):
                    self.i2c.close()
            except Exception:
                pass
        self.i2c = None

    def program_eeprom(self, eeprom):
        i2c = self.ensure_i2c()
        if i2c is None:
            return False

        page_size = 16
        total = len(eeprom)
        addr = 0
        try:
            for addr in range(0, total, page_size):
                dev_addr = 0x50 | ((addr >> 8) & 0x07)
                i2c.writeto_mem(dev_addr, addr & 0xFF,
                                bytes(eeprom[addr:addr + page_size]), addrsize=8)
                self.progress.setValue(min(int((addr + page_size) * 100 / total), 100))
                QApplication.processEvents()
                time.sleep(0.01)
        except Exception as e:
            self.show_status(f"Ошибка записи EEPROM по адресу 0x{addr:04X}: {e}", "error")
            self.reset_i2c()
            return False
        return True

    def read_eeprom(self):
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
                data[addr:addr + page_size] = i2c.readfrom_mem(
                    dev_addr, addr & 0xFF, page_size, addrsize=8)
                self.progress.setValue(min(int((addr + page_size) * 100 / total), 100))
                QApplication.processEvents()
                time.sleep(0.001)
        except Exception as e:
            self.show_status(f"Ошибка чтения EEPROM по адресу 0x{addr:04X}: {e}", "error")
            self.reset_i2c()
            return None
        return bytes(data)


# ============================================================================

def main():
    app = QApplication(sys.argv)
    # Родной стиль Windows частично игнорирует QSS для кнопок, полей ввода
    # и прогресс-баров. Fusion подчиняется стилям полностью.
    app.setStyle("Fusion")

    window = EEPROMTool()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
