# -*- coding: utf-8 -*-
"""

"""

import os
import sys
import math
from dataclasses import dataclass
from typing import Tuple

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtWidgets import QSizePolicy

# -------------------------------------------------------------------
# SETTINGS: пути к картинкам/иконкам (можно оставить "")
# -------------------------------------------------------------------
IMG_HEIGHT = 150

IMG_srt03_IN_TAB   = ""   # например: "img/srt03.png"
IMG_AR_IN_TAB      = ""   # например: "img/ar01_ar02.png"

TAB_ICON_srt03     = ""   # например: "img/srt03_icon.png"
TAB_ICON_AR        = ""   # например: "img/ar_icon.png"

# -------------------------------------------------------------------
# PyInstaller support (ресурсы в onefile)
# -------------------------------------------------------------------
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

    font = QtGui.QFont("Segoe UI", 10)
    app.setFont(font)

    qss = """
    QWidget {
        background: #0f1115;
        color: #e7e9ee;
        font-size: 10pt;
    }

    QTabWidget::pane {
        border: 1px solid #2a2f3a;
        border-radius: 14px;
        top: -1px;
        background: #121622;
    }
    QTabBar::tab {
        background: #151a27;
        border: 1px solid #2a2f3a;
        border-bottom: none;
        padding: 10px 14px;
        margin-right: 6px;
        border-top-left-radius: 12px;
        border-top-right-radius: 12px;
        color: #cfd3dc;
    }
    QTabBar::tab:selected {
        background: #121622;
        color: #ffffff;
        border-color: #3a4a7a;
    }
    QTabBar::tab:hover {
        border-color: #4b5fa0;
    }

    QGroupBox {
        border: 1px solid #2a2f3a;
        border-radius: 14px;
        margin-top: 14px;
        padding: 12px;
        background: #121622;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 14px;
        padding: 0 8px;
        color: #ffffff;
        font-weight: 600;
    }

    QLineEdit, QComboBox, QDoubleSpinBox {
        background: #0f1115;
        border: 1px solid #2a2f3a;
        border-radius: 10px;
        padding: 9px 10px;
        selection-background-color: #3a4a7a;
    }
    QLineEdit:disabled, QComboBox:disabled, QDoubleSpinBox:disabled {
        color: #8b93a6;
        background: #0c0e12;
    }
    QComboBox::drop-down {
        border: none;
        width: 24px;
    }

    QPushButton {
        background: #1a2030;
        border: 1px solid #2a2f3a;
        border-radius: 12px;
        padding: 10px 14px;
        font-weight: 600;
    }
    QPushButton:hover {
        border-color: #4b5fa0;
        background: #1d2436;
    }
    QPushButton:pressed {
        background: #161c2b;
    }
    QPushButton:disabled {
        color: #8b93a6;
        background: #10131b;
        border-color: #1f2430;
    }

    QPushButton#PrimaryButton {
        background: #3a4a7a;
        border-color: #5d74c5;
    }
    QPushButton#PrimaryButton:hover {
        background: #42558d;
        border-color: #6f86da;
    }
    QPushButton#PrimaryButton:pressed {
        background: #33406a;
    }

    QLabel#HeaderTitle {
        font-size: 15pt;
        font-weight: 800;
        color: #ffffff;
    }
    QLabel#HeaderSub {
        color: #aab1c2;
    }

    QLabel#StatusLabel {
        background: #0f1115;
        border: 1px solid #2a2f3a;
        border-radius: 14px;
        padding: 10px 12px;
        color: #cfd3dc;
    }

    QScrollArea {
        border: none;
        background: transparent;
    }
    """
    app.setStyleSheet(qss)

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
# Shared helpers (srt/AR)
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
    rec = data[stsrt:stsrt+REC_LEN]
    if len(rec) != REC_LEN:
        return (0, 0, False)
    p_raw = decode_raw_u32_weird(rec[OFF_P:OFF_P+4])
    q_raw = decode_raw_u32_weird(rec[OFF_Q:OFF_Q+4])
    ok = (crc_xor_16(rec[0:16]) == rec[OFF_CRC])
    return (p_raw, q_raw, ok)

def read_record(data: bytes, stsrt: int, coef: int) -> Tuple[float, float, bool]:
    p_raw, q_raw, ok = read_record_raw(data, stsrt)
    return (p_raw / coef, q_raw / coef, ok)

def write_record(data: bytearray, stsrt: int, p: float, q: float, coef: int) -> None:
    p_raw = int(round(p * coef))
    q_raw = int(round(q * coef))
    data[stsrt+OFF_P:stsrt+OFF_P+4] = encode_raw_u32_weird(p_raw)
    data[stsrt+OFF_Q:stsrt+OFF_Q+4] = encode_raw_u32_weird(q_raw)
    data[stsrt+OFF_CRC] = crc_xor_16(bytes(data[stsrt:stsrt+16]))

# Presets for k
K_srt03 = 4490.54 / 18987.70
K_AR    = 1445.71 / 6384.36

# =============================
# TAB 1: srt03 (T1/T2 + totals)
# =============================
T1_REC_STsrtS = [0x0000, 0x0100]
T2_REC_STsrtS = [0x0011, 0x0111]
TOT_REC_STsrtS = [0x0200]

def _close(a: float, b: float, tol: float = 0.02) -> bool:
    return abs(a - b) <= tol

def choose_totals(t1p: float, t1q: float, t2p: float, t2q: float, totp_file: float, totq_file: float) -> Tuple[float, float, str]:
    sum_p = t1p + t2p
    sum_q = t1q + t2q
    if _close(totp_file, sum_p, tol=0.02) and _close(totq_file, sum_q, tol=0.02):
        return totp_file, totq_file, "FILE"
    return sum_p, sum_q, "SUM"

@dataclass
class srtReadings:
    t1_p: float
    t2_p: float
    t1_q: float
    t2_q: float
    tot_p: float
    tot_q: float

def safe_out_name_srt(in_path: str, readings: srtReadings, coef: int) -> str:
    base = os.path.basename(in_path)
    root, ext = os.path.splitext(base)
    tag = f"P{readings.tot_p:.2f}_Q{readings.tot_q:.2f}_coef{coef}"
    return os.path.join(os.path.dirname(in_path), f"{root}__srt03__patched__{tag}{ext or '.bin'}")

class srt03Tab(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self._current_path = None
        self._file_k = None
        self._sum_k = None
        self._tot_source = "FILE"

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        header = QtWidgets.QHBoxLayout()
        titles = QtWidgets.QVBoxLayout()
        self.h1 = QtWidgets.QLabel("srt03 — активная/реактивная (T1/T2 + общие)")
        self.h1.setObjectName("HeaderTitle")
        self.h2 = QtWidgets.QLabel("Вводишь общие P и T1 P → T2 P считается автоматически. Q считается по k.")
        self.h2.setObjectName("HeaderSub")
        titles.addWidget(self.h1)
        titles.addWidget(self.h2)
        header.addLayout(titles)
        header.addStretch(1)
        root.addLayout(header)

        root.addWidget(make_tab_image_label(IMG_srt03_IN_TAB))

        file_box = QtWidgets.QGroupBox("Файл")
        file_l = QtWidgets.QGridLayout(file_box)
        file_l.setHorizontalSpacing(10)
        file_l.setVerticalSpacing(10)

        self.btn_open = QtWidgets.QPushButton("Открыть srt03 .bin")
        self.btn_open.clicked.connect(self.open_file)
        self.path_edit = QtWidgets.QLineEdit(); self.path_edit.setReadOnly(True)

        file_l.addWidget(self.btn_open, 0, 0, 1, 1)
        file_l.addWidget(self.path_edit, 0, 1, 1, 5)

        self.coef_box = QtWidgets.QComboBox()
        self.coef_box.addItems(["1000", "2000"])
        self.coef_box.setCurrentIndex(0)

        self.k_mode = QtWidgets.QComboBox()
        self.k_mode.addItems([
            "srt03 preset (4490.54/18987.70)",
            "AR preset (1445.71/6384.36)",
            "Из файла Tot@0x0200 (TotQ/TotP)",
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


        file_l.addWidget(QtWidgets.QLabel("Множитель (коэф):"), 1, 0)
        file_l.addWidget(self.coef_box, 1, 1)
        file_l.addWidget(QtWidgets.QLabel("Режим k:"), 1, 2)
        file_l.addWidget(self.k_mode, 1, 3, 1, 2)
        file_l.addWidget(QtWidgets.QLabel("k:"), 1, 5)
        file_l.addWidget(self.ed_k, 1, 6)

        root.addWidget(file_box)

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

        self.lbl_status = QtWidgets.QLabel("Файл не выбран")
        self.lbl_status.setObjectName("StatusLabel")
        self.lbl_status.setWordWrap(True)
        root.addWidget(self.lbl_status)

        self.btn_apply = QtWidgets.QPushButton("Сформировать patched файл")
        self.btn_apply.setObjectName("PrimaryButton")
        self.btn_apply.clicked.connect(self.apply_patch)
        root.addWidget(self.btn_apply)

        root.addStretch(1)

        self.in_t1p.valueChanged.connect(self.refresh_totals)
        self.out_totp.valueChanged.connect(self.refresh_totals)
        self.coef_box.currentIndexChanged.connect(self.reload_from_file)
        self.k_mode.currentIndexChanged.connect(self.on_k_mode_changed)
        self.ed_k.textChanged.connect(self.refresh_totals)

        self.on_k_mode_changed()

    def _setup_spin(self, w: QtWidgets.QDoubleSpinBox):
        w.setDecimals(2)
        w.setRange(0, 999999999.99)
        w.setSingleStep(0.01)

    def coef(self) -> int:
        return int(self.coef_box.currentText())

    def open_file(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Выберите srt03 .bin", "", "BIN (*.bin *.BIN);;All files (*.*)")
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

        coef = self.coef()
        t1p, t1q, ok1 = read_record(data, T1_REC_STsrtS[0], coef)
        t2p, t2q, ok2 = read_record(data, T2_REC_STsrtS[0], coef)
        totp_f, totq_f, ok3 = read_record(data, TOT_REC_STsrtS[0], coef)

        self._file_k = (totq_f / totp_f) if totp_f > 0 else None
        sum_p = t1p + t2p
        sum_q = t1q + t2q
        self._sum_k = (sum_q / sum_p) if sum_p > 0 else None

        totp_use, totq_use, src = choose_totals(t1p, t1q, t2p, t2q, totp_f, totq_f)
        self._tot_source = src

        self.out_totp.blockSignals(True)
        self.in_t1p.blockSignals(True)
        self.out_totp.setValue(totp_use)
        self.in_t1p.setValue(t1p)
        self.out_totp.blockSignals(False)
        self.in_t1p.blockSignals(False)

        self.on_k_mode_changed()
        self.refresh_totals()

        fk = self._file_k if self._file_k is not None else float("nan")
        sk = self._sum_k if self._sum_k is not None else float("nan")
        self.lbl_status.setText(
            f"CRC: T1={'OK' if ok1 else 'BAD'} | T2={'OK' if ok2 else 'BAD'} | TOT@0x0200={'OK' if ok3 else 'BAD'}\n"
            f"Tot@0x0200: P={totp_f:.2f} Q={totq_f:.2f} (k_file={fk:.10f})\n"
            f"Tot(SUM):   P={sum_p:.2f} Q={sum_q:.2f} (k_sum={sk:.10f})\n"
            f"Отображаю Tot как: {self._tot_source}"
        )

    def on_k_mode_changed(self):
        mode = self.k_mode.currentIndex()
        if mode == 0:
            self.ed_k.setText(f"{K_srt03:.10f}")
            self.ed_k.setEnabled(False)
        elif mode == 1:
            self.ed_k.setText(f"{K_AR:.10f}")
            self.ed_k.setEnabled(False)
        elif mode == 2:
            if self._file_k is not None and self._file_k > 0:
                self.ed_k.setText(f"{self._file_k:.10f}")
            else:
                self.ed_k.setText(f"{K_srt03:.10f}")
            self.ed_k.setEnabled(False)
        elif mode == 3:
            if self._sum_k is not None and self._sum_k > 0:
                self.ed_k.setText(f"{self._sum_k:.10f}")
            else:
                self.ed_k.setText(f"{K_srt03:.10f}")
            self.ed_k.setEnabled(False)
        else:
            if not self.ed_k.text().strip():
                self.ed_k.setText(f"{K_srt03:.10f}")
            self.ed_k.setEnabled(True)
        self.refresh_totals()

    def _parse_k(self) -> float:
        s = self.ed_k.text().strip().replace(',', '.')
        try:
            k = float(s)
        except Exception:
            k = K_srt03
        if k <= 0:
            k = K_srt03
        return k

    def refresh_totals(self):
        totp = float(self.out_totp.value())
        t1p = float(self.in_t1p.value())
        t2p = totp - t1p
        if t2p < 0:
            t2p = 0.0

        k = self._parse_k()
        t1q = t1p * k
        t2q = t2p * k
        totq = t1q + t2q

        for w, v in ((self.in_t2p, t2p), (self.in_t1q, t1q), (self.in_t2q, t2q)):
            w.blockSignals(True)
            w.setValue(v)
            w.blockSignals(False)

        self.out_totq.setText(f"{totq:.2f}")

    def apply_patch(self):
        if not self._current_path:
            self.lbl_status.setText("Сначала выбери файл")
            return
        try:
            data = bytearray(open(self._current_path, "rb").read())
        except Exception as e:
            self.lbl_status.setText(f"Ошибка чтения: {e}")
            return

        coef = self.coef()
        totp = float(self.out_totp.value())
        t1p = float(self.in_t1p.value())
        t2p = totp - t1p
        if t2p < 0:
            t2p = 0.0

        k = self._parse_k()
        t1q = t1p * k
        t2q = t2p * k
        totq = t1q + t2q

        readings = srtReadings(t1_p=t1p, t2_p=t2p, t1_q=t1q, t2_q=t2q, tot_p=totp, tot_q=totq)

        for s in T1_REC_STsrtS:
            write_record(data, s, t1p, t1q, coef)
        for s in T2_REC_STsrtS:
            write_record(data, s, t2p, t2q, coef)
        for s in TOT_REC_STsrtS:
            write_record(data, s, totp, totq, coef)

        out_path = safe_out_name_srt(self._current_path, readings, coef)
        try:
            with open(out_path, "wb") as f:
                f.write(data)
        except Exception as e:
            self.lbl_status.setText(f"Ошибка записи: {e}")
            return

        self.lbl_status.setText(f"Готово: {out_path}")

# =============================
# TAB 2: AR01/AR02 totals
# =============================
BASE_OFF = 0x0000
DUP_OFF  = 0x0100

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
    data16 = rec[:16]
    crc_file = rec[OFF_CRC]
    crc_calc = crc_xor_16(data16)
    p_raw = decode_raw_u32_weird(rec[OFF_P:OFF_P+4])
    q_raw = decode_raw_u32_weird(rec[OFF_Q:OFF_Q+4])
    return ParsedRecord(crc_file == crc_calc, p_raw, q_raw, crc_file, crc_calc)

def detect_coef_from_raw(p_raw: int, q_raw: int) -> int:
    step10_ok = (p_raw % 10 == 0) and (q_raw % 10 == 0)
    step20_ok = (p_raw % 20 == 0) and (q_raw % 20 == 0)
    if step20_ok:
        return 2000
    if step10_ok:
        return 1000
    return 1000

def patch_record_totals(buf: bytearray, p_value: float, q_value: float, coef: int) -> None:
    p_raw = int(round(p_value * coef))
    q_raw = int(round(q_value * coef))
    buf[BASE_OFF+OFF_P:BASE_OFF+OFF_P+4] = encode_raw_u32_weird(p_raw)
    buf[BASE_OFF+OFF_Q:BASE_OFF+OFF_Q+4] = encode_raw_u32_weird(q_raw)
    buf[BASE_OFF+OFF_CRC] = crc_xor_16(bytes(buf[BASE_OFF:BASE_OFF+16]))
    buf[DUP_OFF:DUP_OFF+REC_LEN] = buf[BASE_OFF:BASE_OFF+REC_LEN]

class srtotalsTab(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.buf = None
        self.path_in = None
        self._file_k = None

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        header = QtWidgets.QHBoxLayout()
        titles = QtWidgets.QVBoxLayout()
        h1 = QtWidgets.QLabel("AR01 / AR02 — только общие показания")
        h1.setObjectName("HeaderTitle")
        h2 = QtWidgets.QLabel("Вводишь общие P → общая Q считается автоматически по k.")
        h2.setObjectName("HeaderSub")
        titles.addWidget(h1)
        titles.addWidget(h2)
        header.addLayout(titles)
        header.addStretch(1)
        root.addLayout(header)

        root.addWidget(make_tab_image_label(IMG_AR_IN_TAB))

        file_box = QtWidgets.QGroupBox("Файл")
        file_l = QtWidgets.QHBoxLayout(file_box)
        file_l.setSpacing(10)

        self.btn_open = QtWidgets.QPushButton("Открыть BIN")
        self.btn_save = QtWidgets.QPushButton("Сохранить (копию)")
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

        self.rb_auto = QtWidgets.QRadioButton("Авто (по дампу)")
        self.rb_1000 = QtWidgets.QRadioButton("AR02 = 1000")
        self.rb_2000 = QtWidgets.QRadioButton("AR01 = 2000")
        self.rb_auto.setChecked(True)

        coef_row = QtWidgets.QHBoxLayout()
        coef_row.addWidget(self.rb_auto)
        coef_row.addWidget(self.rb_1000)
        coef_row.addWidget(self.rb_2000)
        coef_row.addStretch(1)

        self.k_mode = QtWidgets.QComboBox()
        self.k_mode.addItems(["AR preset (1445.71/6384.36)", "Из файла (Q/P)", "Ручной (поле k)"])
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

        cur = QtWidgets.QGroupBox("Текущие значения из файла (0x0000)")
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
        self.ed_new_q.setValidator(dv2)

        self.ed_new_p.setPlaceholderText("например 6384.36")
        self.ed_new_q.setPlaceholderText("авто")

        new_l.addWidget(QtWidgets.QLabel("P (общие активные):"), 0, 0); new_l.addWidget(self.ed_new_p, 0, 1)
        new_l.addWidget(QtWidgets.QLabel("Q (общие реактивные):"), 0, 2); new_l.addWidget(self.ed_new_q, 0, 3)

        root.addWidget(new)

        self.lbl_status = QtWidgets.QLabel("Файл не открыт")
        self.lbl_status.setObjectName("StatusLabel")
        self.lbl_status.setWordWrap(True)
        root.addWidget(self.lbl_status)

        hint = QtWidgets.QLabel("Формат: P 0..3, Q 8..11, CRC 16, дубль +0x100. CRC = 0xF0 XOR 16 байт данных.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#aab1c2;")
        root.addWidget(hint)

        root.addStretch(1)

        self.btn_open.clicked.connect(self.open_file)
        self.btn_save.clicked.connect(self.save_copy)
        self.ed_new_p.textChanged.connect(self.update_auto_q)
        self.ed_k.textChanged.connect(self.update_auto_q)
        self.k_mode.currentIndexChanged.connect(self.on_k_mode_changed)

        self.rb_auto.toggled.connect(self.refresh_view)
        self.rb_1000.toggled.connect(self.refresh_view)
        self.rb_2000.toggled.connect(self.refresh_view)

        self.on_k_mode_changed()

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
            self.ed_k.setText(f"{K_AR:.10f}")
            self.ed_k.setEnabled(False)
        elif mode == 1:
            if self._file_k is not None and self._file_k > 0:
                self.ed_k.setText(f"{self._file_k:.10f}")
            else:
                self.ed_k.setText(f"{K_AR:.10f}")
            self.ed_k.setEnabled(False)
        else:
            if not self.ed_k.text().strip():
                self.ed_k.setText(f"{K_AR:.10f}")
            self.ed_k.setEnabled(True)
        self.update_auto_q()

    def _parse_k(self) -> float:
        k = self._parse_float(self.ed_k.text(), default=K_AR)
        if math.isnan(k) or k <= 0:
            k = K_AR
        return k

    def update_auto_q(self):
        p = self._parse_float(self.ed_new_p.text(), default=float('nan'))
        k = self._parse_k()
        if math.isnan(p):
            self.ed_new_q.clear()
            return
        self.ed_new_q.setText(f"{(p*k):.2f}")

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
        coef = self.chosen_coef(parsed)
        self._file_k = None
        if parsed.p_raw > 0:
            p = parsed.p_raw / float(coef)
            q = parsed.q_raw / float(coef)
            self._file_k = q / p if p > 0 else None

        self.btn_save.setEnabled(True)
        self.on_k_mode_changed()
        self.refresh_view()

    def refresh_view(self):
        if self.buf is None:
            self.lbl_status.setText("Файл не открыт")
            self.ed_cur_p.clear()
            self.ed_cur_q.clear()
            return

        parsed = parse_record(self.buf, BASE_OFF)
        coef = self.chosen_coef(parsed)
        p = parsed.p_raw / float(coef) if coef else 0.0
        q = parsed.q_raw / float(coef) if coef else 0.0

        self.ed_cur_p.setText(f"{p:.2f}")
        self.ed_cur_q.setText(f"{q:.2f}")

        parsed_dup = parse_record(self.buf, DUP_OFF)
        same = self.buf[BASE_OFF:BASE_OFF+REC_LEN] == self.buf[DUP_OFF:DUP_OFF+REC_LEN]

        fk = self._file_k if self._file_k is not None else float("nan")
        self.lbl_status.setText(
            f"Файл: {os.path.basename(self.path_in)} ({len(self.buf)} байт)\n"
            f"CRC(0x0000): {'OK' if parsed.ok else 'FAIL'} (file=0x{parsed.crc_file:02X}, calc=0x{parsed.crc_calc:02X})\n"
            f"Коэф: {coef} | CRC(0x0100): {'OK' if parsed_dup.ok else 'FAIL'}; дубль {'совпадает' if same else 'НЕ совпадает'}\n"
            f"k_file={fk:.10f}"
        )
        self.update_auto_q()

    def save_copy(self):
        if self.buf is None or self.path_in is None:
            return

        new_p = self._parse_float(self.ed_new_p.text(), default=float('nan'))
        if math.isnan(new_p):
            QtWidgets.QMessageBox.warning(self, 'Ошибка', 'Введите корректное число: Общие активные (P).')
            return

        k = self._parse_k()
        new_q = new_p * k
        self.ed_new_q.setText(f"{new_q:.2f}")

        parsed = parse_record(self.buf, BASE_OFF)
        coef = self.chosen_coef(parsed)

        out_buf = bytearray(self.buf)
        patch_record_totals(out_buf, new_p, new_q, coef)

        base_dir = os.path.dirname(self.path_in)
        base_name = os.path.splitext(os.path.basename(self.path_in))[0]
        out_name = f"{base_name}__AR01AR02__P{new_p:.2f}_Q{new_q:.2f}_coef{coef}.bin"
        out_path = os.path.join(base_dir, out_name)

        if os.path.abspath(out_path) == os.path.abspath(self.path_in):
            out_path = os.path.join(base_dir, f"{base_name}__AR01AR02__patched_coef{coef}.bin")

        with open(out_path, "wb") as f:
            f.write(out_buf)

        QtWidgets.QMessageBox.information(self, "Готово", f"Сохранено:\n{out_path}")

# =============================
# TAB 3: srt29 (T1/T2 + SUM, 4 зеркала)
# =============================
# Формат конкретного дампа:
#   coef = 2000
#   Внутри одного зеркала (блок 0x2000):
#     T1            -> 0x0000, 0x0100
#     T2            -> 0x0011, 0x0111
#     Итоговый блок -> 0x06A6 (и дубль 0x06FB), порядок записей: SUM, T1, T2
#         SUM: +0x00 (0x06A6 / 0x06FB)
#         T1 : +0x11 (0x06B7 / 0x070C)
#         T2 : +0x22 (0x06C8 / 0x071D)
#   Файл (32 КБ) хранит 4 идентичные копии по 0x2000: 0x0000, 0x2000, 0x4000, 0x6000.
MIRROR_STRIDE = 0x2000
MIRROR_COUNT  = 4

# Смещения внутри одного зеркала
SRT29_T1_OFFS  = [0x0000, 0x0100]
SRT29_T2_OFFS  = [0x0011, 0x0111]
SRT29_SUM_OFFS = [0x06A6, 0x06FB]          # начало итогового блока (запись SUM)
SRT29_BLK_T1   = 0x11                       # смещение записи T1 внутри итогового блока
SRT29_BLK_T2   = 0x22                       # смещение записи T2 внутри итогового блока

SRT29_COEF = 2000


def srt29_all_offsets(rec_off: int) -> list:
    """Все физические адреса записи rec_off во всех 4 зеркалах."""
    return [rec_off + m * MIRROR_STRIDE for m in range(MIRROR_COUNT)]


def srt29_set_p_keep_q(data: bytearray, stsrt: int, p: float, coef: int) -> bool:
    """Записать только P в запись, сохранив исходное Q. CRC пересчитывается.
    Если показание (с точностью 0.01) не изменилось — байты не трогаются.
    Возвращает True, если запись была изменена."""
    p_old_raw, q_old_raw, _ = read_record_raw(data, stsrt)
    # Сравниваем на точности отображения (0.01): прибор хранит P точнее (1/coef),
    # чем показано в поле, поэтому сверяем округлённые значения, а не сырые raw.
    if round(p_old_raw / coef, 2) == round(p, 2):
        return False  # показание визуально не изменилось — байты не трогаем
    p_new_raw = int(round(p * coef))
    data[stsrt+OFF_P:stsrt+OFF_P+4] = encode_raw_u32_weird(p_new_raw)
    data[stsrt+OFF_Q:stsrt+OFF_Q+4] = encode_raw_u32_weird(q_old_raw)  # Q сохраняем как было
    data[stsrt+OFF_CRC] = crc_xor_16(bytes(data[stsrt:stsrt+16]))
    return True


class srt29Tab(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self._current_path = None

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        header = QtWidgets.QHBoxLayout()
        titles = QtWidgets.QVBoxLayout()
        h1 = QtWidgets.QLabel("srt29 — T1/T2 + общая сумма (4 зеркала)")
        h1.setObjectName("HeaderTitle")
        h2 = QtWidgets.QLabel("Вводишь T1 и T2 → сумма считается сама. Пишет во все 4 зеркала + итоговый блок.")
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

        self.btn_open = QtWidgets.QPushButton("Открыть srt29 .bin")
        self.btn_open.clicked.connect(self.open_file)
        self.path_edit = QtWidgets.QLineEdit(); self.path_edit.setReadOnly(True)
        file_l.addWidget(self.btn_open, 0, 0)
        file_l.addWidget(self.path_edit, 0, 1, 1, 5)

        self.coef_box = QtWidgets.QComboBox()
        self.coef_box.addItems(["2000", "1000"])
        self.coef_box.setCurrentIndex(0)
        file_l.addWidget(QtWidgets.QLabel("Множитель (коэф):"), 1, 0)
        file_l.addWidget(self.coef_box, 1, 1)
        root.addWidget(file_box)

        calc_box = QtWidgets.QGroupBox("Показания")
        form = QtWidgets.QGridLayout(calc_box)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(10)

        self.in_t1 = QtWidgets.QDoubleSpinBox(); self._setup_spin(self.in_t1)
        self.in_t2 = QtWidgets.QDoubleSpinBox(); self._setup_spin(self.in_t2)
        self.out_sum = QtWidgets.QLineEdit(); self.out_sum.setReadOnly(True)

        r = 0
        form.addWidget(QtWidgets.QLabel("T1 (активная):"), r, 0); form.addWidget(self.in_t1, r, 1)
        form.addWidget(QtWidgets.QLabel("T2 (активная):"), r, 2); form.addWidget(self.in_t2, r, 3)
        r += 1
        form.addWidget(QtWidgets.QLabel("Сумма (T1+T2, авто):"), r, 0); form.addWidget(self.out_sum, r, 1, 1, 3)
        root.addWidget(calc_box)

        self.lbl_status = QtWidgets.QLabel("Файл не выбран")
        self.lbl_status.setObjectName("StatusLabel")
        self.lbl_status.setWordWrap(True)
        root.addWidget(self.lbl_status)

        self.btn_apply = QtWidgets.QPushButton("Сформировать patched файл")
        self.btn_apply.setObjectName("PrimaryButton")
        self.btn_apply.clicked.connect(self.apply_patch)
        root.addWidget(self.btn_apply)

        root.addStretch(1)

        self.in_t1.valueChanged.connect(self.refresh_sum)
        self.in_t2.valueChanged.connect(self.refresh_sum)
        self.coef_box.currentIndexChanged.connect(self.reload_from_file)

    def _setup_spin(self, w: QtWidgets.QDoubleSpinBox):
        w.setDecimals(2)
        w.setRange(0, 999999999.99)
        w.setSingleStep(0.01)

    def coef(self) -> int:
        return int(self.coef_box.currentText())

    def refresh_sum(self):
        s = float(self.in_t1.value()) + float(self.in_t2.value())
        self.out_sum.setText(f"{s:.2f}")

    def open_file(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Выберите srt29 .bin", "", "BIN (*.bin *.BIN);;All files (*.*)")
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

        coef = self.coef()
        t1_p, _, ok_t1 = read_record(data, SRT29_T1_OFFS[0], coef)
        t2_p, _, ok_t2 = read_record(data, SRT29_T2_OFFS[0], coef)
        sum_p, _, ok_s = read_record(data, SRT29_SUM_OFFS[0], coef)

        self.in_t1.blockSignals(True); self.in_t2.blockSignals(True)
        self.in_t1.setValue(t1_p)
        self.in_t2.setValue(t2_p)
        self.in_t1.blockSignals(False); self.in_t2.blockSignals(False)
        self.refresh_sum()

        # Проверим, что зеркала совпадают с базой
        mirrors_ok = all(
            data[m:m + MIRROR_STRIDE] == data[0:MIRROR_STRIDE]
            for m in (0x2000, 0x4000, 0x6000)
            if len(data) >= m + MIRROR_STRIDE
        )

        self.lbl_status.setText(
            f"CRC: T1={'OK' if ok_t1 else 'BAD'} | T2={'OK' if ok_t2 else 'BAD'} | SUM={'OK' if ok_s else 'BAD'}\n"
            f"Из файла: T1={t1_p:.2f}  T2={t2_p:.2f}  SUM={sum_p:.2f}\n"
            f"Зеркала (0x2000/0x4000/0x6000) совпадают с базой: {'да' if mirrors_ok else 'НЕТ'}"
        )

    def apply_patch(self):
        if not self._current_path:
            self.lbl_status.setText("Сначала выбери файл")
            return
        try:
            data = bytearray(open(self._current_path, "rb").read())
        except Exception as e:
            self.lbl_status.setText(f"Ошибка чтения: {e}")
            return

        coef = self.coef()
        t1 = float(self.in_t1.value())
        t2 = float(self.in_t2.value())
        s  = t1 + t2

        # Пишем только P, исходное Q сохраняем; неизменившиеся записи не трогаем.
        points = 0
        for m in range(MIRROR_COUNT):
            base = m * MIRROR_STRIDE
            if base + MIRROR_STRIDE > len(data):
                continue
            # Раздельные T1/T2
            for off in SRT29_T1_OFFS:
                points += srt29_set_p_keep_q(data, base + off, t1, coef)
            for off in SRT29_T2_OFFS:
                points += srt29_set_p_keep_q(data, base + off, t2, coef)
            # Итоговый блок (SUM, T1, T2) и его дубль
            for blk in SRT29_SUM_OFFS:
                points += srt29_set_p_keep_q(data, base + blk,                s,  coef)
                points += srt29_set_p_keep_q(data, base + blk + SRT29_BLK_T1, t1, coef)
                points += srt29_set_p_keep_q(data, base + blk + SRT29_BLK_T2, t2, coef)

        base_dir = os.path.dirname(self._current_path)
        base_name = os.path.splitext(os.path.basename(self._current_path))[0]
        out_name = f"{base_name}__srt29__T1_{t1:.2f}_T2_{t2:.2f}_summa_{s:.2f}_coef{coef}.bin"
        out_path = os.path.join(base_dir, out_name)
        try:
            with open(out_path, "wb") as f:
                f.write(data)
        except Exception as e:
            self.lbl_status.setText(f"Ошибка записи: {e}")
            return

        self.lbl_status.setText(f"Готово ({points} записей пропатчено): {out_path}")


# =============================
# Main Window
# =============================
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("prog")
        self.setMinimumSize(1040, 700)

        central = QtWidgets.QWidget()
        central_l = QtWidgets.QVBoxLayout(central)
        central_l.setContentsMargins(14, 14, 14, 14)
        central_l.setSpacing(10)

        tabs = QtWidgets.QTabWidget()
        tabs.setDocumentMode(True)

        tab_srt = srt03Tab()
        tab_ar = srtotalsTab()
        tab_srt29 = srt29Tab()

        if TAB_ICON_srt03:
            tabs.addTab(tab_srt, QtGui.QIcon(resource_path(TAB_ICON_srt03)), "srt03")
        else:
            tabs.addTab(tab_srt, "srt03")

        if TAB_ICON_AR:
            tabs.addTab(tab_ar, QtGui.QIcon(resource_path(TAB_ICON_AR)), "AR01/AR02")
        else:
            tabs.addTab(tab_ar, "AR01/AR02")

        tabs.addTab(tab_srt29, "srt29")

        central_l.addWidget(tabs)
        self.setCentralWidget(central)

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    apply_pretty_ui(app)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
