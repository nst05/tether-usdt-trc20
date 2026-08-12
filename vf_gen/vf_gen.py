# -*- coding: utf-8 -*-
"""
VF Gen — генератор прошивок ce101 r5 145.

По введённому показанию подбирает байты b1/b2/b3 и дробный блок, собирает
Intel HEX и сохраняет .hex. В отличие от старой версии:
  • берёт ЛЮБОЕ число (дробный блок 0.03 включён и даёт точное попадание);
  • полный диапазон b3 — потолок 14 260 641.25 вместо 891 297.25;
  • анимация запуска и оформление;
  • счётчик сохранённых файлов, не сбрасывается между запусками;
  • привязка к компьютеру (ключ активации).
"""

import glob
import os
import shutil
import subprocess
import sys
import tempfile

from PyQt5 import QtCore, QtGui, QtWidgets

if getattr(sys, "frozen", False):
    os.environ["PATH"] = sys._MEIPASS + os.pathsep + os.environ.get("PATH", "")
    sys.path.insert(0, sys._MEIPASS)
else:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import vf_core as core
import vf_license
from vf_counters import Counters
from vf_storage import app_data_dir

COUNTER_NAME = "hex"

# ── Прошивка через PICkit (ipecmd) ────────────────────────────────────────────
PIC_DEVICE = "16F1934"       # модель чипа (параметр -P)
PIC_TOOL = "PPK3"            # PICkit 3 (для PK4 → PPK4, PK5 → PPK5)
EEPROM_ONLY = True           # писать ТОЛЬКО EEPROM, не трогая прошивку (-ME)
POWER_FROM_TOOL = False      # питать чип от PICkit? обычно нет
VDD = "5.0"


def find_ipecmd():
    """Ищет ipecmd.exe от MPLAB IPE где угодно в папке Microchip.
    Можно жёстко задать путь env IPECMD или файлом ipecmd_path.txt рядом."""
    env = os.environ.get("IPECMD")
    if env and os.path.isfile(env):
        return env
    try:
        base = (os.path.dirname(os.path.abspath(sys.executable))
                if getattr(sys, "frozen", False)
                else os.path.dirname(os.path.abspath(__file__)))
        txt = os.path.join(base, "ipecmd_path.txt")
        if os.path.isfile(txt):
            p = open(txt, encoding="utf-8").read().strip().strip('"')
            if p and os.path.isfile(p):
                return p
    except Exception:
        pass
    w = shutil.which("ipecmd") or shutil.which("ipecmd.exe")
    if w:
        return w
    if os.name != "nt":
        return None
    roots = []
    for var in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)"):
        p = os.environ.get(var)
        if p:
            roots.append(os.path.join(p, "Microchip"))
    roots += [r"C:\Program Files\Microchip", r"C:\Program Files (x86)\Microchip"]
    hits, seen = [], set()
    for base in roots:
        low = base.lower()
        if low in seen or not os.path.isdir(base):
            continue
        seen.add(low)
        hits += glob.glob(os.path.join(base, "**", "ipecmd.exe"), recursive=True)
    return sorted(hits)[-1] if hits else None

# ── Палитра и стиль ───────────────────────────────────────────────────────────
APP_STYLE = """
    QWidget {
        background: #0e1117;
        color: #e8ecf4;
        font-family: 'Segoe UI';
        font-size: 14px;
    }
    QLabel#Title {
        font-size: 22px;
        font-weight: 900;
        color: #ffffff;
    }
    QLabel#Subtitle { font-size: 13px; color: #93a1b8; }
    QLabel#FieldLabel {
        font-size: 12px; font-weight: 700; letter-spacing: .04em;
        color: #93a1b8; text-transform: uppercase;
    }
    QLineEdit {
        background: #161c26;
        border: 2px solid #2b3648;
        border-radius: 12px;
        padding: 12px 14px;
        font-size: 24px;
        font-weight: 700;
        color: #ffffff;
        selection-background-color: #3f6df6;
    }
    QLineEdit:focus { border-color: #6b8cff; }
    QPushButton {
        background: #3f6df6;
        border: 2px solid #6f91ff;
        border-radius: 12px;
        padding: 12px 18px;
        font-size: 16px;
        font-weight: 800;
        color: white;
    }
    QPushButton:hover { background: #4e79ff; }
    QPushButton:pressed { background: #345acb; }
    QPushButton:disabled { background: #2b3240; border-color: #3a4352; color: #8d96a8; }
    QPushButton#Ghost {
        background: #1a2230; border-color: #2b3648; color: #cdd6e6;
        font-size: 14px; font-weight: 700;
    }
    QPushButton#Ghost:hover { background: #222c3d; }
    QCheckBox { font-size: 13px; color: #cdd6e6; spacing: 8px; }
    QCheckBox::indicator {
        width: 20px; height: 20px; border-radius: 6px;
        border: 2px solid #2b3648; background: #161c26;
    }
    QCheckBox::indicator:checked { background: #3f6df6; border-color: #6f91ff; }
    QFrame#Card {
        background: #131a24; border: 2px solid #222c3b; border-radius: 16px;
    }
    QFrame#CandCard {
        background: #131a24; border: 2px solid #222c3b; border-radius: 14px;
    }
    QFrame#CandCard[best="true"] { border-color: #2fc46f; background: #12251b; }
    QLabel#CandValue { font-size: 24px; font-weight: 900; color: #ffffff; }
    QLabel#CandValueBest { font-size: 24px; font-weight: 900; color: #7ff0ac; }
    QLabel#CandMeta { font-size: 12px; color: #93a1b8; }
    QLabel#CandErr { font-size: 12px; font-weight: 700; }
    QLabel#Counter { font-size: 30px; font-weight: 900; color: #7ff0ac; }
    QLabel#CounterCap { font-size: 11px; font-weight: 800; color: #8d96a8; }
    QLabel#Footer { font-size: 11px; color: #7a869c; }
    QTextEdit {
        background: #10151d; border: 2px solid #222c3b; border-radius: 12px;
        color: #a8b3c7; font-family: 'Consolas','Courier New',monospace; font-size: 12px;
    }
    QToolTip { background: #1a2230; color: #e8ecf4; border: 1px solid #2b3648; }
"""


def resource_path(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


# ══════════════════════════════════════════════════════════════════════════════
# Анимация запуска
# ══════════════════════════════════════════════════════════════════════════════

class SplashScreen(QtWidgets.QWidget):
    """Заставка с плавным появлением, вращающимся кольцом и прогрессом."""

    finished = QtCore.pyqtSignal()

    def __init__(self):
        super().__init__(None,
                         QtCore.Qt.FramelessWindowHint |
                         QtCore.Qt.WindowStaysOnTopHint |
                         QtCore.Qt.SplashScreen)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setFixedSize(460, 300)
        self._angle = 0
        self._progress = 0.0
        self._opacity = 0.0
        self._center_to_screen()

        self._spin = QtCore.QTimer(self)
        self._spin.timeout.connect(self._on_spin)
        self._fade = QtCore.QTimer(self)
        self._fade.timeout.connect(self._on_fade_in)

    def _center_to_screen(self):
        screen = QtWidgets.QApplication.primaryScreen().geometry()
        self.move(screen.center() - self.rect().center())

    def start(self):
        self.show()
        self._fade.start(16)
        self._spin.start(16)

    def _on_fade_in(self):
        self._opacity = min(1.0, self._opacity + 0.06)
        self.setWindowOpacity(self._opacity)
        if self._opacity >= 1.0:
            self._fade.stop()

    def _on_spin(self):
        self._angle = (self._angle + 6) % 360
        self._progress = min(1.0, self._progress + 0.012)
        self.update()
        if self._progress >= 1.0:
            self._spin.stop()
            QtCore.QTimer.singleShot(180, self._fade_out)

    def _fade_out(self):
        self._out = QtCore.QTimer(self)

        def step():
            self._opacity = max(0.0, self._opacity - 0.08)
            self.setWindowOpacity(self._opacity)
            if self._opacity <= 0.0:
                self._out.stop()
                self.close()
                self.finished.emit()

        self._out.timeout.connect(step)
        self._out.start(16)

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)

        # карточка
        rect = self.rect().adjusted(10, 10, -10, -10)
        path = QtGui.QPainterPath()
        path.addRoundedRect(QtCore.QRectF(rect), 22, 22)
        p.fillPath(path, QtGui.QColor("#131a24"))
        pen = QtGui.QPen(QtGui.QColor("#222c3b"))
        pen.setWidth(2)
        p.setPen(pen)
        p.drawPath(path)

        cx, cy = self.width() / 2, self.height() / 2 - 26

        # вращающееся кольцо
        ring = QtCore.QRectF(cx - 34, cy - 34, 68, 68)
        p.setPen(QtGui.QPen(QtGui.QColor("#22314a"), 6))
        p.drawArc(ring, 0, 360 * 16)
        grad_pen = QtGui.QPen(QtGui.QColor("#4e79ff"), 6, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap)
        p.setPen(grad_pen)
        p.drawArc(ring, -self._angle * 16, 110 * 16)

        # заголовок
        p.setPen(QtGui.QColor("#ffffff"))
        p.setFont(QtGui.QFont("Segoe UI", 20, QtGui.QFont.Black))
        p.drawText(QtCore.QRectF(0, cy + 34, self.width(), 34),
                   QtCore.Qt.AlignCenter, "VF Gen")
        p.setPen(QtGui.QColor("#93a1b8"))
        p.setFont(QtGui.QFont("Segoe UI", 10))
        p.drawText(QtCore.QRectF(0, cy + 66, self.width(), 22),
                   QtCore.Qt.AlignCenter, "ce101 r5 145 · генератор прошивок")

        # прогресс-полоса
        bar_w = self.width() - 96
        bx, by = 48, self.height() - 46
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor("#22314a"))
        p.drawRoundedRect(QtCore.QRectF(bx, by, bar_w, 6), 3, 3)
        p.setBrush(QtGui.QColor("#4e79ff"))
        p.drawRoundedRect(QtCore.QRectF(bx, by, bar_w * self._progress, 6), 3, 3)
        p.end()


# ══════════════════════════════════════════════════════════════════════════════
# Фоновый подбор (чтобы окно не подвисало)
# ══════════════════════════════════════════════════════════════════════════════

class SolveWorker(QtCore.QThread):
    done = QtCore.pyqtSignal(object)
    failed = QtCore.pyqtSignal(str)

    def __init__(self, target, use_frac, b3_max):
        super().__init__()
        self.target = target
        self.use_frac = use_frac
        self.b3_max = b3_max

    def run(self):
        try:
            result = core.solve(self.target, use_frac=self.use_frac,
                                 b3_max=self.b3_max, max_results=3)
            self.done.emit(result)
        except Exception as exc:              # noqa: BLE001
            self.failed.emit(str(exc))


class FlashWorker(QtCore.QThread):
    """Запускает ipecmd и шьёт EEPROM, не блокируя окно."""

    line = QtCore.pyqtSignal(str)
    done = QtCore.pyqtSignal(int)

    def __init__(self, ipecmd, hex_path):
        super().__init__()
        self.ipecmd = ipecmd
        self.hex_path = hex_path

    def run(self):
        args = [self.ipecmd, "-T" + PIC_TOOL, "-P" + PIC_DEVICE,
                "-F" + self.hex_path, "-ME" if EEPROM_ONLY else "-M"]
        if POWER_FROM_TOOL:
            args.append("-A" + VDD)
        args.append("-OL")
        flags = 0x08000000 if os.name == "nt" else 0     # CREATE_NO_WINDOW
        try:
            proc = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                cwd=os.path.dirname(self.hex_path) or None,
                creationflags=flags)
            for ln in proc.stdout:
                ln = ln.rstrip()
                if ln:
                    self.line.emit(ln)
            proc.wait()
            self.done.emit(proc.returncode)
        except Exception as exc:              # noqa: BLE001
            self.line.emit("Ошибка запуска ipecmd: %s" % exc)
            self.done.emit(-1)


# ══════════════════════════════════════════════════════════════════════════════
# Карточка варианта
# ══════════════════════════════════════════════════════════════════════════════

class CandidateCard(QtWidgets.QFrame):
    save_requested = QtCore.pyqtSignal(int)

    def __init__(self, index, parent=None):
        super().__init__(parent)
        self.setObjectName("CandCard")
        self.setMinimumHeight(70)
        self.index = index
        self.candidate = None
        self._build()

    def _build(self):
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(16, 8, 16, 8)
        lay.setSpacing(14)

        left = QtWidgets.QVBoxLayout()
        left.setSpacing(2)
        self.value_lbl = QtWidgets.QLabel("—")
        self.value_lbl.setObjectName("CandValue")
        self.meta_lbl = QtWidgets.QLabel("")
        self.meta_lbl.setObjectName("CandMeta")
        left.addWidget(self.value_lbl)
        left.addWidget(self.meta_lbl)
        lay.addLayout(left, 1)

        self.err_lbl = QtWidgets.QLabel("")
        self.err_lbl.setObjectName("CandErr")
        self.err_lbl.setAlignment(QtCore.Qt.AlignCenter)
        lay.addWidget(self.err_lbl)

        self.save_btn = QtWidgets.QPushButton("Сохранить .hex")
        self.save_btn.setFixedHeight(48)
        self.save_btn.clicked.connect(lambda: self.save_requested.emit(self.index))
        self.save_btn.setEnabled(False)
        lay.addWidget(self.save_btn)

    def set_candidate(self, cand, is_best):
        self.candidate = cand
        if cand is None:
            self.value_lbl.setText("—")
            self.meta_lbl.setText("")
            self.err_lbl.setText("")
            self.save_btn.setEnabled(False)
            self.setProperty("best", "false")
        else:
            self.value_lbl.setObjectName("CandValueBest" if is_best else "CandValue")
            self.value_lbl.setText(core.format_value(cand.value))
            note = "точное совпадение" if cand.exact else "ближайшее"
            self.meta_lbl.setText(
                "%s · база %s · дробных %d"
                % (note, core.format_value(cand.base_value), cand.n_frac))
            if cand.exact:
                self.err_lbl.setText("ТОЧНО")
                self.err_lbl.setStyleSheet("color:#7ff0ac;")
            else:
                self.err_lbl.setText("±%.2f" % cand.error)
                self.err_lbl.setStyleSheet("color:#ffd27f;")
            self.setProperty("best", "true" if is_best else "false")
            self.save_btn.setEnabled(True)
        self.style().unpolish(self)
        self.style().polish(self)


# ══════════════════════════════════════════════════════════════════════════════
# Активация (диалог)
# ══════════════════════════════════════════════════════════════════════════════

class ActivationDialog(QtWidgets.QDialog):
    def __init__(self, status, parent=None):
        super().__init__(parent)
        self.status = status
        self.setWindowTitle("Активация VF Gen")
        self.setFixedWidth(540)
        self.setStyleSheet(APP_STYLE)
        self._build()

    def _build(self):
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(24, 22, 24, 20)
        v.setSpacing(12)

        title = QtWidgets.QLabel("Активация программы")
        title.setObjectName("Title")
        title.setAlignment(QtCore.Qt.AlignCenter)
        v.addWidget(title)

        hint = QtWidgets.QLabel(
            "Программа работает только на одном компьютере.\n"
            "Отправьте код компьютера поставщику и введите полученный ключ.")
        hint.setObjectName("Subtitle")
        hint.setAlignment(QtCore.Qt.AlignCenter)
        hint.setWordWrap(True)
        v.addWidget(hint)

        cap = QtWidgets.QLabel("КОД ЭТОГО КОМПЬЮТЕРА")
        cap.setObjectName("FieldLabel")
        cap.setAlignment(QtCore.Qt.AlignCenter)
        v.addWidget(cap)

        self.code = QtWidgets.QLineEdit(self.status["machine_code"])
        self.code.setReadOnly(True)
        self.code.setAlignment(QtCore.Qt.AlignCenter)
        self.code.setStyleSheet("color:#7ff0ac; font-size:20px;")
        v.addWidget(self.code)

        copy = QtWidgets.QPushButton("Скопировать код")
        copy.setObjectName("Ghost")
        copy.clicked.connect(self._copy)
        v.addWidget(copy)

        cap2 = QtWidgets.QLabel("КЛЮЧ АКТИВАЦИИ")
        cap2.setObjectName("FieldLabel")
        cap2.setAlignment(QtCore.Qt.AlignCenter)
        v.addWidget(cap2)

        self.key = QtWidgets.QLineEdit()
        self.key.setPlaceholderText("XXXXXXX-XXXXXXX-XXXXXXX")
        self.key.setAlignment(QtCore.Qt.AlignCenter)
        self.key.setStyleSheet("font-size:18px;")
        self.key.returnPressed.connect(self._activate)
        v.addWidget(self.key)

        self.msg = QtWidgets.QLabel(self.status["reason"] or "Введите ключ активации")
        self.msg.setWordWrap(True)
        self.msg.setAlignment(QtCore.Qt.AlignCenter)
        self.msg.setMinimumHeight(48)
        self.msg.setStyleSheet("color:#93a1b8;")
        v.addWidget(self.msg)

        row = QtWidgets.QHBoxLayout()
        ok = QtWidgets.QPushButton("Активировать")
        ok.clicked.connect(self._activate)
        row.addWidget(ok, 2)
        quit_btn = QtWidgets.QPushButton("Выход")
        quit_btn.setObjectName("Ghost")
        quit_btn.clicked.connect(self.reject)
        row.addWidget(quit_btn, 1)
        v.addLayout(row)

        self.key.setFocus()
        self.adjustSize()

    def _copy(self):
        QtWidgets.QApplication.clipboard().setText(self.status["machine_code"])
        self.msg.setStyleSheet("color:#93a1b8;")
        self.msg.setText("Код скопирован в буфер обмена.")

    def _activate(self):
        ok, message = vf_license.activate(self.key.text())
        self.msg.setStyleSheet("color:#7ff0ac;" if ok else "color:#ff9cab;")
        self.msg.setText(message)
        if ok:
            QtCore.QTimer.singleShot(500, self.accept)


# ══════════════════════════════════════════════════════════════════════════════
# Главное окно
# ══════════════════════════════════════════════════════════════════════════════

class MainWindow(QtWidgets.QWidget):
    def __init__(self, license_status):
        super().__init__()
        self.license_status = license_status
        self.counters = Counters([COUNTER_NAME])
        self.candidates = []
        self.worker = None
        self.setWindowTitle("VF Gen — ce101 r5 145")
        self.setMinimumSize(780, 730)
        self.setStyleSheet(APP_STYLE)
        self._build()
        self._appear()

    # ── интерфейс ─────────────────────────────────────────────────────────────

    def _build(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 14)
        root.setSpacing(14)

        # шапка: заголовок + счётчик
        head = QtWidgets.QHBoxLayout()
        tbox = QtWidgets.QVBoxLayout()
        tbox.setSpacing(2)
        title = QtWidgets.QLabel("Генератор прошивок")
        title.setObjectName("Title")
        sub = QtWidgets.QLabel("ce101 r5 145 · авторежим: введите показание → «Записать в прибор»")
        sub.setObjectName("Subtitle")
        tbox.addWidget(title)
        tbox.addWidget(sub)
        head.addLayout(tbox, 1)

        counter_card = QtWidgets.QFrame()
        counter_card.setObjectName("Card")
        cc = QtWidgets.QVBoxLayout(counter_card)
        cc.setContentsMargins(18, 8, 18, 8)
        cc.setSpacing(0)
        cap = QtWidgets.QLabel("ЗАПИСАНО")
        cap.setObjectName("CounterCap")
        cap.setAlignment(QtCore.Qt.AlignCenter)
        self.counter_lbl = QtWidgets.QLabel("0")
        self.counter_lbl.setObjectName("Counter")
        self.counter_lbl.setAlignment(QtCore.Qt.AlignCenter)
        cc.addWidget(cap)
        cc.addWidget(self.counter_lbl)
        head.addWidget(counter_card)
        root.addLayout(head)

        # поле ввода
        input_card = QtWidgets.QFrame()
        input_card.setObjectName("Card")
        input_card.setMinimumHeight(150)
        ic = QtWidgets.QVBoxLayout(input_card)
        ic.setContentsMargins(18, 16, 18, 16)
        ic.setSpacing(12)

        lab = QtWidgets.QLabel("ЦЕЛЕВОЕ ЗНАЧЕНИЕ")
        lab.setObjectName("FieldLabel")
        ic.addWidget(lab)

        row = QtWidgets.QHBoxLayout()
        row.setSpacing(10)
        self.inp = QtWidgets.QLineEdit("7035")
        self.inp.setValidator(QtGui.QDoubleValidator(0.0, 1e12, 2))
        self.inp.setMinimumHeight(56)
        self.inp.returnPressed.connect(self.on_write_auto)   # Enter = записать
        row.addWidget(self.inp, 1)
        self.auto_btn = QtWidgets.QPushButton("ЗАПИСАТЬ В ПРИБОР")
        self.auto_btn.setMinimumWidth(210)
        self.auto_btn.setMinimumHeight(56)
        self.auto_btn.clicked.connect(self.on_write_auto)
        row.addWidget(self.auto_btn)
        ic.addLayout(row)

        opts = QtWidgets.QHBoxLayout()
        self.chk_frac = QtWidgets.QCheckBox("Дробный блок (точное попадание)")
        self.chk_frac.setChecked(True)
        self.chk_frac.setToolTip(
            "Записывает второй блок 0x1E200 с шагом 0.03 — позволяет попасть\n"
            "в любое число. Без него показание всегда кратно 0.85.")
        self.chk_full = QtWidgets.QCheckBox("Полный диапазон (b3 до 0xFF)")
        self.chk_full.setChecked(True)
        self.chk_full.setToolTip(
            "Снимает ограничение старой программы (b3 ≤ 0x0F).\n"
            "Потолок поднимается с 891 297 до 14 260 641.")
        opts.addWidget(self.chk_frac)
        opts.addWidget(self.chk_full)
        opts.addStretch(1)
        # ручной подбор без записи — оставлен для проверки/сохранения .hex
        self.solve_btn = QtWidgets.QPushButton("Только подобрать")
        self.solve_btn.setObjectName("Ghost")
        self.solve_btn.clicked.connect(self.on_solve)
        opts.addWidget(self.solve_btn)
        ic.addLayout(opts)
        root.addWidget(input_card)

        # варианты
        vary_lbl = QtWidgets.QLabel("ВАРИАНТЫ")
        vary_lbl.setObjectName("FieldLabel")
        root.addWidget(vary_lbl)
        self.cards = []
        for i in range(3):
            card = CandidateCard(i)
            card.save_requested.connect(self.on_save)
            self.cards.append(card)
            root.addWidget(card)

        # папка сохранения
        out_row = QtWidgets.QHBoxLayout()
        out_lbl = QtWidgets.QLabel("Папка:")
        out_lbl.setObjectName("Subtitle")
        self.outdir = QtWidgets.QLineEdit(os.getcwd())
        browse = QtWidgets.QPushButton("Обзор…")
        browse.setObjectName("Ghost")
        browse.clicked.connect(self.on_browse)
        out_row.addWidget(out_lbl)
        out_row.addWidget(self.outdir, 1)
        out_row.addWidget(browse)
        root.addLayout(out_row)

        # лог
        self.log = QtWidgets.QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(120)
        root.addWidget(self.log)

        # подвал
        self.footer = QtWidgets.QLabel()
        self.footer.setObjectName("Footer")
        self.footer.setAlignment(QtCore.Qt.AlignCenter)
        root.addWidget(self.footer)

        self._refresh_counter()
        self._refresh_footer()

        self.license_timer = QtCore.QTimer(self)
        self.license_timer.timeout.connect(self._check_license)
        self.license_timer.start(60 * 60 * 1000)

    def _appear(self):
        """Плавное появление окна."""
        self._fx = QtWidgets.QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._fx)
        self._anim = QtCore.QPropertyAnimation(self._fx, b"opacity", self)
        self._anim.setDuration(320)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QtCore.QEasingCurve.OutCubic)
        self._anim.finished.connect(lambda: self.setGraphicsEffect(None))
        self._anim.start()

    # ── данные ────────────────────────────────────────────────────────────────

    def _refresh_counter(self):
        self.counter_lbl.setText(str(self.counters.count(COUNTER_NAME)))

    def _refresh_footer(self):
        self.footer.setText(
            "%s   ·   ПК: %s   ·   данные: %s"
            % (vf_license.status_text(self.license_status),
               self.license_status["machine_code"], app_data_dir()))

    def _check_license(self):
        self.license_status = vf_license.check_license()
        self._refresh_footer()
        return self.license_status

    # ── действия ──────────────────────────────────────────────────────────────

    def on_browse(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Куда сохранять .hex?", self.outdir.text())
        if d:
            self.outdir.setText(d)

    def on_solve(self):
        try:
            target = float(self.inp.text().strip().replace(",", "."))
        except ValueError:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "Введите число.")
            return
        if target < 0:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "Значение не может быть отрицательным.")
            return

        ceiling = core.max_reading(core.B3_MAX_FULL if self.chk_full.isChecked()
                                   else core.B3_MAX_ORIGINAL)
        if target > ceiling:
            QtWidgets.QMessageBox.warning(
                self, "Вне диапазона",
                "Максимум при текущих настройках — %s.\n"
                "Включите «Полный диапазон», если он выключен." % core.format_value(ceiling))
            return

        self.solve_btn.setEnabled(False)
        self.solve_btn.setText("Подбор…")
        for card in self.cards:
            card.set_candidate(None, False)

        self.worker = SolveWorker(
            target,
            self.chk_frac.isChecked(),
            core.B3_MAX_FULL if self.chk_full.isChecked() else core.B3_MAX_ORIGINAL)
        self.worker.done.connect(self._on_solved)
        self.worker.failed.connect(self._on_solve_failed)
        self.worker.start()

    def _on_solved(self, candidates):
        self.candidates = candidates
        self.solve_btn.setEnabled(True)
        self.solve_btn.setText("Только подобрать")
        if not candidates:
            QtWidgets.QMessageBox.warning(self, "Не найдено", "Не удалось подобрать вариант.")
            return
        for i, card in enumerate(self.cards):
            card.set_candidate(candidates[i] if i < len(candidates) else None, i == 0)
        best = candidates[0]
        self.log.append(
            "Цель %s → b1=%02X b2=%02X b3=%02X, дробных %d = %s (%s)"
            % (self.inp.text().strip(), best.b1, best.b2, best.b3, best.n_frac,
               core.format_value(best.value),
               "точно" if best.exact else "±%.2f" % best.error))

    def _on_solve_failed(self, message):
        self.solve_btn.setEnabled(True)
        self.solve_btn.setText("Только подобрать")
        QtWidgets.QMessageBox.critical(self, "Ошибка", message)

    def on_save(self, index):
        if not self.license_status["valid"]:
            QtWidgets.QMessageBox.critical(
                self, "Нет лицензии",
                "Сохранение заблокировано: %s" % self.license_status["reason"])
            return
        if index >= len(self.candidates):
            return
        cand = self.candidates[index]

        out_dir = self.outdir.text().strip() or os.getcwd()
        if not os.path.isdir(out_dir):
            QtWidgets.QMessageBox.critical(self, "Папка", "Папка не существует.")
            return

        text = core.build_hex_for(cand)
        suffix = "V2" if cand.n_frac > 0 else "V1"
        name = "ce101 r5 145_%s__%s.hex" % (suffix, core.format_value(cand.value))
        path = os.path.join(out_dir, name)
        try:
            with open(path, "w", encoding="ascii", newline="\n") as fh:
                fh.write(text)
        except OSError as exc:
            QtWidgets.QMessageBox.critical(self, "Запись", "Не удалось сохранить:\n%s" % exc)
            return

        total = self.counters.increment(COUNTER_NAME, cand.value)
        self._refresh_counter()
        self.log.append("Сохранено (%d): %s" % (total, path))

    # ── АВТОРЕЖИМ: ввёл → «Записать» → подбор + прошивка EEPROM ──────────────

    def on_write_auto(self):
        if getattr(self, "flash_worker", None) and self.flash_worker.isRunning():
            return
        if not self.license_status["valid"]:
            QtWidgets.QMessageBox.critical(
                self, "Нет лицензии",
                "Запись заблокирована: %s" % self.license_status["reason"])
            return
        try:
            target = float(self.inp.text().strip().replace(",", "."))
        except ValueError:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "Введите число.")
            return
        if target < 0:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "Значение не может быть отрицательным.")
            return

        b3_max = core.B3_MAX_FULL if self.chk_full.isChecked() else core.B3_MAX_ORIGINAL
        if target > core.max_reading(b3_max):
            QtWidgets.QMessageBox.warning(
                self, "Вне диапазона",
                "Максимум — %s. Включите «Полный диапазон»." % core.format_value(core.max_reading(b3_max)))
            return

        ipecmd = find_ipecmd()
        if not ipecmd:
            QtWidgets.QMessageBox.critical(
                self, "PICkit не найден",
                "Не найден ipecmd.exe.\n\nУстановите MPLAB IPE (MPLAB X v6.15 или старее — "
                "в v6.20+ PICkit 3 не поддерживается) либо задайте путь в переменной "
                "окружения IPECMD.")
            return

        cands = core.solve(target, use_frac=self.chk_frac.isChecked(),
                           b3_max=b3_max, max_results=3)
        if not cands:
            QtWidgets.QMessageBox.warning(self, "Не найдено", "Не удалось подобрать вариант.")
            return
        self.candidates = cands
        for i, card in enumerate(self.cards):
            card.set_candidate(cands[i] if i < len(cands) else None, i == 0)
        cand = cands[0]

        out_dir = self.outdir.text().strip()
        if not os.path.isdir(out_dir):
            out_dir = tempfile.gettempdir()
        name = "ce101 r5 145_%s__%s.hex" % ("V2" if cand.n_frac > 0 else "V1",
                                            core.format_value(cand.value))
        path = os.path.join(out_dir, name)
        try:
            with open(path, "w", encoding="ascii", newline="\n") as fh:
                fh.write(core.build_hex_for(cand))
        except OSError as exc:
            QtWidgets.QMessageBox.critical(self, "Запись", "Не удалось сохранить .hex:\n%s" % exc)
            return

        self._flash_value = cand.value
        self.log.append("Подобрано %s (%s) → прошиваю EEPROM в PIC%s…"
                        % (core.format_value(cand.value),
                           "точно" if cand.exact else "±%.2f" % cand.error, PIC_DEVICE))
        self.auto_btn.setEnabled(False)
        self.auto_btn.setText("ПРОШИВКА…")
        self.solve_btn.setEnabled(False)

        self.flash_worker = FlashWorker(ipecmd, path)
        self.flash_worker.line.connect(self.log.append)
        self.flash_worker.done.connect(self.on_flash_done)
        self.flash_worker.start()

    def on_flash_done(self, rc):
        self.auto_btn.setEnabled(True)
        self.auto_btn.setText("ЗАПИСАТЬ В ПРИБОР")
        self.solve_btn.setEnabled(True)
        if rc == 0:
            total = self.counters.increment(COUNTER_NAME, getattr(self, "_flash_value", 0))
            self._refresh_counter()
            self.log.append("✓ EEPROM записан (№ %d). Основная прошивка не тронута." % total)
            self.inp.selectAll()
            self.inp.setFocus()
        else:
            self.log.append("✗ Ошибка прошивки (код %d). См. сообщения выше." % rc)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.wait(2000)
        if getattr(self, "flash_worker", None) and self.flash_worker.isRunning():
            self.flash_worker.wait(3000)
        event.accept()


# ══════════════════════════════════════════════════════════════════════════════
# Точка входа
# ══════════════════════════════════════════════════════════════════════════════

def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setStyleSheet(APP_STYLE)

    holder = {}

    def after_splash():
        status = vf_license.check_license()
        if not status["valid"]:
            dlg = ActivationDialog(status)
            if dlg.exec_() != QtWidgets.QDialog.Accepted:
                app.quit()
                return
            status = vf_license.check_license()
            if not status["valid"]:
                app.quit()
                return
        holder["win"] = MainWindow(status)
        holder["win"].show()

    splash = SplashScreen()
    splash.finished.connect(after_splash)
    splash.start()

    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
