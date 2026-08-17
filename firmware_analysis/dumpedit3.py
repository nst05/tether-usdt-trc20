#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dumpedit3.py — простой редактор КОЭФФИЦИЕНТОВ усиления прошивки ne2r
(трёхканальный измеритель). Оформлен как первый редактор (dumpedit.py):
несколько ползунков + строка эффекта «скорость счёта быстрее/медленнее на %».

Коэффициенты усиления идут в аппаратный умножитель (OP2) и задают скорость
накопления (учёт ∝ коэффициенту). Они хранятся в таблицах КОДА и выбираются
номером набора (ниббл из записи 0x1090). Этот редактор правит коэффициенты
АКТИВНОГО набора (номер читается из дампа) — прямо в коде. Контрольные суммы
строк S-record/HEX пересчитываются автоматически; отдельных XOR-сумм у кода
нет, поэтому больше ничего не требуется.

Запуск:
    python3 dumpedit3.py            (или  python dumpedit3.py  в Windows)
    python3 dumpedit3.py ne2r.s19   (сразу открыть файл)

Интерфейс на tkinter (входит в стандартную библиотеку Python).
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from dumpfile import DumpFile

__version__ = '3.1'

# Палитра (как в dumpedit.py).
BG = '#eef1f5'; CARD = '#ffffff'; INK = '#1f2933'; MUTED = '#5b6673'
ACCENT = '#0a58ca'; OK = '#198754'; WARN = '#c07000'; DANGER = '#dc3545'
HEADER = '#0d3b66'

# Коэффициенты усиления: (имя, база таблицы в коде, тип эффекта).
# Адрес для активного набора = база + 2*(набор-1). Базы и назначение
# восстановлены по коду (см. ne2r_analysis.md):
#   0x042C -> произведение U*I -> накопитель энергии 0x0390 (мощность/энергия);
#   0x0428 -> выход 0x0708 (напряжение), постоянен по наборам;
#   0x042A -> выход 0x0738 (ток), меняется с диапазоном (в наборе 3 x2).
# Как и в FE427: скорость счёта задаёт только коэф мощности; U и I —
# только отображаемые величины.
COEFFS = [
    ('Мощность / энергия (основной)', 0xFAFC, 'energy'),
    ('Напряжение (U)', 0xFAEC, 'voltage'),
    ('Ток (I)', 0xFAF4, 'current'),
]


class Row(object):
    """Один коэффициент: ползунок + DEC + HEX + множитель/эффект."""

    def __init__(self, app, parent, r, name, effect_kind):
        self.app = app
        self.name = name
        self.effect_kind = effect_kind
        self.is_main = (effect_kind == 'energy')
        self.addr = None
        self.original = None
        self._sync = False

        box = ttk.LabelFrame(parent, text=name, padding=8)
        box.grid(row=r, column=0, sticky='ew', pady=5)
        box.columnconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)

        self.scale = ttk.Scale(box, from_=0, to=65535, orient='horizontal',
                               command=self._on_scale)
        self.scale.grid(row=0, column=0, columnspan=5, sticky='ew')

        ttk.Label(box, text='Значение:').grid(row=1, column=0, sticky='w',
                                              pady=(6, 0))
        self.dec = ttk.Entry(box, width=8)
        self.dec.grid(row=1, column=1, sticky='w', padx=4, pady=(6, 0))
        self.dec.bind('<KeyRelease>', self._on_dec)
        ttk.Label(box, text='HEX:').grid(row=1, column=2, sticky='e', pady=(6, 0))
        self.hexv = ttk.Entry(box, width=8)
        self.hexv.grid(row=1, column=3, sticky='w', padx=4, pady=(6, 0))
        self.hexv.bind('<KeyRelease>', self._on_hex)
        ttk.Button(box, text='Сброс', width=8,
                   command=self.reset).grid(row=1, column=4, sticky='e',
                                            pady=(6, 0))

        self.info = tk.StringVar()
        ttk.Label(box, textvariable=self.info, foreground=ACCENT,
                  font=('TkDefaultFont', 10, 'bold')).grid(
            row=2, column=0, columnspan=5, sticky='w', pady=(6, 0))

        self.effect = tk.StringVar()
        self.effect_lbl = ttk.Label(box, textvariable=self.effect,
                                    font=('TkDefaultFont', 11, 'bold'))
        self.effect_lbl.grid(row=3, column=0, columnspan=5, sticky='w',
                             pady=(4, 0))

    def bind_addr(self, addr, value):
        self.addr = addr
        self.original = value
        self._set(value)

    def _set(self, value):
        value = max(0, min(65535, int(value)))
        self._sync = True
        self.scale.set(value)
        self.dec.delete(0, 'end'); self.dec.insert(0, str(value))
        self.hexv.delete(0, 'end'); self.hexv.insert(0, '%04X' % value)
        self._sync = False
        self._update(value)
        self.app.mark_dirty()

    def _update(self, value):
        if not self.original:
            self.info.set(''); self.effect.set(''); return
        mult = value / self.original
        pct = (mult - 1) * 100
        self.info.set('множитель ×%.3f (%+.1f%%)   было %d (0x%04X)   адрес 0x%04X'
                      % (mult, pct, self.original, self.original, self.addr))
        # текст эффекта зависит от того, что меняет коэффициент
        if self.effect_kind == 'energy':
            subj, up, down = 'Скорость счёта', 'БЫСТРЕЕ', 'МЕДЛЕННЕЕ'
            note = ''
        elif self.effect_kind == 'voltage':
            subj, up, down = 'Отображаемое напряжение', 'БОЛЬШЕ', 'МЕНЬШЕ'
            note = '  (на скорость счёта не влияет)'
        else:
            subj, up, down = 'Отображаемый ток', 'БОЛЬШЕ', 'МЕНЬШЕ'
            note = '  (на скорость счёта не влияет)'
        if abs(pct) < 0.05:
            self.effect.set('%s: без изменений' % subj)
            self.effect_lbl.configure(foreground=OK)
        elif pct > 0:
            self.effect.set('%s %s на %.1f%%%s' % (subj, up, pct, note))
            self.effect_lbl.configure(foreground=DANGER)
        else:
            self.effect.set('%s %s на %.1f%%%s' % (subj, down, -pct, note))
            self.effect_lbl.configure(foreground=ACCENT)

    def _on_scale(self, _v):
        if not self._sync:
            self._set(float(self.scale.get()))

    def _on_dec(self, _e):
        if self._sync:
            return
        try:
            self._set(int(self.dec.get()))
        except ValueError:
            pass

    def _on_hex(self, _e):
        if self._sync:
            return
        try:
            self._set(int(self.hexv.get(), 16))
        except ValueError:
            pass

    def reset(self):
        if self.original is not None:
            self._set(self.original)

    def value(self):
        try:
            return int(self.dec.get())
        except ValueError:
            return self.original or 0


class App(ttk.Frame):
    def __init__(self, master):
        self.master = master
        self._setup_style()
        super().__init__(master, padding=14, style='App.TFrame')
        self.grid(sticky='nsew')
        master.title('Редактор коэффициентов ne2r  v%s' % __version__)
        master.configure(background=BG)
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.dump = None
        self.path = None
        self.preset = None
        self.rows = []

        self._build_header()
        self._build_file()
        self._build_fields()
        self._build_footer()

    def _setup_style(self):
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass
        style.configure('.', background=CARD, foreground=INK)
        style.configure('App.TFrame', background=BG)
        style.configure('TFrame', background=BG)
        style.configure('TLabel', background=CARD, foreground=INK)
        style.configure('TLabelframe', background=CARD, borderwidth=1,
                        relief='solid')
        style.configure('TLabelframe.Label', background=CARD, foreground=ACCENT,
                        font=('TkDefaultFont', 10, 'bold'))
        style.configure('TButton', padding=6)
        style.configure('Accent.TButton', foreground='#ffffff',
                        background=ACCENT, padding=8,
                        font=('TkDefaultFont', 10, 'bold'))
        style.map('Accent.TButton',
                  background=[('active', '#084298'), ('disabled', '#9db8e0')])

    def _build_header(self):
        head = tk.Frame(self, background=HEADER)
        head.grid(row=0, column=0, sticky='ew', pady=(0, 12))
        head.columnconfigure(0, weight=1)
        tk.Label(head, text='Редактор коэффициентов', bg=HEADER, fg='#ffffff',
                 font=('TkDefaultFont', 15, 'bold')).grid(
            row=0, column=0, sticky='w', padx=14, pady=(10, 0))
        self.sub = tk.StringVar(value='прошивка ne2r · коэффициенты усиления '
                                      '(скорость счёта)')
        tk.Label(head, textvariable=self.sub, bg=HEADER, fg='#bcd3ea',
                 font=('TkDefaultFont', 9)).grid(
            row=1, column=0, sticky='w', padx=14, pady=(0, 10))
        tk.Label(head, text='v%s' % __version__, bg=HEADER, fg='#7ea8d6',
                 font=('TkDefaultFont', 9)).grid(row=0, column=1, sticky='ne',
                                                 padx=12, pady=8)

    def _build_file(self):
        box = ttk.Frame(self, style='App.TFrame')
        box.grid(row=1, column=0, sticky='ew', pady=(0, 8))
        box.columnconfigure(1, weight=1)
        ttk.Button(box, text='Открыть дамп…',
                   command=self.open_file).grid(row=0, column=0)
        self.file_var = tk.StringVar(value='файл не выбран')
        tk.Label(box, textvariable=self.file_var, bg=BG, fg=MUTED).grid(
            row=0, column=1, sticky='w', padx=8)

    def _build_fields(self):
        fields = ttk.Frame(self, style='App.TFrame')
        fields.grid(row=2, column=0, sticky='nsew')
        self.rowconfigure(2, weight=1)
        fields.columnconfigure(0, weight=1)
        for i, (name, base, effect) in enumerate(COEFFS):
            self.rows.append(Row(self, fields, i, name, effect))

    def _build_footer(self):
        box = ttk.Frame(self, style='App.TFrame')
        box.grid(row=3, column=0, sticky='ew', pady=(10, 0))
        box.columnconfigure(0, weight=1)
        self.status = tk.StringVar(value='Откройте дамп ne2r (.s19 или .hex).')
        tk.Label(box, textvariable=self.status, bg=BG, fg=WARN).grid(
            row=0, column=0, sticky='w')
        self.save_btn = ttk.Button(box, text='Сохранить как…',
                                   command=self.save_file, state='disabled',
                                   style='Accent.TButton')
        self.save_btn.grid(row=0, column=1, sticky='e')

    # ------------------------------------------------- действия
    def open_file(self, path=None):
        if path is None:
            path = filedialog.askopenfilename(
                title='Открыть дамп',
                filetypes=[('Дампы прошивки', '*.s19 *.srec *.hex *.ihex'),
                           ('Все файлы', '*.*')])
        if not path:
            return
        try:
            self.dump = DumpFile.load(path)
        except Exception as e:
            messagebox.showerror('Ошибка чтения', str(e))
            return
        sel = self.dump.get_word(0x1092)
        if sel is None:
            messagebox.showwarning('Не тот файл',
                                   'В дампе нет области 0x1090 — это не ne2r?')
            return
        self.preset = sel & 0x0F
        if not (1 <= self.preset <= 4):
            messagebox.showwarning(
                'Набор вне диапазона',
                'Активный набор = %d (ожидался 1..4). Правка может быть '
                'некорректной.' % self.preset)
        self.path = path
        self.file_var.set('%s  [%s]' % (os.path.basename(path),
                                        self.dump.fmt.upper()))
        self.sub.set('прошивка ne2r · активный набор калибровки № %d · '
                     'коэффициенты усиления' % self.preset)
        idx = max(self.preset, 1) - 1
        for row, (_n, base, _m) in zip(self.rows, COEFFS):
            addr = base + 2 * idx
            row.bind_addr(addr, self.dump.get_word(addr))
        self.save_btn.configure(state='normal')
        self.status.set('Загружено. Набор № %d. Меняйте коэффициенты.' %
                        self.preset)

    def mark_dirty(self):
        if self.path:
            self.status.set('Есть несохранённые изменения.')

    def _suggest_name(self):
        """Имя файла = основной коэффициент + знаковый % от исходного."""
        main = self.rows[0]
        newv = main.value()
        pct = (newv / main.original - 1) * 100 if main.original else 0.0
        sign = '+' if pct >= 0 else '-'
        ap = abs(pct)
        p = ('%d' % round(ap)) if abs(round(ap) - ap) < 0.05 \
            else ('%.1f' % ap).replace('.', '_')
        return 'коэф_%d_%s%s%%' % (newv, sign, p)

    def save_file(self):
        if not self.dump:
            return
        changed = []
        for row in self.rows:
            v = row.value()
            self.dump.set_word(row.addr, v)
            if row.original != v:
                changed.append('  0x%04X (%s): 0x%04X -> 0x%04X' %
                               (row.addr, row.name, row.original, v))
        base, ext = os.path.splitext(self.path)
        out = filedialog.asksaveasfilename(
            title='Сохранить изменённый дамп',
            initialdir=os.path.dirname(self.path),
            initialfile=self._suggest_name() + ext,
            defaultextension=ext,
            filetypes=[('Дамп прошивки', '*' + ext), ('Все файлы', '*.*')])
        if not out:
            return
        if os.path.abspath(out) == os.path.abspath(self.path):
            messagebox.showerror('Нельзя перезаписать оригинал',
                                 'Сохраните под другим именем.')
            return
        bak = self.path + '.bak'
        if not os.path.exists(bak):
            try:
                with open(self.path, 'rb') as s, open(bak, 'wb') as d:
                    d.write(s.read())
            except Exception:
                pass
        try:
            self.dump.save(out)
        except Exception as e:
            messagebox.showerror('Ошибка сохранения', str(e))
            return
        summary = '\n'.join(changed) if changed else '  (значения не изменены)'
        self.status.set('Сохранено: %s' % os.path.basename(out))
        messagebox.showinfo(
            'Готово',
            'Сохранено:\n%s\n\nРезервная копия:\n%s\n\n'
            'Контрольные суммы строк пересчитаны.\n\nИзменения:\n%s'
            % (out, bak, summary))


def main():
    root = tk.Tk()
    try:
        root.tk.call('tk', 'scaling', 1.2)
    except Exception:
        pass
    app = App(root)
    root.minsize(680, 620)
    root.update_idletasks()
    w, h = 720, 680
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 2
    root.geometry('%dx%d+%d+%d' % (w, h, max(x, 0), max(y, 0)))
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        app.open_file(sys.argv[1])
    root.mainloop()


if __name__ == '__main__':
    main()
