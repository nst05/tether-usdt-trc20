# -*- coding: utf-8 -*-
"""
231 at-01 — отдельная программа.
Редактирование показаний T1/T2 + общая сумма с записью во все 4 зеркала.

Формат дампа (coef = 2000):
  Внутри одного зеркала (блок 0x2000):
    T1            -> 0x0000, 0x0100
    T2            -> 0x0011, 0x0111
    Итоговый блок -> 0x06A6 (и дубль 0x06FB), порядок записей: SUM, T1, T2
        SUM: +0x00 (0x06A6 / 0x06FB)
        T1 : +0x11 (0x06B7 / 0x070C)
        T2 : +0x22 (0x06C8 / 0x071D)
  Файл (32 КБ) хранит 4 идентичные копии по 0x2000: 0x0000, 0x2000, 0x4000, 0x6000.
"""

import os
import sys
from typing import Tuple

from PyQt5 import QtCore, QtGui, QtWidgets

# -------------------------------------------------------------------
# PyInstaller support (ресурсы в onefile)
# -------------------------------------------------------------------
if getattr(sys, "frozen", False):
    os.environ["PATH"] = sys._MEIPASS + os.pathsep + os.environ.get("PATH", "")

def resource_path(relative_path: str) -> str:
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
    qss = """
    QWidget { background: #0f1115; color: #e7e9ee; font-size: 10pt; }
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
    QPushButton#PrimaryButton { background: #3a4a7a; border-color: #5d74c5; }
    QPushButton#PrimaryButton:hover { background: #42558d; border-color: #6f86da; }
    QPushButton#PrimaryButton:pressed { background: #33406a; }
    QLabel#HeaderTitle { font-size: 15pt; font-weight: 800; color: #ffffff; }
    QLabel#HeaderSub { color: #aab1c2; }
    QLabel#StatusLabel {
        background: #0f1115; border: 1px solid #2a2f3a; border-radius: 14px;
        padding: 10px 12px; color: #cfd3dc;
    }
    """
    app.setStyleSheet(qss)

# =============================
# Низкоуровневые помощники (формат записи)
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

def read_record_raw(data: bytes, start: int) -> Tuple[int, int, bool]:
    rec = data[start:start+REC_LEN]
    if len(rec) != REC_LEN:
        return (0, 0, False)
    p_raw = decode_raw_u32_weird(rec[OFF_P:OFF_P+4])
    q_raw = decode_raw_u32_weird(rec[OFF_Q:OFF_Q+4])
    ok = (crc_xor_16(rec[0:16]) == rec[OFF_CRC])
    return (p_raw, q_raw, ok)

def read_record(data: bytes, start: int, coef: int) -> Tuple[float, float, bool]:
    p_raw, q_raw, ok = read_record_raw(data, start)
    return (p_raw / coef, q_raw / coef, ok)

# =============================
# Карта формата 231 at-01
# =============================
MIRROR_STRIDE = 0x2000
MIRROR_COUNT  = 4

SRT29_T1_OFFS  = [0x0000, 0x0100]
SRT29_T2_OFFS  = [0x0011, 0x0111]
SRT29_SUM_OFFS = [0x06A6, 0x06FB]
SRT29_BLK_T1   = 0x11
SRT29_BLK_T2   = 0x22

def srt29_set_p_keep_q(data: bytearray, start: int, p: float, coef: int) -> bool:
    """Записать только P, сохранив исходное Q. CRC пересчитывается.
    Если показание (точность 0.01) не изменилось — байты не трогаются.
    Возвращает True, если запись была изменена."""
    p_old_raw, q_old_raw, _ = read_record_raw(data, start)
    if round(p_old_raw / coef, 2) == round(p, 2):
        return False
    p_new_raw = int(round(p * coef))
    data[start+OFF_P:start+OFF_P+4] = encode_raw_u32_weird(p_new_raw)
    data[start+OFF_Q:start+OFF_Q+4] = encode_raw_u32_weird(q_old_raw)
    data[start+OFF_CRC] = crc_xor_16(bytes(data[start:start+16]))
    return True

# =============================
# Вкладка 231 at-01
# =============================
class at01Tab(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self._current_path = None

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        header = QtWidgets.QHBoxLayout()
        titles = QtWidgets.QVBoxLayout()
        h1 = QtWidgets.QLabel("231 at-01 — T1/T2 + общая сумма (4 зеркала)")
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

        self.btn_open = QtWidgets.QPushButton("Открыть 231 at-01 .bin")
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

        form.addWidget(QtWidgets.QLabel("T1 (активная):"), 0, 0); form.addWidget(self.in_t1, 0, 1)
        form.addWidget(QtWidgets.QLabel("T2 (активная):"), 0, 2); form.addWidget(self.in_t2, 0, 3)
        form.addWidget(QtWidgets.QLabel("Сумма (T1+T2, авто):"), 1, 0); form.addWidget(self.out_sum, 1, 1, 1, 3)
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
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Выберите 231 at-01 .bin", "", "BIN (*.bin *.BIN);;All files (*.*)")
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
                points += srt29_set_p_keep_q(data, base + blk,                s,  coef)
                points += srt29_set_p_keep_q(data, base + blk + SRT29_BLK_T1, t1, coef)
                points += srt29_set_p_keep_q(data, base + blk + SRT29_BLK_T2, t2, coef)

        base_dir = os.path.dirname(self._current_path)
        base_name = os.path.splitext(os.path.basename(self._current_path))[0]
        out_name = f"{base_name}__231at-01__T1_{t1:.2f}_T2_{t2:.2f}_summa_{s:.2f}_coef{coef}.bin"
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
        self.setWindowTitle("231 at-01")
        self.setMinimumSize(720, 480)

        central = QtWidgets.QWidget()
        central_l = QtWidgets.QVBoxLayout(central)
        central_l.setContentsMargins(14, 14, 14, 14)
        central_l.addWidget(at01Tab())
        self.setCentralWidget(central)

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    apply_pretty_ui(app)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
