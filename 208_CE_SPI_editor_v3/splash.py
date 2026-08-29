"""Экран загрузки редактора CE208.

Показывает знак программы, стадии инициализации и индикатор выполнения.
Пока строится основное окно, цикл событий Tk ещё не запущен, поэтому кадры
анимации прокручиваются вручную методом ``_pump`` — так движение видно даже
во время тяжёлых стадий (разбор дескрипторов, проверка CRC).
"""

from __future__ import annotations

import math
import time
import tkinter as tk

from ui_theme import Palette, draw_chip_mark, fade_window, mix, pick_mono

WIDTH = 720
HEIGHT = 380
LOG_LINES = 5


class SplashScreen(tk.Toplevel):
    """Тёмная приборная заставка с журналом инициализации."""

    def __init__(self, master: tk.Misc, *, title: str = "208_CE V8530P · MSP4xx",
                 subtitle: str = "Редактор энергонезависимой памяти прибора учёта",
                 version: str = "", footer: str = "",
                 parameters: list[tuple[str, str]] | None = None):
        super().__init__(master)
        self.withdraw()
        self.overrideredirect(True)
        self.configure(background=Palette.STEEL_DEEP)
        self.resizable(False, False)

        self._mono = pick_mono(self)
        self._started = time.monotonic()
        self._phase = 0.0
        self._progress = 0.0
        self._target = 0.0
        self._log: list[str] = []
        self._stage_text = "Подготовка"

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = max(0, (screen_w - WIDTH) // 2)
        y = max(0, (screen_h - HEIGHT) // 2 - 40)
        self.geometry(f"{WIDTH}x{HEIGHT}+{x}+{y}")

        self.canvas = tk.Canvas(self, width=WIDTH, height=HEIGHT, highlightthickness=0,
                                borderwidth=0, background=Palette.STEEL_DEEP)
        self.canvas.pack(fill="both", expand=True)

        self._title = title
        self._subtitle = subtitle
        self._version = version
        self._footer_lines = [part.strip() for part in footer.split("|")] if footer else []
        self._parameters = parameters or []
        self._stage_index = 0

        self._draw_static()
        try:
            self.attributes("-alpha", 0.0)
        except Exception:
            pass
        self.deiconify()
        try:
            self.attributes("-topmost", True)
        except Exception:
            pass
        self.update()
        self._fade_in()

    # ── статичная часть ────────────────────────────────────────────────────
    def _draw_static(self) -> None:
        canvas = self.canvas

        # Вертикальный градиент стали
        steps = 48
        for index in range(steps):
            ratio = index / (steps - 1)
            color = mix(Palette.STEEL, Palette.STEEL_DEEP, ratio)
            canvas.create_rectangle(0, HEIGHT * index / steps, WIDTH, HEIGHT * (index + 1) / steps + 1,
                                    fill=color, outline="")

        # Технический растр — едва заметная сетка
        grid = mix(Palette.STEEL_DEEP, Palette.STEEL_LINE, 0.30)
        for x in range(0, WIDTH, 26):
            canvas.create_line(x, 0, x, HEIGHT, fill=grid)
        for y in range(0, HEIGHT, 26):
            canvas.create_line(0, y, WIDTH, y, fill=grid)

        # Рамка
        canvas.create_rectangle(1, 1, WIDTH - 1, HEIGHT - 1, outline=Palette.STEEL_LINE, width=1)
        canvas.create_rectangle(0, 0, WIDTH, 4, fill=Palette.ACCENT, outline="")

        # Знак программы
        draw_chip_mark(canvas, 72, background=Palette.STEEL, offset=(46, 52))

        canvas.create_text(146, 66, text=self._title, anchor="w", fill="#FFFFFF",
                           font=("TkDefaultFont", 21, "bold"))
        canvas.create_text(148, 96, text=self._subtitle, anchor="w", fill=Palette.ON_DARK_SOFT,
                           font=("TkDefaultFont", 10))
        if self._version:
            canvas.create_rectangle(146, 112, 146 + 9 * len(self._version) + 16, 134,
                                    fill=Palette.STEEL_SOFT, outline=Palette.STEEL_LINE)
            canvas.create_text(154, 123, text=self._version, anchor="w", fill=Palette.ACCENT_SOFT,
                               font=(self._mono, 9, "bold"))

        canvas.create_line(40, 156, WIDTH - 40, 156, fill=Palette.STEEL_LINE)

        # Левая колонка — журнал инициализации
        canvas.create_text(40, 172, text="ЖУРНАЛ ИНИЦИАЛИЗАЦИИ", anchor="w",
                           fill=Palette.ACCENT_SOFT, font=("TkDefaultFont", 8, "bold"))
        self._log_items = [
            canvas.create_text(40, 194 + index * 20, text="", anchor="w",
                               fill=Palette.ON_DARK_SOFT, font=(self._mono, 9))
            for index in range(LOG_LINES)
        ]

        # Правая колонка — параметры восстановленной модели памяти
        canvas.create_line(404, 166, 404, 288, fill=Palette.STEEL_LINE)
        canvas.create_text(424, 172, text="ПАРАМЕТРЫ МОДЕЛИ", anchor="w",
                           fill=Palette.ACCENT_SOFT, font=("TkDefaultFont", 8, "bold"))
        for index, (key, value) in enumerate(self._parameters):
            y = 192 + index * 19
            canvas.create_text(424, y, text=key, anchor="w", fill=Palette.ON_DARK_SOFT,
                               font=("TkDefaultFont", 8))
            canvas.create_text(WIDTH - 40, y, text=value, anchor="e", fill=Palette.ON_DARK,
                               font=(self._mono, 9, "bold"))

        # Индикатор выполнения
        self._bar_x0, self._bar_x1, self._bar_y = 40, WIDTH - 40, 306
        canvas.create_rectangle(self._bar_x0, self._bar_y, self._bar_x1, self._bar_y + 14,
                                fill=Palette.STEEL_DEEP, outline=Palette.STEEL_LINE)
        self._bar_fill = canvas.create_rectangle(self._bar_x0 + 1, self._bar_y + 1,
                                                 self._bar_x0 + 1, self._bar_y + 13,
                                                 fill=Palette.TEAL, outline="")
        self._bar_head = canvas.create_rectangle(0, 0, 0, 0, fill=Palette.ACCENT_SOFT, outline="")
        self._percent = canvas.create_text(self._bar_x1, self._bar_y - 12, text="0 %", anchor="e",
                                           fill=Palette.ON_DARK, font=(self._mono, 10, "bold"))
        self._stage_item = canvas.create_text(self._bar_x0 + 24, self._bar_y - 12, text="этап 0",
                                              anchor="w", fill=Palette.ON_DARK_SOFT,
                                              font=("TkDefaultFont", 9))
        # Вращающийся индикатор занятости слева от счётчика этапов
        self._spinner = canvas.create_arc(self._bar_x0 + 1, self._bar_y - 20, self._bar_x0 + 15, self._bar_y - 6,
                                          start=0, extent=90, style="arc", outline=Palette.ACCENT_SOFT, width=2)

        canvas.create_line(40, 332, WIDTH - 40, 332, fill=Palette.STEEL_LINE)
        footer_color = mix(Palette.STEEL_DEEP, Palette.ON_DARK_SOFT, 0.72)
        for index, line in enumerate(self._footer_lines):
            canvas.create_text(40, 348 + index * 14, text=line, anchor="w",
                               fill=footer_color, font=(self._mono, 8))

    # ── публичный интерфейс ────────────────────────────────────────────────
    def stage(self, text: str, percent: float, *, settle: int = 260) -> None:
        """Отметить стадию: записать в журнал и доехать до процента."""
        if self._log:
            self._log[-1] = "✓ " + self._log[-1][2:]
        self._log.append("▸ " + text)
        del self._log[:-LOG_LINES]
        self._stage_text = text
        self._stage_index += 1
        self._target = max(self._target, min(100.0, float(percent)))
        self.canvas.itemconfigure(self._stage_item, text=f"этап {self._stage_index}")
        self._redraw_log()
        self._pump(settle)

    def note(self, text: str) -> None:
        """Строка журнала без изменения процента (подробность инициализации)."""
        if self._log:
            self._log[-1] = "✓ " + self._log[-1][2:]
        self._log.append("· " + text)
        del self._log[:-LOG_LINES]
        self._redraw_log()
        self._pump(90)

    def finish(self, *, minimum: float = 1.9) -> None:
        """Довести полосу до 100 %, выдержать паузу и плавно погасить экран."""
        self._target = 100.0
        if self._log:
            self._log[-1] = "✓ " + self._log[-1][2:]
            self._redraw_log()
        self.canvas.itemconfigure(self._stage_item, text="инициализация завершена")
        self.canvas.itemconfigure(self._spinner, outline=Palette.OK)
        remaining = max(0.0, minimum - (time.monotonic() - self._started))
        self._pump(int(max(remaining, 0.45) * 1000))
        try:
            fade_window(self, 1.0, 0.0, steps=12, interval=16)
            for _ in range(14):
                self.update()
                time.sleep(0.016)
        except Exception:
            pass
        self.destroy()

    # ── анимация ───────────────────────────────────────────────────────────
    def _fade_in(self) -> None:
        for index in range(11):
            try:
                self.attributes("-alpha", index / 10)
            except Exception:
                break
            self.update()
            time.sleep(0.012)

    def _pump(self, milliseconds: int) -> None:
        """Прокрутить кадры анимации указанное время (цикл Tk ещё не запущен)."""
        deadline = time.monotonic() + milliseconds / 1000.0
        while time.monotonic() < deadline:
            self._frame()
            try:
                self.update()
            except tk.TclError:
                return
            time.sleep(0.016)

    def _frame(self) -> None:
        self._phase += 8.0
        delta = self._target - self._progress
        self._progress += delta * 0.16 if abs(delta) > 0.3 else delta

        span = (self._bar_x1 - self._bar_x0 - 2) * self._progress / 100.0
        x0 = self._bar_x0 + 1
        self.canvas.coords(self._bar_fill, x0, self._bar_y + 1, x0 + span, self._bar_y + 11)
        # Светлая «голова» полосы — видно направление движения
        if span > 6:
            self.canvas.coords(self._bar_head, x0 + span - 6, self._bar_y + 1, x0 + span, self._bar_y + 11)
        else:
            self.canvas.coords(self._bar_head, 0, 0, 0, 0)
        self.canvas.itemconfigure(self._percent, text=f"{self._progress:5.1f} %")

        self.canvas.itemconfigure(self._spinner, start=-self._phase % 360,
                                  extent=90 + 40 * math.sin(math.radians(self._phase * 0.7)))

    LOG_WIDTH = 46  # символов моноширинного шрифта до правой колонки

    def _redraw_log(self) -> None:
        for index, item in enumerate(self._log_items):
            text = self._log[index] if index < len(self._log) else ""
            if len(text) > self.LOG_WIDTH:
                text = text[:self.LOG_WIDTH - 1] + "…"
            color = Palette.ON_DARK if text.startswith("▸") else Palette.ON_DARK_SOFT
            if text.startswith("✓"):
                color = mix(Palette.STEEL_DEEP, Palette.OK, 0.85)
            self.canvas.itemconfigure(item, text=text, fill=color)
