"""Tkinter GUI for the recovered CE208 V8530P non-volatile model."""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ce208_model import (
    AT25_SIZE,
    ENERGY_ARCHIVES,
    EVENT_LOGS,
    FIXED_DESCRIPTORS,
    SMALL_SIZE,
    CE208State,
    ClockValue,
    EnergyBank,
    TimeCounterBlock,
    at25_program_sectors,
    crc_scheme_title,
    decode_energy,
    set_crc_scheme,
    encode_energy,
    sha256,
)

# Оформление вынесено в отдельные модули и не влияет на модель памяти.
from ui_theme import (
    ActivityStrip,
    AnimatedProgressbar,
    Marquee,
    Palette,
    ProgressPanel,
    SectorMap,
    StatusLED,
    apply_theme,
    draw_chip_mark,
    flash_widget,
)
from app_icon import set_window_icon
from splash import SplashScreen

# Прямая запись через CH341 (i2cpy) — как в MT_Writer. Необязательная зависимость.
try:
    from i2cpy import I2C
    I2C_IMPORT_ERROR = None
except Exception as _i2c_exc:  # noqa: BLE001
    I2C = None
    I2C_IMPORT_ERROR = f"{type(_i2c_exc).__name__}: {_i2c_exc}"


APP_VERSION = "2.2.0"
# Имя программы: прибор плюс семейство контроллера, чьи дампы редактор понимает.
APP_NAME = "208_CE V8530P · MSP432"
APP_TITLE = f"{APP_NAME} — редактор памяти — {APP_VERSION}"

# Короткие подписи схем контрольной суммы для правой панели.
CRC_SCHEME_LABELS = {
    "ce208": "V8530 CRC-32",
    "msp432": "MSP432 CRC-16",
}

# Выбор процессора прибора: от него зависит алгоритм контрольной суммы записи.
# «Авто» — определить по самому образу, остальные — жёстко задать.
CRC_MODES = {
    "Авто": "auto",
    "V8530": "ce208",
    "MSP432": "msp432",
}
CRC_MODE_TITLES = {value: key for key, value in CRC_MODES.items()}

# Технические строки внизу экрана загрузки (разделитель строк — «|»).
BOOT_FOOTER = (
    "CRC-32 MSB 0x04C11DB7 · запись 0x44 Б · 13 ячеек u40le · 4 банка"
    " | "
    "архивы 0/1/2/5 · журналы 0x47E70..0x49DEF (70) · зеркальные копии + CRC"
)

# Сводка восстановленной модели памяти — правая колонка экрана загрузки.
BOOT_PARAMETERS = [
    ("Внешняя SPI", "25DF041B · 0x80000"),
    ("Внутренняя EEPROM", "24LC64 · 0x2000"),
    ("Энергобанки", "4 × 13 × u40"),
    ("Кольцевые архивы", "типы 0/1/2/5"),
    ("Журналы событий", "70"),
]


# ═══════════════════════════════════════════════════════════════════════════
#  Прямая запись в I²C EEPROM через CH341 (логика из MT_Writer, адаптирована).
#  MT_Writer писал 24C16 (блочная адресация, addrsize=8). Здесь основной чип —
#  24LC64: 8 КБ, 16-битный адрес (addrsize=16), страница 32 байта, устр. 0x50.
# ═══════════════════════════════════════════════════════════════════════════

CHIP_PROFILES = {
    # name: (size, addrsize, page, device_base, uses_block_in_addr)
    "24LC64 (8 КБ)":  (0x2000, 16, 32, 0x50, False),
    "24C16 (2 КБ)":   (0x0800, 8, 16, 0x50, True),
}


class DirectWriter:
    """Порт i2c-логики MT_Writer: открыть CH341, писать страницами, проверить."""

    def __init__(self, profile_name: str = "24LC64 (8 КБ)"):
        self.set_profile(profile_name)
        self.i2c = None

    def set_profile(self, name: str) -> None:
        self.profile_name = name
        self.size, self.addrsize, self.page, self.dev_base, self.block_in_addr = CHIP_PROFILES[name]

    def available(self) -> bool:
        return I2C is not None

    def open(self) -> None:
        if I2C is None:
            hint = f" (импорт не удался: {I2C_IMPORT_ERROR})" if I2C_IMPORT_ERROR else " (pip install i2cpy)"
            raise RuntimeError("Библиотека i2cpy недоступна" + hint)
        self.close()
        self.i2c = I2C(driver="ch341")

    def close(self) -> None:
        obj, self.i2c = self.i2c, None
        if obj is not None:
            for m in ("close", "deinit", "disconnect"):
                fn = getattr(obj, m, None)
                if callable(fn):
                    try:
                        fn()
                    except Exception:
                        pass
                    break
        time.sleep(0.05)

    def _addr(self, address: int):
        """Возвращает (device_address, memory_address) с учётом профиля."""
        if self.block_in_addr:  # 24C16-подобная: блок в адресе устройства
            block = (address >> 8) & 0x07
            return self.dev_base | block, address & 0xFF
        return self.dev_base, address  # 24LC64: полный адрес, addrsize=16

    def read_bytes(self, address: int, length: int) -> bytes:
        if self.i2c is None:
            raise RuntimeError("Программатор не открыт.")
        out = bytearray()
        cur, rem = address, length
        while rem > 0:
            dev, mem = self._addr(cur)
            step = min(rem, 0x100 - (mem & 0xFF)) if self.block_in_addr else min(rem, 0x1000)
            chunk = self.i2c.readfrom_mem(dev, mem, step, addrsize=self.addrsize)
            out.extend(bytes(chunk))
            cur += step
            rem -= step
        return bytes(out)

    def write_bytes(self, address: int, payload: bytes) -> None:
        if self.i2c is None:
            raise RuntimeError("Программатор не открыт.")
        # Пишем страницами, не пересекая границу страницы (требование EEPROM)
        i = 0
        while i < len(payload):
            dev, mem = self._addr(address + i)
            room = self.page - ((address + i) % self.page)
            step = min(room, len(payload) - i)
            self.i2c.writeto_mem(dev, mem, bytes(payload[i:i + step]), addrsize=self.addrsize)
            time.sleep(0.006)  # внутренний цикл записи EEPROM (tWR)
            i += step

    def write_image(self, image: bytes, progress=None) -> None:
        """Запись всего образа страницами + прогресс (0..100)."""
        total = min(len(image), self.size)
        step = self.page
        for off in range(0, total, step):
            self.write_bytes(off, image[off:off + step])
            if progress:
                progress(int(100 * (off + step) / total))

    def verify_image(self, image: bytes, progress=None) -> tuple[bool, int]:
        """Читает обратно и сравнивает. Возвращает (совпало, первый_несовпавший_адрес)."""
        total = min(len(image), self.size)
        chunk = 256
        for off in range(0, total, chunk):
            got = self.read_bytes(off, min(chunk, total - off))
            exp = image[off:off + len(got)]
            if got != exp:
                for k in range(len(got)):
                    if got[k] != exp[k]:
                        return False, off + k
            if progress:
                progress(int(100 * (off + chunk) / total))
        return True, -1


class Editor(tk.Tk):
    def __init__(self, show_splash: bool = True, crc_mode: str = "auto") -> None:
        super().__init__()
        self.withdraw()  # окно появится после экрана загрузки
        self.title(APP_TITLE)
        self.geometry("1480x1000")
        self.minsize(1240, 820)

        # Оформление: единая палитра «инженерная сталь» и стили ttk.
        self.fonts = apply_theme(self)
        self.mono_font = self.fonts["mono"]
        # Имена цветов сохранены прежними — на них ссылается остальной код.
        self.bg_color = Palette.APP
        self.fg_color = Palette.INK
        self.accent_color = Palette.ACCENT_DEEP
        self.header_color = Palette.STEEL
        self.border_color = Palette.BORDER
        self.success_color = Palette.OK
        self.warning_color = Palette.WARN
        self.configure(bg=self.bg_color)
        self.app_icon = set_window_icon(self)

        boot = SplashScreen(
            self,
            title=APP_NAME,
            version=f"версия {APP_VERSION}",
            footer=BOOT_FOOTER,
            parameters=BOOT_PARAMETERS,
        ) if show_splash else None

        if boot:
            boot.stage("Инициализация модели энергонезависимой памяти", 12)
        self.state_model = CE208State()
        self.at25_path: Path | None = None
        self.at25_loaded = False
        self.source_kind = "spi"  # "spi" (512К 25DF041B) или "24lc64" (8К внутр. EEPROM)
        self.raw_selected = None
        self.crc_ok_count = 0
        self.crc_total_count = len(FIXED_DESCRIPTORS)
        if boot:
            boot.note(f"карта: {len(FIXED_DESCRIPTORS)} дескрипторов, {len(EVENT_LOGS)} журналов событий")

        if boot:
            boot.stage("Проверка программатора CH341 (i2cpy)", 26)
        self.direct_writer = DirectWriter("24LC64 (8 КБ)")
        if boot:
            boot.note("i2cpy найдена — прямая запись доступна" if self.direct_writer.available()
                      else "i2cpy не установлена — режим работы с файлом образа")

        self.crc_mode = tk.StringVar(value=CRC_MODE_TITLES.get(crc_mode, "Авто"))
        self.status_var = tk.StringVar(value="Откройте дамп 24LC64 (8 КиБ) или 25DF041B (512 КиБ)")
        self.at25_var = tk.StringVar(value="SPI: не загружен")
        self.telemetry_var = tk.StringVar(value="изменено: — · CRC —")
        self.clock_var = tk.StringVar(value="--:--:--")

        if boot:
            boot.stage("Построение панелей интерфейса", 48)
        self._build_ui()
        if boot:
            boot.note("8 разделов: время, счётчики, энергия, архивы, события, raw, запись, проверка")

        if boot:
            boot.stage("Разбор дескрипторов и проверка контрольных сумм", 78)
        self.refresh_all()
        if boot:
            boot.note(f"контрольные суммы: {self.crc_ok_count} из {self.crc_total_count} записей верны")
            boot.stage("Подготовка рабочего места", 96)
            boot.finish()

        self._tick_clock()
        self.deiconify()
        self.lift()
        self.focus_force()

    def _warning_text(self) -> str:
        if getattr(self, "source_kind", "spi") == "24lc64":
            return (
                "Загружена внутренняя EEPROM 24LC64 (8 КиБ) — здесь хранятся часы, тарифы и текущие показания "
                "(small-path). Архивы и журналы событий лежат во внешней SPI 25DF041B (512 КиБ)."
            )
        return (
            "Загружена внешняя SPI 25DF041B (512 КиБ): архивы, резервные области и события. Логический small-path — "
            "нижние 0x2000 байт этого же BIN; текущие показания прибор обычно держит во внутренней EEPROM 24LC64."
        )

    def _scrollable_tab(self, notebook: ttk.Notebook, text: str) -> ttk.Frame:
        """Добавляет вкладку с вертикальным скроллом и возвращает внутренний фрейм,
        на котором строится содержимое (как обычная вкладка)."""
        container = ttk.Frame(notebook)
        notebook.add(container, text=text)
        # Тонкая акцентная полоса — визуальная «шина» раздела
        tk.Frame(container, background=Palette.ACCENT_SOFT, height=2).pack(fill="x", side="top")

        canvas = tk.Canvas(container, borderwidth=0, highlightthickness=0, background=self.bg_color)
        vbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vbar.set)
        vbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = ttk.Frame(canvas, padding=14)
        window = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner_configure(_e=None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(e) -> None:
            canvas.itemconfigure(window, width=e.width)  # тянем содержимое по ширине

        inner.bind("<Configure>", _on_inner_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        # Прокрутка колесом: активна, пока курсор над этой вкладкой
        def _on_wheel(event) -> None:
            delta = event.delta
            if delta == 0:
                return
            canvas.yview_scroll(int(-delta / 120) or (-1 if delta > 0 else 1), "units")

        def _on_wheel_linux(event) -> None:
            canvas.yview_scroll(-1 if event.num == 4 else 1, "units")

        def _bind_wheel(_e=None) -> None:
            canvas.bind_all("<MouseWheel>", _on_wheel)
            canvas.bind_all("<Button-4>", _on_wheel_linux)
            canvas.bind_all("<Button-5>", _on_wheel_linux)

        def _unbind_wheel(_e=None) -> None:
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        canvas.bind("<Enter>", _bind_wheel)
        canvas.bind("<Leave>", _unbind_wheel)
        return inner

    # ═══════════════════════════════════════════════════════════════════
    #  Каркас окна: приборная шапка, панель операций, разделы, статусная
    #  строка. Всё оформление держится здесь и не касается модели памяти.
    # ═══════════════════════════════════════════════════════════════════

    def _build_ui(self) -> None:
        self._build_header()
        self._build_toolbar()

        # Информационная плашка (зависит от источника)
        self.warning_var = tk.StringVar(value=self._warning_text())
        self.notice = ttk.Label(
            self,
            textvariable=self.warning_var,
            style="NoteWarn.TLabel",
            wraplength=1040,
            justify="left",
        )
        self.notice.pack(fill="x", padx=14, pady=(4, 10))

        content = ttk.Frame(self)
        content.pack(fill="both", expand=True, padx=14, pady=(0, 8))
        self._build_side_panel(content)

        tabs = ttk.Notebook(content)
        tabs.pack(side="left", fill="both", expand=True, padx=(0, 12))
        # Каждая вкладка — прокручиваемый контейнер (общий вертикальный скролл)
        self.clock_tab = self._scrollable_tab(tabs, "01 · Время")
        self.counter_tab = self._scrollable_tab(tabs, "02 · Счётчики")
        self.energy_tab = self._scrollable_tab(tabs, "03 · Энергия")
        self.archive_tab = self._scrollable_tab(tabs, "04 · Архивы")
        self.event_tab = self._scrollable_tab(tabs, "05 · События")
        self.raw_tab = self._scrollable_tab(tabs, "06 · Raw")
        self.direct_tab = self._scrollable_tab(tabs, "07 · Запись")
        self.audit_tab = self._scrollable_tab(tabs, "08 · Проверка")
        self._build_clock_tab()
        self._build_counter_tab()
        self._build_energy_tab()
        self._build_archive_tab()
        self._build_event_tab()
        self._build_raw_tab()
        self._build_direct_tab()
        self._build_audit_tab()

        self._build_statusbar()

    def _build_header(self) -> None:
        """Тёмная приборная шапка: знак, название, индикаторы состояния."""
        header = tk.Frame(self, background=Palette.STEEL_DEEP)
        header.pack(fill="x", side="top")
        tk.Frame(header, background=Palette.ACCENT, height=3).pack(fill="x")

        body = tk.Frame(header, background=Palette.STEEL_DEEP)
        body.pack(fill="x", padx=16, pady=10)

        logo = tk.Canvas(body, width=44, height=44, background=Palette.STEEL_DEEP,
                         highlightthickness=0, borderwidth=0)
        logo.pack(side="left", padx=(0, 12))
        draw_chip_mark(logo, 44, background=Palette.STEEL_DEEP)

        titles = tk.Frame(body, background=Palette.STEEL_DEEP)
        titles.pack(side="left", anchor="w")
        tk.Label(titles, text=APP_NAME, background=Palette.STEEL_DEEP, foreground="#FFFFFF",
                 font=("TkDefaultFont", 15, "bold")).pack(anchor="w")
        tk.Label(titles, text="Редактор энергонезависимой памяти · прошивка 10.14 · SPI 25DF041B / EEPROM 24LC64",
                 background=Palette.STEEL_DEEP, foreground=Palette.ON_DARK_SOFT,
                 font=("TkDefaultFont", 9)).pack(anchor="w")

        # Правый блок — телеметрия и индикаторы
        right = tk.Frame(body, background=Palette.STEEL_DEEP)
        right.pack(side="right")

        top_right = tk.Frame(right, background=Palette.STEEL_DEEP)
        top_right.pack(anchor="e")
        tk.Label(top_right, text=f"версия {APP_VERSION}", background=Palette.STEEL_DEEP,
                 foreground=Palette.ACCENT_SOFT, font=(self.mono_font, 9, "bold")).pack(side="left", padx=(0, 14))
        tk.Label(top_right, textvariable=self.clock_var, background=Palette.STEEL_DEEP,
                 foreground=Palette.ON_DARK, font=(self.mono_font, 12, "bold")).pack(side="left")

        leds = tk.Frame(right, background=Palette.STEEL_DEEP)
        leds.pack(anchor="e", pady=(6, 0))
        self.activity = ActivityStrip(leds, width=132, height=22, background=Palette.STEEL_DEEP)
        self.activity.pack(side="left", padx=(0, 14))
        self.led_source = StatusLED(leds, "ОБРАЗ", background=Palette.STEEL_DEEP, width=104)
        self.led_source.pack(side="left")
        self.led_crc = StatusLED(leds, "CRC", background=Palette.STEEL_DEEP, width=96)
        self.led_crc.pack(side="left")
        self.led_link = StatusLED(leds, "CH341", background=Palette.STEEL_DEEP, width=84)
        self.led_link.pack(side="left")
        self.led_link.set_state("ok" if self.direct_writer.available() else "off", "CH341")

    def _build_toolbar(self) -> None:
        """Светлая панель файловых операций под шапкой."""
        toolbar = ttk.Frame(self, padding=(14, 12, 14, 8))
        toolbar.pack(fill="x")

        ttk.Label(toolbar, text="ОБРАЗ ПАМЯТИ", style="Faint.TLabel").pack(side="left", padx=(0, 12))
        ttk.Button(toolbar, text="Открыть дамп…", style="Primary.TButton",
                   command=self.open_at25).pack(side="left", padx=(0, 8))
        ttk.Button(toolbar, text="Сохранить как…", command=self.save_spi).pack(side="left", padx=(0, 8))
        ttk.Button(toolbar, text="Экспорт отчёта", command=self.save_audit).pack(side="left", padx=(0, 8))

        ttk.Label(toolbar, textvariable=self.at25_var, style="Section.TLabel").pack(side="right")
        ttk.Label(toolbar, text="ИСТОЧНИК", style="Faint.TLabel").pack(side="right", padx=(0, 10))

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=14)

    def _build_side_panel(self, parent: ttk.Frame) -> None:
        """Правая колонка: сводка по образу, контроль целостности, карта секторов."""
        panel = ttk.Frame(parent, width=292)
        panel.pack(side="right", fill="y")
        panel.pack_propagate(False)

        ttk.Label(panel, text="СОСТОЯНИЕ ОБРАЗА", style="Faint.TLabel").pack(anchor="w")
        ttk.Separator(panel, orient="horizontal").pack(fill="x", pady=(4, 8))

        table = ttk.Frame(panel)
        table.pack(fill="x")
        table.columnconfigure(1, weight=1)
        self.side_vars: dict[str, tk.StringVar] = {}
        rows = [
            ("Файл", "не загружен"),
            ("Память", "—"),
            ("Объём", "—"),
            ("Контроль", "—"),
            ("Изменено", "0 / 0"),
            ("Часы", "—"),
            ("Тариф", "—"),
            ("События", "0"),
            ("Программатор", "—"),
        ]
        for index, (key, value) in enumerate(rows):
            variable = tk.StringVar(value=value)
            self.side_vars[key] = variable
            ttk.Label(table, text=key, style="Faint.TLabel").grid(row=index, column=0, sticky="w", pady=2)
            ttk.Label(table, textvariable=variable, style="Mono.TLabel", anchor="e").grid(
                row=index, column=1, sticky="e", pady=2)

        # Режим контрольной суммы: подбор по образу или жёстко заданная схема
        mode_row = ttk.Frame(panel)
        mode_row.pack(fill="x", pady=(10, 0))
        ttk.Label(mode_row, text="Процессор", style="Faint.TLabel").pack(side="left")
        mode_box = ttk.Combobox(mode_row, values=list(CRC_MODES), textvariable=self.crc_mode,
                                width=9, state="readonly")
        mode_box.pack(side="right")
        mode_box.bind("<<ComboboxSelected>>", self.change_crc_mode)

        # Контроль целостности — доля записей с верной CRC
        ttk.Label(panel, text="КОНТРОЛЬ ЦЕЛОСТНОСТИ", style="Faint.TLabel").pack(anchor="w", pady=(16, 0))
        ttk.Separator(panel, orient="horizontal").pack(fill="x", pady=(4, 8))
        self.crc_caption = tk.StringVar(value="CRC записей: —")
        ttk.Label(panel, textvariable=self.crc_caption, style="Info.TLabel").pack(anchor="w")
        self.crc_bar = AnimatedProgressbar(panel, style="Ok.Horizontal.TProgressbar", maximum=100)
        self.crc_bar.pack(fill="x", pady=(4, 10))

        self.sector_caption = tk.StringVar(value="Секторы к прошивке: 0 из 128")
        ttk.Label(panel, textvariable=self.sector_caption, style="Info.TLabel").pack(anchor="w")
        self.sector_bar = AnimatedProgressbar(panel, style="Accent.Horizontal.TProgressbar", maximum=100)
        self.sector_bar.pack(fill="x", pady=(4, 10))

        # Карта секторов SPI: 128 блоков по 4 КиБ
        ttk.Label(panel, text="КАРТА СЕКТОРОВ SPI · 4 КиБ", style="Faint.TLabel").pack(anchor="w", pady=(6, 0))
        ttk.Separator(panel, orient="horizontal").pack(fill="x", pady=(4, 8))
        self.sector_map = SectorMap(panel, columns=16, rows=8, cell=16, background=Palette.APP)
        self.sector_map.pack(anchor="w")
        ttk.Label(panel, text="серый — сектор не тронут, синий — требует стирания и записи",
                  style="Faint.TLabel", wraplength=270, justify="left").pack(anchor="w", pady=(8, 0))

    def crc_scheme_arg(self) -> str:
        """Выбранный процессор в виде ключа схемы: auto / ce208 / msp432."""
        return CRC_MODES.get(self.crc_mode.get(), "auto")

    def change_crc_mode(self, _event=None) -> None:
        """Оператор переключил режим контроля — применяем к открытому образу."""
        mode = self.crc_scheme_arg()
        model = self.state_model
        model.crc_forced = None if mode == "auto" else mode
        model.crc_scheme = model.crc_forced or getattr(model, "crc_detected", "ce208")
        set_crc_scheme(model.crc_scheme)
        self.refresh_all()
        self.status_var.set(
            f"Процессор: {self.crc_mode.get()}; контроль записей {crc_scheme_title(model.crc_scheme)}; "
            f"верных записей {self.crc_ok_count} из {self.crc_total_count}"
        )
        self.check_processor_match()

    def check_processor_match(self, ask: bool = False) -> bool:
        """Соответствует ли открытый образ выбранному процессору.

        При жёстком выборе (V8530 или MSP432) образ чужого прибора не читается:
        ни одна запись не проходит контроль. Тогда программа прямо об этом
        сообщает и предлагает переключиться на подходящий процессор.
        """
        model = self.state_model
        forced = getattr(model, "crc_forced", None)
        hits = getattr(model, "crc_scheme_hits", {})
        detected = getattr(model, "crc_detected", "ce208")
        if not self.at25_loaded or not forced or not hits:
            return True
        if hits.get(forced, 0) or not hits.get(detected, 0):
            return True

        mine, theirs = CRC_MODE_TITLES.get(forced, forced), CRC_MODE_TITLES.get(detected, detected)
        message = (
            f"Открытый дамп не соответствует выбранному процессору {mine}: по его схеме "
            f"({crc_scheme_title(forced)}) не сходится ни одна запись, а по схеме {theirs} "
            f"({crc_scheme_title(detected)}) сходится {hits.get(detected, 0)}. "
            f"Выберите процессор {theirs} или режим «Авто»."
        )
        self.warning_var.set(message)
        self.notice.configure(style="NoteErr.TLabel")
        self.status_var.set(f"Дамп не соответствует процессору {mine} — подходит {theirs}")
        self.status_led.set_state("err", "НЕ ТОТ")
        if ask and messagebox.askyesno(APP_TITLE, message + "\n\nПереключить на " + theirs + "?"):
            self.crc_mode.set(theirs)
            self.change_crc_mode()
            return True
        return False

    def _update_side_panel(self) -> None:
        """Пересчёт сводки: читает модель, ничего в ней не меняет."""
        if not hasattr(self, "side_vars"):
            return
        model = self.state_model
        name = self.at25_path.name if self.at25_path else "не загружен"
        self.side_vars["Файл"].set(name if len(name) <= 20 else "…" + name[-19:])
        self.side_vars["Память"].set("24LC64 внутр." if self.source_kind == "24lc64" else "25DF041B внешн.")
        self.side_vars["Объём"].set(f"0x{SMALL_SIZE:04X}" if self.source_kind == "24lc64" else f"0x{AT25_SIZE:05X}")
        # Схема контрольной суммы определяется по самому образу при загрузке
        self.side_vars["Контроль"].set(CRC_SCHEME_LABELS.get(
            getattr(self.state_model, "crc_scheme", "ce208"), "—"))
        try:
            small_changed, at25_changed = model.changed_counts()
        except Exception:
            small_changed = at25_changed = 0
        self.side_vars["Изменено"].set(f"{small_changed} / {at25_changed}")
        try:
            clock, _ = model.read_clock()
            self.side_vars["Часы"].set(
                f"{clock.year:04d}-{clock.month:02d}-{clock.day:02d} {clock.hour:02d}:{clock.minute:02d}")
        except Exception:
            self.side_vars["Часы"].set("нет записи")
        try:
            tariff, _ = model.read_active_tariff()
            self.side_vars["Тариф"].set(f"T{tariff}")
        except Exception:
            self.side_vars["Тариф"].set("—")
        try:
            self.side_vars["События"].set(str(model.event_global_counter()))
        except Exception:
            self.side_vars["События"].set("—")
        self.side_vars["Программатор"].set(
            self.direct_writer.profile_name if self.direct_writer.available() else "i2cpy нет")

        # Полоса контроля целостности
        total = max(1, self.crc_total_count)
        percent = 100.0 * self.crc_ok_count / total
        self.crc_caption.set(f"CRC записей: {self.crc_ok_count} из {self.crc_total_count} верны")
        self.crc_bar.configure(style="Ok.Horizontal.TProgressbar" if self.crc_ok_count == self.crc_total_count
                               else ("Warn.Horizontal.TProgressbar" if self.crc_ok_count else "Err.Horizontal.TProgressbar"))
        self.crc_bar["value"] = percent

        # Карта секторов: сравнение исходного и текущего образов по 4 КиБ
        original = memoryview(model.original_at25)
        current = memoryview(model.at25)
        flags = [original[start:start + 0x1000] != current[start:start + 0x1000]
                 for start in range(0, AT25_SIZE, 0x1000)]
        changed_sectors = sum(flags)
        self.sector_map.set_flags(flags)
        self.sector_caption.set(f"Секторы к прошивке: {changed_sectors} из {len(flags)}")
        self.sector_bar["value"] = 100.0 * changed_sectors / len(flags)

    def _build_statusbar(self) -> None:
        """Нижняя строка: индикатор состояния, сообщение, телеметрия."""
        bar = tk.Frame(self, background=Palette.STEEL_DEEP)
        bar.pack(fill="x", side="bottom")
        tk.Frame(bar, background=Palette.STEEL_LINE, height=1).pack(fill="x")

        row = tk.Frame(bar, background=Palette.STEEL_DEEP)
        row.pack(fill="x", padx=12, pady=6)

        self.status_led = StatusLED(row, "ГОТОВ", background=Palette.STEEL_DEEP, width=76)
        self.status_led.pack(side="left", padx=(0, 8))
        self.status_led.set_state("ok", "ГОТОВ")

        tk.Label(row, textvariable=self.telemetry_var, background=Palette.STEEL_DEEP,
                 foreground=Palette.ON_DARK_SOFT, font=(self.mono_font, 8)).pack(side="right", padx=(12, 0))

        self.busy_strip = Marquee(row, width=150, height=4, background=Palette.STEEL_DEEP,
                                  color=Palette.TEAL)
        self.busy_strip.pack(side="right", padx=(12, 8), pady=6)
        self.busy_strip.configure(width=150)

        tk.Label(row, textvariable=self.status_var, background=Palette.STEEL_DEEP,
                 foreground=Palette.ON_DARK, font=("TkDefaultFont", 9), anchor="w",
                 justify="left").pack(side="left", fill="x", expand=True)

    # ── живые индикаторы ───────────────────────────────────────────────────

    def _stage(self, bar, text: str, percent: float | None = None, style_name: str | None = None) -> None:
        """Подпись стадии у индикатора выполнения (безопасно для любого виджета)."""
        if hasattr(bar, "set_stage"):
            bar.set_stage(text, percent, style_name=style_name)
        elif percent is not None:
            bar["value"] = percent
        self.update_idletasks()

    def _tick_clock(self) -> None:
        """Часы ПК в шапке — ориентир при записи времени в прибор."""
        self.clock_var.set(datetime.now().strftime("%H:%M:%S"))
        self.after(1000, self._tick_clock)

    def _set_busy(self, active: bool, text: str | None = None) -> None:
        """Показать/убрать индикацию фоновой работы в статусной строке."""
        if text:
            self.status_var.set(text)
        if not hasattr(self, "busy_strip"):
            return
        if active:
            self.status_led.set_state("busy", "РАБОТА")
            self.busy_strip.start()
        else:
            self.status_led.set_state("ok", "ГОТОВ")
            self.busy_strip.stop()
        self.update_idletasks()

    def _update_notice(self) -> None:
        """Плашка-подсказка окрашивается по типу загруженного образа."""
        if not hasattr(self, "notice"):
            return
        self.warning_var.set(self._warning_text())
        self.notice.configure(style="NoteInfo.TLabel" if self.source_kind == "24lc64" else "NoteWarn.TLabel")

    def _update_telemetry(self) -> None:
        """Сводка состояния: изменённые байты, контрольные суммы, объём."""
        if not hasattr(self, "telemetry_var"):
            return
        try:
            small_changed, at25_changed = self.state_model.changed_counts()
        except Exception:
            small_changed = at25_changed = 0
        size = SMALL_SIZE if self.source_kind == "24lc64" else AT25_SIZE
        scheme = CRC_SCHEME_LABELS.get(getattr(self.state_model, "crc_scheme", "ce208"), "—")
        self.telemetry_var.set(
            f"изменено: small {small_changed} Б · SPI {at25_changed} Б   │   "
            f"CRC {self.crc_ok_count}/{self.crc_total_count} · {scheme}   │   "
            f"объём 0x{size:05X}   │   события {self.state_model.event_global_counter()}"
        )
        if hasattr(self, "led_source"):
            if self.at25_loaded:
                self.led_source.set_state("ok", "24LC64 8К" if self.source_kind == "24lc64" else "SPI 512К")
            else:
                self.led_source.set_state("off", "ОБРАЗ НЕТ")
        if hasattr(self, "led_crc"):
            if self.crc_ok_count == self.crc_total_count:
                self.led_crc.set_state("ok", f"CRC {self.crc_ok_count}/{self.crc_total_count}")
            elif self.crc_ok_count:
                self.led_crc.set_state("warn", f"CRC {self.crc_ok_count}/{self.crc_total_count}")
            else:
                self.led_crc.set_state("err", "CRC —")
        self._update_side_panel()

    def _build_clock_tab(self) -> None:
        ttk.Label(self.clock_tab, text="▎ Текущее время устройства", style='Title.TLabel').grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 12))
        ttk.Label(self.clock_tab, text="Штатная 10-байтная запись @0x0000, резерв @0x19E0", style='Info.TLabel').grid(row=1, column=0, columnspan=4, sticky="w", pady=(0, 14))

        self.clock_vars = {name: tk.StringVar() for name in ("year", "month", "day", "hour", "minute", "second", "weekday", "flags")}
        fields = [
            ("year", "Год"), ("month", "Месяц"), ("day", "День"),
            ("hour", "Часы"), ("minute", "Минуты"), ("second", "Секунды"),
            ("weekday", "День недели 0..6"), ("flags", "Служебный байт"),
        ]
        for index, (name, label) in enumerate(fields):
            row = 2 + index // 2
            column = (index % 2) * 2
            ttk.Label(self.clock_tab, text=label, font=('TkDefaultFont', 10)).grid(row=row, column=column, sticky="e", padx=8, pady=8)
            ttk.Entry(self.clock_tab, textvariable=self.clock_vars[name], width=16).grid(row=row, column=column + 1, sticky="w", padx=8, pady=8)

        # Визуальный разделитель
        ttk.Label(self.clock_tab, text="").grid(row=6, column=0, columnspan=4)

        actions = ttk.Frame(self.clock_tab)
        actions.grid(row=7, column=0, columnspan=4, sticky="w", pady=12)
        ttk.Button(actions, text="⟳ Прочитать", command=self.load_clock).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="◷ Время ПК", command=self.clock_now).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="⇩ Записать + CRC", command=self.apply_clock).pack(side="left")

        ttk.Label(self.clock_tab, text="").grid(row=8, column=0, columnspan=4)
        self.clock_info = tk.StringVar()
        ttk.Label(self.clock_tab, textvariable=self.clock_info, wraplength=940, style='Info.TLabel').grid(row=9, column=0, columnspan=4, sticky="w")

    def _build_counter_tab(self) -> None:
        ttk.Label(
            self.counter_tab,
            text="▎ Временные счётчики",
            style='Title.TLabel',
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 12))
        ttk.Label(
            self.counter_tab,
            text="Два штатных блока по 8 пар: timestamp + uint32 counter",
            style='Info.TLabel',
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(0, 14))

        self.counter_block = tk.StringVar(value="0")
        ttk.Label(self.counter_tab, text="Блок 0/1:", font=('TkDefaultFont', 10)).grid(row=2, column=0, sticky="e", padx=8, pady=8)
        ttk.Spinbox(self.counter_tab, from_=0, to=1, textvariable=self.counter_block, width=5).grid(row=2, column=1, sticky="w", padx=8, pady=8)

        ttk.Label(self.counter_tab, text="Канал", font=('TkDefaultFont', 10, 'bold')).grid(row=3, column=0, sticky="e", padx=8, pady=8)
        ttk.Label(self.counter_tab, text="Начальное время", font=('TkDefaultFont', 10, 'bold')).grid(row=3, column=1, sticky="w", padx=8)
        ttk.Label(self.counter_tab, text="Счётчик raw uint32", font=('TkDefaultFont', 10, 'bold')).grid(row=3, column=2, sticky="w", padx=8)

        self.counter_times = []
        self.counter_values = []
        now = datetime.now().replace(microsecond=0).isoformat(sep=" ")
        for index in range(8):
            time_var = tk.StringVar(value=now)
            counter_var = tk.StringVar(value="0")
            self.counter_times.append(time_var)
            self.counter_values.append(counter_var)
            ttk.Label(self.counter_tab, text=str(index), font=('TkDefaultFont', 10)).grid(row=4 + index, column=0, sticky="e", padx=8, pady=5)
            ttk.Entry(self.counter_tab, textvariable=time_var, width=24).grid(row=4 + index, column=1, sticky="w", padx=8, pady=5)
            ttk.Entry(self.counter_tab, textvariable=counter_var, width=18).grid(row=4 + index, column=2, sticky="w", padx=8, pady=5)

        ttk.Label(self.counter_tab, text="").grid(row=12, column=0, columnspan=4)
        actions = ttk.Frame(self.counter_tab)
        actions.grid(row=13, column=0, columnspan=4, sticky="w", pady=12)
        ttk.Button(actions, text="⟳ Прочитать блок", command=self.load_time_counters).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="◷ Инициализировать", command=self.initialize_time_counters).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="⇩ Записать + CRC", command=self.apply_time_counters).pack(side="left")

        ttk.Label(self.counter_tab, text="").grid(row=14, column=0, columnspan=4)
        self.counter_info = tk.StringVar(
            value="Формат восстановлен точно из 0x2E88C/0x2E8DA; назначение отдельных каналов зависит от конфигурации прибора."
        )
        ttk.Label(self.counter_tab, textvariable=self.counter_info, wraplength=940, style='Info.TLabel').grid(row=15, column=0, columnspan=4, sticky="w", pady=8)

    def _energy_controls(self, parent: ttk.Frame, archive: bool) -> tuple[list[tk.StringVar], tk.StringVar, tk.StringVar, tk.StringVar, tk.StringVar]:
        selector = ttk.Frame(parent)
        selector.pack(fill="x", pady=(0, 14))
        bank_var = tk.StringVar(value="0")
        divisor_var = tk.StringVar(value="1")
        decimals_var = tk.StringVar(value="5")
        tariff_count_var = tk.StringVar(value="2")
        ttk.Label(selector, text="Количество тарифов:", font=('TkDefaultFont', 9)).pack(side="left", padx=(0, 6))
        ttk.Spinbox(selector, from_=1, to=8, textvariable=tariff_count_var, width=5).pack(side="left", padx=(0, 20))
        ttk.Label(selector, text="Банк 0..3:", font=('TkDefaultFont', 9)).pack(side="left", padx=(0, 6))
        ttk.Spinbox(selector, from_=0, to=3, textvariable=bank_var, width=5).pack(side="left", padx=(0, 20))
        ttk.Label(selector, text="Делитель K:", font=('TkDefaultFont', 9)).pack(side="left", padx=(0, 6))
        ttk.Entry(selector, textvariable=divisor_var, width=10).pack(side="left", padx=(0, 20))
        ttk.Label(selector, text="Десятичных знаков:", font=('TkDefaultFont', 9)).pack(side="left", padx=(0, 6))
        ttk.Spinbox(selector, from_=0, to=12, textvariable=decimals_var, width=5).pack(side="left")

        ttk.Label(parent, text="Тарифы", style='Section.TLabel').pack(anchor="w", pady=(4, 4))

        grid = ttk.Frame(parent)
        grid.pack(fill="x", pady=(0, 12))
        values = [tk.StringVar(value="0.00000") for _ in range(8)]
        entries = []
        for index, var in enumerate(values):
            row, column = divmod(index, 4)
            base = column * 2
            ttk.Label(grid, text=f"T{index + 1}", font=('TkDefaultFont', 10, 'bold')).grid(row=row, column=base, sticky="e", padx=8, pady=4)
            entry = ttk.Entry(grid, textvariable=var, width=18)
            entry.grid(row=row, column=base + 1, sticky="w", padx=8, pady=4)
            entries.append(entry)

        # Все поля T1..T8 всегда доступны для ввода. «Количество тарифов» — только
        # подсказка для превью суммы; запись берёт все 8 введённых значений.
        for entry in entries:
            entry.configure(state="normal")
        return values, bank_var, divisor_var, decimals_var, tariff_count_var

    def _build_energy_tab(self) -> None:
        ttk.Label(self.energy_tab, text="▎ Текущая энергия", style='Title.TLabel').pack(anchor="w", pady=(0, 12))
        ttk.Label(self.energy_tab, text="Текущие 4 × 0x44 записи в нижней области SPI", style='Info.TLabel').pack(anchor="w", pady=(0, 14))

        tariff = ttk.Frame(self.energy_tab)
        tariff.pack(fill="x", pady=(0, 12))
        self.active_tariff = tk.StringVar(value="1")
        ttk.Label(tariff, text="Активный тариф 1..8:", font=('TkDefaultFont', 10)).pack(side="left", padx=(0, 8))
        ttk.Spinbox(tariff, from_=1, to=8, textvariable=self.active_tariff, width=5).pack(side="left", padx=(0, 16))
        ttk.Button(tariff, text="⟳ Прочитать", command=self.load_active_tariff).pack(side="left", padx=(0, 8))
        ttk.Button(tariff, text="⇩ Записать + CRC", command=self.apply_active_tariff).pack(side="left")
        self.energy_values, self.energy_bank, self.energy_divisor, self.energy_decimals, self.energy_tariff_count = self._energy_controls(self.energy_tab, False)

        sync_options = ttk.Frame(self.energy_tab)
        sync_options.pack(fill="x", pady=(0, 12))
        self.energy_sync_all_banks = tk.BooleanVar(value=False)
        self.energy_sync_marker = tk.StringVar(value="0")
        ttk.Checkbutton(
            sync_options,
            text="Синхронизировать все 4 энергетических банка",
            variable=self.energy_sync_all_banks,
        ).pack(side="left", padx=(0, 20))
        ttk.Label(sync_options, text="Маркер:", font=('TkDefaultFont', 9)).pack(side="left", padx=(0, 6))
        ttk.Entry(sync_options, textvariable=self.energy_sync_marker, width=7).pack(side="left")

        # Авто-реактивная: слот2 = слот0 × K_r
        react = ttk.Frame(self.energy_tab)
        react.pack(fill="x", pady=(0, 8))
        self.reactive_auto = tk.BooleanVar(value=True)
        self.reactive_k = tk.StringVar(value="0.0090121")  # 439/48712 из дампа
        ttk.Checkbutton(
            react,
            text="Авто-реактивная (слот 2) = активная (слот 0) × K",
            variable=self.reactive_auto,
        ).pack(side="left", padx=(0, 12))
        ttk.Label(react, text="K реактивной:", font=('TkDefaultFont', 9)).pack(side="left", padx=(0, 6))
        ttk.Entry(react, textvariable=self.reactive_k, width=12).pack(side="left", padx=(0, 8))
        ttk.Button(react, text="K из дампа", command=self.reactive_k_from_dump).pack(side="left")

        self.energy_sum = tk.StringVar(value="∑ Сумма: —")
        ttk.Label(self.energy_tab, textvariable=self.energy_sum, style="Sum.TLabel").pack(anchor="w", pady=(8, 6))

        for variable in [*self.energy_values, self.energy_tariff_count, self.energy_divisor, self.energy_decimals]:
            variable.trace_add("write", self.preview_current_sum)
        self.preview_current_sum()

        # Опции единой операции
        opt = ttk.Frame(self.energy_tab)
        opt.pack(fill="x", pady=(6, 4))
        self.opt_save_bin = tk.BooleanVar(value=True)
        self.opt_direct = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt, text="Сохранить .bin (имя из тарифов+сумма)", variable=self.opt_save_bin).pack(side="left", padx=(0, 16))
        ttk.Checkbutton(opt, text="Прямая запись в чип (CH341)", variable=self.opt_direct).pack(side="left")

        # ОДНА главная кнопка
        big = ttk.Frame(self.energy_tab)
        big.pack(anchor="w", pady=(6, 4))
        ttk.Button(big, text="СОГЛАСОВАТЬ И ЗАПИСАТЬ", style="Hero.TButton",
                   command=self.apply_and_write).pack(side="left", padx=(0, 10))
        ttk.Button(big, text="Прочитать банк", style="Ghost.TButton",
                   command=self.load_current_energy).pack(side="left")

        self.energy_progress = ProgressPanel(self.energy_tab, caption="Операция не запускалась")
        self.energy_progress.pack(fill="x", pady=(8, 6))

        self.energy_info = tk.StringVar(value="Одна кнопка: часы=текущее, активная+реактивная(×K)+тариф+счётчики (+архивы/событие для SPI), CRC, сохранение .bin и прямая запись.")
        ttk.Label(self.energy_tab, textvariable=self.energy_info, wraplength=1040, style='Info.TLabel').pack(anchor="w", pady=(4, 6))

    def _build_archive_tab(self) -> None:
        ttk.Label(self.archive_tab, text="▎ Архивы энергии", style='Title.TLabel').pack(anchor="w", pady=(0, 12))
        ttk.Label(self.archive_tab, text="Кольцевые энергетические архивы в AT25", style='Info.TLabel').pack(anchor="w", pady=(0, 14))

        selector = ttk.Frame(self.archive_tab)
        selector.pack(fill="x", pady=(0, 14))
        self.archive_type = tk.StringVar(value="0")
        self.archive_slot = tk.StringVar(value="0")
        self.archive_marker = tk.StringVar(value="0")
        ttk.Label(selector, text="Тип 0/1/2/5:", font=('TkDefaultFont', 10)).pack(side="left", padx=(0, 6))
        ttk.Combobox(selector, values=["0", "1", "2", "5"], textvariable=self.archive_type, width=5, state="readonly").pack(side="left", padx=(0, 20))
        ttk.Label(selector, text="Номер/индекс:", font=('TkDefaultFont', 10)).pack(side="left", padx=(0, 6))
        ttk.Entry(selector, textvariable=self.archive_slot, width=9).pack(side="left", padx=(0, 20))
        ttk.Label(selector, text="Маркер:", font=('TkDefaultFont', 10)).pack(side="left", padx=(0, 6))
        ttk.Entry(selector, textvariable=self.archive_marker, width=8).pack(side="left")

        self.archive_values, self.archive_bank, self.archive_divisor, self.archive_decimals, self.archive_tariff_count = self._energy_controls(self.archive_tab, True)

        ttk.Label(self.archive_tab, text="").pack()
        self.archive_sum = tk.StringVar(value="∑ Сумма: —")
        ttk.Label(self.archive_tab, textvariable=self.archive_sum, style="Sum.TLabel").pack(anchor="w", pady=10)

        for variable in [*self.archive_values, self.archive_tariff_count, self.archive_divisor, self.archive_decimals]:
            variable.trace_add("write", self.preview_archive_sum)
        self.preview_archive_sum()

        ttk.Label(self.archive_tab, text="").pack()
        actions = ttk.Frame(self.archive_tab)
        actions.pack(anchor="w", pady=12)
        ttk.Button(actions, text="⟳ Прочитать архив", command=self.load_archive).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="✕ Создать нулевую", command=self.zero_archive).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="⇩ Записать запись", command=self.apply_archive).pack(side="left")

        ttk.Label(self.archive_tab, text="").pack()
        self.archive_info = tk.StringVar()
        ttk.Label(self.archive_tab, textvariable=self.archive_info, wraplength=1040, style='Info.TLabel').pack(anchor="w", pady=8)

    def _build_event_tab(self) -> None:
        ttk.Label(
            self.event_tab,
            text="▎ Журналы событий",
            style='Title.TLabel',
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 12))
        ttk.Label(
            self.event_tab,
            text="70 кольцевых журналов событий + счётчики в нижней области того же SPI",
            style='Info.TLabel',
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(0, 14))

        self.event_id = tk.StringVar(value="0")
        self.event_history = tk.StringVar(value="0")
        self.event_time = tk.StringVar(value=datetime.now().replace(microsecond=0).isoformat(sep=" "))
        self.event_status = tk.StringVar(value="0")
        self.event_value = tk.StringVar(value="0")
        event_choices = [
            f"{event_id}: group={log.group} sub={log.sub} code={log.display_code}"
            for event_id, log in EVENT_LOGS.items()
        ]
        ttk.Label(self.event_tab, text="ID события 0..69", font=('TkDefaultFont', 10)).grid(row=2, column=0, sticky="e", padx=8, pady=8)
        event_combo = ttk.Combobox(self.event_tab, values=event_choices, width=38, state="readonly")
        event_combo.grid(row=2, column=1, sticky="w", padx=8, pady=8)
        event_combo.current(0)

        def select_event(_event=None) -> None:
            self.event_id.set(event_combo.get().split(":", 1)[0])
            self.refresh_event_info()

        event_combo.bind("<<ComboboxSelected>>", select_event)
        ttk.Label(self.event_tab, text="Смещение от нового", font=('TkDefaultFont', 10)).grid(row=2, column=2, sticky="e", padx=8, pady=8)
        ttk.Entry(self.event_tab, textvariable=self.event_history, width=10).grid(row=2, column=3, sticky="w", padx=8, pady=8)

        ttk.Label(self.event_tab, text="Дата/время", font=('TkDefaultFont', 10)).grid(row=3, column=0, sticky="e", padx=8, pady=8)
        ttk.Entry(self.event_tab, textvariable=self.event_time, width=24).grid(row=3, column=1, sticky="w", padx=8, pady=8)
        ttk.Label(self.event_tab, text="Статус 0..255", font=('TkDefaultFont', 10)).grid(row=3, column=2, sticky="e", padx=8, pady=8)
        ttk.Entry(self.event_tab, textvariable=self.event_status, width=10).grid(row=3, column=3, sticky="w", padx=8, pady=8)

        ttk.Label(self.event_tab, text="Доп. значение", font=('TkDefaultFont', 10)).grid(row=4, column=0, sticky="e", padx=8, pady=8)
        ttk.Entry(self.event_tab, textvariable=self.event_value, width=24).grid(row=4, column=1, sticky="w", padx=8, pady=8)

        ttk.Label(self.event_tab, text="").grid(row=5, column=0, columnspan=4)

        actions = ttk.Frame(self.event_tab)
        actions.grid(row=6, column=0, columnspan=4, sticky="w", pady=12)
        ttk.Button(actions, text="◷ Текущее время", command=self.event_now).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="⟳ Прочитать", command=self.load_event).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="✎ Добавить событие", command=self.append_event).pack(side="left")

        ttk.Label(self.event_tab, text="").grid(row=7, column=0, columnspan=4)
        self.event_info = tk.StringVar()
        ttk.Label(self.event_tab, textvariable=self.event_info, wraplength=1040, justify="left", style='Info.TLabel').grid(
            row=8, column=0, columnspan=4, sticky="w", pady=8
        )
        ttk.Label(
            self.event_tab,
            text=(
                "Добавление повторяет функции прошивки: увеличивает общий 24-битный номер, счётчик ID в primary+backup, "
                "выбирает слот по modulo, пишет время, статус, значение и CRC в AT25."
            ),
            wraplength=1040,
            style="NoteInfo.TLabel",
            justify="left",
        ).grid(row=9, column=0, columnspan=4, sticky="ew", pady=8)

    def _build_raw_tab(self) -> None:
        header = ttk.Label(self.raw_tab, text="▎ Raw данные — статические записи", style='Title.TLabel')
        header.pack(anchor="w", padx=14, pady=(14, 12))

        left = ttk.Frame(self.raw_tab)
        left.pack(side="left", fill="both", expand=True, padx=(14, 7), pady=(0, 14))
        columns = ("name", "path", "primary", "backup", "length", "status")
        headings = {
            "name": "Запись", "path": "Путь", "primary": "Основная",
            "backup": "Резервная", "length": "Длина", "status": "Контроль",
        }
        self.record_tree = ttk.Treeview(left, columns=columns, show="headings", height=20)
        widths = (178, 56, 88, 124, 62, 104)
        for column, width in zip(columns, widths):
            self.record_tree.heading(column, text=headings[column])
            self.record_tree.column(column, width=width, anchor="w")
        # Чередование строк и подсветка контрольной суммы
        self.record_tree.tag_configure("even", background=Palette.SURFACE)
        self.record_tree.tag_configure("odd", background=Palette.GRID)
        self.record_tree.tag_configure("ok", foreground=Palette.INK)
        self.record_tree.tag_configure("bad", foreground=Palette.ERR)
        self.record_tree.pack(side="left", fill="both", expand=True)
        tree_scroll = ttk.Scrollbar(left, orient="vertical", command=self.record_tree.yview)
        tree_scroll.pack(side="right", fill="y")
        self.record_tree.configure(yscrollcommand=tree_scroll.set)
        self.record_tree.bind("<<TreeviewSelect>>", self.select_raw_record)

        right = ttk.Frame(self.raw_tab, padding=(12, 0, 0, 0))
        right.pack(side="right", fill="both", expand=True, padx=(0, 14), pady=(0, 14))
        self.raw_info = tk.StringVar(value="Выберите запись из таблицы…")
        ttk.Label(right, textvariable=self.raw_info, wraplength=450, style='Info.TLabel').pack(anchor="w", pady=(0, 12))
        ttk.Label(right, text="Hex данные (без CRC):", font=('TkDefaultFont', 10, 'bold')).pack(anchor="w", pady=(0, 6))
        self.raw_text = tk.Text(
            right, height=20, width=52, font=(self.mono_font, 10), wrap="word",
            background=Palette.SURFACE, foreground=Palette.INK,
            insertbackground=Palette.ACCENT_DEEP, selectbackground=Palette.ACCENT_SOFT,
            relief="flat", highlightthickness=1, highlightbackground=Palette.BORDER,
            highlightcolor=Palette.ACCENT, padx=10, pady=8,
        )
        self.raw_text.pack(fill="both", expand=True, pady=(0, 12))
        ttk.Button(right, text="⇩ Записать + CRC", command=self.apply_raw_record).pack(anchor="w")

    def _build_direct_tab(self) -> None:
        """Полноценный редактор энергии (те же поля, что на вкладке «Энергия»,
        привязаны к общим переменным) + выбор чипа и прямая запись CH341."""
        ttk.Label(self.direct_tab, text="▎ Прямая запись в прибор (CH341)", style='Title.TLabel').pack(anchor="w", pady=(0, 4))
        avail = self.direct_writer.available()
        if avail:
            avail_txt = "Программатор готов: библиотека i2cpy найдена, прямая запись доступна"
        elif I2C_IMPORT_ERROR:
            avail_txt = f"Внимание: i2cpy найдена, но не импортируется: {I2C_IMPORT_ERROR}. Проверьте драйвер CH341/тот же Python."
        else:
            avail_txt = "Внимание: i2cpy не установлена (pip install i2cpy) — доступно только сохранение .bin"
        ttk.Label(self.direct_tab, text=avail_txt,
                  foreground=(self.success_color if avail else "#D84315"),
                  font=('TkDefaultFont', 10, 'bold'), wraplength=1040).pack(anchor="w", pady=(0, 6))
        ttk.Label(self.direct_tab, text=f"Python: {sys.executable}", style='Info.TLabel', wraplength=1040).pack(anchor="w", pady=(0, 10))

        # Выбор чипа
        row = ttk.Frame(self.direct_tab)
        row.pack(fill="x", pady=(0, 8))
        ttk.Label(row, text="Микросхема:", font=('TkDefaultFont', 10)).pack(side="left", padx=(0, 6))
        self.direct_chip = tk.StringVar(value="24LC64 (8 КБ)")
        ttk.Combobox(row, values=list(CHIP_PROFILES.keys()), textvariable=self.direct_chip,
                     width=18, state="readonly").pack(side="left", padx=(0, 16))
        ttk.Label(row, text="I²C 0x50 · CH341", style='Info.TLabel').pack(side="left")

        # ── Те же элементы, что на вкладке «Энергия», привязаны к ОБЩИМ переменным ──
        tariff = ttk.Frame(self.direct_tab)
        tariff.pack(fill="x", pady=(6, 0))
        ttk.Label(tariff, text="Активный тариф 1..8:", font=('TkDefaultFont', 10)).pack(side="left", padx=(0, 8))
        ttk.Spinbox(tariff, from_=1, to=8, textvariable=self.active_tariff, width=5).pack(side="left", padx=(0, 16))
        ttk.Label(tariff, text="Банк:", font=('TkDefaultFont', 10)).pack(side="left", padx=(0, 6))
        ttk.Spinbox(tariff, from_=0, to=3, textvariable=self.energy_bank, width=5).pack(side="left", padx=(0, 16))
        ttk.Label(tariff, text="K реактивной:", font=('TkDefaultFont', 9)).pack(side="left", padx=(0, 6))
        ttk.Entry(tariff, textvariable=self.reactive_k, width=12).pack(side="left")

        scale = ttk.Frame(self.direct_tab)
        scale.pack(fill="x", pady=(6, 6))
        ttk.Label(scale, text="Делитель K:", font=('TkDefaultFont', 9)).pack(side="left", padx=(0, 6))
        ttk.Entry(scale, textvariable=self.energy_divisor, width=8).pack(side="left", padx=(0, 16))
        ttk.Label(scale, text="Десятичных знаков:", font=('TkDefaultFont', 9)).pack(side="left", padx=(0, 6))
        ttk.Spinbox(scale, from_=0, to=12, textvariable=self.energy_decimals, width=5).pack(side="left")

        ttk.Label(self.direct_tab, text="Тарифы", style='Section.TLabel').pack(anchor="w", pady=(4, 4))
        grid = ttk.Frame(self.direct_tab)
        grid.pack(fill="x", pady=(0, 8))
        for index, var in enumerate(self.energy_values):  # общие переменные!
            r, c = divmod(index, 4)
            base = c * 2
            ttk.Label(grid, text=f"T{index + 1}", font=('TkDefaultFont', 10, 'bold')).grid(row=r, column=base, sticky="e", padx=8, pady=4)
            ttk.Entry(grid, textvariable=var, width=18).grid(row=r, column=base + 1, sticky="w", padx=8, pady=4)

        ttk.Checkbutton(self.direct_tab, text="Авто-реактивная (слот 2) = активная (слот 0) × K",
                        variable=self.reactive_auto).pack(anchor="w", pady=(0, 4))
        ttk.Label(self.direct_tab, textvariable=self.energy_sum, style="Sum.TLabel").pack(anchor="w", pady=(4, 6))
        ttk.Checkbutton(self.direct_tab, text="Также сохранить .bin (имя из тарифов+сумма)",
                        variable=self.opt_save_bin).pack(anchor="w", pady=(0, 8))

        # ГЛАВНАЯ кнопка — всё то же + прямая запись
        big = ttk.Frame(self.direct_tab)
        big.pack(anchor="w", pady=(4, 6))
        ttk.Button(big, text="СОГЛАСОВАТЬ И ЗАПИСАТЬ В ЧИП", style="Hero.TButton",
                   command=lambda: self.apply_and_write(force_direct=True, progressbar=self.direct_progress)).pack(side="left", padx=(0, 10))
        ttk.Button(big, text="Прочитать чип → в редактор", style="Ghost.TButton",
                   command=self.direct_read).pack(side="left", padx=(0, 8))
        ttk.Button(big, text="Проверить чип", style="Ghost.TButton",
                   command=self.direct_verify).pack(side="left")

        self.direct_progress = ProgressPanel(self.direct_tab, caption="Программатор не задействован")
        self.direct_progress.pack(fill="x", pady=(10, 6))
        self.direct_status = tk.StringVar(value="Готово к работе")
        ttk.Label(self.direct_tab, textvariable=self.direct_status, wraplength=1040, font=('TkDefaultFont', 10)).pack(anchor="w", pady=(0, 6))

        ttk.Label(self.direct_tab,
                  text="Внимание: прямая запись адаптирована из MT_Writer, но не проверена на этом железе. "
                       "Сначала убедитесь на стенде; держите заводской дамп для отката.",
                  style="NoteErr.TLabel", wraplength=1040).pack(fill="x", pady=(10, 0))

    def _set_direct(self, text: str, ok=None, pct: int | None = None) -> None:
        self.direct_status.set(text)
        # Стиль полосы отражает исход: зелёный — успех, красный — сбой.
        style_name = "Accent.Horizontal.TProgressbar"
        if ok is True:
            style_name = "Ok.Horizontal.TProgressbar"
        elif ok is False:
            style_name = "Err.Horizontal.TProgressbar"
        self.direct_progress.set_stage(text, pct, style_name=style_name)
        if ok is not None:
            self._set_busy(False)
            self.status_led.set_state("ok" if ok else "err", "ГОТОВ" if ok else "ОШИБКА")
        else:
            self._set_busy(True)
        self.update_idletasks()

    def _direct_progress(self, pct: int) -> None:
        self.direct_progress["value"] = max(0, min(100, pct))
        self.update_idletasks()

    def direct_read(self) -> None:
        try:
            self.direct_writer.set_profile(self.direct_chip.get())
            if not self.direct_writer.available():
                raise RuntimeError("i2cpy не установлена")
            self._set_direct("Открываю CH341…", pct=5)
            self.direct_writer.open()
            size = self.direct_writer.size
            self._set_direct(f"Чтение {size} байт…", pct=20)
            data = self.direct_writer.read_bytes(0, size)
            self.direct_writer.close()
            if size == SMALL_SIZE:
                self.state_model = CE208State(small=data, crc=self.crc_scheme_arg())
                self.source_kind = "24lc64"
            else:
                # 24C16 и т.п. — грузим в small с добивкой
                self.state_model = CE208State(small=data.ljust(SMALL_SIZE, b"\xFF")[:SMALL_SIZE],
                                              crc=self.crc_scheme_arg())
                self.source_kind = "24lc64"
            self.at25_loaded = True
            self.at25_var.set(f"CH341: {self.direct_chip.get()} прочитан")
            self._set_direct(f"Прочитано {size} байт с чипа — загружено в редактор.", ok=True, pct=100)
            self.refresh_all()
        except Exception as exc:
            try:
                self.direct_writer.close()
            except Exception:
                pass
            self._set_direct(f"Ошибка чтения: {exc}", ok=False, pct=0)
            messagebox.showerror(APP_TITLE, str(exc))

    def direct_write(self) -> None:
        try:
            self.direct_writer.set_profile(self.direct_chip.get())
            if not self.direct_writer.available():
                raise RuntimeError("i2cpy не установлена")
            image = bytes(self.state_model.small)[: self.direct_writer.size]
            if not messagebox.askyesno(APP_TITLE, f"Записать {len(image)} байт в {self.direct_chip.get()} через CH341?"):
                return
            self._set_direct("Открываю CH341…", pct=3)
            self.direct_writer.open()
            self._set_direct("Запись образа…", pct=5)
            self.direct_writer.write_image(image, progress=self._direct_progress)
            self._set_direct("Проверка записи…", pct=0)
            ok, bad = self.direct_writer.verify_image(image, progress=self._direct_progress)
            self.direct_writer.close()
            if ok:
                self._set_direct("Записано и проверено: чип совпадает с образом.", ok=True, pct=100)
            else:
                self._set_direct(f"Несовпадение по адресу 0x{bad:04X}.", ok=False)
        except Exception as exc:
            try:
                self.direct_writer.close()
            except Exception:
                pass
            self._set_direct(f"Ошибка записи: {exc}", ok=False, pct=0)
            messagebox.showerror(APP_TITLE, str(exc))

    def direct_verify(self) -> None:
        try:
            self.direct_writer.set_profile(self.direct_chip.get())
            if not self.direct_writer.available():
                raise RuntimeError("i2cpy не установлена")
            image = bytes(self.state_model.small)[: self.direct_writer.size]
            self._set_direct("Открываю CH341…", pct=5)
            self.direct_writer.open()
            ok, bad = self.direct_writer.verify_image(image, progress=self._direct_progress)
            self.direct_writer.close()
            if ok:
                self._set_direct("Чип совпадает с текущим образом.", ok=True, pct=100)
            else:
                self._set_direct(f"Отличие по адресу 0x{bad:04X}.", ok=False)
        except Exception as exc:
            try:
                self.direct_writer.close()
            except Exception:
                pass
            self._set_direct(f"Ошибка: {exc}", ok=False, pct=0)

    def _build_audit_tab(self) -> None:
        header = ttk.Label(self.audit_tab, text="▎ Проверка и изменения", style='Title.TLabel')
        header.pack(anchor="w", pady=(0, 12))

        actions = ttk.Frame(self.audit_tab)
        actions.pack(fill="x", pady=(0, 12))
        ttk.Button(actions, text="⟳ Обновить проверку", command=self.refresh_audit).pack(side="left")

        ttk.Label(self.audit_tab, text="JSON-отчёт всех произведённых изменений:", style='Info.TLabel').pack(anchor="w", pady=(0, 8))
        self.audit_text = tk.Text(
            self.audit_tab, font=(self.mono_font, 9), wrap="none",
            background=Palette.SURFACE, foreground=Palette.INK,
            insertbackground=Palette.ACCENT_DEEP, selectbackground=Palette.ACCENT_SOFT,
            relief="flat", highlightthickness=1, highlightbackground=Palette.BORDER,
            highlightcolor=Palette.ACCENT, padx=12, pady=10,
        )
        self.audit_text.pack(fill="both", expand=True)

    def open_at25(self) -> None:
        path = filedialog.askopenfilename(
            title="Дамп памяти: 24LC64 (8 КиБ) или 25DF041B (512 КиБ)",
            filetypes=[("BIN", "*.bin"), ("Все файлы", "*.*")],
        )
        if not path:
            return
        self._set_busy(True, f"Чтение файла {Path(path).name}…")
        raw = Path(path).read_bytes()
        if len(raw) == SMALL_SIZE:
            # Внутренняя EEPROM 24LC64 — это и есть small-path (часы, тарифы, текущая энергия)
            self.state_model = CE208State(small=raw, crc=self.crc_scheme_arg())
            self.source_kind = "24lc64"
            self.at25_var.set(f"24LC64: {Path(path).name}  (8 КиБ, показания)")
            self.status_var.set("Внутренняя EEPROM 24LC64 загружена — показания в small-path")
        elif len(raw) == AT25_SIZE:
            self.state_model = CE208State(at25=raw, crc=self.crc_scheme_arg())
            self.source_kind = "spi"
            self.at25_var.set(f"SPI 25DF041B: {Path(path).name}  (512 КиБ, архивы)")
            self.status_var.set("Внешняя SPI 25DF041B загружена")
        else:
            messagebox.showerror(
                APP_TITLE,
                f"Нужен дамп 24LC64 ({SMALL_SIZE} б) или 25DF041B ({AT25_SIZE} б); получено {len(raw)} б",
            )
            self._set_busy(False, "Файл не распознан — образ не загружен")
            self.status_led.set_state("err", "ОШИБКА")
            return
        self.at25_path = Path(path)
        self.at25_loaded = True
        self.refresh_all()
        self._set_busy(False)
        self.activity.pulse(1.0)
        # Схема CRC подбирается по образу; она же используется при записи.
        scheme = getattr(self.state_model, "crc_scheme", "ce208")
        hits = getattr(self.state_model, "crc_scheme_hits", {})
        self.status_var.set(
            f"{self.status_var.get()}; процессор {self.crc_mode.get()}, контроль записей: "
            f"{crc_scheme_title(scheme)}"
            + (f" (сошлось {hits.get(scheme, 0)} записей)" if hits.get(scheme) else "")
        )
        # Жёстко выбранный процессор и чужой дамп — сообщаем и предлагаем переключиться
        self.check_processor_match(ask=True)

    def save_spi(self) -> None:
        if not self.at25_loaded:
            if not messagebox.askyesno(APP_TITLE, "Исходный образ не был загружен. Сохранить новый созданный образ?"):
                return
        if self.source_kind == "24lc64":
            out_path = filedialog.asksaveasfilename(
                title="Сохранить 24LC64 (8 КиБ)", defaultextension=".bin", initialfile="CE208_24LC64_edited.bin"
            )
            if not out_path:
                return
            # Пишем только 8-КБ область (внутренняя EEPROM)
            self._set_busy(True, "Запись файла образа 24LC64…")
            Path(out_path).write_bytes(bytes(self.state_model.small))
            audit_path = Path(out_path).with_suffix(".audit.json")
            self.state_model.save_audit(audit_path)
            self._set_busy(False, f"24LC64 (8 КиБ) сохранён; отчёт: {audit_path.name}")
            self.activity.pulse(1.0)
            return
        at25_path = filedialog.asksaveasfilename(title="Сохранить SPI 25DF041B", defaultextension=".bin", initialfile="CE208_25DF041B_edited.bin")
        if not at25_path:
            return
        self._set_busy(True, "Запись образа SPI и построение плана прошивки…")
        Path(at25_path).write_bytes(self.state_model.at25)
        audit_path = Path(at25_path).with_suffix(".audit.json")
        plan_path = Path(at25_path).with_suffix(".at25_plan.json")
        self.state_model.save_audit(audit_path)
        plan_path.write_text(json.dumps(at25_program_sectors(self.state_model.original_at25, self.state_model.at25), ensure_ascii=False, indent=2), encoding="utf-8")
        self._set_busy(False, f"SPI сохранён; отчёт: {audit_path.name}; план прошивки: {plan_path.name}")
        self.activity.pulse(1.0)

    def save_audit(self) -> None:
        path = filedialog.asksaveasfilename(title="Экспорт отчёта", defaultextension=".json", initialfile="CE208_NVM_audit.json")
        if path:
            self.state_model.save_audit(path)
            self.status_var.set(f"Отчёт сохранён: {path}")

    def refresh_all(self) -> None:
        self._update_notice()
        self.refresh_record_tree()
        self.refresh_audit()
        self.refresh_event_info()
        if self.at25_loaded:
            try:
                self.load_clock()
            except Exception:
                pass
            try:
                self.load_active_tariff()
            except Exception:
                pass
            try:
                self.load_current_energy()
            except Exception:
                pass
        self._update_telemetry()

    def clock_now(self) -> None:
        value = ClockValue.from_datetime(datetime.now())
        for name in self.clock_vars:
            self.clock_vars[name].set(str(getattr(value, name)))

    def load_clock(self) -> None:
        value, result = self.state_model.read_clock()
        for name in self.clock_vars:
            self.clock_vars[name].set(str(getattr(value, name)))
        self.clock_info.set(f"Выбрана копия {result.source} @0x{result.address:04X}; CRC={result.stored_crc:04X}, верна")

    def apply_clock(self) -> None:
        try:
            args = {name: int(var.get(), 0) for name, var in self.clock_vars.items()}
            self.state_model.write_clock(ClockValue(**args))
            self.clock_info.set("Обе копии времени обновлены; CRC пересчитана")
            self.after_change("Время записано по штатной схеме")
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def load_active_tariff(self) -> None:
        tariff, result = self.state_model.read_active_tariff()
        self.active_tariff.set(str(tariff))
        self.status_var.set(f"Активный тариф T{tariff}; источник small @0x{result.address:04X}")

    def apply_active_tariff(self) -> None:
        try:
            tariff = int(self.active_tariff.get(), 0)
            self.state_model.write_active_tariff(tariff)
            self.after_change(f"Активный тариф T{tariff} записан в primary и backup")
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def load_time_counters(self) -> None:
        try:
            block = int(self.counter_block.get(), 0)
            value, result = self.state_model.read_time_counters(block)
            for index, (timestamp, counter) in enumerate(value.pairs):
                self.counter_times[index].set(timestamp.isoformat(sep=" "))
                self.counter_values[index].set(str(counter))
            self.counter_info.set(f"small @0x{result.address:04X}; CRC={result.stored_crc:04X}, верна")
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def initialize_time_counters(self) -> None:
        value = TimeCounterBlock.initialized(datetime.now())
        for index, (timestamp, counter) in enumerate(value.pairs):
            self.counter_times[index].set(timestamp.isoformat(sep=" "))
            self.counter_values[index].set(str(counter))

    def apply_time_counters(self) -> None:
        try:
            block = int(self.counter_block.get(), 0)
            pairs = [
                (datetime.fromisoformat(time_var.get().strip()), int(counter_var.get(), 0))
                for time_var, counter_var in zip(self.counter_times, self.counter_values)
            ]
            self.state_model.write_time_counters(block, TimeCounterBlock(pairs))
            self.after_change(f"Блок временных счётчиков {block} записан")
            self.load_time_counters()
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def _load_energy_vars(self, value: EnergyBank, variables: list[tk.StringVar], divisor_text: str, decimals_text: str, sum_var: tk.StringVar, count_var: tk.StringVar | None = None) -> None:
        divisor, decimals = int(divisor_text, 0), int(decimals_text, 0)
        # Авто-раскрытие количества тарифов до реально заполненных, чтобы значения
        # не оставались в заблокированных (серых) полях.
        if count_var is not None:
            highest = max((i + 1 for i, raw in enumerate(value.tariffs) if raw), default=1)
            try:
                if int(count_var.get(), 0) < highest:
                    count_var.set(str(highest))
            except ValueError:
                count_var.set(str(highest))
        for var, raw in zip(variables, value.tariffs):
            var.set(format(decode_energy(raw, divisor, decimals), f".{decimals}f"))
        total = decode_energy(value.total, divisor, decimals)
        sum_var.set(f"∑ T1…T8: {format(total, f'.{decimals}f')}  (raw={value.total})")

    def _energy_from_vars(
        self,
        base: EnergyBank,
        variables: list[tk.StringVar],
        divisor_text: str,
        decimals_text: str,
        tariff_count_text: str,
    ) -> EnergyBank:
        divisor, decimals = int(divisor_text, 0), int(decimals_text, 0)
        # Берём все 8 полей как есть (пустые/нулевые остаются нулями)
        base.set_tariffs([encode_energy(var.get(), divisor, decimals) for var in variables[:8]])
        return base

    def _preview_sum(
        self,
        variables: list[tk.StringVar],
        tariff_count_var: tk.StringVar,
        divisor_var: tk.StringVar,
        decimals_var: tk.StringVar,
        output: tk.StringVar,
    ) -> None:
        try:
            divisor = int(divisor_var.get(), 0)
            decimals = int(decimals_var.get(), 0)
            raw_values = [encode_energy(var.get(), divisor, decimals) for var in variables[:8]]
            count = sum(1 for v in raw_values if v)
            raw_sum = sum(raw_values) % (10**12)
            shown = decode_energy(raw_sum, divisor, decimals)
            output.set(
                f"∑ T1…T8: {format(shown, f'.{decimals}f')}  (заполнено тарифов: {count})"
                if True
                else f"∑ T1…T8: {format(shown, f'.{decimals}f')}"
            )
        except Exception:
            output.set("∑ Введите корректные значения")

    def preview_current_sum(self, *_args) -> None:
        self._preview_sum(
            self.energy_values,
            self.energy_tariff_count,
            self.energy_divisor,
            self.energy_decimals,
            self.energy_sum,
        )

    def preview_archive_sum(self, *_args) -> None:
        self._preview_sum(
            self.archive_values,
            self.archive_tariff_count,
            self.archive_divisor,
            self.archive_decimals,
            self.archive_sum,
        )

    def load_current_energy(self) -> None:
        try:
            bank = int(self.energy_bank.get(), 0)
            value, result = self.state_model.read_current_energy(bank)
            self._load_energy_vars(value, self.energy_values, self.energy_divisor.get(), self.energy_decimals.get(), self.energy_sum, self.energy_tariff_count)
            self.energy_info.set(f"Источник small @0x{result.address:04X}; CRC={result.stored_crc:04X}; marker={value.marker}; cells0..2={value.cells[:3]}; cells11..12={value.cells[11:]}")
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def zero_current_energy(self) -> None:
        try:
            bank = int(self.energy_bank.get(), 0)
            self.state_model.write_current_energy(bank, EnergyBank.empty())
            self.load_current_energy()
            self.after_change(f"Создан нулевой текущий банк {bank}")
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def _energy_filename(self, ext: str = ".bin") -> str:
        """Имя файла из ненулевых тарифов со значениями + сумма всех тарифов."""
        try:
            decimals = int(self.energy_decimals.get(), 0)
        except Exception:
            decimals = 2
        parts, total = [], 0.0
        for i, var in enumerate(self.energy_values):
            s = var.get().strip().replace(",", ".")
            try:
                v = float(s)
            except ValueError:
                v = 0.0
            if v > 0:
                parts.append(f"T{i + 1}-{v:.{decimals}f}")
                total += v
        if not parts:
            parts = ["empty"]
        name = "_".join(parts) + f"_SUM-{total:.{decimals}f}"
        safe = "".join(c for c in name if c.isalnum() or c in "-_.")
        return safe + ext

    def apply_and_write(self, force_direct: bool = False, progressbar=None) -> None:
        """ЕДИНАЯ кнопка: согласованная запись под показания + сохранение .bin
        (имя из тарифов+сумма) + прямая запись в чип (по галочке или force_direct)."""
        bar = progressbar if progressbar is not None else self.energy_progress
        try:
            self._stage(bar, "Согласование записей памяти…", 0, "Accent.Horizontal.TProgressbar")
            self.energy_progress["value"] = 0
            self._set_busy(True, "Выполняется согласованная запись…")
            divisor = int(self.energy_divisor.get(), 0)
            decimals = int(self.energy_decimals.get(), 0)
            now = datetime.now().replace(microsecond=0)

            # 1) Часы = текущее время
            self.state_model.write_clock(ClockValue.from_datetime(now))
            # 2) Активная (слот 0) = введённые тарифы
            try:
                active, _ = self.state_model.read_current_energy(0)
            except ValueError:
                active = EnergyBank.empty()
            active.set_tariffs([encode_energy(v.get(), divisor, decimals) for v in self.energy_values[:8]])
            self.state_model.write_current_energy(0, active)
            # 3) Реактивная (слот 2) = активная × K (если включено)
            if self.reactive_auto.get():
                k = float(self.reactive_k.get())
                reactive = EnergyBank.empty()
                reactive.marker = active.marker
                reactive.cells = [round(c * k) for c in active.cells]
                # Итог c0/c2 = сумма тарифных ячеек: прибор считает «Сумму» именно так,
                # иначе округление даёт расхождение в единицу младшего разряда.
                reactive.set_tariffs(reactive.cells[3:11])
                self.state_model.write_current_energy(2, reactive)
            # 4) Счётчики времени = сейчас
            try:
                for blk in (0, 1):
                    self.state_model.write_time_counters(blk, TimeCounterBlock.initialized(now))
            except Exception:
                pass
            # 5) Для полного SPI — архивы + событие
            if self.source_kind == "spi":
                try:
                    self.state_model.synchronize_energy_everywhere([0], list(active.tariffs), 0)
                    self.state_model.append_event(0, now, status=1, value=None)
                except Exception:
                    pass
            self._stage(bar, "Часы, тарифы, реактивная и счётчики записаны", 25)
            self.update_idletasks()

            steps = ["часы", "активная", "реактивная" if self.reactive_auto.get() else "", "счётчики"]
            saved = None
            # 6) Сохранить .bin с умным именем
            if self.opt_save_bin.get():
                initial = self._energy_filename()
                path = filedialog.asksaveasfilename(title="Сохранить образ", defaultextension=".bin", initialfile=initial)
                if path:
                    if self.source_kind == "24lc64":
                        Path(path).write_bytes(bytes(self.state_model.small))
                    else:
                        Path(path).write_bytes(self.state_model.at25)
                    self.state_model.save_audit(Path(path).with_suffix(".audit.json"))
                    saved = Path(path).name
                    steps.append(f".bin «{saved}»")
            self._stage(bar, "Образ сохранён" if saved else "Сохранение образа пропущено", 55)
            self.update_idletasks()

            # 7) Прямая запись в чип (по галочке ИЛИ принудительно с вкладки прямой записи)
            def _bar(p, lo, span):
                bar["value"] = max(0, min(100, int(lo + p * span)))
                self.update_idletasks()
            if force_direct or self.opt_direct.get():
                self.direct_writer.set_profile(self.direct_chip.get() if hasattr(self, "direct_chip") else "24LC64 (8 КБ)")
                if not self.direct_writer.available():
                    raise RuntimeError("Прямая запись включена, но i2cpy не установлена")
                image = bytes(self.state_model.small)[: self.direct_writer.size]
                if messagebox.askyesno(APP_TITLE, f"Записать {len(image)} байт в {self.direct_writer.profile_name} через CH341?"):
                    self.direct_writer.open()
                    self.direct_writer.write_image(image, progress=lambda p: _bar(p, 55, 0.30))
                    ok, bad = self.direct_writer.verify_image(image, progress=lambda p: _bar(p, 85, 0.15))
                    self.direct_writer.close()
                    steps.append("прямая запись+проверка OK" if ok else f"прямая запись НЕСОВПАД @0x{bad:04X}")

            self._stage(bar, "Операция завершена", 100, "Ok.Horizontal.TProgressbar")
            self.energy_progress["value"] = 100
            self._set_busy(False)
            self.load_clock(); self.load_active_tariff(); self.load_current_energy()
            self.after_change("Согласовано и записано: " + ", ".join(s for s in steps if s))
        except Exception as exc:
            try:
                self.direct_writer.close()
            except Exception:
                pass
            self._stage(bar, f"Операция прервана: {exc}", 0, "Err.Horizontal.TProgressbar")
            self.energy_progress["value"] = 0
            self._set_busy(False, f"Операция прервана: {exc}")
            self.status_led.set_state("err", "ОШИБКА")
            messagebox.showerror(APP_TITLE, str(exc))

    def _energy_prog(self, pct: float) -> None:
        self.energy_progress["value"] = max(0, min(100, int(pct)))
        self.update_idletasks()

    def apply_consistent_write(self) -> None:
        """Единая согласованная запись под введённые показания:
        часы=текущее время, энергобанк(и) primary+backup, активный тариф,
        и (для полного SPI) снимок во все архивы + запись события с текущим временем."""
        try:
            bank = int(self.energy_bank.get(), 0)
            divisor = int(self.energy_divisor.get(), 0)
            decimals = int(self.energy_decimals.get(), 0)
            raw_tariffs = [encode_energy(var.get(), divisor, decimals) for var in self.energy_values[:8]]
            tariff_count = 8  # пишем все 8 полей как введены
            banks = list(range(4)) if self.energy_sync_all_banks.get() else [bank]
            marker = int(self.energy_sync_marker.get(), 0)
            now = datetime.now().replace(microsecond=0)

            is_spi = self.source_kind == "spi"
            archive_note = (
                f"+ снимок во все архивы ({sum(v[1] for v in ENERGY_ARCHIVES.values())*len(banks)}) и запись события"
                if is_spi else
                "(архивы/события — в SPI 25DF041B; тут 24LC64: часы+банки+тариф+счётчики)"
            )
            if not messagebox.askyesno(
                APP_TITLE,
                f"Согласованная запись под текущие показания:\n"
                f"• Часы → {now.isoformat(sep=' ')}\n"
                f"• Банки {banks}: T1…T{tariff_count} + Сумма + активный тариф\n"
                f"• {archive_note}\n\nПродолжить?",
            ):
                return

            steps = []
            # 1) Часы = текущее время (обе копии + CRC)
            self.state_model.write_clock(ClockValue.from_datetime(now))
            steps.append("часы")
            # 2) Счётчики времени: пометить текущим временем (оба блока)
            try:
                for blk in (0, 1):
                    self.state_model.write_time_counters(blk, TimeCounterBlock.initialized(now))
                steps.append("счётчики времени")
            except Exception:
                pass
            # 3) Энергия + (для SPI) архивы синхронно
            if is_spi:
                stats = self.state_model.synchronize_energy_everywhere(banks, raw_tariffs, marker)
                steps.append(f"энергия+архивы ({stats['archive_records']})")
                # 4) Событие «изменение данных» с текущим временем в журнал 0
                try:
                    _e, _a, _c = self.state_model.append_event(0, now, status=1, value=None)
                    steps.append("событие ж.0")
                except Exception:
                    pass
            else:
                # 24LC64: только текущие банки primary+backup
                for b in banks:
                    try:
                        energy, _ = self.state_model.read_current_energy(b)
                    except ValueError:
                        energy = EnergyBank.empty()
                    energy.set_tariffs(raw_tariffs + [0] * (8 - tariff_count))
                    self.state_model.write_current_energy(b, energy)
                # активный тариф выравниваем
                try:
                    active, _ = self.state_model.read_active_tariff()
                    if active > tariff_count:
                        self.state_model.write_active_tariff(1)
                except ValueError:
                    pass
                steps.append(f"энергобанки {banks}")

            # обновить экран
            self.load_clock()
            self.load_active_tariff()
            self.load_current_energy()
            self.after_change(
                "Согласованная запись выполнена: " + ", ".join(steps)
                + ".  Теперь «Сохранить SPI как…» и прошейте."
            )
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def reactive_k_from_dump(self) -> None:
        """Вычислить коэффициент реактивной из загруженного дампа: слот2.c0 / слот0.c0."""
        try:
            active, _ = self.state_model.read_current_energy(0)
            reactive, _ = self.state_model.read_current_energy(2)
            a = active.cells[0]
            r = reactive.cells[0]
            if a == 0:
                raise ValueError("Активная (слот 0) = 0, коэффициент не определить")
            k = r / a
            self.reactive_k.set(f"{k:.7g}")
            self.status_var.set(f"K реактивной из дампа: {r}/{a} = {k:.7g}")
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def apply_active_and_reactive(self) -> None:
        """Записать активную (слот 0) из полей и авто-реактивную (слот 2) = активная × K.
        Обе записи — primary+backup+CRC. Пропорция применяется ко всем 13 ячейкам."""
        try:
            divisor = int(self.energy_divisor.get(), 0)
            decimals = int(self.energy_decimals.get(), 0)
            k = float(self.reactive_k.get())
            if k < 0:
                raise ValueError("K реактивной не может быть отрицательным")
            # 1) Активная — слот 0: берём введённые 8 полей, сохраняя прочие ячейки
            try:
                active, _ = self.state_model.read_current_energy(0)
            except ValueError:
                active = EnergyBank.empty()
            active.set_tariffs([encode_energy(var.get(), divisor, decimals) for var in self.energy_values[:8]])
            self.state_model.write_current_energy(0, active)
            # 2) Реактивная — слот 2: все 13 ячеек = round(активная × K)
            reactive = EnergyBank.empty()
            reactive.marker = active.marker
            reactive.cells = [round(c * k) for c in active.cells]
            # Итог c0/c2 = сумма тарифных ячеек (как считает прибор)
            reactive.set_tariffs(reactive.cells[3:11])
            self.state_model.write_current_energy(2, reactive)
            self.load_current_energy()
            a0, r0 = active.cells[0], reactive.cells[0]
            self.after_change(
                f"Записаны: активная (слот 0, raw c0={a0}) и реактивная (слот 2, raw c0={r0}=round({a0}×{k:g})), "
                f"обе primary+backup+CRC.  Далее «Сохранить SPI как…»."
            )
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def apply_current_bank_only(self) -> None:
        """Записать ТОЛЬКО текущий банк (primary+backup+CRC), без архивов SPI.
        Правильный режим для внутренней EEPROM 24LC64."""
        try:
            bank = int(self.energy_bank.get(), 0)
            divisor = int(self.energy_divisor.get(), 0)
            decimals = int(self.energy_decimals.get(), 0)
            raw_tariffs = [encode_energy(var.get(), divisor, decimals) for var in self.energy_values[:8]]
            tariff_count = 8  # пишем все 8 полей как введены
            # Сохраняем прочие ячейки (0..2, 11..12) и маркер прежнего банка
            try:
                energy, _ = self.state_model.read_current_energy(bank)
            except ValueError:
                energy = EnergyBank.empty()
            energy.set_tariffs(raw_tariffs + [0] * (8 - tariff_count))
            self.state_model.write_current_energy(bank, energy)
            # Активный тариф подравниваем, если вышли за диапазон
            try:
                active, _ = self.state_model.read_active_tariff()
                if active > tariff_count:
                    self.state_model.write_active_tariff(1)
                    self.active_tariff.set("1")
            except ValueError:
                pass
            self.load_current_energy()
            self.after_change(
                f"Банк {bank} записан (primary @0x{0x20 + bank*0x44:04X} + backup, CRC пересчитана). "
                f"Теперь «Сохранить SPI как…» → пишите .bin в прибор."
            )
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def apply_current_energy(self) -> None:
        try:
            bank = int(self.energy_bank.get(), 0)
            divisor = int(self.energy_divisor.get(), 0)
            decimals = int(self.energy_decimals.get(), 0)
            raw_tariffs = [
                encode_energy(var.get(), divisor, decimals)
                for var in self.energy_values[:8]
            ]
            tariff_count = 8  # пишем все 8 полей как введены
            banks = list(range(4)) if self.energy_sync_all_banks.get() else [bank]
            archive_count = sum(item[1] for item in ENERGY_ARCHIVES.values()) * len(banks)
            if not messagebox.askyesno(
                APP_TITLE,
                f"Будут переписаны текущие записи и {archive_count} архивных записей для банков {banks}. Продолжить?",
            ):
                return
            stats = self.state_model.synchronize_energy_everywhere(
                banks,
                raw_tariffs,
                int(self.energy_sync_marker.get(), 0),
            )
            active_tariff, _ = self.state_model.read_active_tariff()
            self.active_tariff.set(str(active_tariff))
            self.load_current_energy()
            self.after_change(
                f"Синхронизированы банки {stats['banks']}: current primary/backup и {stats['archive_records']} архивных записей; "
                f"T1…T{tariff_count}, сумма, active tariff и CRC обновлены"
            )
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def archive_params(self) -> tuple[int, int, int]:
        return int(self.archive_type.get(), 0), int(self.archive_slot.get(), 0), int(self.archive_bank.get(), 0)

    def load_archive(self) -> None:
        try:
            archive_type, slot, bank = self.archive_params()
            value, result = self.state_model.read_archive_energy(archive_type, slot, bank)
            self.archive_marker.set(str(value.marker))
            self._load_energy_vars(value, self.archive_values, self.archive_divisor.get(), self.archive_decimals.get(), self.archive_sum, self.archive_tariff_count)
            base, count, _ = ENERGY_ARCHIVES[archive_type]
            self.archive_info.set(f"AT25 @0x{result.address:05X}; slot={slot % count}/{count}; base=0x{base:05X}; CRC={result.stored_crc:04X}")
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def zero_archive(self) -> None:
        try:
            archive_type, slot, bank = self.archive_params()
            marker = int(self.archive_marker.get(), 0)
            self.state_model.write_archive_energy(archive_type, slot, bank, EnergyBank.empty(), marker)
            self.load_archive()
            self.after_change("Создана нулевая архивная запись")
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def apply_archive(self) -> None:
        try:
            archive_type, slot, bank = self.archive_params()
            try:
                value, _ = self.state_model.read_archive_energy(archive_type, slot, bank)
            except ValueError:
                value = EnergyBank.empty()
            value = self._energy_from_vars(
                value,
                self.archive_values,
                self.archive_divisor.get(),
                self.archive_decimals.get(),
                self.archive_tariff_count.get(),
            )
            self.state_model.write_archive_energy(archive_type, slot, bank, value, int(self.archive_marker.get(), 0))
            self.load_archive()
            self.after_change("Архивная запись обновлена")
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def event_now(self) -> None:
        self.event_time.set(datetime.now().replace(microsecond=0).isoformat(sep=" "))

    def event_params(self) -> tuple[int, int]:
        return int(self.event_id.get(), 0), int(self.event_history.get(), 0)

    def refresh_event_info(self) -> None:
        try:
            event_id = int(self.event_id.get(), 0)
            log = EVENT_LOGS[event_id]
            count = self.state_model.event_count(event_id)
            self.event_info.set(
                f"ID={event_id}; group={log.group}, sub={log.sub}; display_code={log.display_code}; "
                f"body={log.body_length}, record={log.record_length}; capacity={log.capacity}; "
                f"AT25 base=0x{log.base:05X}; записано={count}; общий sequence={self.state_model.event_global_counter()}"
            )
        except Exception as exc:
            self.event_info.set(str(exc))

    def load_event(self) -> None:
        try:
            event_id, history = self.event_params()
            event, result, counter = self.state_model.read_event(event_id, history)
            self.event_time.set(event.timestamp.isoformat(sep=" "))
            self.event_status.set(str(event.status))
            self.event_value.set("—" if event.value is None else str(event.value))
            self.refresh_event_info()
            self.event_info.set(
                self.event_info.get()
                + f"\nВыбран counter={counter}, sequence={event.sequence}, AT25 @0x{result.address:05X}, CRC={result.stored_crc:04X}."
            )
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def append_event(self) -> None:
        try:
            event_id = int(self.event_id.get(), 0)
            log = EVENT_LOGS[event_id]
            timestamp = datetime.fromisoformat(self.event_time.get().strip())
            status = int(self.event_status.get(), 0)
            value = int(self.event_value.get(), 0) if log.body_length == 12 else None
            event, address, counter = self.state_model.append_event(event_id, timestamp, status, value)
            self.event_history.set("0")
            self.after_change(
                f"Событие ID {event_id} добавлено: counter={counter}, sequence={event.sequence}, AT25 @0x{address:05X}"
            )
            self.refresh_event_info()
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def refresh_record_tree(self) -> None:
        for item in self.record_tree.get_children():
            self.record_tree.delete(item)
        valid_count = 0
        for index, descriptor in enumerate(FIXED_DESCRIPTORS):
            try:
                result = self.state_model.read_descriptor(descriptor)
                status = "CRC OK" if result.valid else "CRC ERROR"
                if result.valid:
                    valid_count += 1
            except Exception:
                status = "ERROR"
            backup = "—" if descriptor.backup is None else f"{descriptor.backup_path}:0x{descriptor.backup:05X}"
            # Тег задаёт чередование фона и цвет статуса — таблица читается быстрее.
            tag = "ok" if status == "CRC OK" else "bad"
            stripe = "even" if index % 2 == 0 else "odd"
            self.record_tree.insert("", "end", iid=str(index), tags=(tag, stripe),
                                    values=(descriptor.name, descriptor.path, f"0x{descriptor.primary:05X}", backup, descriptor.length, status))
        self.crc_ok_count = valid_count
        self.crc_total_count = len(FIXED_DESCRIPTORS)
        self._update_telemetry()

    def select_raw_record(self, _event=None) -> None:
        selected = self.record_tree.selection()
        if not selected:
            return
        descriptor = FIXED_DESCRIPTORS[int(selected[0])]
        result = self.state_model.read_descriptor(descriptor)
        self.raw_selected = descriptor
        self.raw_text.delete("1.0", "end")
        self.raw_text.insert("1.0", result.record[:-2].hex(" ").upper())
        self.raw_info.set(
            f"{descriptor.name}: выбран {result.source} @0x{result.address:05X}; len=0x{descriptor.length:X}; "
            f"CRC stored={result.stored_crc:04X}, calc={result.calculated_crc:04X}; RAM=0x{(descriptor.ram or 0):08X}; template=0x{(descriptor.template or 0):05X}"
        )

    def apply_raw_record(self) -> None:
        if self.raw_selected is None:
            return
        try:
            raw = bytes.fromhex(self.raw_text.get("1.0", "end"))
            if len(raw) > self.raw_selected.length - 2:
                raise ValueError(f"Тело длиннее {self.raw_selected.length - 2} байт")
            self.state_model.write_descriptor_body(self.raw_selected, raw)
            self.after_change(f"Запись {self.raw_selected.name} обновлена")
            self.select_raw_record()
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def refresh_audit(self) -> None:
        audit = self.state_model.audit()
        text = json.dumps(audit, ensure_ascii=False, indent=2)
        self.audit_text.delete("1.0", "end")
        self.audit_text.insert("1.0", text)

    def after_change(self, message: str) -> None:
        self.status_var.set(message)
        self.refresh_record_tree()
        self.refresh_audit()
        # Отклик оформления: всплеск на диаграмме активности и зелёный индикатор.
        if hasattr(self, "activity"):
            self.activity.pulse(1.0)
        if hasattr(self, "status_led"):
            self.status_led.set_state("ok", "ЗАПИСЬ")
            self.after(1400, lambda: self.status_led.set_state("ok", "ГОТОВ"))


def main() -> None:
    # --crc=auto|ce208|msp432 — жёстко задать режим контроля (ярлыки запуска).
    arguments = [value for value in sys.argv[1:] if not value.startswith("--")]
    crc_mode = "auto"
    for value in sys.argv[1:]:
        if value.startswith("--crc"):
            crc_mode = value.split("=", 1)[-1].strip().lower()
    app = Editor(crc_mode=crc_mode if crc_mode in ("auto", "ce208", "msp432") else "auto")
    if arguments:
        candidate = Path(arguments[0])
        if candidate.exists():
            raw = candidate.read_bytes()
            if len(raw) == SMALL_SIZE:
                app.state_model = CE208State(small=raw, crc=app.crc_scheme_arg())
                app.source_kind = "24lc64"
                app.at25_path = candidate
                app.at25_loaded = True
                app.at25_var.set(f"24LC64: {candidate.name}  (8 КиБ, показания)")
            elif len(raw) == AT25_SIZE:
                app.state_model = CE208State(at25=raw, crc=app.crc_scheme_arg())
                app.source_kind = "spi"
                app.at25_path = candidate
                app.at25_loaded = True
                app.at25_var.set(f"SPI 25DF041B: {candidate.name}  (512 КиБ, архивы)")
            else:
                messagebox.showerror(APP_TITLE, f"Нужен дамп 24LC64 ({SMALL_SIZE} б) или 25DF041B ({AT25_SIZE} б)")
            app.refresh_all()
    app.mainloop()


if __name__ == "__main__":
    main()
