import sys
import os
import time
import json
import random
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLineEdit, QLabel, QProgressBar, QFormLayout,
    QGraphicsOpacityEffect, QFrame, QDialog, QColorDialog,
    QSpinBox, QCheckBox, QMessageBox
)
from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QColor

# --- База для путей (для CH341A.DLL внутри exe) ---
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
    os.environ["PATH"] = sys._MEIPASS + os.pathsep + os.environ.get("PATH", "")
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Пытаемся подключить i2cpy (CH341 I2C)
try:
    from i2cpy import I2C
except ImportError:
    I2C = None


# ----------------- Настройки (цвета + логика случайных чисел) -----------------

def _dir_writable(path: str) -> bool:
    """Проверка, можно ли реально писать в папку (создаём и удаляем тестовый файл)."""
    try:
        os.makedirs(path, exist_ok=True)
        test_file = os.path.join(path, ".write_test_tmp")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("test")
        os.remove(test_file)
        return True
    except Exception:
        return False


def _resolve_settings_path() -> str:
    """
    Путь к settings.json:
      1) рядом со скриптом/exe — если туда можно писать (удобно, файл виден рядом с программой);
      2) иначе — в %APPDATA%\\201_drob_random (или ~/.201_drob_random на не-Windows) —
         так настройки сохранятся, даже если программа лежит в защищённой папке
         (например Program Files) или запущена без прав записи.
    """
    primary_dir = BASE_DIR
    if _dir_writable(primary_dir):
        return os.path.join(primary_dir, "settings.json")

    appdata = os.environ.get("APPDATA")
    if appdata:
        fallback_dir = os.path.join(appdata, "201_drob_random")
    else:
        fallback_dir = os.path.join(os.path.expanduser("~"), ".201_drob_random")

    os.makedirs(fallback_dir, exist_ok=True)
    return os.path.join(fallback_dir, "settings.json")


SETTINGS_PATH = _resolve_settings_path()

DEFAULT_SETTINGS = {
    "colors": {
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
    },
    "random": {
        # диапазон случайной дробной части (сотые), 0..99
        "frac_min": 0,
        "frac_max": 99,
        "use_fixed_frac": False,
        "fixed_frac_value": 50,
    },
    "window": {
        "width": 620,
        "height": 420,
        "font_scale": 100,   # проценты, 100 = стандартный размер
        "always_on_top": False,
    },
    "counter": {
        "persist": False,   # сохранять ли счётчик прошивок между запусками
        "value": 0,
    },
}


def load_settings():
    settings = json.loads(json.dumps(DEFAULT_SETTINGS))  # глубокая копия
    if os.path.isfile(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            for section in ("colors", "random", "window", "counter"):
                if section in data and isinstance(data[section], dict):
                    settings[section].update(data[section])
        except Exception:
            pass
    return settings


def save_settings(settings) -> bool:
    try:
        os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


# ----------------- Утилиты -----------------

def to_bcd_bytes(value: int) -> bytes:
    """Преобразование целой части в 3 BCD-байта (6 цифр)."""
    digits = list(str(value).rjust(6, '0'))
    d1 = int(digits[0]) * 16 + int(digits[1])
    d2 = int(digits[2]) * 16 + int(digits[3])
    d3 = int(digits[4]) * 16 + int(digits[5])
    return bytes([d1, d2, d3])


def crc16_ibm(data: bytes) -> int:
    """CRC-16 IBM (полином 0xA001, init=0xFFFF)."""
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def hund_to_bcd(hund: int) -> int:
    """0..99 -> один BCD-байт."""
    tens = hund // 10
    ones = hund % 10
    return (tens << 4) | ones


# ----------------- Диалог настроек -----------------

class ColorSwatchButton(QPushButton):
    """Кнопка-образец цвета: клик открывает QColorDialog."""

    def __init__(self, hex_color: str, parent=None):
        super().__init__(parent)
        self.hex_color = hex_color
        self.setFixedSize(72, 32)
        self.setCursor(Qt.PointingHandCursor)
        self._refresh()
        self.clicked.connect(self.pick_color)

    def _refresh(self):
        self.setStyleSheet(
            f"background-color: {self.hex_color}; border: 1px solid #999; border-radius: 6px;"
        )
        self.setText(self.hex_color)

    def pick_color(self):
        color = QColorDialog.getColor(QColor(self.hex_color), self, "Выберите цвет")
        if color.isValid():
            self.hex_color = color.name()
            self._refresh()


class SettingsDialog(QDialog):
    """Настройки: цвета интерфейса и логика генерации случайной дробной части."""

    def __init__(self, current_settings, current_counter=0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки")
        self.setMinimumWidth(420)

        self.settings = json.loads(json.dumps(current_settings))  # копия для редактирования
        self.current_counter = current_counter
        self.counter_reset_requested = False
        self.color_buttons = {}

        outer = QVBoxLayout(self)
        outer.setSpacing(16)

        # --- Цвета ---
        colors_title = QLabel("Цвета интерфейса")
        colors_title.setStyleSheet("font-weight: 600; font-size: 15px;")
        outer.addWidget(colors_title)

        color_labels = {
            "bg": "Фон окна",
            "card": "Фон карточки",
            "card_border": "Рамка карточки",
            "title": "Заголовок",
            "field_label": "Подпись поля",
            "input_bg": "Фон поля ввода",
            "input_border": "Рамка поля ввода",
            "accent": "Акцент (кнопка)",
            "accent_hover": "Акцент (наведение)",
            "accent_pressed": "Акцент (нажатие)",
            "counter": "Текст счётчика",
            "success": "Текст успеха",
            "error": "Текст ошибки",
        }

        colors_form = QFormLayout()
        colors_form.setSpacing(8)
        for key, label in color_labels.items():
            btn = ColorSwatchButton(self.settings["colors"].get(key, "#ffffff"), self)
            self.color_buttons[key] = btn
            colors_form.addRow(QLabel(label), btn)
        outer.addLayout(colors_form)

        # --- Логика случайных чисел ---
        random_title = QLabel("Логика случайной дробной части")
        random_title.setStyleSheet("font-weight: 600; font-size: 15px; margin-top: 8px;")
        outer.addWidget(random_title)

        random_form = QFormLayout()
        random_form.setSpacing(8)

        self.frac_min_spin = QSpinBox(self)
        self.frac_min_spin.setRange(0, 99)
        self.frac_min_spin.setValue(int(self.settings["random"].get("frac_min", 0)))
        random_form.addRow(QLabel("Мин. значение сотых (0..99):"), self.frac_min_spin)

        self.frac_max_spin = QSpinBox(self)
        self.frac_max_spin.setRange(0, 99)
        self.frac_max_spin.setValue(int(self.settings["random"].get("frac_max", 99)))
        random_form.addRow(QLabel("Макс. значение сотых (0..99):"), self.frac_max_spin)

        self.use_fixed_check = QCheckBox("Использовать фиксированное значение вместо случайного", self)
        self.use_fixed_check.setChecked(bool(self.settings["random"].get("use_fixed_frac", False)))
        random_form.addRow(self.use_fixed_check)

        self.fixed_value_spin = QSpinBox(self)
        self.fixed_value_spin.setRange(0, 99)
        self.fixed_value_spin.setValue(int(self.settings["random"].get("fixed_frac_value", 50)))
        random_form.addRow(QLabel("Фиксированное значение сотых:"), self.fixed_value_spin)

        outer.addLayout(random_form)

        # --- Окно и шрифт ---
        window_title = QLabel("Окно и шрифт")
        window_title.setStyleSheet("font-weight: 600; font-size: 15px; margin-top: 8px;")
        outer.addWidget(window_title)

        window_form = QFormLayout()
        window_form.setSpacing(8)

        self.width_spin = QSpinBox(self)
        self.width_spin.setRange(400, 1600)
        self.width_spin.setSingleStep(10)
        self.width_spin.setValue(int(self.settings["window"].get("width", 620)))
        window_form.addRow(QLabel("Ширина окна (px):"), self.width_spin)

        self.height_spin = QSpinBox(self)
        self.height_spin.setRange(300, 1200)
        self.height_spin.setSingleStep(10)
        self.height_spin.setValue(int(self.settings["window"].get("height", 420)))
        window_form.addRow(QLabel("Высота окна (px):"), self.height_spin)

        self.font_scale_spin = QSpinBox(self)
        self.font_scale_spin.setRange(80, 200)
        self.font_scale_spin.setSingleStep(10)
        self.font_scale_spin.setSuffix(" %")
        self.font_scale_spin.setValue(int(self.settings["window"].get("font_scale", 100)))
        window_form.addRow(QLabel("Масштаб шрифта:"), self.font_scale_spin)

        self.always_on_top_check = QCheckBox("Окно поверх остальных", self)
        self.always_on_top_check.setChecked(bool(self.settings["window"].get("always_on_top", False)))
        window_form.addRow(self.always_on_top_check)

        outer.addLayout(window_form)

        # --- Счётчик прошивок ---
        counter_title = QLabel("Счётчик прошивок")
        counter_title.setStyleSheet("font-weight: 600; font-size: 15px; margin-top: 8px;")
        outer.addWidget(counter_title)

        counter_form = QFormLayout()
        counter_form.setSpacing(8)

        self.persist_counter_check = QCheckBox("Сохранять счётчик между запусками программы", self)
        self.persist_counter_check.setChecked(bool(self.settings["counter"].get("persist", False)))
        counter_form.addRow(self.persist_counter_check)

        counter_row = QHBoxLayout()
        self.counter_value_label = QLabel(f"Текущее значение: {self.current_counter}", self)
        counter_row.addWidget(self.counter_value_label, 1)
        self.btn_reset_counter = QPushButton("Сбросить на 0", self)
        self.btn_reset_counter.clicked.connect(self.reset_counter)
        counter_row.addWidget(self.btn_reset_counter, 0)
        counter_form.addRow(counter_row)

        outer.addLayout(counter_form)

        # --- Кнопки ---
        btn_row = QHBoxLayout()
        self.btn_reset = QPushButton("Сбросить по умолчанию", self)
        self.btn_reset.clicked.connect(self.reset_defaults)
        btn_row.addWidget(self.btn_reset)
        btn_row.addStretch(1)

        self.btn_cancel = QPushButton("Отмена", self)
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_cancel)

        self.btn_save = QPushButton("Сохранить", self)
        self.btn_save.setDefault(True)
        self.btn_save.clicked.connect(self.on_save)
        btn_row.addWidget(self.btn_save)

        outer.addLayout(btn_row)

    def reset_defaults(self):
        defaults = json.loads(json.dumps(DEFAULT_SETTINGS))
        for key, btn in self.color_buttons.items():
            btn.hex_color = defaults["colors"].get(key, "#ffffff")
            btn._refresh()
        self.frac_min_spin.setValue(defaults["random"]["frac_min"])
        self.frac_max_spin.setValue(defaults["random"]["frac_max"])
        self.use_fixed_check.setChecked(defaults["random"]["use_fixed_frac"])
        self.fixed_value_spin.setValue(defaults["random"]["fixed_frac_value"])
        self.width_spin.setValue(defaults["window"]["width"])
        self.height_spin.setValue(defaults["window"]["height"])
        self.font_scale_spin.setValue(defaults["window"]["font_scale"])
        self.always_on_top_check.setChecked(defaults["window"]["always_on_top"])
        self.persist_counter_check.setChecked(defaults["counter"]["persist"])

    def reset_counter(self):
        answer = QMessageBox.question(
            self, "Сбросить счётчик",
            "Сбросить счётчик прошивок на 0?\nДействие применится сразу после сохранения настроек.",
            QMessageBox.Yes | QMessageBox.No
        )
        if answer == QMessageBox.Yes:
            self.counter_reset_requested = True
            self.current_counter = 0
            self.counter_value_label.setText(f"Текущее значение: {self.current_counter} (будет сброшено)")

    def on_save(self):
        if self.frac_min_spin.value() > self.frac_max_spin.value():
            QMessageBox.warning(
                self, "Ошибка",
                "Минимальное значение сотых не может быть больше максимального."
            )
            return

        for key, btn in self.color_buttons.items():
            self.settings["colors"][key] = btn.hex_color

        self.settings["random"]["frac_min"] = self.frac_min_spin.value()
        self.settings["random"]["frac_max"] = self.frac_max_spin.value()
        self.settings["random"]["use_fixed_frac"] = self.use_fixed_check.isChecked()
        self.settings["random"]["fixed_frac_value"] = self.fixed_value_spin.value()

        self.settings["window"]["width"] = self.width_spin.value()
        self.settings["window"]["height"] = self.height_spin.value()
        self.settings["window"]["font_scale"] = self.font_scale_spin.value()
        self.settings["window"]["always_on_top"] = self.always_on_top_check.isChecked()

        self.settings["counter"]["persist"] = self.persist_counter_check.isChecked()
        self.settings["counter"]["value"] = self.current_counter

        self.accept()

    def get_settings(self):
        return self.settings

    def get_counter_reset_requested(self):
        return self.counter_reset_requested


# ----------------- Основное окно -----------------

class EEPROMTool(QWidget):
    def __init__(self):
        super().__init__()

        self.i2c = None

        self._progress_anim = None
        self._status_anim = None
        self._status_effect = None
        self._last_status_kind = "info"

        self.settings = load_settings()

        # счётчик: восстанавливаем из настроек, если включено сохранение
        if self.settings["counter"].get("persist", False):
            self.program_counter = int(self.settings["counter"].get("value", 0))
        else:
            self.program_counter = 0

        self.init_ui()

    # ---------- UI ----------

    def init_ui(self):
        self.setWindowTitle('201 RANDOM')
        w = int(self.settings["window"].get("width", 620))
        h = int(self.settings["window"].get("height", 420))
        self.setGeometry(200, 200, w, h)
        self.setMinimumSize(420, 320)
        self._apply_always_on_top(self.settings["window"].get("always_on_top", False))

        self.setStyleSheet(self._build_stylesheet())

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
        self.btn_settings.setToolTip("Настройки: цвета и логика случайных чисел")
        self.btn_settings.clicked.connect(self.open_settings)

        title_row = QHBoxLayout()
        title_row.addWidget(title, 1)
        title_row.addWidget(self.btn_settings, 0)
        outer.addLayout(title_row)

        card = QFrame(self)
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(16)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignLeft)

        self.label_int = QLabel("Целая часть (например, 575):", self)
        self.label_int.setObjectName("fieldLabel")

        self.value_input = QLineEdit(self)
        self.value_input.setObjectName("valueInput")
        self.value_input.setPlaceholderText("575")
        self.value_input.setAlignment(Qt.AlignCenter)
        self.value_input.setMinimumHeight(52)

        form.addRow(self.label_int, self.value_input)
        card_layout.addLayout(form)

        self.btn_program_verify = QPushButton("⚡  Записать и проверить", self)
        self.btn_program_verify.setObjectName("mainButton")
        self.btn_program_verify.setMinimumHeight(56)
        self.btn_program_verify.setCursor(Qt.PointingHandCursor)
        self.btn_program_verify.clicked.connect(self.on_program_and_verify)
        card_layout.addWidget(self.btn_program_verify)

        self.progress = QProgressBar(self)
        self.progress.setObjectName("progressBar")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setMinimumHeight(28)
        card_layout.addWidget(self.progress)

        self.counter_label = QLabel(f"Счётчик прошивок: {self.program_counter}", self)
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
        self.setLayout(outer)

    def _apply_always_on_top(self, enabled: bool):
        enabled = bool(enabled)
        already = bool(self.windowFlags() & Qt.WindowStaysOnTopHint)
        if already == enabled:
            return  # ничего не меняем — иначе окно зря мигает и теряет позицию

        was_visible = self.isVisible()
        geometry = self.geometry()

        flags = self.windowFlags()
        if enabled:
            flags |= Qt.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)

        # setWindowFlags сбрасывает геометрию и прячет окно — возвращаем обратно
        self.setGeometry(geometry)
        if was_visible:
            self.show()

    def _scale(self, px: int) -> int:
        scale = int(self.settings["window"].get("font_scale", 100))
        return max(1, round(px * scale / 100))

    def _build_stylesheet(self):
        c = self.settings["colors"]
        s = self._scale
        return f"""
        QWidget {{
            background-color: {c['bg']};
            font-family: 'Segoe UI', 'Arial';
        }}
        #titleLabel {{
            color: {c['title']};
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
            font-size: {s(15)}px;
            font-weight: 500;
        }}
        #valueInput {{
            background-color: {c['input_bg']};
            color: {c['title']};
            border: 2px solid {c['input_border']};
            border-radius: 10px;
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
            font-size: {s(17)}px;
            font-weight: 600;
        }}
        #mainButton:hover {{
            background-color: {c['accent_hover']};
        }}
        #mainButton:pressed {{
            background-color: {c['accent_pressed']};
        }}
        #mainButton:disabled {{
            background-color: {c['input_border']};
            color: #ffffff;
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
            font-size: {s(14)}px;
            font-weight: 500;
        }}
        #statusLabel {{
            font-size: {s(15)}px;
            font-weight: 600;
            color: {c['title']};
            padding: 6px;
        }}
        """

    # ---------- Анимации ----------

    def animate_progress_to(self, value: int):
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

    def show_status(self, text: str, kind: str = "info"):
        """kind: 'success' | 'error' | 'info' — красит текст и делает fade-in."""
        c = self.settings["colors"]
        colors = {
            "success": c["success"],
            "error": c["error"],
            "info": c["title"],
        }
        color = colors.get(kind, colors["info"])
        self._last_status_kind = kind
        self.status_label.setStyleSheet(f"#statusLabel {{ color: {color}; font-size: {self._scale(15)}px; font-weight: 600; padding: 6px; }}")
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

    def open_settings(self):
        dialog = SettingsDialog(self.settings, self.program_counter, self)
        if dialog.exec_() != QDialog.Accepted:
            return

        new_settings = dialog.get_settings()

        # применяем сброс счётчика, если запрошен
        if dialog.get_counter_reset_requested():
            self.program_counter = 0
            new_settings["counter"]["value"] = 0
        else:
            new_settings["counter"]["value"] = self.program_counter

        # СНАЧАЛА применяем настройки в самой программе, и только потом пишем на диск:
        # даже если файл записать не удалось, настройки работают в текущем сеансе.
        self.apply_settings(new_settings)

        if not save_settings(new_settings):
            QMessageBox.warning(
                self, "Ошибка сохранения",
                f"Настройки применены, но не удалось записать settings.json в:\n{SETTINGS_PATH}\n\n"
                "Проверьте права на запись в эту папку — иначе настройки "
                "не сохранятся до следующего запуска."
            )

    def apply_settings(self, new_settings):
        """Применить настройки к уже открытому окну — без перезапуска программы."""
        self.settings = new_settings

        # 1) цвета и масштаб шрифта
        self.setStyleSheet(self._build_stylesheet())
        self._repolish()

        # 2) размер окна (resize, а не setGeometry — позиция окна сохраняется)
        self.resize(
            int(self.settings["window"].get("width", 620)),
            int(self.settings["window"].get("height", 420)),
        )

        # 3) "поверх остальных окон"
        self._apply_always_on_top(self.settings["window"].get("always_on_top", False))

        # 4) счётчик прошивок
        self.counter_label.setText(f"Счётчик прошивок: {self.program_counter}")

        # 5) строка статуса: у неё свой inline-стиль, перекрашиваем вручную
        text = self.status_label.text()
        if text:
            opacity = self._status_effect.opacity()
            self.show_status(text, self._last_status_kind)
            if opacity >= 1.0 and self._status_anim is not None:
                self._status_anim.stop()
                self._status_effect.setOpacity(1.0)

    def _repolish(self):
        """Заставить Qt пересчитать QSS для уже созданных виджетов.
        Без этого часть стилей (рамки, фон полей) остаётся от старой темы."""
        for widget in [self] + self.findChildren(QWidget):
            style = widget.style()
            style.unpolish(widget)
            style.polish(widget)
            widget.update()

    # ---------- Вспомогательное ----------

    def _get_int_part(self):
        """Считать целую часть."""
        try:
            int_part = int(self.value_input.text())
        except ValueError:
            self.show_status("Ошибка! Введите корректное целое число.", "error")
            return None
        return int_part

    def _generate_frac_hund(self) -> int:
        """Дробная часть (сотые, 0..99) по текущим настройкам."""
        r = self.settings["random"]
        if r.get("use_fixed_frac"):
            return max(0, min(99, int(r.get("fixed_frac_value", 50))))

        lo = max(0, min(99, int(r.get("frac_min", 0))))
        hi = max(0, min(99, int(r.get("frac_max", 99))))
        if lo > hi:
            lo, hi = hi, lo
        return random.randint(lo, hi)

    def blocks_match(self, golden: bytes, actual: bytes) -> bool:
        """
        Сравнение БОЛЬШОЙ части кадров целой части:
          - 0x30..0x35 (6 байт: BCD + инверсии)
          - 0x50..0x55 (6 байт: BCD + инверсии)
        CRC (последние 2 байта каждого кадра) не проверяем.
        """
        if len(golden) < 0x56 or len(actual) < 0x56:
            return False

        # 0x30..0x35
        for addr in range(0x30, 0x36):
            if golden[addr] != actual[addr]:
                return False

        # 0x50..0x55
        for addr in range(0x50, 0x56):
            if golden[addr] != actual[addr]:
                return False

        return True

    def reset_i2c(self):
        """Мягкий ресет CH341."""
        if self.i2c is not None:
            try:
                if hasattr(self.i2c, "close"):
                    self.i2c.close()
            except Exception:
                pass
        self.i2c = None

    # ---------- Кнопка: всё сразу ----------

    def on_program_and_verify(self):
        self.progress.setValue(0)
        self.status_label.setText("")
        self._status_effect.setOpacity(0.0)

        self.reset_i2c()

        int_part = self._get_int_part()
        if int_part is None:
            return

        # дробная часть по настройкам: случайная в диапазоне [frac_min, frac_max] или фиксированная
        frac_hund = self._generate_frac_hund()

        # 1) Генерация образа
        try:
            eeprom = self.build_eeprom(int_part, frac_hund)
        except Exception as e:
            self.show_status(f"Ошибка генерации EEPROM: {e}", "error")
            return

        # 2) Прошивка
        if not self.program_eeprom_with_ch341(eeprom):
            return

        # 3) Чтение обратно
        read_back = self.read_eeprom_with_ch341()
        if read_back is None:
            return

        if len(eeprom) != len(read_back):
            self.show_status("Ошибка: размер данных после чтения не совпадает.", "error")
            return

        if all(b == 0xFF for b in read_back):
            self.show_status("Ошибка: всё 0xFF — память не подключена/не отвечает.", "error")
            return
        if all(b == 0x00 for b in read_back):
            self.show_status("Ошибка: всё 0x00 — проблемы с подключением памяти.", "error")
            return

        # 4) Сравнение целой части (без CRC)
        if self.blocks_match(eeprom, read_back):
            self.program_counter += 1
            self.counter_label.setText(f"Счётчик прошивок: {self.program_counter}")

            if self.settings["counter"].get("persist", False):
                self.settings["counter"]["value"] = self.program_counter
                save_settings(self.settings)  # тихое сохранение, без перезапуска

            frac_source = "фиксировано в настройках" if self.settings["random"].get("use_fixed_frac") else "выбрано случайно"
            self.show_status(
                f"✓ Успех: показания записаны корректно "
                f"({int_part}.{str(frac_hund).rjust(2,'0')}) (дробь {frac_source}).",
                "success"
            )
            self.animate_progress_to(100)
        else:
            self.show_status(
                "Ошибка: целая часть в EEPROM не совпадает с ожидаемой (BCD/инверсии).",
                "error"
            )

    # ---------- Генерация EEPROM ----------

    def build_eeprom(self, int_value: int, frac_hund: int) -> bytes:
        """
        Целая часть:
            BCD(3 байта) + инверсии + CRC16 IBM -> 0x30..0x37 и 0x50..0x57.
        Дробная часть:
            Блок 0x20..0x27 = [A,B,C,D,E,F,CRClo,CRChi], где:
                B = 0x00
                C = BCD(сотые)
                E = 0xFF
                F = 0xFF - C
                A = 0x03
                D = 0xFC
                CRC16 IBM по [A,B,C,D,E,F]
        """
        # --- целая часть ---
        bcd = to_bcd_bytes(int_value)
        inv = bytes([0xFF - b for b in bcd])
        crc6 = crc16_ibm(bcd + inv)
        crc_low = crc6 & 0xFF
        crc_high = (crc6 >> 8) & 0xFF

        frame_int = bcd + inv + bytes([crc_low, crc_high])  # 8 байт

        # --- дробная часть ---
        frac_bcd = hund_to_bcd(frac_hund)

        A = 0x03
        B = 0x00
        C = frac_bcd
        D = 0xFC
        E = 0xFF
        F = (0xFF - C) & 0xFF

        first6 = bytes([A, B, C, D, E, F])
        crc_frac = crc16_ibm(first6)
        crc_frac_low = crc_frac & 0xFF
        crc_frac_high = (crc_frac >> 8) & 0xFF

        frame_frac = first6 + bytes([crc_frac_low, crc_frac_high])

        # --- собрать EEPROM 2КБ ---
        eeprom = bytearray([0xFF] * 2048)

        # дробь 0x20..0x27
        eeprom[0x20:0x28] = frame_frac

        # инверсии 0x33..0x35 (как раньше)
        eeprom[0x33:0x36] = inv

        # целая часть 0x30..0x37 и 0x50..0x57
        eeprom[0x30:0x38] = frame_int
        eeprom[0x50:0x58] = frame_int

        return bytes(eeprom)

    # ---------- CH341 / 24C16 ----------

    def ensure_i2c(self):
        if I2C is None:
            self.show_status("Ошибка: не установлена библиотека i2cpy.\nУстанови: pip install i2cpy", "error")
            return None
        if self.i2c is None:
            try:
                self.i2c = I2C(driver="ch341")
            except Exception as e:
                self.show_status(f"Ошибка инициализации CH341: {e}", "error")
                return None
        return self.i2c

    def program_eeprom_with_ch341(self, eeprom: bytes) -> bool:
        i2c = self.ensure_i2c()
        if i2c is None:
            return False

        page_size = 16
        total = len(eeprom)

        try:
            for addr in range(0, total, page_size):
                chunk = bytes(eeprom[addr:addr + page_size])

                block = (addr >> 8) & 0x07
                dev_addr = 0x50 | block
                memaddr = addr & 0xFF

                i2c.writeto_mem(dev_addr, memaddr, chunk, addrsize=8)

                percent = int((addr + page_size) * 100 / total)
                self.progress.setValue(min(percent, 100))
                QApplication.processEvents()
                time.sleep(0.01)
        except Exception as e:
            self.show_status(f"Ошибка записи EEPROM через CH341 при адресе 0x{addr:04X}: {e}", "error")
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

        try:
            for addr in range(0, total, page_size):
                block = (addr >> 8) & 0x07
                dev_addr = 0x50 | block
                memaddr = addr & 0xFF

                chunk = i2c.readfrom_mem(dev_addr, memaddr, page_size, addrsize=8)
                data[addr:addr + page_size] = chunk

                percent = int((addr + page_size) * 100 / total)
                self.progress.setValue(min(percent, 100))
                QApplication.processEvents()
                time.sleep(0.001)
        except Exception as e:
            self.show_status(f"Ошибка чтения EEPROM через CH341 при адресе 0x{addr:04X}: {e}", "error")
            self.reset_i2c()
            return None

        return bytes(data)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    # ВАЖНО: на Windows нативный стиль (windowsvista) частично игнорирует QSS
    # для кнопок/прогресс-баров/полей ввода. Fusion полностью подчиняется стилям,
    # поэтому настройки цвета из окна "Настройки" гарантированно применяются.
    app.setStyle("Fusion")
    win = EEPROMTool()
    win.show()
    sys.exit(app.exec_())
