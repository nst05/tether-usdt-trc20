#!/usr/bin/env python3
"""Настольный клиент взаимодействия со стендом по RS-485 (PyQt5).

Безопасный контур по разделу 27 технического отчёта:
  - подключение к COM-порту, автопоиск скорости/чётности;
  - диагностическое чтение (CMD 0x08) — идентификация, конфигурация, адрес,
    флаги состояния, мгновенные значения фаз;
  - авторизация штатным паролем (CMD 0x01, уровни 1/2) и чтение памяти (CMD 0x06);
  - живой лог кадров запрос/ответ в HEX.

Команды записи (CMD 0x03/0x07) в клиент намеренно не включены.

Запуск с реальным портом:   python3 gui.py
Запуск на симуляторе:        python3 gui.py --sim
"""
from __future__ import annotations

import sys
import queue
import threading
import time
from datetime import datetime

import stand

try:
    from PyQt5 import QtCore, QtGui, QtWidgets
except ImportError:  # модуль импортируется и без Qt (для проверки/CI)
    QtCore = QtGui = QtWidgets = None


# --------------------------------------------------------------------------
# Рабочий поток: держит соединение и выполняет задачи, не блокируя интерфейс.
# --------------------------------------------------------------------------
class Worker(QtCore.QObject if QtCore else object):
    if QtCore:
        sig_frame = QtCore.pyqtSignal(str, str)      # direction, hex
        sig_result = QtCore.pyqtSignal(str, str)     # заголовок, текст
        sig_error = QtCore.pyqtSignal(str)           # текст ошибки
        sig_conn = QtCore.pyqtSignal(bool, str)      # подключено?, сообщение

    def __init__(self):
        super().__init__()
        self._tasks: "queue.Queue" = queue.Queue()
        self._dev = None
        self._stop = False
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def post(self, fn):
        self._tasks.put(fn)

    def shutdown(self):
        self._stop = True
        self._tasks.put(None)

    def _loop(self):
        while not self._stop:
            fn = self._tasks.get()
            if fn is None:
                break
            try:
                fn()
            except stand.ResultError as e:
                self.sig_error.emit(str(e))
            except stand.StandError as e:
                self.sig_error.emit(str(e))
            except Exception as e:  # noqa: BLE001 — показываем оператору любую ошибку
                self.sig_error.emit(f"{type(e).__name__}: {e}")
        if self._dev:
            try:
                self._dev.close()
            except Exception:
                pass

    # --- операции соединения (выполняются в рабочем потоке) ---
    def connect(self, sim, port, address, baud, parity):
        def task():
            if self._dev:
                try:
                    self._dev.close()
                except Exception:
                    pass
            if sim:
                import sim as simmod
                self._dev = simmod.make_sim_stand(address)
            else:
                self._dev = stand.Stand(port, address, baud, parity,
                                        timeout=0.4, retries=3)
            self._dev.on_frame = lambda d, f: self.sig_frame.emit(d, f.hex(' '))
            self._dev.test_link()
            self.sig_conn.emit(True, f"подключено: {'СИМ' if sim else port}, "
                                     f"{baud} бод, {parity}, адрес {address:#04x}")
        self.post(task)

    def autodetect(self, port, address):
        def task():
            baud, parity = stand.find_stand(port, address)
            self._dev = stand.Stand(port, address, baud, parity, timeout=0.4, retries=3)
            self._dev.on_frame = lambda d, f: self.sig_frame.emit(d, f.hex(' '))
            self.sig_conn.emit(True, f"найдено: {baud} бод, {parity}")
        self.post(task)

    def disconnect(self):
        def task():
            if self._dev:
                self._dev.close()
                self._dev = None
            self.sig_conn.emit(False, "отключено")
        self.post(task)

    def call(self, title, fn):
        """fn(dev) -> str; результат отправляется в sig_result."""
        def task():
            if not self._dev:
                self.sig_error.emit("нет соединения")
                return
            self.sig_result.emit(title, fn(self._dev))
        self.post(task)


# --------------------------------------------------------------------------
# Главное окно
# --------------------------------------------------------------------------
if QtWidgets:
    class MainWindow(QtWidgets.QMainWindow):
        def __init__(self, sim=False):
            super().__init__()
            self.sim = sim
            self.setWindowTitle("Клиент стенда RS-485" + ("  [СИМУЛЯТОР]" if sim else ""))
            self.resize(920, 640)
            self.worker = Worker()
            self.worker.sig_frame.connect(self._on_frame)
            self.worker.sig_result.connect(self._on_result)
            self.worker.sig_error.connect(self._on_error)
            self.worker.sig_conn.connect(self._on_conn)
            self._build_ui()
            self._set_connected(False)

        # ---- построение интерфейса ----
        def _build_ui(self):
            central = QtWidgets.QWidget()
            self.setCentralWidget(central)
            root = QtWidgets.QVBoxLayout(central)

            root.addWidget(self._connection_bar())

            split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
            split.addWidget(self._command_panel())
            split.addWidget(self._log_panel())
            split.setStretchFactor(0, 0)
            split.setStretchFactor(1, 1)
            root.addWidget(split, 1)

            self.status = self.statusBar()
            self.status.showMessage("не подключено")

        def _connection_bar(self):
            box = QtWidgets.QGroupBox("Соединение")
            lay = QtWidgets.QHBoxLayout(box)

            self.cb_port = QtWidgets.QComboBox()
            self.cb_port.setEditable(True)
            self.cb_port.setMinimumWidth(160)
            self._refresh_ports()

            self.cb_baud = QtWidgets.QComboBox()
            for b in sorted(stand.BAUD_TABLE.values(), reverse=True):
                self.cb_baud.addItem(str(b), b)
            self.cb_baud.setCurrentText(str(stand.BAUD_DEFAULT))

            self.cb_parity = QtWidgets.QComboBox()
            for p, name in (("O", "8-O-1"), ("E", "8-E-1"), ("N", "8-N-1")):
                self.cb_parity.addItem(name, p)

            self.sp_addr = QtWidgets.QSpinBox()
            self.sp_addr.setRange(0, 255)
            self.sp_addr.setPrefix("адрес ")
            self.sp_addr.setValue(0)

            self.bt_conn = QtWidgets.QPushButton("Подключить")
            self.bt_conn.clicked.connect(self._toggle_connect)
            self.bt_auto = QtWidgets.QPushButton("Автопоиск")
            self.bt_auto.clicked.connect(self._do_autodetect)
            bt_ref = QtWidgets.QPushButton("⟳")
            bt_ref.setFixedWidth(32)
            bt_ref.clicked.connect(self._refresh_ports)

            for w in (QtWidgets.QLabel("Порт"), self.cb_port, bt_ref,
                      QtWidgets.QLabel("Скорость"), self.cb_baud,
                      QtWidgets.QLabel("Чётность"), self.cb_parity,
                      self.sp_addr, self.bt_auto, self.bt_conn):
                lay.addWidget(w)
            lay.addStretch(1)
            return box

        def _command_panel(self):
            panel = QtWidgets.QWidget()
            lay = QtWidgets.QVBoxLayout(panel)
            lay.setContentsMargins(0, 0, 0, 0)

            # Диагностика — только чтение
            g1 = QtWidgets.QGroupBox("Диагностика (только чтение)")
            v1 = QtWidgets.QVBoxLayout(g1)
            self._diag_buttons = []
            for text, title, fn in (
                ("Тест связи", "Тест связи",
                 lambda d: "OK" if d.test_link() else "нет ответа"),
                ("Идентификация (SN, дата)", "Идентификация",
                 lambda d: str(d.read_identity())),
                ("Базовая конфигурация", "Конфигурация 0x04E0..",
                 lambda d: d.read_config().hex(' ')),
                ("Сетевой адрес", "Адрес узла",
                 lambda d: f"{d.read_address():#04x}"),
                ("Флаги состояния", "Слово состояния",
                 lambda d: d.read_status_flags().hex(' ')),
                ("Мгновенные значения фаз", "Фазы A/B/C",
                 lambda d: "  ".join(f"{v:#06x}" for v in d.read_phase_values())),
            ):
                b = QtWidgets.QPushButton(text)
                b.clicked.connect(lambda _, t=title, f=fn: self.worker.call(t, f))
                v1.addWidget(b)
                self._diag_buttons.append(b)
            lay.addWidget(g1)

            # Авторизация
            g2 = QtWidgets.QGroupBox("Авторизация (штатный пароль)")
            f2 = QtWidgets.QFormLayout(g2)
            self.ed_pwd = QtWidgets.QLineEdit()
            self.ed_pwd.setPlaceholderText("6 байт HEX, напр. 01 01 01 01 01 01")
            self.cb_level = QtWidgets.QComboBox()
            self.cb_level.addItem("уровень 1", 1)
            self.cb_level.addItem("уровень 2", 2)
            row = QtWidgets.QHBoxLayout()
            self.bt_login = QtWidgets.QPushButton("Войти")
            self.bt_login.clicked.connect(self._do_login)
            self.bt_logout = QtWidgets.QPushButton("Выйти")
            self.bt_logout.clicked.connect(
                lambda: self.worker.call("Выход", lambda d: d.logout() or "канал закрыт"))
            row.addWidget(self.bt_login)
            row.addWidget(self.bt_logout)
            f2.addRow("Пароль", self.ed_pwd)
            f2.addRow("Уровень", self.cb_level)
            f2.addRow(row)
            lay.addWidget(g2)

            # Чтение памяти
            g3 = QtWidgets.QGroupBox("Чтение памяти (CMD 0x06)")
            f3 = QtWidgets.QFormLayout(g3)
            self.ed_addr = QtWidgets.QLineEdit("0x0048")
            self.sp_len = QtWidgets.QSpinBox()
            self.sp_len.setRange(1, 16)
            self.sp_len.setValue(6)
            self.cb_mode = QtWidgets.QComboBox()
            self.cb_mode.addItem("MODE 2 (внешняя память)", 2)
            self.cb_mode.addItem("MODE 1 (таблицы)", 1)
            self.bt_memrd = QtWidgets.QPushButton("Читать блок")
            self.bt_memrd.clicked.connect(self._do_memread)
            f3.addRow("Адрес", self.ed_addr)
            f3.addRow("Длина", self.sp_len)
            f3.addRow("Режим", self.cb_mode)
            f3.addRow(self.bt_memrd)
            lay.addWidget(g3)

            # Произвольная команда — только чтение
            g4 = QtWidgets.QGroupBox("Произвольная команда (чтение)")
            f4 = QtWidgets.QVBoxLayout(g4)
            self.ed_raw = QtWidgets.QLineEdit()
            self.ed_raw.setPlaceholderText("CMD и аргументы HEX, напр. 08 1B")
            self.bt_raw = QtWidgets.QPushButton("Отправить")
            self.bt_raw.clicked.connect(self._do_raw)
            f4.addWidget(self.ed_raw)
            f4.addWidget(self.bt_raw)
            lay.addWidget(g4)

            lay.addStretch(1)
            scroll = QtWidgets.QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(panel)
            scroll.setMinimumWidth(320)
            return scroll

        def _log_panel(self):
            box = QtWidgets.QGroupBox("Обмен и результаты")
            lay = QtWidgets.QVBoxLayout(box)
            self.results = QtWidgets.QTextEdit()
            self.results.setReadOnly(True)
            self.results.setMaximumHeight(140)
            self.log = QtWidgets.QPlainTextEdit()
            self.log.setReadOnly(True)
            self.log.setFont(QtGui.QFont("monospace"))
            btn_clear = QtWidgets.QPushButton("Очистить лог")
            btn_clear.clicked.connect(self.log.clear)
            lay.addWidget(QtWidgets.QLabel("Результаты команд:"))
            lay.addWidget(self.results)
            lay.addWidget(QtWidgets.QLabel("Живой лог кадров (HEX):"))
            lay.addWidget(self.log, 1)
            lay.addWidget(btn_clear)
            return box

        # ---- обработчики ----
        def _refresh_ports(self):
            self.cb_port.clear()
            try:
                from serial.tools import list_ports
                for p in list_ports.comports():
                    self.cb_port.addItem(p.device)
            except Exception:
                pass
            if self.sim:
                self.cb_port.addItem("СИМУЛЯТОР")

        def _params(self):
            return (self.cb_port.currentText(), self.sp_addr.value(),
                    self.cb_baud.currentData(), self.cb_parity.currentData())

        def _toggle_connect(self):
            if self.bt_conn.text() == "Подключить":
                port, addr, baud, parity = self._params()
                self.worker.connect(self.sim, port, addr, baud, parity)
            else:
                self.worker.disconnect()

        def _do_autodetect(self):
            if self.sim:
                self._toggle_connect()
                return
            port, addr, _, _ = self._params()
            self.status.showMessage("автопоиск…")
            self.worker.autodetect(port, addr)

        def _parse_hex(self, text):
            text = text.replace(",", " ").replace("0x", " ")
            return bytes(int(t, 16) for t in text.split())

        def _do_login(self):
            try:
                pwd = self._parse_hex(self.ed_pwd.text())
            except ValueError:
                self._on_error("пароль: неверный HEX")
                return
            if len(pwd) != 6:
                self._on_error("пароль должен быть 6 байт")
                return
            level = self.cb_level.currentData()
            self.worker.call("Авторизация",
                             lambda d: d.login(pwd, level) or f"канал открыт, уровень {level}")

        def _do_memread(self):
            try:
                addr = int(self.ed_addr.text(), 16)
            except ValueError:
                self._on_error("адрес: неверный HEX")
                return
            length = self.sp_len.value()
            mode = self.cb_mode.currentData()
            self.worker.call(f"Память 0x{addr:04X}/{length}",
                             lambda d: d.memory_read(addr, length, mode).hex(' '))

        def _do_raw(self):
            try:
                data = self._parse_hex(self.ed_raw.text())
            except ValueError:
                self._on_error("команда: неверный HEX")
                return
            if not data:
                return
            cmd, args = data[0], data[1:]
            self.worker.call(f"RAW {data.hex(' ')}",
                             lambda d: (d.raw(cmd, *args) or b"").hex(' ') or "(пусто)")

        # ---- сигналы из рабочего потока ----
        def _on_frame(self, direction, hexstr):
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            self.log.appendPlainText(f"{ts}  {direction}  {hexstr}")

        def _on_result(self, title, text):
            self.results.append(f"<b>{title}:</b> {text}")

        def _on_error(self, text):
            self.results.append(f"<span style='color:#c0392b'><b>Ошибка:</b> {text}</span>")
            self.status.showMessage(text, 5000)

        def _on_conn(self, connected, msg):
            self._set_connected(connected)
            self.status.showMessage(msg, 5000)

        def _set_connected(self, connected):
            self.bt_conn.setText("Отключить" if connected else "Подключить")
            for w in (getattr(self, n) for n in dir(self) if n.startswith("bt_")):
                pass
            enable = connected
            for b in self._diag_buttons:
                b.setEnabled(enable)
            for name in ("bt_login", "bt_logout", "bt_memrd", "bt_raw"):
                getattr(self, name).setEnabled(enable)

        def closeEvent(self, ev):
            self.worker.shutdown()
            super().closeEvent(ev)


def main():
    sim = "--sim" in sys.argv
    if QtWidgets is None:
        print("Требуется PyQt5:  pip install PyQt5 pyserial", file=sys.stderr)
        return 2
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow(sim=sim)
    win.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
