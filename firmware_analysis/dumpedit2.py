#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dumpedit2.py — редактор калибровочных записей прошивки MSP430 «ne2r»
(другой прибор, не FE427-счётчик; см. отличия в анализе).

Отличие от dumpedit.py: калибровка этого прибора хранится в info-flash не
отдельными словами, а СТРУКТУРАМИ (записями), каждая из которых защищена
контрольной суммой XOR (init 0xF0F0). Поэтому при любой правке значения
программа сама пересчитывает КС записи — иначе прошивка отметит калибровку
как ошибочную (флаг 0x0200). Контрольные суммы строк S-record/HEX тоже
пересчитываются.

Структура восстановлена по дизассемблированию (функция копирования/проверки
0x81FC). Записи:
    0x1000 — 8 слов данных + КС(0x1010)
    0x1014 — 8 слов данных + КС(0x1024)
    0x1028 — 8 слов данных + КС(0x1038)
    0x103C — 5 слов данных + КС(0x1046)
    0x104A — 5 слов данных + КС(0x1054)
    0x1058 — 6 слов данных + КС(0x1064)
Физический смысл отдельных слов требует дальнейшего разбора; здесь они
подписаны адресом. Правки применяются корректно (с пересчётом КС).

Запуск:
    python3 dumpedit2.py            (или  python dumpedit2.py  в Windows)
    python3 dumpedit2.py ne2r.s19   (сразу открыть файл)

Интерфейс на tkinter (входит в стандартную библиотеку Python).
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from dumpfile import DumpFile

__version__ = '2.0'

# Палитра.
BG = '#eef1f5'; CARD = '#ffffff'; INK = '#1f2933'; MUTED = '#5b6673'
ACCENT = '#0a58ca'; OK = '#198754'; WARN = '#c07000'; DANGER = '#dc3545'
HEADER = '#0d3b66'

CKSUM_INIT = 0xF0F0

# Калибровочные записи: (адрес, число слов данных). КС хранится после данных.
RECORDS = [
    (0x1000, 8),
    (0x1014, 8),
    (0x1028, 8),
    (0x103C, 5),
    (0x104A, 5),
    (0x1058, 6),
]


def record_checksum(words):
    """КС записи: 0xF0F0 XOR всех слов данных."""
    x = CKSUM_INIT
    for w in words:
        x ^= w & 0xFFFF
    return x & 0xFFFF


class WordRow(object):
    """Одно 16-битное слово записи: ползунок + DEC + HEX."""

    def __init__(self, app, parent, r, addr, idx):
        self.app = app
        self.addr = addr
        self.original = None
        self._sync = False

        ttk.Label(parent, text='слово %d  (0x%04X):' % (idx, addr),
                  width=18).grid(row=r, column=0, sticky='w', pady=2)
        self.scale = ttk.Scale(parent, from_=0, to=65535, orient='horizontal',
                               command=self._on_scale)
        self.scale.grid(row=r, column=1, sticky='ew', padx=6)
        parent.columnconfigure(1, weight=1)

        self.dec = ttk.Entry(parent, width=7)
        self.dec.grid(row=r, column=2, padx=2)
        self.dec.bind('<KeyRelease>', self._on_dec)
        ttk.Label(parent, text='HEX').grid(row=r, column=3)
        self.hexv = ttk.Entry(parent, width=6)
        self.hexv.grid(row=r, column=4, padx=2)
        self.hexv.bind('<KeyRelease>', self._on_hex)
        ttk.Button(parent, text='Сброс', width=7,
                   command=self.reset).grid(row=r, column=5, padx=2)

    def load(self, value):
        self.original = value
        self._set(value)

    def _set(self, value):
        value = max(0, min(65535, int(value)))
        self._sync = True
        self.scale.set(value)
        self.dec.delete(0, 'end'); self.dec.insert(0, str(value))
        self.hexv.delete(0, 'end'); self.hexv.insert(0, '%04X' % value)
        self._sync = False
        self.app.on_change()

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


class RecordFrame(object):
    """Секция одной записи: слова + статус контрольной суммы."""

    def __init__(self, app, parent, r, base, n):
        self.base = base
        self.n = n
        self.cksum_addr = base + 2 * n
        box = ttk.LabelFrame(
            parent, padding=8,
            text='Запись 0x%04X  (%d слов, КС в 0x%04X)' % (base, n, self.cksum_addr))
        box.grid(row=r, column=0, sticky='ew', pady=5)
        box.columnconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)

        grid = ttk.Frame(box)
        grid.grid(row=0, column=0, sticky='ew')
        grid.columnconfigure(0, weight=1)
        self.rows = [WordRow(app, grid, i, base + 2 * i, i) for i in range(n)]

        self.status = tk.StringVar()
        self.status_lbl = ttk.Label(box, textvariable=self.status,
                                    font=('TkDefaultFont', 10, 'bold'))
        self.status_lbl.grid(row=1, column=0, sticky='w', pady=(6, 0))

    def load(self, dump):
        for i, row in enumerate(self.rows):
            row.load(dump.get_word(self.base + 2 * i))
        self.update_status(dump.get_word(self.cksum_addr))

    def values(self):
        return [row.value() for row in self.rows]

    def update_status(self, stored=None):
        calc = record_checksum(self.values())
        if stored is None:
            self.status.set('КС будет записана: 0x%04X (пересчитывается '
                            'автоматически)' % calc)
            self.status_lbl.configure(foreground=ACCENT)
        elif calc == stored:
            self.status.set('КС 0x%04X — совпадает' % calc)
            self.status_lbl.configure(foreground=OK)
        else:
            self.status.set('КС в файле 0x%04X, будет исправлена на 0x%04X'
                            % (stored, calc))
            self.status_lbl.configure(foreground=WARN)


class App(ttk.Frame):
    def __init__(self, master):
        self.master = master
        self._setup_style()
        super().__init__(master, padding=14, style='App.TFrame')
        self.grid(sticky='nsew')
        master.title('Редактор калибровочных записей (ne2r)  v%s' % __version__)
        master.configure(background=BG)
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.dump = None
        self.path = None
        self.records = []

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
        style.configure('TFrame', background=CARD)
        style.configure('TLabel', background=CARD, foreground=INK)
        style.configure('TLabelframe', background=CARD, borderwidth=1,
                        relief='solid')
        style.configure('TLabelframe.Label', background=CARD, foreground=ACCENT,
                        font=('TkDefaultFont', 10, 'bold'))
        style.configure('TButton', padding=5)
        style.configure('Accent.TButton', foreground='#ffffff',
                        background=ACCENT, padding=8,
                        font=('TkDefaultFont', 10, 'bold'))
        style.map('Accent.TButton',
                  background=[('active', '#084298'), ('disabled', '#9db8e0')])

    def _build_header(self):
        head = tk.Frame(self, background=HEADER)
        head.grid(row=0, column=0, sticky='ew', pady=(0, 12))
        head.columnconfigure(0, weight=1)
        tk.Label(head, text='Редактор калибровочных записей',
                 bg=HEADER, fg='#ffffff',
                 font=('TkDefaultFont', 15, 'bold')).grid(
            row=0, column=0, sticky='w', padx=14, pady=(10, 0))
        tk.Label(head, text='прошивка ne2r · записи INFO Flash с контрольной '
                            'суммой XOR (пересчитывается автоматически)',
                 bg=HEADER, fg='#bcd3ea', font=('TkDefaultFont', 9)).grid(
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
        outer = ttk.Frame(self, style='App.TFrame')
        outer.grid(row=2, column=0, sticky='nsew')
        self.rowconfigure(2, weight=1)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)

        canvas = tk.Canvas(outer, background=BG, highlightthickness=0)
        canvas.grid(row=0, column=0, sticky='nsew')
        vsb = ttk.Scrollbar(outer, orient='vertical', command=canvas.yview)
        vsb.grid(row=0, column=1, sticky='ns')
        canvas.configure(yscrollcommand=vsb.set)

        inner = ttk.Frame(canvas, style='App.TFrame')
        win = canvas.create_window((0, 0), window=inner, anchor='nw')
        inner.columnconfigure(0, weight=1)
        canvas.bind('<Configure>',
                    lambda e: canvas.itemconfigure(win, width=e.width))
        inner.bind('<Configure>',
                   lambda e: canvas.configure(scrollregion=canvas.bbox('all')))

        def _wheel(e):
            canvas.yview_scroll(1 if (e.num == 5 or e.delta < 0) else -1, 'units')
        canvas.bind_all('<MouseWheel>', _wheel)
        canvas.bind_all('<Button-4>', _wheel)
        canvas.bind_all('<Button-5>', _wheel)

        for i, (base, n) in enumerate(RECORDS):
            self.records.append(RecordFrame(self, inner, i, base, n))

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
        if self.dump.get_word(0x1000) is None:
            messagebox.showwarning('Нет данных',
                                   'В дампе нет области 0x1000 — файл не тот?')
            return
        self.path = path
        self.file_var.set('%s  [%s]' % (os.path.basename(path),
                                        self.dump.fmt.upper()))
        for rec in self.records:
            rec.load(self.dump)
        self.save_btn.configure(state='normal')
        self.status.set('Дамп загружен. Меняйте значения — КС записей '
                        'пересчитываются при сохранении.')

    def on_change(self):
        # обновлять статус КС «на лету» (без учёта записанного значения)
        for rec in self.records:
            rec.update_status(None)
        if self.path:
            self.status.set('Есть несохранённые изменения.')

    def save_file(self):
        if not self.dump:
            return
        # применить слова и пересчитать КС каждой записи
        changed = []
        for rec in self.records:
            vals = rec.values()
            for i, v in enumerate(vals):
                self.dump.set_word(rec.base + 2 * i, v)
                if rec.rows[i].original != v:
                    changed.append('  0x%04X: 0x%04X -> 0x%04X' %
                                   (rec.base + 2 * i, rec.rows[i].original, v))
            cs = record_checksum(vals)
            self.dump.set_word(rec.cksum_addr, cs)   # автопересчёт КС

        base, ext = os.path.splitext(self.path)
        out = filedialog.asksaveasfilename(
            title='Сохранить изменённый дамп',
            initialdir=os.path.dirname(self.path),
            initialfile=os.path.basename(base) + '_edited' + ext,
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
            'Контрольные суммы всех записей пересчитаны автоматически.\n\n'
            'Изменения:\n%s' % (out, bak, summary))


def main():
    root = tk.Tk()
    try:
        root.tk.call('tk', 'scaling', 1.2)
    except Exception:
        pass
    app = App(root)
    root.minsize(720, 720)
    root.update_idletasks()
    w, h = 760, 800
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 2
    root.geometry('%dx%d+%d+%d' % (w, h, max(x, 0), max(y, 0)))
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        app.open_file(sys.argv[1])
    root.mainloop()


if __name__ == '__main__':
    main()
