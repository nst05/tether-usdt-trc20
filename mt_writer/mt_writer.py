# -*- coding: utf-8 -*-
"""
MT Writer — запись значения в EEPROM 24C16 через программатор CH341.

Объединяет две программы (200_MT и 310_MT) в одном окне: каждая — своя
вкладка со своим счётчиком прошивок, который сохраняется между запусками.
Программа привязана к компьютеру: без ключа активации записать нельзя.
"""

import ctypes
import gc
import os
import random
import sys
import time

from PyQt5 import QtCore, QtGui, QtWidgets

if getattr(sys, "frozen", False):
    BASE_DIR = sys._MEIPASS
    os.environ["PATH"] = BASE_DIR + os.pathsep + os.environ.get("PATH", "")
    sys.path.insert(0, BASE_DIR)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, BASE_DIR)


def prepare_ch341_dll():
    """Находит CH341DLL.DLL рядом с программой и предзагружает её.

    i2cpy грузит библиотеку по имени «CH341DLL.DLL». Если положить её рядом
    с exe (или упаковать в сборку — тогда она окажется в _MEIPASS), эта
    функция добавит папки в путь поиска и предзагрузит DLL по абсолютному
    пути. После этого i2cpy находит её по имени, и системная установка
    CH341PAR больше не нужна. Возвращает путь к загруженной DLL или None.
    """
    if os.name != "nt":
        return None

    exe_dir = (os.path.dirname(os.path.abspath(sys.executable))
               if getattr(sys, "frozen", False) else BASE_DIR)
    search_dirs = []
    for d in (BASE_DIR, exe_dir):
        if d and d not in search_dirs:
            search_dirs.append(d)

    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
        try:
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(d)
        except OSError:
            pass

    # Предзагрузка по абсолютному пути: имя файла обязательно CH341DLL.DLL,
    # иначе Windows не сопоставит его с запросом i2cpy по имени.
    for d in search_dirs:
        dll = os.path.join(d, "CH341DLL.DLL")
        if os.path.isfile(dll):
            try:
                ctypes.WinDLL(dll)
                return dll
            except OSError:
                pass
    return None


prepare_ch341_dll()

import mt_license
from mt_counters import Counters
from mt_storage import app_data_dir

try:
    from i2cpy import I2C
except ImportError:
    I2C = None


# 24C16 / 24AA16: 2 КБ, 8 блоков по 256 байт.
EEPROM_SIZE = 2048
VALUE_OFFSET = 0x0040
VALUE_SIZE = 4
SCALE = 100
BASE_I2C_ADDRESS = 0x50

# Вкладки программы. Значения EEPROM у обеих версий одинаковые —
# если для какой-то модели адрес изменится, правится только эта таблица.
PROFILES = [
    {"name": "200_MT", "offset": VALUE_OFFSET, "title": "ЗАПИСЬ ЗНАЧЕНИЯ — 200_MT"},
    {"name": "310_MT", "offset": VALUE_OFFSET, "title": "ЗАПИСЬ ЗНАЧЕНИЯ — 310_MT"},
]

APP_STYLE = """
    QWidget {
        background: #10131a;
        color: #f2f4f8;
        font-family: Segoe UI;
        font-size: 15px;
    }
    QLineEdit {
        background: #181d27;
        border: 2px solid #38445a;
        border-radius: 14px;
        padding: 16px 18px;
        font-size: 28px;
        font-weight: 700;
        color: #ffffff;
        selection-background-color: #4f7cff;
    }
    QLineEdit:focus { border-color: #6b8cff; }
    QPushButton {
        background: #3f6df6;
        border: 2px solid #6f91ff;
        border-radius: 16px;
        padding: 18px;
        font-size: 22px;
        font-weight: 800;
        color: white;
    }
    QPushButton:hover { background: #4e79ff; }
    QPushButton:pressed { background: #345acb; }
    QPushButton:disabled {
        background: #2b3240;
        border-color: #3a4352;
        color: #8d96a8;
    }
    QLabel#TitleLabel {
        font-size: 21px;
        font-weight: 900;
        color: #ffffff;
    }
    QLabel#HintLabel {
        font-size: 14px;
        color: #aab3c5;
    }
    QProgressBar {
        border: 2px solid #3d4a60;
        border-radius: 10px;
        background: #18202c;
        color: white;
        text-align: center;
        height: 24px;
        font-weight: 700;
    }
    QProgressBar::chunk {
        border-radius: 8px;
        background: #3f6df6;
    }
    QTabWidget::pane {
        border: 2px solid #2a3346;
        border-radius: 16px;
        top: -2px;
        background: #10131a;
    }
    QTabWidget::tab-bar { left: 10px; }
    QTabBar::tab {
        background: #181d27;
        color: #aab3c5;
        border: 2px solid #2a3346;
        border-bottom: none;
        border-top-left-radius: 14px;
        border-top-right-radius: 14px;
        padding: 10px 30px;
        margin-right: 6px;
        font-size: 16px;
        font-weight: 800;
    }
    QTabBar::tab:selected {
        background: #3f6df6;
        color: #ffffff;
        border-color: #6f91ff;
    }
    QTabBar::tab:hover:!selected { background: #202838; color: #dfe5f0; }
    QFrame#CounterCard {
        background: #18202c;
        border: 2px solid #3d4a60;
        border-radius: 14px;
    }
    QLabel#CounterValue {
        font-size: 34px;
        font-weight: 900;
        color: #7ff0ac;
    }
    QLabel#CounterCaption {
        font-size: 12px;
        font-weight: 800;
        color: #8d96a8;
    }
    QLabel#CounterDetail {
        font-size: 12px;
        color: #aab3c5;
    }
    QLabel#FooterLabel {
        font-size: 12px;
        color: #8d96a8;
    }
"""

STATUS_STYLES = {
    True: """
        QLabel {
            background: #153c28; border: 2px solid #2fc46f; color: #7ff0ac;
            border-radius: 14px; padding: 16px; font-size: 18px; font-weight: 800;
        }
    """,
    False: """
        QLabel {
            background: #471d25; border: 2px solid #ff5a6f; color: #ff9cab;
            border-radius: 14px; padding: 16px; font-size: 18px; font-weight: 800;
        }
    """,
    None: """
        QLabel {
            background: #18202c; border: 2px solid #3d4a60; color: #d9dfeb;
            border-radius: 14px; padding: 16px; font-size: 18px; font-weight: 800;
        }
    """,
}


def encode_value(value: float) -> bytes:
    raw = int(round(value * SCALE))
    if not 0 <= raw <= 0xFFFFFFFF:
        raise ValueError("Значение слишком большое.")
    return raw.to_bytes(4, "little", signed=False)


def decode_value(data: bytes) -> float:
    if len(data) != 4:
        raise ValueError("Неверная длина данных.")
    return int.from_bytes(data, "little", signed=False) / SCALE


class ProgrammerBusy(RuntimeError):
    """Программатор уже занят другой вкладкой."""


class ProgrammerLock:
    """Один программатор CH341 на всю программу — вкладки не мешают друг другу."""

    def __init__(self):
        self.busy = False

    def acquire(self):
        if self.busy:
            raise ProgrammerBusy("Программатор занят другой вкладкой.")
        self.busy = True

    def release(self):
        self.busy = False


# ══════════════════════════════════════════════════════════════════════════════
# Вкладка записи
# ══════════════════════════════════════════════════════════════════════════════

class WriterTab(QtWidgets.QWidget):
    def __init__(self, profile, counters, lock, license_check, parent=None):
        super().__init__(parent)
        self.profile = profile
        self.name = profile["name"]
        self.offset = profile["offset"]
        self.counters = counters
        self.lock = lock
        self.license_check = license_check
        self.i2c = None
        self.init_ui()

    # ── интерфейс ─────────────────────────────────────────────────────────────

    def init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        header = QtWidgets.QHBoxLayout()
        header.setSpacing(14)

        title_box = QtWidgets.QVBoxLayout()
        title_box.setSpacing(4)
        title = QtWidgets.QLabel(self.profile["title"])
        title.setObjectName("TitleLabel")
        title_box.addWidget(title)

        hint = QtWidgets.QLabel(
            "Введите целую часть. Дробная часть 01–99 добавляется автоматически."
        )
        hint.setObjectName("HintLabel")
        hint.setWordWrap(True)
        title_box.addWidget(hint)
        header.addLayout(title_box, 1)

        header.addWidget(self.build_counter_card())
        layout.addLayout(header)

        self.value_input = QtWidgets.QLineEdit()
        self.value_input.setPlaceholderText("Например: 3456")
        self.value_input.setAlignment(QtCore.Qt.AlignCenter)
        self.value_input.setMinimumHeight(64)

        validator = QtGui.QDoubleValidator(0.0, 42949672.95, 2, self)
        validator.setNotation(QtGui.QDoubleValidator.StandardNotation)
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

        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)
        self.status.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.status)

        self.set_status("Готово к работе")
        self.refresh_counter()

    def build_counter_card(self):
        card = QtWidgets.QFrame()
        card.setObjectName("CounterCard")
        card.setMinimumWidth(196)

        box = QtWidgets.QVBoxLayout(card)
        box.setContentsMargins(16, 10, 16, 10)
        box.setSpacing(2)

        caption = QtWidgets.QLabel("ПРОШИВОК ВСЕГО")
        caption.setObjectName("CounterCaption")
        caption.setAlignment(QtCore.Qt.AlignCenter)
        box.addWidget(caption)

        self.counter_value = QtWidgets.QLabel("0")
        self.counter_value.setObjectName("CounterValue")
        self.counter_value.setAlignment(QtCore.Qt.AlignCenter)
        box.addWidget(self.counter_value)

        self.counter_detail = QtWidgets.QLabel()
        self.counter_detail.setObjectName("CounterDetail")
        self.counter_detail.setAlignment(QtCore.Qt.AlignCenter)
        self.counter_detail.setWordWrap(True)
        box.addWidget(self.counter_detail)

        return card

    def refresh_counter(self):
        self.counter_value.setText(str(self.counters.count(self.name)))
        detail = self.counters.summary(self.name)
        if self.counters.readonly:
            detail += "\n⚠ счётчик не сохраняется: нет прав на запись файла"
        elif self.counters.tampered:
            detail += "\n⚠ файл счётчиков был изменён вручную"
        self.counter_detail.setText(detail)

    def set_status(self, text: str, ok=None):
        self.status.setText(text)
        self.status.setStyleSheet(STATUS_STYLES[ok])
        QtWidgets.QApplication.processEvents()

    # ── программатор ──────────────────────────────────────────────────────────

    def open_programmer(self):
        if I2C is None:
            raise RuntimeError("Не установлена библиотека i2cpy.")

        self.close_programmer()
        try:
            self.i2c = I2C(driver="ch341")
        except Exception as exc:
            # Чаще всего — не найдена CH341DLL.DLL.
            if "ch341" in str(exc).lower() or "load" in str(exc).lower():
                raise RuntimeError(
                    "Не найдена библиотека CH341DLL.DLL. "
                    "Положите CH341DLL.DLL (нужной разрядности) рядом с программой "
                    "или пересоберите exe с упакованной DLL."
                ) from exc
            raise

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
    def split_address(address: int):
        """
        24C16:
        A10..A8 входят в I2C-адрес устройства 0x50..0x57,
        внутри блока используется 8-битный адрес 0x00..0xFF.
        """
        if not 0 <= address < EEPROM_SIZE:
            raise ValueError("Адрес выходит за пределы 24C16.")

        block = (address >> 8) & 0x07
        device_address = BASE_I2C_ADDRESS | block
        memory_address = address & 0xFF
        return device_address, memory_address

    def read_bytes(self, address: int, length: int) -> bytes:
        if self.i2c is None:
            raise RuntimeError("Программатор не инициализирован.")

        result = bytearray()
        current = address
        remaining = length

        while remaining > 0:
            dev_addr, mem_addr = self.split_address(current)
            chunk_len = min(remaining, 0x100 - mem_addr)

            chunk = self.i2c.readfrom_mem(
                dev_addr,
                mem_addr,
                chunk_len,
                addrsize=8,
            )
            result.extend(bytes(chunk))
            current += chunk_len
            remaining -= chunk_len

        return bytes(result)

    def write_bytes(self, address: int, payload: bytes):
        if self.i2c is None:
            raise RuntimeError("Программатор не инициализирован.")

        dev_addr, mem_addr = self.split_address(address)

        # Значение 0x0040..0x0043 не пересекает блок или страницу.
        self.i2c.writeto_mem(
            dev_addr,
            mem_addr,
            bytes(payload),
            addrsize=8,
        )

    # ── запись ────────────────────────────────────────────────────────────────

    def parse_value(self) -> float:
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
        # Лицензия проверяется не только при запуске, но и перед каждой записью.
        license_status = self.license_check()
        if not license_status["valid"]:
            self.set_status("Запись заблокирована: %s" % license_status["reason"], False)
            return

        try:
            self.lock.acquire()
        except ProgrammerBusy as exc:
            self.set_status(str(exc), False)
            return

        self.write_button.setEnabled(False)
        self.progress.setValue(5)
        self.set_status("Запись...")

        try:
            value = self.parse_value()
            expected = encode_value(value)

            # 1. Сессия записи.
            self.progress.setValue(20)
            self.open_programmer()

            previous = self.read_bytes(self.offset, VALUE_SIZE)

            self.progress.setValue(45)
            self.write_bytes(self.offset, expected)

            self.close_programmer()

            # Ожидаем внутренний цикл записи EEPROM.
            self.progress.setValue(65)
            time.sleep(0.15)

            # 2. Новая сессия проверки.
            self.progress.setValue(80)
            self.open_programmer()

            actual = None
            for _ in range(10):
                try:
                    actual = self.read_bytes(self.offset, VALUE_SIZE)
                    if actual == expected:
                        break
                except Exception:
                    pass
                time.sleep(0.05)

            if actual != expected:
                raise RuntimeError("Проверка записи не пройдена.")

            verified = decode_value(actual)

            # Счётчик растёт только после успешной проверки чтением.
            total = self.counters.increment(self.name, verified)
            self.refresh_counter()

            self.progress.setValue(100)
            self.value_input.clear()
            self.value_input.setFocus()

            self.set_status(
                "Успех: записано %.2f (было %.2f) · прошивка № %d"
                % (verified, decode_value(previous), total),
                True,
            )

        except Exception as exc:
            self.progress.setValue(0)
            self.set_status("Ошибка: %s" % exc, False)

        finally:
            self.close_programmer()
            self.lock.release()
            self.write_button.setEnabled(True)


# ══════════════════════════════════════════════════════════════════════════════
# Активация
# ══════════════════════════════════════════════════════════════════════════════

class ActivationDialog(QtWidgets.QDialog):
    """Окно ввода ключа. Показывается, пока программа не активирована."""

    def __init__(self, status, parent=None):
        super().__init__(parent)
        self.status = status
        self.setWindowTitle("Активация программы")
        self.setFixedWidth(560)
        self.setStyleSheet(APP_STYLE)
        self.build_ui()

    def build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 22)
        layout.setSpacing(12)

        title = QtWidgets.QLabel("АКТИВАЦИЯ ПРОГРАММЫ")
        title.setObjectName("TitleLabel")
        title.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(title)

        hint = QtWidgets.QLabel(
            "Программа работает только на одном компьютере.\n"
            "Отправьте код компьютера поставщику и введите полученный ключ."
        )
        hint.setObjectName("HintLabel")
        hint.setAlignment(QtCore.Qt.AlignCenter)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        caption = QtWidgets.QLabel("КОД ЭТОГО КОМПЬЮТЕРА")
        caption.setObjectName("CounterCaption")
        caption.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(caption)

        self.code_field = QtWidgets.QLineEdit(self.status["machine_code"])
        self.code_field.setReadOnly(True)
        self.code_field.setAlignment(QtCore.Qt.AlignCenter)
        self.code_field.setStyleSheet("font-size: 22px; color: #7ff0ac;")
        layout.addWidget(self.code_field)

        copy_button = QtWidgets.QPushButton("СКОПИРОВАТЬ КОД")
        copy_button.setStyleSheet(
            "font-size: 15px; padding: 10px; background: #2b3240; border-color: #3d4a60;")
        copy_button.clicked.connect(self.copy_code)
        layout.addWidget(copy_button)

        key_caption = QtWidgets.QLabel("КЛЮЧ АКТИВАЦИИ")
        key_caption.setObjectName("CounterCaption")
        key_caption.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(key_caption)

        self.key_input = QtWidgets.QLineEdit()
        self.key_input.setPlaceholderText("XXXXXXX-XXXXXXX-XXXXXXX")
        self.key_input.setAlignment(QtCore.Qt.AlignCenter)
        self.key_input.setStyleSheet("font-size: 20px;")
        self.key_input.returnPressed.connect(self.try_activate)
        layout.addWidget(self.key_input)

        self.message = QtWidgets.QLabel()
        self.message.setWordWrap(True)
        self.message.setAlignment(QtCore.Qt.AlignCenter)
        self.message.setStyleSheet(STATUS_STYLES[None])
        self.message.setText(self.status["reason"] or "Введите ключ активации")
        self.message.setMinimumHeight(78)
        layout.addWidget(self.message)

        buttons = QtWidgets.QHBoxLayout()
        buttons.setSpacing(10)

        activate_button = QtWidgets.QPushButton("АКТИВИРОВАТЬ")
        activate_button.setMinimumHeight(56)
        activate_button.clicked.connect(self.try_activate)
        buttons.addWidget(activate_button, 2)

        quit_button = QtWidgets.QPushButton("ВЫХОД")
        quit_button.setMinimumHeight(56)
        quit_button.setStyleSheet(
            "background: #2b3240; border-color: #3d4a60; font-size: 18px;")
        quit_button.clicked.connect(self.reject)
        buttons.addWidget(quit_button, 1)

        layout.addLayout(buttons)

        footer = QtWidgets.QLabel("Данные программы: %s" % app_data_dir())
        footer.setObjectName("FooterLabel")
        footer.setAlignment(QtCore.Qt.AlignCenter)
        footer.setWordWrap(True)
        layout.addWidget(footer)

        self.key_input.setFocus()
        self.adjustSize()

    def copy_code(self):
        QtWidgets.QApplication.clipboard().setText(self.status["machine_code"])
        self.message.setStyleSheet(STATUS_STYLES[None])
        self.message.setText("Код скопирован в буфер обмена.")

    def try_activate(self):
        ok, message = mt_license.activate(self.key_input.text())
        self.message.setStyleSheet(STATUS_STYLES[True if ok else False])
        self.message.setText(message)
        if ok:
            QtCore.QTimer.singleShot(600, self.accept)


# ══════════════════════════════════════════════════════════════════════════════
# Главное окно
# ══════════════════════════════════════════════════════════════════════════════

class MainWindow(QtWidgets.QWidget):
    def __init__(self, license_status):
        super().__init__()
        self.license_status = license_status
        self.lock = ProgrammerLock()
        self.counters = Counters([p["name"] for p in PROFILES])
        self.tabs_by_name = {}
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("MT Writer — 200_MT / 310_MT")
        self.setFixedSize(720, 580)
        self.setStyleSheet(APP_STYLE)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 10)
        layout.setSpacing(8)

        self.tabs = QtWidgets.QTabWidget()
        for profile in PROFILES:
            tab = WriterTab(profile, self.counters, self.lock, self.check_license)
            self.tabs.addTab(tab, profile["name"])
            self.tabs_by_name[profile["name"]] = tab
        layout.addWidget(self.tabs)

        self.footer = QtWidgets.QLabel()
        self.footer.setObjectName("FooterLabel")
        self.footer.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.footer)
        self.update_footer()

        # Раз в час перепроверяем срок лицензии, если программа не закрывается.
        self.license_timer = QtCore.QTimer(self)
        self.license_timer.timeout.connect(self.check_license)
        self.license_timer.start(60 * 60 * 1000)

    def update_footer(self):
        self.footer.setText(
            "%s   ·   ПК: %s   ·   данные: %s"
            % (mt_license.status_text(self.license_status),
               self.license_status["machine_code"],
               app_data_dir())
        )

    def check_license(self):
        self.license_status = mt_license.check_license()
        self.update_footer()
        return self.license_status

    def closeEvent(self, event):
        for tab in self.tabs_by_name.values():
            tab.close_programmer()
        event.accept()


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setStyleSheet(APP_STYLE)

    status = mt_license.check_license()
    if not status["valid"]:
        dialog = ActivationDialog(status)
        if dialog.exec_() != QtWidgets.QDialog.Accepted:
            return 0
        status = mt_license.check_license()
        if not status["valid"]:
            return 0

    window = MainWindow(status)
    window.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
