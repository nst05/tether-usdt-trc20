"""Оформление интерфейса редактора CE208: палитра, стили ttk, анимации.

Модуль отвечает только за внешний вид и не содержит логики работы с памятью
прибора. Любой виджет отсюда можно убрать, не затронув модель CE208State.

Палитра «инженерная сталь»: средние, неяркие тона — тёмно-стальная шапка,
светло-серый рабочий фон, синий приборный акцент и три сигнальных цвета
(норма / внимание / ошибка), как на панели измерительного оборудования.
"""

from __future__ import annotations

import math
import tkinter as tk
from tkinter import ttk


# ═══════════════════════════════════════════════════════════════════════════
#  Палитра
# ═══════════════════════════════════════════════════════════════════════════

class Palette:
    """Средние приятные тона: сталь, приборный синий, сигнальные цвета."""

    # Фоны
    APP = "#E7ECF1"          # рабочий фон окна
    PANEL = "#F2F6F9"        # панель под содержимым вкладки
    SURFACE = "#FFFFFF"      # карточка, поле ввода, таблица
    SUBTLE = "#DEE6ED"       # разделители, «утопленные» зоны

    # Тёмная сталь — шапка, экран загрузки, заголовки таблиц
    STEEL = "#31414F"
    STEEL_DEEP = "#26333E"
    STEEL_SOFT = "#3D5063"
    STEEL_LINE = "#4A6076"

    # Текст
    INK = "#26313C"          # основной
    INK_SOFT = "#5E6E7D"     # пояснения
    INK_FAINT = "#8496A6"    # подписи, единицы измерения
    ON_DARK = "#E8EFF5"      # текст на тёмной стали
    ON_DARK_SOFT = "#9FB3C4"

    # Приборный акцент
    ACCENT = "#3E7CA6"
    ACCENT_DEEP = "#2F6288"
    ACCENT_SOFT = "#B4CFE1"
    ACCENT_TINT = "#DCE9F2"

    # Сигнальные
    OK = "#4E9A6B"
    OK_TINT = "#E1F0E7"
    WARN = "#C08A3E"
    WARN_TINT = "#F7EEDD"
    ERR = "#BC6154"
    ERR_TINT = "#F6E4E1"
    TEAL = "#3E9490"

    # Линии
    BORDER = "#C6D2DE"
    BORDER_SOFT = "#D9E2EB"
    GRID = "#E3EAF1"


# Шрифты подбираются под систему: моноширинный — для адресов, CRC и hex.
FONT_UI = "TkDefaultFont"
FONT_MONO_CANDIDATES = ("Consolas", "Cascadia Mono", "DejaVu Sans Mono", "Courier New", "TkFixedFont")


def pick_mono(root: tk.Misc) -> str:
    """Первый доступный моноширинный шрифт системы."""
    try:
        from tkinter import font as tkfont
        families = {name.lower() for name in tkfont.families(root)}
        for name in FONT_MONO_CANDIDATES:
            if name.lower() in families:
                return name
    except Exception:
        pass
    return "TkFixedFont"


def mix(color_a: str, color_b: str, ratio: float) -> str:
    """Смешивание двух #RRGGBB: ratio=0 → color_a, ratio=1 → color_b."""
    ratio = max(0.0, min(1.0, ratio))
    a = (int(color_a[1:3], 16), int(color_a[3:5], 16), int(color_a[5:7], 16))
    b = (int(color_b[1:3], 16), int(color_b[3:5], 16), int(color_b[5:7], 16))
    out = tuple(round(x + (y - x) * ratio) for x, y in zip(a, b))
    return "#%02X%02X%02X" % out


# ═══════════════════════════════════════════════════════════════════════════
#  Стили ttk
# ═══════════════════════════════════════════════════════════════════════════

def apply_theme(root: tk.Misc) -> dict:
    """Настраивает все стили ttk. Возвращает словарь со шрифтами."""
    style = ttk.Style(root)
    style.theme_use("clam")

    mono = pick_mono(root)
    fonts = {
        "mono": mono,
        "ui": FONT_UI,
        "display": (FONT_UI, 15, "bold"),
        "title": (FONT_UI, 12, "bold"),
        "section": (FONT_UI, 10, "bold"),
        "body": (FONT_UI, 10),
        "small": (FONT_UI, 9),
        "tiny": (FONT_UI, 8),
        "mono_body": (mono, 10),
        "mono_small": (mono, 9),
        "mono_tiny": (mono, 8),
    }

    root.option_add("*Font", fonts["body"])
    root.option_add("*Toplevel.background", Palette.APP)

    # ── Контейнеры ─────────────────────────────────────────────────────────
    style.configure("TFrame", background=Palette.APP)
    style.configure("Panel.TFrame", background=Palette.PANEL)
    style.configure("Card.TFrame", background=Palette.SURFACE, relief="solid", borderwidth=1)
    style.configure("Steel.TFrame", background=Palette.STEEL)
    style.configure("SteelDeep.TFrame", background=Palette.STEEL_DEEP)
    style.configure("Rail.TFrame", background=Palette.SUBTLE)
    style.configure("TLabelframe", background=Palette.APP, bordercolor=Palette.BORDER,
                    relief="solid", borderwidth=1, padding=10)
    style.configure("TLabelframe.Label", background=Palette.APP,
                    foreground=Palette.ACCENT_DEEP, font=fonts["section"])
    style.configure("Card.TLabelframe", background=Palette.SURFACE, bordercolor=Palette.BORDER_SOFT)
    style.configure("Card.TLabelframe.Label", background=Palette.SURFACE,
                    foreground=Palette.ACCENT_DEEP, font=fonts["section"])

    # ── Надписи ────────────────────────────────────────────────────────────
    style.configure("TLabel", background=Palette.APP, foreground=Palette.INK, font=fonts["body"])
    style.configure("Display.TLabel", background=Palette.APP, foreground=Palette.STEEL, font=fonts["display"])
    style.configure("Title.TLabel", background=Palette.APP, foreground=Palette.STEEL, font=fonts["title"])
    style.configure("Section.TLabel", background=Palette.APP, foreground=Palette.ACCENT_DEEP, font=fonts["section"])
    style.configure("Info.TLabel", background=Palette.APP, foreground=Palette.INK_SOFT, font=fonts["small"])
    style.configure("Faint.TLabel", background=Palette.APP, foreground=Palette.INK_FAINT, font=fonts["small"])
    style.configure("Mono.TLabel", background=Palette.APP, foreground=Palette.INK_SOFT, font=fonts["mono_small"])
    style.configure("Field.TLabel", background=Palette.APP, foreground=Palette.INK, font=fonts["body"])
    style.configure("Unit.TLabel", background=Palette.APP, foreground=Palette.INK_FAINT, font=fonts["tiny"])
    style.configure("Ok.TLabel", background=Palette.APP, foreground=Palette.OK, font=fonts["section"])
    style.configure("Warn.TLabel", background=Palette.APP, foreground=Palette.WARN, font=fonts["section"])
    style.configure("Err.TLabel", background=Palette.APP, foreground=Palette.ERR, font=fonts["section"])
    style.configure("Sum.TLabel", background=Palette.APP, foreground=Palette.ACCENT_DEEP,
                    font=(mono, 12, "bold"))
    # На тёмной стали
    style.configure("OnSteel.TLabel", background=Palette.STEEL, foreground=Palette.ON_DARK, font=fonts["body"])
    style.configure("SteelTitle.TLabel", background=Palette.STEEL, foreground="#FFFFFF", font=(FONT_UI, 13, "bold"))
    style.configure("SteelSub.TLabel", background=Palette.STEEL, foreground=Palette.ON_DARK_SOFT, font=fonts["small"])
    style.configure("SteelMono.TLabel", background=Palette.STEEL, foreground=Palette.ON_DARK_SOFT, font=(mono, 9))
    # Плашки-подсказки
    style.configure("NoteInfo.TLabel", background=Palette.ACCENT_TINT, foreground=Palette.ACCENT_DEEP,
                    font=fonts["small"], padding=10)
    style.configure("NoteWarn.TLabel", background=Palette.WARN_TINT, foreground="#8A5B1B",
                    font=fonts["small"], padding=10)
    style.configure("NoteErr.TLabel", background=Palette.ERR_TINT, foreground="#8C3A2E",
                    font=fonts["small"], padding=10)

    # ── Кнопки ─────────────────────────────────────────────────────────────
    style.configure(
        "TButton", font=fonts["body"], padding=(12, 7), relief="flat", borderwidth=1,
        background=Palette.SURFACE, foreground=Palette.INK, bordercolor=Palette.BORDER,
        focuscolor=Palette.ACCENT_SOFT,
    )
    style.map(
        "TButton",
        background=[("disabled", Palette.SUBTLE), ("pressed", Palette.ACCENT_TINT),
                    ("active", mix(Palette.SURFACE, Palette.ACCENT_TINT, 0.65))],
        foreground=[("disabled", Palette.INK_FAINT), ("active", Palette.ACCENT_DEEP)],
        bordercolor=[("active", Palette.ACCENT_SOFT), ("pressed", Palette.ACCENT)],
    )

    style.configure(
        "Primary.TButton", font=(FONT_UI, 10, "bold"), padding=(16, 9), relief="flat", borderwidth=0,
        background=Palette.ACCENT, foreground="#FFFFFF",
    )
    style.map(
        "Primary.TButton",
        background=[("disabled", Palette.ACCENT_SOFT), ("pressed", Palette.ACCENT_DEEP),
                    ("active", mix(Palette.ACCENT, "#FFFFFF", 0.14))],
        foreground=[("disabled", "#F0F5F9")],
    )

    style.configure(
        "Hero.TButton", font=(FONT_UI, 11, "bold"), padding=(22, 12), relief="flat", borderwidth=0,
        background=Palette.ACCENT_DEEP, foreground="#FFFFFF",
    )
    style.map(
        "Hero.TButton",
        background=[("disabled", Palette.ACCENT_SOFT), ("pressed", "#27516F"),
                    ("active", Palette.ACCENT)],
    )

    style.configure("Ghost.TButton", font=fonts["body"], padding=(12, 7), relief="flat", borderwidth=1,
                    background=Palette.SURFACE, foreground=Palette.ACCENT_DEEP, bordercolor=Palette.ACCENT)
    style.map("Ghost.TButton",
              background=[("active", Palette.ACCENT_TINT), ("pressed", Palette.ACCENT_SOFT)],
              bordercolor=[("active", Palette.ACCENT)])

    style.configure("Steel.TButton", font=fonts["small"], padding=(10, 6), relief="flat", borderwidth=1,
                    background=Palette.STEEL_SOFT, foreground=Palette.ON_DARK, bordercolor=Palette.STEEL_LINE)
    style.map("Steel.TButton",
              background=[("active", mix(Palette.STEEL_SOFT, "#FFFFFF", 0.14)), ("pressed", Palette.STEEL_DEEP)],
              foreground=[("active", "#FFFFFF")])

    style.configure("Danger.TButton", font=fonts["body"], padding=(12, 7), relief="flat", borderwidth=1,
                    background=Palette.SURFACE, foreground=Palette.ERR, bordercolor=mix(Palette.ERR, "#FFFFFF", 0.55))
    style.map("Danger.TButton",
              background=[("active", Palette.ERR_TINT), ("pressed", mix(Palette.ERR, "#FFFFFF", 0.75))])

    # ── Поля ввода ─────────────────────────────────────────────────────────
    for name in ("TEntry", "TCombobox", "TSpinbox"):
        style.configure(
            name, font=fonts["body"], padding=6, relief="flat", borderwidth=1,
            fieldbackground=Palette.SURFACE, background=Palette.SURFACE,
            foreground=Palette.INK, bordercolor=Palette.BORDER,
            insertcolor=Palette.ACCENT_DEEP, arrowcolor=Palette.ACCENT_DEEP,
            selectbackground=Palette.ACCENT_SOFT, selectforeground=Palette.INK,
        )
        style.map(
            name,
            bordercolor=[("focus", Palette.ACCENT), ("hover", Palette.ACCENT_SOFT)],
            fieldbackground=[("readonly", Palette.PANEL), ("disabled", Palette.SUBTLE)],
            foreground=[("disabled", Palette.INK_FAINT)],
            lightcolor=[("focus", Palette.ACCENT_SOFT)],
            darkcolor=[("focus", Palette.ACCENT_SOFT)],
        )
    style.configure("Mono.TEntry", font=fonts["mono_body"])
    root.option_add("*TCombobox*Listbox.background", Palette.SURFACE)
    root.option_add("*TCombobox*Listbox.foreground", Palette.INK)
    root.option_add("*TCombobox*Listbox.selectBackground", Palette.ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", "#FFFFFF")

    # ── Флажки ─────────────────────────────────────────────────────────────
    style.configure("TCheckbutton", background=Palette.APP, foreground=Palette.INK, font=fonts["body"],
                    focuscolor=Palette.ACCENT_SOFT, indicatorcolor=Palette.SURFACE,
                    bordercolor=Palette.BORDER, padding=4)
    style.map("TCheckbutton",
              indicatorcolor=[("selected", Palette.ACCENT), ("pressed", Palette.ACCENT_DEEP)],
              foreground=[("active", Palette.ACCENT_DEEP)],
              background=[("active", Palette.APP)])
    style.configure("TRadiobutton", background=Palette.APP, foreground=Palette.INK, font=fonts["body"])

    # ── Вкладки ────────────────────────────────────────────────────────────
    style.configure("TNotebook", background=Palette.APP, borderwidth=0, tabmargins=(2, 6, 2, 0))
    style.configure("TNotebook.Tab", font=fonts["body"], padding=(12, 10), borderwidth=0,
                    background=Palette.SUBTLE, foreground=Palette.INK_SOFT)
    style.map(
        "TNotebook.Tab",
        background=[("selected", Palette.PANEL), ("active", mix(Palette.SUBTLE, Palette.SURFACE, 0.5))],
        foreground=[("selected", Palette.ACCENT_DEEP), ("active", Palette.INK)],
        font=[("selected", (FONT_UI, 10, "bold"))],
        padding=[("selected", (12, 11))],
    )

    # ── Таблица ────────────────────────────────────────────────────────────
    style.configure("Treeview", font=fonts["mono_small"], background=Palette.SURFACE,
                    fieldbackground=Palette.SURFACE, foreground=Palette.INK,
                    rowheight=25, borderwidth=1, relief="solid", bordercolor=Palette.BORDER_SOFT)
    style.configure("Treeview.Heading", font=(FONT_UI, 9, "bold"), background=Palette.STEEL,
                    foreground=Palette.ON_DARK, relief="flat", padding=(8, 8), borderwidth=0)
    style.map("Treeview.Heading", background=[("active", Palette.STEEL_SOFT)])
    style.map("Treeview",
              background=[("selected", Palette.ACCENT)],
              foreground=[("selected", "#FFFFFF")])

    # ── Полосы прокрутки ───────────────────────────────────────────────────
    style.configure("Vertical.TScrollbar", background=Palette.SUBTLE, troughcolor=Palette.PANEL,
                    bordercolor=Palette.PANEL, arrowcolor=Palette.INK_SOFT, relief="flat", borderwidth=0)
    style.map("Vertical.TScrollbar", background=[("active", Palette.ACCENT_SOFT), ("pressed", Palette.ACCENT)])
    style.configure("Horizontal.TScrollbar", background=Palette.SUBTLE, troughcolor=Palette.PANEL,
                    bordercolor=Palette.PANEL, arrowcolor=Palette.INK_SOFT, relief="flat", borderwidth=0)

    # ── Разделители ────────────────────────────────────────────────────────
    style.configure("TSeparator", background=Palette.BORDER)
    style.configure("Steel.TSeparator", background=Palette.STEEL_LINE)

    # ── Индикаторы выполнения ──────────────────────────────────────────────
    style.configure("Horizontal.TProgressbar", troughcolor=Palette.SUBTLE, background=Palette.ACCENT,
                    bordercolor=Palette.SUBTLE, lightcolor=Palette.ACCENT, darkcolor=Palette.ACCENT,
                    borderwidth=0, thickness=14)
    style.configure("Accent.Horizontal.TProgressbar", troughcolor=Palette.SUBTLE, background=Palette.ACCENT,
                    bordercolor=Palette.SUBTLE, lightcolor=mix(Palette.ACCENT, "#FFFFFF", 0.25),
                    darkcolor=Palette.ACCENT_DEEP, borderwidth=0, thickness=16)
    style.configure("Ok.Horizontal.TProgressbar", troughcolor=Palette.SUBTLE, background=Palette.OK,
                    bordercolor=Palette.SUBTLE, lightcolor=mix(Palette.OK, "#FFFFFF", 0.25),
                    darkcolor=Palette.OK, borderwidth=0, thickness=16)
    style.configure("Warn.Horizontal.TProgressbar", troughcolor=Palette.SUBTLE, background=Palette.WARN,
                    bordercolor=Palette.SUBTLE, lightcolor=Palette.WARN, darkcolor=Palette.WARN,
                    borderwidth=0, thickness=16)
    style.configure("Err.Horizontal.TProgressbar", troughcolor=Palette.SUBTLE, background=Palette.ERR,
                    bordercolor=Palette.SUBTLE, lightcolor=Palette.ERR, darkcolor=Palette.ERR,
                    borderwidth=0, thickness=16)
    style.configure("Thin.Horizontal.TProgressbar", troughcolor=Palette.SUBTLE, background=Palette.ACCENT,
                    bordercolor=Palette.SUBTLE, lightcolor=Palette.ACCENT, darkcolor=Palette.ACCENT,
                    borderwidth=0, thickness=5)
    style.configure("Steel.Horizontal.TProgressbar", troughcolor=Palette.STEEL_DEEP, background=Palette.TEAL,
                    bordercolor=Palette.STEEL_DEEP, lightcolor=mix(Palette.TEAL, "#FFFFFF", 0.3),
                    darkcolor=Palette.TEAL, borderwidth=0, thickness=8)

    return fonts


# ═══════════════════════════════════════════════════════════════════════════
#  Плавный индикатор выполнения
# ═══════════════════════════════════════════════════════════════════════════

class AnimatedProgressbar(ttk.Progressbar):
    """ttk.Progressbar, который доезжает до нового значения плавно.

    Присваивание ``bar["value"] = 60`` задаёт цель, а виджет подтягивается к
    ней кадрами по ~16 мс. Совместим по интерфейсу с обычным Progressbar,
    поэтому вызывающий код менять не нужно.
    """

    def __init__(self, master=None, *, ease: float = 0.22, **kwargs):
        kwargs.setdefault("mode", "determinate")
        kwargs.setdefault("maximum", 100)
        super().__init__(master, **kwargs)
        self._ease = ease
        self._target = float(kwargs.get("value", 0) or 0)
        self._job = None
        self.bind("<Destroy>", self._stop, add="+")

    # -- совместимость с обычным виджетом ----------------------------------
    def configure(self, cnf=None, **kwargs):  # noqa: D401
        captured = False
        if isinstance(cnf, dict) and "value" in cnf:
            cnf = dict(cnf)
            self.set_target(cnf.pop("value"))
            captured = True
        if "value" in kwargs:
            self.set_target(kwargs.pop("value"))
            captured = True
        if cnf is None and not kwargs:
            return None if captured else super().configure()
        if cnf is None:
            return super().configure(**kwargs)
        return super().configure(cnf, **kwargs)

    config = configure

    # -- анимация ----------------------------------------------------------
    def set_target(self, value) -> None:
        try:
            target = float(value)
        except (TypeError, ValueError):
            return
        maximum = float(self.cget("maximum") or 100)
        self._target = max(0.0, min(maximum, target))
        # Сброс в ноль показываем сразу — так понятнее, что операция началась.
        if self._target == 0.0:
            self._stop()
            super().configure(value=0)
            return
        self._start()

    def jump_to(self, value) -> None:
        """Мгновенно, без анимации."""
        self._stop()
        self._target = float(value)
        super().configure(value=self._target)

    def _start(self) -> None:
        if self._job is None:
            self._job = self.after(16, self._tick)

    def _stop(self, _event=None) -> None:
        job, self._job = self._job, None
        if job is not None:
            try:
                self.after_cancel(job)
            except Exception:
                pass

    def _tick(self) -> None:
        self._job = None
        try:
            current = float(self.cget("value") or 0)
        except Exception:
            return
        delta = self._target - current
        if abs(delta) < 0.4:
            super().configure(value=self._target)
            return
        step = delta * self._ease
        # Минимальный шаг, чтобы «хвост» не полз бесконечно долго.
        if abs(step) < 0.6:
            step = 0.6 if delta > 0 else -0.6
        super().configure(value=current + step)
        self._job = self.after(16, self._tick)


class ProgressPanel(ttk.Frame):
    """Индикатор выполнения + подпись стадии + процент — как на приборе."""

    def __init__(self, master, *, caption: str = "Ожидание команды", style_name: str = "Accent.Horizontal.TProgressbar", **kwargs):
        super().__init__(master, **kwargs)
        self.columnconfigure(0, weight=1)

        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(0, weight=1)

        self.caption_var = tk.StringVar(value=caption)
        self.percent_var = tk.StringVar(value="0 %")
        ttk.Label(top, textvariable=self.caption_var, style="Info.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(top, textvariable=self.percent_var, style="Mono.TLabel").grid(row=0, column=1, sticky="e")

        self.bar = AnimatedProgressbar(self, style=style_name, maximum=100)
        self.bar.grid(row=1, column=0, sticky="ew", pady=(4, 0))

        self._poll = None
        self._watch()

    # Прокси: панель можно использовать там, где ожидается Progressbar.
    def __setitem__(self, key, value):
        if key == "value":
            self.bar.set_target(value)
            return
        super().__setitem__(key, value)

    def __getitem__(self, key):
        if key == "value":
            return self.bar.cget("value")
        return super().__getitem__(key)

    def set_stage(self, text: str, percent: float | None = None, style_name: str | None = None) -> None:
        self.caption_var.set(text)
        if style_name:
            self.bar.configure(style=style_name)
        if percent is not None:
            self.bar.set_target(percent)

    def _watch(self) -> None:
        try:
            value = float(self.bar.cget("value") or 0)
            self.percent_var.set(f"{value:5.1f} %")
        except Exception:
            pass
        self._poll = self.after(80, self._watch)

    def destroy(self) -> None:
        if self._poll is not None:
            try:
                self.after_cancel(self._poll)
            except Exception:
                pass
        super().destroy()


# ═══════════════════════════════════════════════════════════════════════════
#  Мелкие приборные индикаторы
# ═══════════════════════════════════════════════════════════════════════════

class StatusLED(tk.Canvas):
    """Светодиод с подписью: норма / внимание / ошибка / выключен.

    В состоянии «работа» мягко пульсирует — видно, что процесс идёт.
    """

    COLORS = {
        "off": (Palette.STEEL_LINE, Palette.ON_DARK_SOFT),
        "ok": (Palette.OK, Palette.ON_DARK),
        "warn": (Palette.WARN, Palette.ON_DARK),
        "err": (Palette.ERR, Palette.ON_DARK),
        "busy": (Palette.TEAL, Palette.ON_DARK),
    }

    def __init__(self, master, text: str, *, background: str = Palette.STEEL, width: int = 96, font=None):
        super().__init__(master, width=width, height=20, background=background,
                         highlightthickness=0, borderwidth=0)
        self._bg = background
        self._state = "off"
        self._phase = 0.0
        self._job = None
        self._glow = self.create_oval(3, 6, 13, 16, fill=Palette.STEEL_LINE, outline="")
        self._dot = self.create_oval(5, 8, 11, 14, fill=Palette.STEEL_LINE, outline="")
        self._label = self.create_text(19, 11, text=text, anchor="w",
                                       fill=Palette.ON_DARK_SOFT, font=font or (FONT_UI, 8, "bold"))
        self.bind("<Destroy>", self._stop, add="+")

    def set_state(self, state: str, text: str | None = None) -> None:
        self._state = state if state in self.COLORS else "off"
        color, text_color = self.COLORS[self._state]
        self.itemconfigure(self._dot, fill=color)
        self.itemconfigure(self._glow, fill=mix(self._bg, color, 0.35))
        self.itemconfigure(self._label, fill=text_color if state != "off" else Palette.ON_DARK_SOFT)
        if text is not None:
            self.itemconfigure(self._label, text=text)
        if self._state == "busy":
            self._start()
        else:
            self._stop()

    def _start(self) -> None:
        if self._job is None:
            self._job = self.after(60, self._pulse)

    def _stop(self, _event=None) -> None:
        job, self._job = self._job, None
        if job is not None:
            try:
                self.after_cancel(job)
            except Exception:
                pass

    def _pulse(self) -> None:
        self._job = None
        if self._state != "busy":
            return
        self._phase = (self._phase + 0.18) % (2 * math.pi)
        level = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(self._phase))
        color, _ = self.COLORS["busy"]
        self.itemconfigure(self._dot, fill=mix(self._bg, color, level))
        self.itemconfigure(self._glow, fill=mix(self._bg, color, level * 0.4))
        self._job = self.after(60, self._pulse)


class ActivityStrip(tk.Canvas):
    """Бегущая диаграмма активности в шапке — «прибор на связи».

    Рисует затухающую телеметрию; всплеск добавляется методом ``pulse()``
    при каждой операции с памятью.
    """

    def __init__(self, master, *, width: int = 150, height: int = 26, background: str = Palette.STEEL_DEEP):
        super().__init__(master, width=width, height=height, background=background,
                         highlightthickness=0, borderwidth=0)
        # Имена _cw/_ch: поле _w у виджета Tkinter занято путём виджета.
        self._cw, self._ch = width, height
        self._bg = background
        self._values = [0.06] * max(8, width // 3)
        self._phase = 0.0
        self._boost = 0.0
        self._job = None
        self.bind("<Destroy>", self._stop, add="+")
        self._tick()

    def pulse(self, strength: float = 1.0) -> None:
        self._boost = max(self._boost, min(1.0, strength))

    def _stop(self, _event=None) -> None:
        job, self._job = self._job, None
        if job is not None:
            try:
                self.after_cancel(job)
            except Exception:
                pass

    def _tick(self) -> None:
        self._phase += 0.35
        base = 0.10 + 0.06 * math.sin(self._phase) + 0.04 * math.sin(self._phase * 2.3)
        value = min(1.0, base + self._boost)
        self._boost *= 0.72
        if self._boost < 0.02:
            self._boost = 0.0
        self._values.append(value)
        self._values.pop(0)
        self._redraw()
        self._job = self.after(90, self._tick)

    def _redraw(self) -> None:
        self.delete("bar")
        # Подложка шкалы — так полоска читается даже в покое
        self.create_rectangle(0, 1, self._cw, self._ch - 1,
                              fill=mix(self._bg, Palette.STEEL_LINE, 0.35), outline="", tags="bar")
        count = len(self._values)
        step = self._cw / count
        for index, value in enumerate(self._values):
            height = max(4.0, (0.22 + 0.78 * value) * (self._ch - 6))
            x0 = index * step
            fade = 0.30 + 0.70 * (index / count)
            color = mix(self._bg, Palette.TEAL if value < 0.5 else Palette.ACCENT_SOFT, fade)
            self.create_rectangle(x0, self._ch - 3 - height, x0 + step - 1.2, self._ch - 3,
                                  fill=color, outline="", tags="bar")


class Marquee(tk.Canvas):
    """Тонкая «бегущая» полоса — индикатор фоновой занятости без процентов."""

    def __init__(self, master, *, width: int = 200, height: int = 4,
                 background: str = Palette.SUBTLE, color: str = Palette.ACCENT):
        super().__init__(master, height=height, background=background,
                         highlightthickness=0, borderwidth=0)
        self._color = color
        self._bg = background
        self._pos = 0.0
        self._job = None
        self._running = False
        self.bind("<Destroy>", lambda _e: self.stop(), add="+")

    def start(self) -> None:
        if not self._running:
            self._running = True
            self._pos = -0.25
            self._step()

    def stop(self) -> None:
        self._running = False
        job, self._job = self._job, None
        if job is not None:
            try:
                self.after_cancel(job)
            except Exception:
                pass
        try:  # виджет мог быть уже уничтожен
            self.delete("all")
        except tk.TclError:
            pass

    def _step(self) -> None:
        if not self._running:
            return
        width = max(self.winfo_width(), 1)
        height = max(self.winfo_height(), 1)
        self.delete("all")
        span = width * 0.28
        x = self._pos * width
        self.create_rectangle(x, 0, x + span, height, fill=self._color, outline="")
        self.create_rectangle(x - span * 0.4, 0, x, height,
                              fill=mix(self._bg, self._color, 0.4), outline="")
        self._pos += 0.022
        if self._pos > 1.05:
            self._pos = -0.3
        self._job = self.after(24, self._step)


class MiniLogo(tk.Canvas):
    """Знак программы: микросхема с выводами и импульсом энергии."""

    def __init__(self, master, size: int = 36, *, background: str = Palette.STEEL):
        super().__init__(master, width=size, height=size, background=background,
                         highlightthickness=0, borderwidth=0)
        draw_chip_mark(self, size, background=background)


def draw_chip_mark(canvas: tk.Canvas, size: int, *, background: str = Palette.STEEL,
                   body: str | None = None, accent: str | None = None, offset: tuple[int, int] = (0, 0)) -> None:
    """Рисует фирменный знак: корпус микросхемы, выводы и молнию."""
    body = body or mix(background, Palette.ACCENT_SOFT, 0.22)
    accent = accent or Palette.ACCENT_SOFT
    ox, oy = offset
    unit = size / 36.0

    def sx(value: float) -> float:
        return ox + value * unit

    def sy(value: float) -> float:
        return oy + value * unit

    pin = mix(background, accent, 0.55)
    for index in range(4):
        y = 9 + index * 6
        canvas.create_rectangle(sx(1), sy(y), sx(7), sy(y + 2.4), fill=pin, outline="")
        canvas.create_rectangle(sx(29), sy(y), sx(35), sy(y + 2.4), fill=pin, outline="")

    canvas.create_rectangle(sx(6), sy(6), sx(30), sy(30),
                            fill=mix(background, "#000000", 0.18), outline="")
    canvas.create_rectangle(sx(5), sy(5), sx(29), sy(29), fill=body,
                            outline=mix(accent, "#FFFFFF", 0.25), width=max(1, int(unit)))
    # Молния — энергия
    bolt = [18.5, 8.5, 12.5, 18.0, 16.5, 18.0, 14.5, 26.0, 21.5, 15.5, 17.0, 15.5, 20.5, 8.5]
    points = []
    for index in range(0, len(bolt), 2):
        points.extend((sx(bolt[index]), sy(bolt[index + 1])))
    canvas.create_polygon(points, fill=mix(accent, "#FFFFFF", 0.55), outline="")


# ═══════════════════════════════════════════════════════════════════════════
#  Микро-анимации
# ═══════════════════════════════════════════════════════════════════════════

def flash_widget(widget: tk.Misc, colors: tuple[str, ...] = (Palette.OK_TINT, Palette.SURFACE),
                 *, option: str = "background", steps: int = 12, interval: int = 40) -> None:
    """Короткая заливка виджета цветом с плавным возвратом — подтверждение."""
    start, end = colors[0], colors[-1]

    def frame(index: int = 0) -> None:
        if index > steps:
            try:
                widget.configure(**{option: end})
            except Exception:
                pass
            return
        try:
            widget.configure(**{option: mix(start, end, index / steps)})
        except Exception:
            return
        widget.after(interval, frame, index + 1)

    frame()


def fade_window(window: tk.Misc, start: float, end: float, *, steps: int = 14,
                interval: int = 16, on_done=None) -> None:
    """Плавное изменение прозрачности окна (там, где ОС это поддерживает)."""
    def frame(index: int = 0) -> None:
        ratio = index / steps
        try:
            window.attributes("-alpha", start + (end - start) * ratio)
        except Exception:
            if on_done:
                on_done()
            return
        if index >= steps:
            if on_done:
                on_done()
            return
        window.after(interval, frame, index + 1)

    frame()


class SectorMap(tk.Canvas):
    """Карта секторов SPI: какие 4-КиБ блоки отличаются от исходного образа.

    Наглядно показывает объём предстоящей прошивки: серая клетка — сектор не
    тронут, синяя — содержимое изменено. Новые изменения подсвечиваются и
    плавно гаснут до обычного цвета.
    """

    def __init__(self, master, *, columns: int = 16, rows: int = 8, cell: int = 15,
                 background: str = Palette.APP):
        width = columns * cell + 1
        height = rows * cell + 1
        super().__init__(master, width=width, height=height, background=background,
                         highlightthickness=0, borderwidth=0)
        self._columns, self._rows, self._cell = columns, rows, cell
        self._flags = [False] * (columns * rows)
        self._fresh: set[int] = set()
        self._phase = 0.0
        self._job = None
        self._cells = []
        for index in range(columns * rows):
            column, row = index % columns, index // columns
            x0, y0 = column * cell + 1, row * cell + 1
            self._cells.append(self.create_rectangle(
                x0, y0, x0 + cell - 2, y0 + cell - 2,
                fill=Palette.SUBTLE, outline=""))
        self.bind("<Destroy>", self._stop, add="+")

    def set_flags(self, flags: list[bool]) -> None:
        previous = self._flags
        self._flags = list(flags)[: len(self._cells)]
        self._flags += [False] * (len(self._cells) - len(self._flags))
        self._fresh = {index for index, value in enumerate(self._flags)
                       if value and not (index < len(previous) and previous[index])}
        self._paint()
        if self._fresh:
            self._phase = 1.0
            self._start()

    def _paint(self) -> None:
        for index, item in enumerate(self._cells):
            if not self._flags[index]:
                self.itemconfigure(item, fill=Palette.SUBTLE)
            elif index in self._fresh:
                self.itemconfigure(item, fill=mix(Palette.ACCENT, "#FFFFFF", self._phase * 0.7))
            else:
                self.itemconfigure(item, fill=Palette.ACCENT)

    def _start(self) -> None:
        if self._job is None:
            self._job = self.after(40, self._tick)

    def _stop(self, _event=None) -> None:
        job, self._job = self._job, None
        if job is not None:
            try:
                self.after_cancel(job)
            except Exception:
                pass

    def _tick(self) -> None:
        self._job = None
        self._phase -= 0.08
        if self._phase <= 0:
            self._phase = 0.0
            self._fresh.clear()
            self._paint()
            return
        self._paint()
        self._job = self.after(40, self._tick)
