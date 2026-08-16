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


# Редактируемые 16-битные коэффициенты: (адрес, короткое имя, пояснение, интерпретация)
FIELDS = [
    (0x1000, 'ADAPTI1 (0x1000)',
     'Аппаратный коэффициент усиления ESP430 (формат +1.14).',
     lambda v: '= %.4f (v/16384)' % (v / 16384.0)),
    (0x1002, 'Масштаб напряжения (0x1002)',
     'Множитель канала напряжения: показание U ≈ сырое × коэф.',
     None),
    (0x1004, 'Масштаб тока (0x1004)',
     'Множитель канала тока: показание I ≈ сырое × коэф. '
     'Влияет и на энергию (U×I).',
     None),
]


class Row(object):
    """Один редактируемый коэффициент: подпись, ползунок, поля, множитель."""

    def __init__(self, app, parent, r, addr, name, help_text, interp):
        self.app = app
        self.addr = addr
        self.interp = interp
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
        self.effect_lbl = tk.Label(box, textvariable=self.effect,
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
        """Скорость учёта энергии линейно зависит от коэффициента."""
        if not self.original:
            self.effect.set('')
            return
        pct = (mult - 1) * 100
        if abs(pct) < 0.05:
            self.effect.set('Учёт энергии: без изменений')
            self.effect_lbl.configure(fg='#198754')
        elif pct > 0:
            self.effect.set('Учёт энергии БЫСТРЕЕ на %.1f%%  '
                            '(счётчик спешит, завышает)' % pct)
            self.effect_lbl.configure(fg='#dc3545')
        else:
            self.effect.set('Учёт энергии МЕДЛЕННЕЕ на %.1f%%  '
                            '(счётчик отстаёт, занижает)' % -pct)
            self.effect_lbl.configure(fg='#0a58ca')

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
        super().__init__(master, padding=12)
        self.grid(sticky='nsew')
        master.title('Редактор коэффициентов дампа MSP430FE427')
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.dump = None
        self.path = None
        self.rows = []

        self._build_file()
        self._build_fields()
        self._build_footer()

    def _build_file(self):
        box = ttk.Frame(self)
        box.grid(row=0, column=0, sticky='ew', pady=(0, 8))
        box.columnconfigure(1, weight=1)
        ttk.Button(box, text='Открыть дамп…',
                   command=self.open_file).grid(row=0, column=0)
        self.file_var = tk.StringVar(value='файл не выбран')
        ttk.Label(box, textvariable=self.file_var, foreground='#555').grid(
            row=0, column=1, sticky='w', padx=8)

    def _build_fields(self):
        self.fields_box = ttk.Frame(self)
        self.fields_box.grid(row=1, column=0, sticky='nsew')
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)
        for i, (addr, name, help_text, interp) in enumerate(FIELDS):
            self.rows.append(Row(self, self.fields_box, i, addr, name,
                                 help_text, interp))

        info = ttk.LabelFrame(self.fields_box, text='Только для справки (не меняется)',
                              padding=8)
        info.grid(row=len(FIELDS), column=0, sticky='ew', pady=5)
        self.ref_var = tk.StringVar(value='—')
        ttk.Label(info, textvariable=self.ref_var,
                  font=('monospace', 10)).grid(sticky='w')

    def _build_footer(self):
        box = ttk.Frame(self)
        box.grid(row=2, column=0, sticky='ew', pady=(8, 0))
        box.columnconfigure(0, weight=1)
        self.status = tk.StringVar(value='Откройте дамп прибора (.s19 или .hex).')
        ttk.Label(box, textvariable=self.status, foreground='#c07000').grid(
            row=0, column=0, sticky='w')
        self.save_btn = ttk.Button(box, text='Сохранить как…',
                                   command=self.save_file, state='disabled')
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
        flags = self.dump.get_word(0x1006)
        self.ref_var.set('ID прибора (0x1008): %s      флаги (0x1006): 0x%04X' %
                         (' '.join('%02X' % b for b in idb), flags or 0))
        self.save_btn.configure(state='normal')
        self.status.set('Дамп загружен. Меняйте коэффициенты ползунками.')

    def mark_dirty(self):
        if self.path:
            self.status.set('Есть несохранённые изменения.')

    def save_file(self):
        if not self.dump:
            return
        # применяем значения ползунков в дамп
        for row in self.rows:
            self.dump.set_word(row.addr, row.value())

        base, ext = os.path.splitext(self.path)
        default = base + '_edited' + ext
        out = filedialog.asksaveasfilename(
            title='Сохранить изменённый дамп',
            initialfile=os.path.basename(default),
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
    root.minsize(660, 620)
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        app.open_file(sys.argv[1])
    root.mainloop()


if __name__ == '__main__':
    main()
