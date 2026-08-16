#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dumpedit.py — редактор калибровочных коэффициентов прямо в дампе прошивки
(форматы .s19 / .hex) с ползунками.

Запуск:
    python3 dumpedit.py            (или  python dumpedit.py  в Windows)
    python3 dumpedit.py файл.s19   (сразу открыть файл)

Что делает:
    * открывает дамп прибора (Motorola S-record или Intel HEX);
    * показывает коэффициенты INFO Flash (ADAPTI1 0x1000, масштаб напряжения
      0x1002, масштаб тока 0x1004) и даёт менять их ползунками;
    * рядом показывает множитель относительно исходного значения — сразу видно,
      как изменятся показания (например ×0.5 = ток занижается вдвое);
    * сохраняет в НОВЫЙ файл, автоматически создавая резервную копию оригинала;
      меняются только отредактированные байты, контрольные суммы строк
      пересчитываются, остальной дамп остаётся побайтно неизменным.

ВНИМАНИЕ: эти значения задают заводскую калибровку измерений. Меняйте их
осознанно и только имея резервную копию исходного дампа.

Интерфейс на tkinter (входит в стандартную библиотеку Python).
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from dumpfile import DumpFile

__version__ = '1.4'

# Цветовая палитра интерфейса.
BG = '#eef1f5'          # фон окна
CARD = '#ffffff'        # фон карточек-секций
INK = '#1f2933'         # основной текст
MUTED = '#5b6673'       # второстепенный текст
ACCENT = '#0a58ca'      # акцент (синий)
OK = '#198754'          # зелёный
WARN = '#c07000'        # оранжевый
DANGER = '#dc3545'      # красный
HEADER = '#0d3b66'      # шапка


# Редактируемые 16-битные коэффициенты.
# (адрес, имя, пояснение, интерпретация, эффект)
# эффект: 'energy' | 'voltage' | 'current' — что именно меняется (по разбору
# алгоритма учёта: энергию считает ESP430, и на неё влияет только ADAPTI1;
# 0x1002/0x1004 масштабируют лишь ОТОБРАЖАЕМЫЕ U и I).
FIELDS = [
    (0x1000, 'ADAPTI1 (0x1000)',
     'Коэффициент адаптации токового канала ВНУТРИ ESP430, до расчёта '
     'активной энергии (формат +1.14). Влияет и на учёт энергии, и на '
     'измеряемый ток.',
     lambda v: '= %.4f (v/16384)' % (v / 16384.0),
     'energy'),
    (0x1002, 'Масштаб напряжения (0x1002)',
     'Множитель ОТОБРАЖАЕМОГО напряжения (применяется к V1RMS уже после '
     'измерения). На учёт энергии НЕ влияет.',
     None,
     'voltage'),
    (0x1004, 'Масштаб тока (0x1004)',
     'Множитель ОТОБРАЖАЕМОГО тока (применяется к IRMS уже после измерения). '
     'На учёт энергии НЕ влияет.',
     None,
     'current'),
]


class Row(object):
    """Один редактируемый коэффициент: подпись, ползунок, поля, множитель."""

    def __init__(self, app, parent, r, addr, name, help_text, interp, effect):
        self.app = app
        self.addr = addr
        self.interp = interp
        self.effect_kind = effect
        self.original = None
        self._sync = False       # защита от рекурсии slider<->entry

        box = ttk.LabelFrame(parent, text=name, padding=8)
        box.grid(row=r, column=0, sticky='ew', pady=5)
        box.columnconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)

        ttk.Label(box, text=help_text, foreground='#555',
                  wraplength=560, justify='left').grid(
            row=0, column=0, columnspan=5, sticky='w', pady=(0, 6))

        self.var = tk.IntVar(value=0)
        self.scale = ttk.Scale(box, from_=0, to=65535, orient='horizontal',
                               command=self._on_scale)
        self.scale.grid(row=1, column=0, columnspan=5, sticky='ew')

        ttk.Label(box, text='Значение:').grid(row=2, column=0, sticky='w',
                                              pady=(6, 0))
        self.dec = ttk.Entry(box, width=8)
        self.dec.grid(row=2, column=1, sticky='w', padx=4, pady=(6, 0))
        self.dec.bind('<KeyRelease>', self._on_dec)

        ttk.Label(box, text='HEX:').grid(row=2, column=2, sticky='e', pady=(6, 0))
        self.hexv = ttk.Entry(box, width=8)
        self.hexv.grid(row=2, column=3, sticky='w', padx=4, pady=(6, 0))
        self.hexv.bind('<KeyRelease>', self._on_hex)

        ttk.Button(box, text='Сброс', width=8,
                   command=self.reset).grid(row=2, column=4, sticky='e',
                                            pady=(6, 0))

        self.info = tk.StringVar()
        ttk.Label(box, textvariable=self.info, foreground='#0a58ca',
                  font=('TkDefaultFont', 10, 'bold')).grid(
            row=3, column=0, columnspan=5, sticky='w', pady=(6, 0))

        # заметная строка: как меняется скорость учёта энергии
        self.effect = tk.StringVar()
        self.effect_lbl = ttk.Label(box, textvariable=self.effect,
                                    font=('TkDefaultFont', 11, 'bold'))
        self.effect_lbl.grid(row=4, column=0, columnspan=5, sticky='w',
                             pady=(4, 0))

    def load(self, value):
        self.original = value
        self._set(value, refresh_all=True)

    def _set(self, value, refresh_all=False):
        value = max(0, min(65535, int(value)))
        self._sync = True
        self.var.set(value)
        self.scale.set(value)
        self.dec.delete(0, 'end'); self.dec.insert(0, str(value))
        self.hexv.delete(0, 'end'); self.hexv.insert(0, '%04X' % value)
        self._sync = False
        self._update_info(value)
        self.app.mark_dirty()

    def _update_info(self, value):
        parts = []
        if self.interp:
            parts.append(self.interp(value))
        mult = value / self.original if self.original else 0
        if self.original:
            pct = (mult - 1) * 100
            parts.append('множитель к оригиналу ×%.3f (%+.1f%%)' % (mult, pct))
        if self.original is not None:
            parts.append('было %d (0x%04X)' % (self.original, self.original))
        self.info.set('   '.join(parts))
        self._update_effect(mult)

    def _update_effect(self, mult):
        """Показывает эффект изменения. Текст зависит от того, что именно
        меняет коэффициент: учёт энергии (ADAPTI1) или только отображаемое
        значение (масштабы U/I). Зависимость линейная."""
        if not self.original:
            self.effect.set('')
            return
        pct = (mult - 1) * 100

        if self.effect_kind == 'energy':
            subj, up, down = 'Учёт энергии', 'БЫСТРЕЕ', 'МЕДЛЕННЕЕ'
            up_note, down_note = 'счётчик спешит, завышает', \
                                 'счётчик отстаёт, занижает'
        elif self.effect_kind == 'voltage':
            subj, up, down = 'Отображаемое напряжение', 'БОЛЬШЕ', 'МЕНЬШЕ'
            up_note = down_note = 'на учёт энергии НЕ влияет'
        else:  # current
            subj, up, down = 'Отображаемый ток', 'БОЛЬШЕ', 'МЕНЬШЕ'
            up_note = down_note = 'на учёт энергии НЕ влияет'

        if abs(pct) < 0.05:
            self.effect.set('%s: без изменений' % subj)
            self.effect_lbl.configure(foreground='#198754')
        elif pct > 0:
            self.effect.set('%s %s на %.1f%%  (%s)' % (subj, up, pct, up_note))
            self.effect_lbl.configure(foreground='#dc3545')
        else:
            self.effect.set('%s %s на %.1f%%  (%s)' % (subj, down, -pct, down_note))
            self.effect_lbl.configure(foreground='#0a58ca')

    def _on_scale(self, _v):
        if self._sync:
            return
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
        return self.var.get()


class App(ttk.Frame):
    def __init__(self, master):
        self.master = master
        self._setup_style()
        super().__init__(master, padding=14, style='App.TFrame')
        self.grid(sticky='nsew')
        master.title('Редактор коэффициентов дампа MSP430FE427  v%s' % __version__)
        master.configure(background=BG)
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.dump = None
        self.path = None
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
        style.configure('Card.TFrame', background=CARD)
        style.configure('TLabel', background=CARD, foreground=INK)
        style.configure('Muted.TLabel', background=CARD, foreground=MUTED)
        style.configure('Head.TLabel', background=HEADER, foreground='#ffffff')
        style.configure('HeadSub.TLabel', background=HEADER, foreground='#bcd3ea')
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
        style.configure('Horizontal.TScale', background=CARD)

    def _build_header(self):
        head = tk.Frame(self, background=HEADER)
        head.grid(row=0, column=0, sticky='ew', pady=(0, 12))
        head.columnconfigure(0, weight=1)
        tk.Label(head, text='Редактор коэффициентов дампа',
                 bg=HEADER, fg='#ffffff',
                 font=('TkDefaultFont', 15, 'bold')).grid(
            row=0, column=0, sticky='w', padx=14, pady=(10, 0))
        tk.Label(head, text='MSP430FE427 · калибровка и серийный номер '
                            'в файле прошивки (.s19 / .hex)',
                 bg=HEADER, fg='#bcd3ea',
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
        # прокручиваемая область, чтобы все секции были доступны на любом экране
        outer = ttk.Frame(self, style='App.TFrame')
        outer.grid(row=2, column=0, sticky='nsew')
        self.rowconfigure(2, weight=1)
        self.columnconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)

        canvas = tk.Canvas(outer, background=BG, highlightthickness=0,
                           borderwidth=0)
        canvas.grid(row=0, column=0, sticky='nsew')
        vsb = ttk.Scrollbar(outer, orient='vertical', command=canvas.yview)
        vsb.grid(row=0, column=1, sticky='ns')
        canvas.configure(yscrollcommand=vsb.set)

        self.fields_box = ttk.Frame(canvas, style='App.TFrame')
        win = canvas.create_window((0, 0), window=self.fields_box, anchor='nw')
        self.fields_box.columnconfigure(0, weight=1)
        canvas.bind('<Configure>',
                    lambda e: canvas.itemconfigure(win, width=e.width))
        self.fields_box.bind(
            '<Configure>',
            lambda e: canvas.configure(scrollregion=canvas.bbox('all')))

        def _wheel(e):
            if e.num == 5 or e.delta < 0:
                canvas.yview_scroll(1, 'units')
            else:
                canvas.yview_scroll(-1, 'units')
        canvas.bind_all('<MouseWheel>', _wheel)     # Windows / macOS
        canvas.bind_all('<Button-4>', _wheel)       # Linux вверх
        canvas.bind_all('<Button-5>', _wheel)       # Linux вниз

        for i, (addr, name, help_text, interp, effect) in enumerate(FIELDS):
            self.rows.append(Row(self, self.fields_box, i, addr, name,
                                 help_text, interp, effect))

        # --- редактируемый серийный номер (ID прибора, 0x1008, 4 байта) ---
        sn = ttk.LabelFrame(self.fields_box,
                            text='Серийный номер / ID прибора (0x1008)',
                            padding=8)
        sn.grid(row=len(FIELDS), column=0, sticky='ew', pady=5)
        sn.columnconfigure(1, weight=1)
        ttk.Label(sn, text='4 байта, HEX (например 04 A2 CB 71). '
                          'Этим ID прибор отвечает на команду поиска 0x53.',
                  foreground='#555', wraplength=560, justify='left').grid(
            row=0, column=0, columnspan=3, sticky='w', pady=(0, 6))
        ttk.Label(sn, text='ID:').grid(row=1, column=0, sticky='w')
        self.sn_var = tk.StringVar()
        self.sn_entry = ttk.Entry(sn, textvariable=self.sn_var,
                                  font=('monospace', 11))
        self.sn_entry.grid(row=1, column=1, sticky='ew', padx=4)
        self.sn_entry.bind('<KeyRelease>', lambda _e: self._check_sn())
        ttk.Button(sn, text='Сброс', width=8,
                   command=self._reset_sn).grid(row=1, column=2, sticky='e')
        self.sn_info = tk.StringVar()
        self.sn_lbl = ttk.Label(sn, textvariable=self.sn_info,
                                font=('TkDefaultFont', 10, 'bold'))
        self.sn_lbl.grid(row=2, column=0, columnspan=3, sticky='w', pady=(6, 0))
        self.sn_original = None

        # --- справка (не меняется) ---
        info = ttk.LabelFrame(self.fields_box, text='Только для справки (не меняется)',
                              padding=8)
        info.grid(row=len(FIELDS) + 1, column=0, sticky='ew', pady=5)
        self.ref_var = tk.StringVar(value='—')
        ttk.Label(info, textvariable=self.ref_var,
                  font=('monospace', 10)).grid(sticky='w')

    # -------- серийный номер --------
    def _parse_sn(self):
        """Разбор поля ID → 4 байта. None, если формат неверный."""
        t = self.sn_var.get().strip().replace(':', ' ').replace('-', ' ')
        try:
            if ' ' in t:
                parts = [int(x, 16) for x in t.split()]
            else:
                t = t.replace('0x', '')
                parts = [int(t[i:i + 2], 16) for i in range(0, len(t), 2)]
        except ValueError:
            return None
        if len(parts) != 4 or any(b < 0 or b > 255 for b in parts):
            return None
        return bytes(parts)

    def _check_sn(self):
        b = self._parse_sn()
        if b is None:
            self.sn_info.set('Нужно ровно 4 байта HEX (00..FF).')
            self.sn_lbl.configure(foreground='#dc3545')
            return False
        if self.sn_original is not None and b != self.sn_original:
            self.sn_info.set('Будет изменён (было %s)' %
                             ' '.join('%02X' % x for x in self.sn_original))
            self.sn_lbl.configure(foreground='#c07000')
        else:
            self.sn_info.set('Без изменений')
            self.sn_lbl.configure(foreground='#198754')
        return True

    def _reset_sn(self):
        if self.sn_original is not None:
            self.sn_var.set(' '.join('%02X' % x for x in self.sn_original))
            self._check_sn()

    def _build_footer(self):
        box = ttk.Frame(self, style='App.TFrame')
        box.grid(row=3, column=0, sticky='ew', pady=(10, 0))
        box.columnconfigure(0, weight=1)
        self.status = tk.StringVar(value='Откройте дамп прибора (.s19 или .hex).')
        tk.Label(box, textvariable=self.status, bg=BG, fg=WARN).grid(
            row=0, column=0, sticky='w')
        self.save_btn = ttk.Button(box, text='Сохранить как…',
                                   command=self.save_file, state='disabled',
                                   style='Accent.TButton')
        self.save_btn.grid(row=0, column=1, sticky='e')

    # --------------------------------------------------- действия
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
        self.path = path
        self.file_var.set('%s  [%s]' % (os.path.basename(path),
                                        self.dump.fmt.upper()))
        for row in self.rows:
            w = self.dump.get_word(row.addr)
            if w is None:
                messagebox.showwarning(
                    'Нет данных',
                    'В дампе нет адреса 0x%04X — файл не тот?' % row.addr)
                w = 0
            row.load(w)
        idb = self.dump.get_bytes(0x1008, 4)
        self.sn_original = bytes(idb)
        self.sn_var.set(' '.join('%02X' % b for b in idb))
        self._check_sn()
        flags = self.dump.get_word(0x1006)
        self.ref_var.set('флаги (0x1006): 0x%04X' % (flags or 0))
        self.save_btn.configure(state='normal')
        self.status.set('Дамп загружен. Меняйте коэффициенты и серийный номер.')

    def mark_dirty(self):
        if self.path:
            self.status.set('Есть несохранённые изменения.')

    @staticmethod
    def _fmt_pct(p):
        """Процент в виде для имени файла: 50 или 12_5."""
        if abs(p - round(p)) < 0.05:
            return '%d' % round(p)
        return ('%.1f' % p).replace('.', '_')

    def _suggest_name(self, sn):
        """Имя выходного файла: эффект учёта энергии + серийный номер.

        Учёт энергии зависит от ADAPTI1 (0x1000): меньше → экономия,
        больше → быстрее (счётчик спешит)."""
        energy_row = next((r for r in self.rows if r.effect_kind == 'energy'),
                          None)
        eff = 'без_изменений'
        if energy_row and energy_row.original:
            pct = (energy_row.value() / energy_row.original - 1) * 100
            if abs(pct) >= 0.05:
                eff = ('быстрее_%s%%' % self._fmt_pct(pct)) if pct > 0 else \
                      ('экономия_%s%%' % self._fmt_pct(-pct))
        serial = ''.join('%02X' % b for b in sn)
        return '%s_%s' % (eff, serial)

    def save_file(self):
        if not self.dump:
            return
        # серийный номер: проверить формат перед сохранением
        sn = self._parse_sn()
        if sn is None:
            messagebox.showerror(
                'Неверный серийный номер',
                'Поле «Серийный номер / ID» должно содержать ровно 4 байта HEX '
                '(например 04 A2 CB 71).')
            return
        # применяем значения ползунков и серийный номер в дамп
        for row in self.rows:
            self.dump.set_word(row.addr, row.value())
        for i, b in enumerate(sn):
            self.dump.set_byte(0x1008 + i, b)

        base, ext = os.path.splitext(self.path)
        default_name = self._suggest_name(sn) + ext
        out = filedialog.asksaveasfilename(
            title='Сохранить изменённый дамп',
            initialdir=os.path.dirname(self.path),
            initialfile=default_name,
            defaultextension=ext,
            filetypes=[('Дамп прошивки', '*' + ext), ('Все файлы', '*.*')])
        if not out:
            return
        if os.path.abspath(out) == os.path.abspath(self.path):
            messagebox.showerror(
                'Нельзя перезаписать оригинал',
                'Сохраните под другим именем, чтобы не потерять исходный дамп.')
            return

        # резервная копия оригинала (один раз)
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

        changes = []
        for row in self.rows:
            if row.original != row.value():
                changes.append('  0x%04X: 0x%04X → 0x%04X' %
                               (row.addr, row.original, row.value()))
        if self.sn_original is not None and sn != self.sn_original:
            changes.append('  0x1008 ID: %s → %s' % (
                ' '.join('%02X' % b for b in self.sn_original),
                ' '.join('%02X' % b for b in sn)))
        summary = '\n'.join(changes) if changes else '  (значения не изменены)'
        self.status.set('Сохранено: %s' % os.path.basename(out))
        messagebox.showinfo(
            'Готово',
            'Изменённый дамп сохранён:\n%s\n\nРезервная копия оригинала:\n%s\n\n'
            'Изменения:\n%s' % (out, bak, summary))


def main():
    root = tk.Tk()
    try:
        root.tk.call('tk', 'scaling', 1.2)
    except Exception:
        pass
    app = App(root)
    root.minsize(700, 700)
    # разместить окно по центру экрана
    root.update_idletasks()
    w, h = 720, 760
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 2
    root.geometry('%dx%d+%d+%d' % (w, h, max(x, 0), max(y, 0)))
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        app.open_file(sys.argv[1])
    root.mainloop()


if __name__ == '__main__':
    main()
