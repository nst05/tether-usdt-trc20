# -*- coding: utf-8 -*-
"""
Правка показаний напрямую в SPI FRAM через программатор CH341.

Переделано с работы по файлам: раньше открывался .bin и рядом создавался
patched-файл, теперь содержимое читается из микросхемы и пишется обратно
в неё же.

  ART         MB85RS256 / MB85RS128 / MB85RS64
  AR          FM25L04B
  231-AT-01   FM25V02

Формат записей не изменился: 17 байт, P и Q в перемешанном порядке байт,
CRC = 0xF0 XOR по 16 байтам данных.
"""

import math
import os
import sys
from dataclasses import dataclass
from typing import Tuple

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtWidgets import QSizePolicy

from spi_memory import CH341SPI, SPIFram, SPIError, CHIPS, TAB_CHIPS, probe_size

try:
    from splash_screen import LoadingSplash
except ImportError:
    LoadingSplash = None

# Палитра экрана загрузки под тему этой программы.
SPLASH_PALETTE = {
    "bg_top": "#151A27",
    "bg_bottom": "#0F1115",
    "border": "#2A2F3A",
    "track": "#1A2030",
    "arc_from": "#3A4A7A",
    "arc_to": "#7C8FE0",
    "glint": "#AFC0FF",
    "title": "#FFFFFF",
    "subtitle": "#8B93A6",
    "status": "#7C8FE0",
}

IMG_HEIGHT = 150

IMG_srt03_IN_TAB = ""
IMG_AR_IN_TAB = ""

TAB_ICON_srt03 = ""
TAB_ICON_AR = ""

APP_NAME = "MERK-3F"

# Иконка и заставка лежат рядом с программой, а в сборке PyInstaller —
# в распакованной временной папке; resource_path разбирается с обоими.
ICON_FILES = ("icon_srt.ico", "icon_srt.png")


def load_app_icon() -> "QtGui.QIcon":
    for name in ICON_FILES:
        path = resource_path(name)
        if os.path.isfile(path):
            return QtGui.QIcon(path)
    return QtGui.QIcon()


def close_pyinstaller_splash():
    """Погасить заставку PyInstaller: она есть только внутри собранного exe"""
    try:
        import pyi_splash
    except ImportError:
        return
    try:
        pyi_splash.close()
    except Exception:
        pass

if getattr(sys, "frozen", False):
    os.environ["PATH"] = sys._MEIPASS + os.pathsep + os.environ.get("PATH", "")


def resource_path(relative_path: str) -> str:
    """Работает и в .py, и внутри PyInstaller EXE."""
    if getattr(sys, "frozen", False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


# -------------------------------------------------------------------
# PRETTY UI (Fusion + QSS)
# -------------------------------------------------------------------
def apply_pretty_ui(app: QtWidgets.QApplication) -> None:
    app.setStyle("Fusion")
    app.setFont(QtGui.QFont("Segoe UI", 10))
    app.setStyleSheet("""
    QWidget { background: #0f1115; color: #e7e9ee; font-size: 10pt; }

    QTabWidget::pane {
        border: 1px solid #2a2f3a; border-radius: 14px;
        top: -1px; background: #121622;
    }
    QTabBar::tab {
        background: #151a27; border: 1px solid #2a2f3a; border-bottom: none;
        padding: 10px 14px; margin-right: 6px;
        border-top-left-radius: 12px; border-top-right-radius: 12px;
        color: #cfd3dc;
    }
    QTabBar::tab:selected { background: #121622; color: #fff; border-color: #3a4a7a; }
    QTabBar::tab:hover { border-color: #4b5fa0; }

    QGroupBox {
        border: 1px solid #2a2f3a; border-radius: 14px;
        margin-top: 14px; padding: 12px; background: #121622;
    }
    QGroupBox::title {
        subcontrol-origin: margin; left: 14px; padding: 0 8px;
        color: #ffffff; font-weight: 600;
    }

    QLineEdit, QComboBox, QDoubleSpinBox {
        background: #0f1115; border: 1px solid #2a2f3a; border-radius: 10px;
        padding: 9px 10px; selection-background-color: #3a4a7a;
    }
    QLineEdit:disabled, QComboBox:disabled, QDoubleSpinBox:disabled {
        color: #8b93a6; background: #0c0e12;
    }
    QComboBox::drop-down { border: none; width: 24px; }

    QPushButton {
        background: #1a2030; border: 1px solid #2a2f3a; border-radius: 12px;
        padding: 10px 14px; font-weight: 600;
    }
    QPushButton:hover { border-color: #4b5fa0; background: #1d2436; }
    QPushButton:pressed { background: #161c2b; }
    QPushButton:disabled { color: #8b93a6; background: #10131b; border-color: #1f2430; }

    QPushButton#PrimaryButton { background: #3a4a7a; border-color: #5d74c5; }
    QPushButton#PrimaryButton:hover { background: #42558d; border-color: #6f86da; }
    QPushButton#PrimaryButton:pressed { background: #33406a; }

    QLabel#BrandTitle {
        font-size: 20pt; font-weight: 800; color: #ffffff;
        letter-spacing: 1px;
    }
    QLabel#BrandSub { color: #8b93a6; font-size: 9pt; }

    QLabel#HeaderTitle { font-size: 15pt; font-weight: 800; color: #ffffff; }
    QLabel#HeaderSub { color: #aab1c2; }

    QLabel#StatusLabel {
        background: #0f1115; border: 1px solid #2a2f3a; border-radius: 14px;
        padding: 10px 12px; color: #cfd3dc;
    }

    QProgressBar {
        border: 1px solid #2a2f3a; border-radius: 10px;
        background: #0f1115; height: 20px; text-align: center;
    }
    QProgressBar::chunk { background: #3a4a7a; border-radius: 8px; }

    QScrollArea { border: none; background: transparent; }
    """)


# -------------------------------------------------------------------
# Clickable image
# -------------------------------------------------------------------
class ClickableImageLabel(QtWidgets.QLabel):
    def __init__(self, img_rel_path: str, parent=None):
        super().__init__(parent)
        self.original_pixmap = None
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMaximumHeight(IMG_HEIGHT)

        if img_rel_path:
            pix = QtGui.QPixmap(resource_path(img_rel_path))
            if not pix.isNull():
                self.original_pixmap = pix
                self.setPixmap(pix.scaledToHeight(
                    IMG_HEIGHT, QtCore.Qt.SmoothTransformation))

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
        dlg.resize(min(self.original_pixmap.width() + 60, 1200),
                   min(self.original_pixmap.height() + 90, 800))
        dlg.exec_()


def make_tab_image_label(img_path: str) -> QtWidgets.QLabel:
    if not img_path:
        lbl = QtWidgets.QLabel()
        lbl.setFixedHeight(0)
        return lbl
    return ClickableImageLabel(img_path)


# =============================
# Shared helpers (формат записей — без изменений)
# =============================
REC_LEN = 17
OFF_P = 0
OFF_Q = 8
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


def read_record_raw(data: bytes, stsrt: int) -> Tuple[int, int, bool]:
    rec = data[stsrt:stsrt + REC_LEN]
    if len(rec) != REC_LEN:
        return (0, 0, False)
    p_raw = decode_raw_u32_weird(rec[OFF_P:OFF_P + 4])
    q_raw = decode_raw_u32_weird(rec[OFF_Q:OFF_Q + 4])
    ok = (crc_xor_16(rec[0:16]) == rec[OFF_CRC])
    return (p_raw, q_raw, ok)


def read_record(data: bytes, stsrt: int, coef: int) -> Tuple[float, float, bool]:
    p_raw, q_raw, ok = read_record_raw(data, stsrt)
    return (p_raw / coef, q_raw / coef, ok)


def write_record(data: bytearray, stsrt: int, p: float, q: float, coef: int) -> None:
    p_raw = int(round(p * coef))
    q_raw = int(round(q * coef))
    data[stsrt + OFF_P:stsrt + OFF_P + 4] = encode_raw_u32_weird(p_raw)
    data[stsrt + OFF_Q:stsrt + OFF_Q + 4] = encode_raw_u32_weird(q_raw)
    data[stsrt + OFF_CRC] = crc_xor_16(bytes(data[stsrt:stsrt + 16]))


K_srt03 = 4490.54 / 18987.70
K_AR = 1445.71 / 6384.36


# =============================
# Панель работы с микросхемой
# =============================
class MemoryPanel(QtWidgets.QGroupBox):
    """
    Выбор микросхемы, чтение и запись через программатор.

    Панель одна на вкладку и умеет ровно три вещи: определить микросхему,
    вычитать её целиком и записать обратно то, что вкладка подготовила.
    Запись идёт только по изменившимся байтам и сразу проверяется чтением.
    """

    dataRead = QtCore.pyqtSignal(bytes)

    def __init__(self, chip_names, parent=None):
        super().__init__("Микросхема", parent)

        self.buf = None            # то, что прочитали
        self._busy = False

        grid = QtWidgets.QGridLayout(self)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)

        grid.addWidget(QtWidgets.QLabel("Тип:"), 0, 0)
        self.chip_box = QtWidgets.QComboBox()
        for name in chip_names:
            self.chip_box.addItem(CHIPS[name]["title"], name)
        grid.addWidget(self.chip_box, 0, 1, 1, 2)

        self.btn_detect = QtWidgets.QPushButton("Определить")
        self.btn_detect.setToolTip(
            "Прочитать идентификатор и проверить реальный объём памяти")
        self.btn_detect.clicked.connect(self.detect)
        grid.addWidget(self.btn_detect, 0, 3)

        self.btn_read = QtWidgets.QPushButton("Прочитать из памяти")
        self.btn_read.clicked.connect(self.read_chip)
        grid.addWidget(self.btn_read, 0, 4)

        self.btn_write = QtWidgets.QPushButton("Записать в память")
        self.btn_write.setObjectName("PrimaryButton")
        self.btn_write.setEnabled(False)
        grid.addWidget(self.btn_write, 0, 5)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        grid.addWidget(self.progress, 1, 0, 1, 6)

        grid.setColumnStretch(2, 1)

    # ── Служебное ─────────────────────────────────────────────────────

    def chip(self) -> str:
        return self.chip_box.currentData()

    def size(self) -> int:
        return CHIPS[self.chip()]["size"]

    def _set_busy(self, busy: bool):
        self._busy = busy
        for w in (self.btn_detect, self.btn_read, self.btn_write,
                  self.chip_box):
            w.setEnabled(not busy)
        if not busy:
            self.btn_write.setEnabled(self.buf is not None)
        self.progress.setVisible(busy)
        if not busy:
            self.progress.setValue(0)
        QtWidgets.QApplication.processEvents()

    def _progress(self, percent: int):
        self.progress.setValue(percent)
        QtWidgets.QApplication.processEvents()

    def _session(self):
        """Открыть программатор и вернуть готовый к работе SPIFram"""
        transport = CH341SPI()
        transport.open()
        return SPIFram(self.chip(), transport), transport

    def report(self, text: str):
        """Отдать сообщение вкладке через родителя"""
        parent = self.parent()
        while parent is not None and not hasattr(parent, "set_status"):
            parent = parent.parent()
        if parent is not None:
            parent.set_status(text)

    # ── Действия ──────────────────────────────────────────────────────

    def detect(self):
        self._set_busy(True)
        transport = None
        try:
            fram, transport = self._session()
            ident = fram.read_id()
            actual = probe_size(fram)

            lines = [f"Программатор открыт, выбран {fram.title}"]
            if ident:
                lines.append("Идентификатор: " + ident.hex(" ").upper())
            else:
                lines.append("Идентификатор: микросхема его не поддерживает")

            if actual == fram.size:
                lines.append(f"Объём подтверждён: {actual} байт")
            else:
                lines.append(
                    f"ВНИМАНИЕ: реальный объём {actual} байт вместо "
                    f"{fram.size}. Адреса заворачиваются — выбран не тот тип."
                )
            self.report("\n".join(lines))

        except SPIError as exc:
            self.report(f"Ошибка: {exc}")
        finally:
            if transport is not None:
                transport.close()
            self._set_busy(False)

    def read_chip(self):
        self._set_busy(True)
        transport = None
        try:
            fram, transport = self._session()
            data = fram.read_all(progress=self._progress)
            self.buf = data
            self.report(f"Прочитано {len(data)} байт из {fram.title}")
            self.dataRead.emit(data)
        except SPIError as exc:
            self.report(f"Ошибка чтения: {exc}")
        finally:
            if transport is not None:
                transport.close()
            self._set_busy(False)

    def write_chip(self, new_data: bytes) -> bool:
        """
        Записать подготовленный буфер, затронув только изменившееся,
        и сразу проверить чтением.
        """
        if self.buf is None:
            self.report("Сначала прочитайте память.")
            return False
        if len(new_data) != len(self.buf):
            self.report(
                f"Длина не совпадает: подготовлено {len(new_data)} байт, "
                f"в памяти {len(self.buf)}.")
            return False

        self._set_busy(True)
        transport = None
        try:
            fram, transport = self._session()
            written = fram.write_changed(self.buf, new_data,
                                         progress=self._progress)

            if written == 0:
                self.report("Изменений нет — в память ничего не писалось.")
                return True

            ok, bad = fram.verify(new_data)
            if ok:
                self.buf = bytes(new_data)
                self.report(
                    f"Записано {written} байт, проверка чтением пройдена.")
                return True

            preview = ", ".join(
                f"0x{a:04X}: ждали {e:02X}, прочитали {g:02X}"
                for a, e, g in bad[:5])
            self.report(
                f"Записано {written} байт, но проверка НЕ пройдена: "
                f"{len(bad)} расхождений.\n{preview}")
            return False

        except SPIError as exc:
            self.report(f"Ошибка записи: {exc}")
            return False
        finally:
            if transport is not None:
                transport.close()
            self._set_busy(False)


# =============================
# TAB 1: art03 (T1/T2 + totals)
# =============================
T1_REC_STsrtS = [0x0000, 0x0100]
T2_REC_STsrtS = [0x0011, 0x0111]
TOT_REC_STsrtS = [0x0200]


def _close(a: float, b: float, tol: float = 0.02) -> bool:
    return abs(a - b) <= tol


def choose_totals(t1p, t1q, t2p, t2q, totp_file, totq_file) -> Tuple[float, float, str]:
    sum_p = t1p + t2p
    sum_q = t1q + t2q
    if _close(totp_file, sum_p, tol=0.02) and _close(totq_file, sum_q, tol=0.02):
        return totp_file, totq_file, "ПАМЯТЬ"
    return sum_p, sum_q, "СУММА"


@dataclass
class srtReadings:
    t1_p: float
    t2_p: float
    t1_q: float
    t2_q: float
    tot_p: float
    tot_q: float


class srt03Tab(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self._file_k = None
        self._sum_k = None
        self._tot_source = "ПАМЯТЬ"

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        header = QtWidgets.QHBoxLayout()
        titles = QtWidgets.QVBoxLayout()
        self.h1 = QtWidgets.QLabel("ART — активная/реактивная (T1/T2 + общие)")
        self.h1.setObjectName("HeaderTitle")
        self.h2 = QtWidgets.QLabel(
            "Вводишь общие P и T1 P → T2 P считается автоматически. Q считается по k.")
        self.h2.setObjectName("HeaderSub")
        titles.addWidget(self.h1)
        titles.addWidget(self.h2)
        header.addLayout(titles)
        header.addStretch(1)
        root.addLayout(header)

        root.addWidget(make_tab_image_label(IMG_srt03_IN_TAB))

        self.mem = MemoryPanel(TAB_CHIPS["srt03"], self)
        self.mem.dataRead.connect(self.on_data_read)
        self.mem.btn_write.clicked.connect(self.apply_patch)
        root.addWidget(self.mem)

        opts = QtWidgets.QGroupBox("Параметры")
        opts_l = QtWidgets.QGridLayout(opts)
        opts_l.setHorizontalSpacing(10)
        opts_l.setVerticalSpacing(10)

        self.coef_box = QtWidgets.QComboBox()
        self.coef_box.addItems(["1000", "2000"])
        self.coef_box.setCurrentIndex(0)

        self.k_mode = QtWidgets.QComboBox()
        self.k_mode.addItems([
            "art03 preset (4490.54/18987.70)",
            "AR preset (1445.71/6384.36)",
            "Из памяти Tot@0x0200 (TotQ/TotP)",
            "Из суммы (T1+T2)",
            "Ручной (поле k)",
        ])
        self.k_mode.setCurrentIndex(0)

        self.ed_k = QtWidgets.QLineEdit()
        dvk = QtGui.QDoubleValidator(0.0, 9999.0, 10, self)
        dvk.setNotation(QtGui.QDoubleValidator.StandardNotation)
        self.ed_k.setValidator(dvk)
        self.ed_k.setText(f"{K_srt03:.10f}")
        self.ed_k.setToolTip("k = Q/P")

        opts_l.addWidget(QtWidgets.QLabel("Множитель (коэф):"), 0, 0)
        opts_l.addWidget(self.coef_box, 0, 1)
        opts_l.addWidget(QtWidgets.QLabel("Режим k:"), 0, 2)
        opts_l.addWidget(self.k_mode, 0, 3, 1, 2)
        opts_l.addWidget(QtWidgets.QLabel("k:"), 0, 5)
        opts_l.addWidget(self.ed_k, 0, 6)
        root.addWidget(opts)

        calc_box = QtWidgets.QGroupBox("Расчёт / Подстановка")
        form = QtWidgets.QGridLayout(calc_box)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(10)

        self.out_totp = QtWidgets.QDoubleSpinBox(); self._setup_spin(self.out_totp)
        self.out_totq = QtWidgets.QLineEdit(); self.out_totq.setReadOnly(True)
        self.in_t1p = QtWidgets.QDoubleSpinBox(); self._setup_spin(self.in_t1p)
        self.in_t2p = QtWidgets.QDoubleSpinBox(); self._setup_spin(self.in_t2p); self.in_t2p.setEnabled(False)
        self.in_t1q = QtWidgets.QDoubleSpinBox(); self._setup_spin(self.in_t1q); self.in_t1q.setEnabled(False)
        self.in_t2q = QtWidgets.QDoubleSpinBox(); self._setup_spin(self.in_t2q); self.in_t2q.setEnabled(False)

        r = 0
        form.addWidget(QtWidgets.QLabel("Общие P (активная):"), r, 0); form.addWidget(self.out_totp, r, 1)
        form.addWidget(QtWidgets.QLabel("Общие Q (авто):"), r, 2); form.addWidget(self.out_totq, r, 3, 1, 3)
        r += 1
        form.addWidget(QtWidgets.QLabel("T1 P:"), r, 0); form.addWidget(self.in_t1p, r, 1)
        form.addWidget(QtWidgets.QLabel("T2 P (TotP − T1P):"), r, 2); form.addWidget(self.in_t2p, r, 3, 1, 3)
        r += 1
        form.addWidget(QtWidgets.QLabel("T1 Q (авто):"), r, 0); form.addWidget(self.in_t1q, r, 1)
        form.addWidget(QtWidgets.QLabel("T2 Q (авто):"), r, 2); form.addWidget(self.in_t2q, r, 3, 1, 3)
        root.addWidget(calc_box)

        self.lbl_status = QtWidgets.QLabel("Микросхема не прочитана")
        self.lbl_status.setObjectName("StatusLabel")
        self.lbl_status.setWordWrap(True)
        root.addWidget(self.lbl_status)

        root.addStretch(1)

        self.in_t1p.valueChanged.connect(self.refresh_totals)
        self.out_totp.valueChanged.connect(self.refresh_totals)
        self.coef_box.currentIndexChanged.connect(self.reparse)
        self.k_mode.currentIndexChanged.connect(self.on_k_mode_changed)
        self.ed_k.textChanged.connect(self.refresh_totals)

        self.on_k_mode_changed()

    def set_status(self, text: str):
        self.lbl_status.setText(text)

    def _setup_spin(self, w: QtWidgets.QDoubleSpinBox):
        w.setDecimals(2)
        w.setRange(0, 999999999.99)
        w.setSingleStep(0.01)

    def coef(self) -> int:
        return int(self.coef_box.currentText())

    def on_data_read(self, data: bytes):
        self.reparse()

    def reparse(self):
        data = self.mem.buf
        if data is None:
            return

        coef = self.coef()
        t1p, t1q, ok1 = read_record(data, T1_REC_STsrtS[0], coef)
        t2p, t2q, ok2 = read_record(data, T2_REC_STsrtS[0], coef)
        totp_f, totq_f, ok3 = read_record(data, TOT_REC_STsrtS[0], coef)

        self._file_k = (totq_f / totp_f) if totp_f > 0 else None
        sum_p, sum_q = t1p + t2p, t1q + t2q
        self._sum_k = (sum_q / sum_p) if sum_p > 0 else None

        totp_use, totq_use, src = choose_totals(t1p, t1q, t2p, t2q, totp_f, totq_f)
        self._tot_source = src

        self.out_totp.blockSignals(True); self.in_t1p.blockSignals(True)
        self.out_totp.setValue(totp_use)
        self.in_t1p.setValue(t1p)
        self.out_totp.blockSignals(False); self.in_t1p.blockSignals(False)

        self.on_k_mode_changed()
        self.refresh_totals()

        fk = self._file_k if self._file_k is not None else float("nan")
        sk = self._sum_k if self._sum_k is not None else float("nan")
        self.set_status(
            f"Прочитано {len(data)} байт из {CHIPS[self.mem.chip()]['title']}\n"
            f"CRC: T1={'OK' if ok1 else 'BAD'} | T2={'OK' if ok2 else 'BAD'} "
            f"| TOT@0x0200={'OK' if ok3 else 'BAD'}\n"
            f"Tot@0x0200: P={totp_f:.2f} Q={totq_f:.2f} (k={fk:.10f})\n"
            f"Tot(СУММА): P={sum_p:.2f} Q={sum_q:.2f} (k={sk:.10f})\n"
            f"Показываю Tot как: {self._tot_source}"
        )

    def on_k_mode_changed(self):
        mode = self.k_mode.currentIndex()
        if mode == 0:
            self.ed_k.setText(f"{K_srt03:.10f}"); self.ed_k.setEnabled(False)
        elif mode == 1:
            self.ed_k.setText(f"{K_AR:.10f}"); self.ed_k.setEnabled(False)
        elif mode == 2:
            k = self._file_k if self._file_k and self._file_k > 0 else K_srt03
            self.ed_k.setText(f"{k:.10f}"); self.ed_k.setEnabled(False)
        elif mode == 3:
            k = self._sum_k if self._sum_k and self._sum_k > 0 else K_srt03
            self.ed_k.setText(f"{k:.10f}"); self.ed_k.setEnabled(False)
        else:
            if not self.ed_k.text().strip():
                self.ed_k.setText(f"{K_srt03:.10f}")
            self.ed_k.setEnabled(True)
        self.refresh_totals()

    def _parse_k(self) -> float:
        try:
            k = float(self.ed_k.text().strip().replace(',', '.'))
        except Exception:
            k = K_srt03
        return k if k > 0 else K_srt03

    def refresh_totals(self):
        totp = float(self.out_totp.value())
        t1p = float(self.in_t1p.value())
        t2p = max(0.0, totp - t1p)

        k = self._parse_k()
        t1q, t2q = t1p * k, t2p * k

        for w, v in ((self.in_t2p, t2p), (self.in_t1q, t1q), (self.in_t2q, t2q)):
            w.blockSignals(True); w.setValue(v); w.blockSignals(False)

        self.out_totq.setText(f"{(t1q + t2q):.2f}")

    def build_buffer(self) -> bytes:
        data = bytearray(self.mem.buf)
        coef = self.coef()

        totp = float(self.out_totp.value())
        t1p = float(self.in_t1p.value())
        t2p = max(0.0, totp - t1p)
        k = self._parse_k()
        t1q, t2q = t1p * k, t2p * k

        for s in T1_REC_STsrtS:
            write_record(data, s, t1p, t1q, coef)
        for s in T2_REC_STsrtS:
            write_record(data, s, t2p, t2q, coef)
        for s in TOT_REC_STsrtS:
            write_record(data, s, totp, t1q + t2q, coef)

        return bytes(data)

    def apply_patch(self):
        if self.mem.buf is None:
            self.set_status("Сначала прочитайте память.")
            return
        self.mem.write_chip(self.build_buffer())


# =============================
# TAB 2: AR01/AR02 totals
# =============================
BASE_OFF = 0x0000
DUP_OFF = 0x0100


@dataclass
class ParsedRecord:
    ok: bool
    p_raw: int
    q_raw: int
    crc_file: int
    crc_calc: int


def parse_record(buf: bytes, base_off: int) -> ParsedRecord:
    if len(buf) < base_off + REC_LEN:
        return ParsedRecord(False, 0, 0, 0, 0)
    rec = buf[base_off: base_off + REC_LEN]
    crc_file = rec[OFF_CRC]
    crc_calc = crc_xor_16(rec[:16])
    p_raw = decode_raw_u32_weird(rec[OFF_P:OFF_P + 4])
    q_raw = decode_raw_u32_weird(rec[OFF_Q:OFF_Q + 4])
    return ParsedRecord(crc_file == crc_calc, p_raw, q_raw, crc_file, crc_calc)


def detect_coef_from_raw(p_raw: int, q_raw: int) -> int:
    if (p_raw % 20 == 0) and (q_raw % 20 == 0):
        return 2000
    return 1000


def patch_record_totals(buf: bytearray, p_value: float, q_value: float, coef: int) -> None:
    p_raw = int(round(p_value * coef))
    q_raw = int(round(q_value * coef))
    buf[BASE_OFF + OFF_P:BASE_OFF + OFF_P + 4] = encode_raw_u32_weird(p_raw)
    buf[BASE_OFF + OFF_Q:BASE_OFF + OFF_Q + 4] = encode_raw_u32_weird(q_raw)
    buf[BASE_OFF + OFF_CRC] = crc_xor_16(bytes(buf[BASE_OFF:BASE_OFF + 16]))
    buf[DUP_OFF:DUP_OFF + REC_LEN] = buf[BASE_OFF:BASE_OFF + REC_LEN]


class srtotalsTab(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self._file_k = None

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        header = QtWidgets.QHBoxLayout()
        titles = QtWidgets.QVBoxLayout()
        h1 = QtWidgets.QLabel("AR — только общие показания")
        h1.setObjectName("HeaderTitle")
        h2 = QtWidgets.QLabel("Вводишь общие P → общая Q считается автоматически по k.")
        h2.setObjectName("HeaderSub")
        titles.addWidget(h1); titles.addWidget(h2)
        header.addLayout(titles); header.addStretch(1)
        root.addLayout(header)

        root.addWidget(make_tab_image_label(IMG_AR_IN_TAB))

        self.mem = MemoryPanel(TAB_CHIPS["ar"], self)
        self.mem.dataRead.connect(self.on_data_read)
        self.mem.btn_write.clicked.connect(self.write_back)
        root.addWidget(self.mem)

        settings_box = QtWidgets.QGroupBox("Настройки")
        s = QtWidgets.QGridLayout(settings_box)
        s.setHorizontalSpacing(10); s.setVerticalSpacing(10)

        self.rb_auto = QtWidgets.QRadioButton("Авто (по дампу)")
        self.rb_1000 = QtWidgets.QRadioButton("AR02 = 1000")
        self.rb_2000 = QtWidgets.QRadioButton("AR01 = 2000")
        self.rb_auto.setChecked(True)

        coef_row = QtWidgets.QHBoxLayout()
        coef_row.addWidget(self.rb_auto); coef_row.addWidget(self.rb_1000)
        coef_row.addWidget(self.rb_2000); coef_row.addStretch(1)

        self.k_mode = QtWidgets.QComboBox()
        self.k_mode.addItems(["AR preset (1445.71/6384.36)",
                              "Из памяти (Q/P)", "Ручной (поле k)"])
        self.k_mode.setCurrentIndex(0)

        self.ed_k = QtWidgets.QLineEdit()
        dv = QtGui.QDoubleValidator(0.0, 9999.0, 10, self)
        dv.setNotation(QtGui.QDoubleValidator.StandardNotation)
        self.ed_k.setValidator(dv)
        self.ed_k.setText(f"{K_AR:.10f}")
        self.ed_k.setEnabled(False)

        s.addWidget(QtWidgets.QLabel("Множитель (коэф):"), 0, 0)
        s.addLayout(coef_row, 0, 1, 1, 4)
        s.addWidget(QtWidgets.QLabel("Режим k:"), 1, 0)
        s.addWidget(self.k_mode, 1, 1, 1, 2)
        s.addWidget(QtWidgets.QLabel("k:"), 1, 3)
        s.addWidget(self.ed_k, 1, 4)
        root.addWidget(settings_box)

        cur = QtWidgets.QGroupBox("Текущие значения из памяти (0x0000)")
        cur_l = QtWidgets.QGridLayout(cur)
        cur_l.setHorizontalSpacing(10); cur_l.setVerticalSpacing(10)
        self.ed_cur_p = QtWidgets.QLineEdit(); self.ed_cur_p.setReadOnly(True)
        self.ed_cur_q = QtWidgets.QLineEdit(); self.ed_cur_q.setReadOnly(True)
        cur_l.addWidget(QtWidgets.QLabel("P:"), 0, 0); cur_l.addWidget(self.ed_cur_p, 0, 1)
        cur_l.addWidget(QtWidgets.QLabel("Q:"), 0, 2); cur_l.addWidget(self.ed_cur_q, 0, 3)
        root.addWidget(cur)

        new = QtWidgets.QGroupBox("Новые значения (запись в 0x0000 и 0x0100)")
        new_l = QtWidgets.QGridLayout(new)
        new_l.setHorizontalSpacing(10); new_l.setVerticalSpacing(10)
        self.ed_new_p = QtWidgets.QLineEdit()
        self.ed_new_q = QtWidgets.QLineEdit(); self.ed_new_q.setReadOnly(True)
        dv2 = QtGui.QDoubleValidator(0.0, 999999999.99, 2, self)
        dv2.setNotation(QtGui.QDoubleValidator.StandardNotation)
        self.ed_new_p.setValidator(dv2)
        self.ed_new_p.setPlaceholderText("например 6384.36")
        self.ed_new_q.setPlaceholderText("авто")
        new_l.addWidget(QtWidgets.QLabel("P (общие активные):"), 0, 0); new_l.addWidget(self.ed_new_p, 0, 1)
        new_l.addWidget(QtWidgets.QLabel("Q (общие реактивные):"), 0, 2); new_l.addWidget(self.ed_new_q, 0, 3)
        root.addWidget(new)

        self.lbl_status = QtWidgets.QLabel("Микросхема не прочитана")
        self.lbl_status.setObjectName("StatusLabel")
        self.lbl_status.setWordWrap(True)
        root.addWidget(self.lbl_status)

        hint = QtWidgets.QLabel(
            "Формат: P 0..3, Q 8..11, CRC 16, дубль +0x100. "
            "CRC = 0xF0 XOR 16 байт данных.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#aab1c2;")
        root.addWidget(hint)

        root.addStretch(1)

        self.ed_new_p.textChanged.connect(self.update_auto_q)
        self.ed_k.textChanged.connect(self.update_auto_q)
        self.k_mode.currentIndexChanged.connect(self.on_k_mode_changed)
        self.rb_auto.toggled.connect(self.refresh_view)
        self.rb_1000.toggled.connect(self.refresh_view)
        self.rb_2000.toggled.connect(self.refresh_view)

        self.on_k_mode_changed()

    def set_status(self, text: str):
        self.lbl_status.setText(text)

    def _parse_float(self, s, default=float('nan')):
        s = ("" if s is None else str(s)).strip().replace(',', '.')
        if not s:
            return default
        try:
            return float(s)
        except ValueError:
            return default

    def chosen_coef(self, parsed: ParsedRecord) -> int:
        if self.rb_1000.isChecked():
            return 1000
        if self.rb_2000.isChecked():
            return 2000
        return detect_coef_from_raw(parsed.p_raw, parsed.q_raw)

    def on_k_mode_changed(self):
        mode = self.k_mode.currentIndex()
        if mode == 0:
            self.ed_k.setText(f"{K_AR:.10f}"); self.ed_k.setEnabled(False)
        elif mode == 1:
            k = self._file_k if self._file_k and self._file_k > 0 else K_AR
            self.ed_k.setText(f"{k:.10f}"); self.ed_k.setEnabled(False)
        else:
            if not self.ed_k.text().strip():
                self.ed_k.setText(f"{K_AR:.10f}")
            self.ed_k.setEnabled(True)
        self.update_auto_q()

    def _parse_k(self) -> float:
        k = self._parse_float(self.ed_k.text(), default=K_AR)
        return K_AR if (math.isnan(k) or k <= 0) else k

    def update_auto_q(self):
        p = self._parse_float(self.ed_new_p.text())
        if math.isnan(p):
            self.ed_new_q.clear()
            return
        self.ed_new_q.setText(f"{(p * self._parse_k()):.2f}")

    def on_data_read(self, data: bytes):
        if len(data) < DUP_OFF + REC_LEN:
            self.set_status(
                f"Прочитано {len(data)} байт, а нужно минимум "
                f"{DUP_OFF + REC_LEN}: дубль лежит по 0x0100.")
            return

        parsed = parse_record(data, BASE_OFF)
        coef = self.chosen_coef(parsed)
        self._file_k = None
        if parsed.p_raw > 0:
            p = parsed.p_raw / float(coef)
            q = parsed.q_raw / float(coef)
            self._file_k = q / p if p > 0 else None

        self.on_k_mode_changed()
        self.refresh_view()

    def refresh_view(self):
        data = self.mem.buf
        if data is None:
            self.set_status("Микросхема не прочитана")
            self.ed_cur_p.clear(); self.ed_cur_q.clear()
            return

        parsed = parse_record(data, BASE_OFF)
        coef = self.chosen_coef(parsed)
        p = parsed.p_raw / float(coef) if coef else 0.0
        q = parsed.q_raw / float(coef) if coef else 0.0

        self.ed_cur_p.setText(f"{p:.2f}")
        self.ed_cur_q.setText(f"{q:.2f}")

        parsed_dup = parse_record(data, DUP_OFF)
        same = data[BASE_OFF:BASE_OFF + REC_LEN] == data[DUP_OFF:DUP_OFF + REC_LEN]
        fk = self._file_k if self._file_k is not None else float("nan")

        self.set_status(
            f"{CHIPS[self.mem.chip()]['title']} — прочитано {len(data)} байт\n"
            f"CRC(0x0000): {'OK' if parsed.ok else 'FAIL'} "
            f"(в памяти=0x{parsed.crc_file:02X}, расчёт=0x{parsed.crc_calc:02X})\n"
            f"Коэф: {coef} | CRC(0x0100): {'OK' if parsed_dup.ok else 'FAIL'}; "
            f"дубль {'совпадает' if same else 'НЕ совпадает'}\n"
            f"k={fk:.10f}"
        )
        self.update_auto_q()

    def write_back(self):
        if self.mem.buf is None:
            self.set_status("Сначала прочитайте память.")
            return

        new_p = self._parse_float(self.ed_new_p.text())
        if math.isnan(new_p):
            QtWidgets.QMessageBox.warning(
                self, 'Ошибка', 'Введите корректное число: Общие активные (P).')
            return

        new_q = new_p * self._parse_k()
        self.ed_new_q.setText(f"{new_q:.2f}")

        parsed = parse_record(self.mem.buf, BASE_OFF)
        coef = self.chosen_coef(parsed)

        out = bytearray(self.mem.buf)
        patch_record_totals(out, new_p, new_q, coef)

        if self.mem.write_chip(bytes(out)):
            self.refresh_view()


# =============================
# TAB 3: srt29 (T1/T2 + SUM, 4 зеркала)
# =============================
MIRROR_STRIDE = 0x2000
MIRROR_COUNT = 4

SRT29_T1_OFFS = [0x0000, 0x0100]
SRT29_T2_OFFS = [0x0011, 0x0111]
SRT29_SUM_OFFS = [0x06A6, 0x06FB]
SRT29_BLK_T1 = 0x11
SRT29_BLK_T2 = 0x22

SRT29_COEF = 2000


def srt29_set_p_keep_q(data: bytearray, stsrt: int, p: float, coef: int) -> bool:
    """
    Записать только P, сохранив исходное Q. CRC пересчитывается.
    Если показание (с точностью 0.01) не изменилось — байты не трогаются.
    """
    p_old_raw, q_old_raw, _ = read_record_raw(data, stsrt)
    if round(p_old_raw / coef, 2) == round(p, 2):
        return False
    p_new_raw = int(round(p * coef))
    data[stsrt + OFF_P:stsrt + OFF_P + 4] = encode_raw_u32_weird(p_new_raw)
    data[stsrt + OFF_Q:stsrt + OFF_Q + 4] = encode_raw_u32_weird(q_old_raw)
    data[stsrt + OFF_CRC] = crc_xor_16(bytes(data[stsrt:stsrt + 16]))
    return True


class srt29Tab(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        header = QtWidgets.QHBoxLayout()
        titles = QtWidgets.QVBoxLayout()
        h1 = QtWidgets.QLabel("231-AT-01 — T1/T2 + общая сумма (4 зеркала)")
        h1.setObjectName("HeaderTitle")
        h2 = QtWidgets.QLabel(
            "Вводишь T1 и T2 → сумма считается сама. "
            "Пишет во все 4 зеркала + итоговый блок.")
        h2.setObjectName("HeaderSub")
        titles.addWidget(h1); titles.addWidget(h2)
        header.addLayout(titles); header.addStretch(1)
        root.addLayout(header)

        self.mem = MemoryPanel(TAB_CHIPS["srt29"], self)
        self.mem.dataRead.connect(self.on_data_read)
        self.mem.btn_write.clicked.connect(self.apply_patch)
        root.addWidget(self.mem)

        opts = QtWidgets.QGroupBox("Параметры")
        opts_l = QtWidgets.QGridLayout(opts)
        self.coef_box = QtWidgets.QComboBox()
        self.coef_box.addItems(["2000", "1000"])
        self.coef_box.setCurrentIndex(0)
        opts_l.addWidget(QtWidgets.QLabel("Множитель (коэф):"), 0, 0)
        opts_l.addWidget(self.coef_box, 0, 1)
        opts_l.setColumnStretch(2, 1)
        root.addWidget(opts)

        calc_box = QtWidgets.QGroupBox("Показания")
        form = QtWidgets.QGridLayout(calc_box)
        form.setHorizontalSpacing(10); form.setVerticalSpacing(10)

        self.in_t1 = QtWidgets.QDoubleSpinBox(); self._setup_spin(self.in_t1)
        self.in_t2 = QtWidgets.QDoubleSpinBox(); self._setup_spin(self.in_t2)
        self.out_sum = QtWidgets.QLineEdit(); self.out_sum.setReadOnly(True)

        form.addWidget(QtWidgets.QLabel("T1 (активная):"), 0, 0); form.addWidget(self.in_t1, 0, 1)
        form.addWidget(QtWidgets.QLabel("T2 (активная):"), 0, 2); form.addWidget(self.in_t2, 0, 3)
        form.addWidget(QtWidgets.QLabel("Сумма (T1+T2, авто):"), 1, 0); form.addWidget(self.out_sum, 1, 1, 1, 3)
        root.addWidget(calc_box)

        self.lbl_status = QtWidgets.QLabel("Микросхема не прочитана")
        self.lbl_status.setObjectName("StatusLabel")
        self.lbl_status.setWordWrap(True)
        root.addWidget(self.lbl_status)

        root.addStretch(1)

        self.in_t1.valueChanged.connect(self.refresh_sum)
        self.in_t2.valueChanged.connect(self.refresh_sum)
        self.coef_box.currentIndexChanged.connect(self.reparse)

    def set_status(self, text: str):
        self.lbl_status.setText(text)

    def _setup_spin(self, w: QtWidgets.QDoubleSpinBox):
        w.setDecimals(2)
        w.setRange(0, 999999999.99)
        w.setSingleStep(0.01)

    def coef(self) -> int:
        return int(self.coef_box.currentText())

    def refresh_sum(self):
        s = float(self.in_t1.value()) + float(self.in_t2.value())
        self.out_sum.setText(f"{s:.2f}")

    def on_data_read(self, data: bytes):
        self.reparse()

    def reparse(self):
        data = self.mem.buf
        if data is None:
            return

        coef = self.coef()
        t1_p, _, ok_t1 = read_record(data, SRT29_T1_OFFS[0], coef)
        t2_p, _, ok_t2 = read_record(data, SRT29_T2_OFFS[0], coef)
        sum_p, _, ok_s = read_record(data, SRT29_SUM_OFFS[0], coef)

        self.in_t1.blockSignals(True); self.in_t2.blockSignals(True)
        self.in_t1.setValue(t1_p); self.in_t2.setValue(t2_p)
        self.in_t1.blockSignals(False); self.in_t2.blockSignals(False)
        self.refresh_sum()

        mirrors_ok = all(
            data[m:m + MIRROR_STRIDE] == data[0:MIRROR_STRIDE]
            for m in (0x2000, 0x4000, 0x6000)
            if len(data) >= m + MIRROR_STRIDE
        )

        self.set_status(
            f"{CHIPS[self.mem.chip()]['title']} — прочитано {len(data)} байт\n"
            f"CRC: T1={'OK' if ok_t1 else 'BAD'} | T2={'OK' if ok_t2 else 'BAD'} "
            f"| SUM={'OK' if ok_s else 'BAD'}\n"
            f"Из памяти: T1={t1_p:.2f}  T2={t2_p:.2f}  SUM={sum_p:.2f}\n"
            f"Зеркала (0x2000/0x4000/0x6000) совпадают с базой: "
            f"{'да' if mirrors_ok else 'НЕТ'}"
        )

    def build_buffer(self) -> Tuple[bytes, int]:
        data = bytearray(self.mem.buf)
        coef = self.coef()
        t1 = float(self.in_t1.value())
        t2 = float(self.in_t2.value())
        s = t1 + t2

        points = 0
        for m in range(MIRROR_COUNT):
            base = m * MIRROR_STRIDE
            if base + MIRROR_STRIDE > len(data):
                continue
            for off in SRT29_T1_OFFS:
                points += srt29_set_p_keep_q(data, base + off, t1, coef)
            for off in SRT29_T2_OFFS:
                points += srt29_set_p_keep_q(data, base + off, t2, coef)
            for blk in SRT29_SUM_OFFS:
                points += srt29_set_p_keep_q(data, base + blk, s, coef)
                points += srt29_set_p_keep_q(data, base + blk + SRT29_BLK_T1, t1, coef)
                points += srt29_set_p_keep_q(data, base + blk + SRT29_BLK_T2, t2, coef)

        return bytes(data), points

    def apply_patch(self):
        if self.mem.buf is None:
            self.set_status("Сначала прочитайте память.")
            return

        buf, points = self.build_buffer()
        if self.mem.write_chip(buf):
            self.set_status(self.lbl_status.text()
                            + f"\nЗаписей пропатчено: {points}")


# =============================
# Main Window
# =============================
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1040, 800)

        central = QtWidgets.QWidget()
        central_l = QtWidgets.QVBoxLayout(central)
        central_l.setContentsMargins(14, 14, 14, 14)
        central_l.setSpacing(10)

        # Общая шапка над вкладками.
        head = QtWidgets.QHBoxLayout()
        head.setSpacing(12)

        self.logo = QtWidgets.QLabel()
        icon = load_app_icon()
        if not icon.isNull():
            self.logo.setPixmap(icon.pixmap(40, 40))
        head.addWidget(self.logo)

        names = QtWidgets.QVBoxLayout()
        names.setSpacing(0)
        brand = QtWidgets.QLabel(APP_NAME)
        brand.setObjectName("BrandTitle")
        sub = QtWidgets.QLabel("Прямая работа с SPI FRAM через программатор CH341")
        sub.setObjectName("BrandSub")
        names.addWidget(brand)
        names.addWidget(sub)
        head.addLayout(names)
        head.addStretch(1)

        central_l.addLayout(head)

        tabs = QtWidgets.QTabWidget()
        tabs.setDocumentMode(True)

        self.tab_srt = srt03Tab()
        self.tab_ar = srtotalsTab()
        self.tab_srt29 = srt29Tab()

        if TAB_ICON_srt03:
            tabs.addTab(self.tab_srt, QtGui.QIcon(resource_path(TAB_ICON_srt03)), "ART")
        else:
            tabs.addTab(self.tab_srt, "ART")

        if TAB_ICON_AR:
            tabs.addTab(self.tab_ar, QtGui.QIcon(resource_path(TAB_ICON_AR)), "AR")
        else:
            tabs.addTab(self.tab_ar, "AR")

        tabs.addTab(self.tab_srt29, "231-AT-01")

        central_l.addWidget(tabs)
        self.setCentralWidget(central)


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    apply_pretty_ui(app)

    icon = load_app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)

    splash = None
    if LoadingSplash is not None:
        splash = LoadingSplash(
            icon,
            title=APP_NAME,
            subtitle="Прямая работа с SPI FRAM · CH341",
            palette=SPLASH_PALETTE,
        )
        splash.start()
        splash.step("Загрузка модулей...", 20)

    # Заставку PyInstaller гасим только когда есть чем её заменить,
    # иначе между ними мигнёт пустой экран.
    close_pyinstaller_splash()

    if splash:
        splash.step("Подготовка вкладок...", 55)

    win = MainWindow()
    if not icon.isNull():
        win.setWindowIcon(icon)

    if splash:
        splash.step("Готово", 100)
        splash.finish(win)
    else:
        win.show()

    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
