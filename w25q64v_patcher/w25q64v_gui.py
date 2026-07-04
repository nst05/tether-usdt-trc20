#!/usr/bin/env python3
"""
W25Q64V patcher — GUI (tkinter, no external dependencies).

Open a flash dump, browse the decoded records, set the on-screen reading for
one / a range / all records, and save a patched .bin. The patch touches ONLY
the reading bytes; if anything else would change the save is aborted.

Run:  python3 w25q64v_gui.py
"""

import os
import struct
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import w25q64v_patcher as core


class App(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=8)
        self.grid(sticky="nsew")
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        self.path = None
        self.original = None      # working buffer (mutated by patches)
        self.loaded = None        # pristine bytes as loaded from disk
        self.bases = []
        self.dirty = False        # True once a patch has actually changed bytes

        self._build_toolbar()
        self._build_controls()
        self._build_table()
        self._build_status()

    # ---------------------------------------------------------------- UI parts
    def _build_toolbar(self):
        bar = ttk.Frame(self)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(bar, text="Открыть дамп…", command=self.open_file).pack(side="left")
        ttk.Button(bar, text="Сохранить как…", command=self.save_as).pack(side="left", padx=6)
        self.info_lbl = ttk.Label(bar, text="файл не загружен")
        self.info_lbl.pack(side="left", padx=12)

    def _build_controls(self):
        box = ttk.LabelFrame(self, text="Патч показания (reading)", padding=8)
        box.grid(row=1, column=0, sticky="ew", pady=(0, 6))

        ttk.Label(box, text="Новое значение:").grid(row=0, column=0, sticky="w")
        self.value_var = tk.StringVar(value="1.290275")
        ttk.Entry(box, textvariable=self.value_var, width=16).grid(row=0, column=1, padx=6)

        # default: change ONLY the value shown on screen (the newest record),
        # i.e. its two mirror copies at DATA+0x0C and +0x1C.
        self.scope = tk.StringVar(value="current")
        ttk.Radiobutton(box, text="Текущее показание (экран)", variable=self.scope,
                        value="current").grid(row=0, column=2, padx=(12, 4))
        ttk.Radiobutton(box, text="Выделенная запись", variable=self.scope,
                        value="sel").grid(row=0, column=3, padx=4)
        ttk.Radiobutton(box, text="Все записи (вся история!)", variable=self.scope,
                        value="all").grid(row=0, column=4, padx=(12, 4))

        ttk.Button(box, text="Применить →", command=self.apply_patch).grid(
            row=0, column=5, padx=12)

        # shows the two file offsets that will actually be written
        self.addr_lbl = ttk.Label(box, text="два адреса: —", foreground="#0a7")
        self.addr_lbl.grid(row=1, column=0, columnspan=6, sticky="w", pady=(6, 0))
        self.applied = False
        # keep the address label in sync with scope / selection
        self.scope.trace_add("write", self._update_addr_label)

    def _build_table(self):
        cols = ("idx", "time", "cnt", "reading", "temp1", "temp2")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", selectmode="browse")
        widths = dict(idx=60, time=160, cnt=70, reading=110, temp1=80, temp2=80)
        titles = dict(idx="#", time="время (UTC)", cnt="счётчик",
                      reading="показание", temp1="темп.1", temp2="темп.2")
        for c in cols:
            self.tree.heading(c, text=titles[c])
            self.tree.column(c, width=widths[c],
                             anchor="center" if c != "time" else "w")
        self.tree.grid(row=2, column=0, sticky="nsew")
        vs = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        vs.grid(row=2, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.bind("<<TreeviewSelect>>", self._update_addr_label)

    def _build_status(self):
        self.status = tk.StringVar(value="Откройте дамп .bin, считанный CH341.")
        ttk.Label(self, textvariable=self.status, relief="sunken",
                  anchor="w", padding=4).grid(row=3, column=0, columnspan=2,
                                              sticky="ew", pady=(6, 0))

    # ------------------------------------------------------------------ actions
    def open_file(self):
        path = filedialog.askopenfilename(
            title="Выберите дамп W25Q64V",
            filetypes=[("Дампы", "*.bin"), ("Все файлы", "*.*")])
        if not path:
            return
        try:
            with open(path, "rb") as f:
                data = f.read()
            bases = core.find_records(bytearray(data))
            if not bases:
                messagebox.showerror("Ошибка", "Записи не найдены в этом файле.")
                return
        except Exception as e:                       # noqa: BLE001
            messagebox.showerror("Ошибка", str(e))
            return
        self.path, self.original, self.bases = path, data, bases
        self.loaded = data
        self.dirty = False
        self.applied = False
        self._reload_table()
        # auto-select the record shown on screen (newest timestamp) and reveal it
        self._select_current()
        self._update_addr_label()
        self.status.set(f"Загружено: {os.path.basename(path)} — "
                        f"{len(bases)} записей. Выбрано текущее показание (экран).")

    def _newest_index(self):
        """Index of the record shown on screen = the newest timestamp."""
        newest = max(range(len(self.bases)),
                     key=lambda i: struct.unpack_from("<I", self.original,
                                                      self.bases[i])[0])
        return newest

    def _select_current(self):
        idx = self._newest_index()
        iid = str(idx)
        self.tree.selection_set(iid)
        self.tree.focus(iid)
        self.tree.see(iid)

    def _target_index(self):
        """The record index the current scope will patch (for the addr label)."""
        mode = self.scope.get()
        if mode == "current":
            return self._newest_index()
        sel = self.tree.selection()
        return int(sel[0]) if sel else self._newest_index()

    def _update_addr_label(self, *_):
        if self.original is None or not self.bases:
            return
        if self.scope.get() == "all":
            self.addr_lbl.config(
                text=f"ВСЕ {len(self.bases)} записей — перезапишет всю историю показаний!",
                foreground="#c33")
            return
        idx = self._target_index()
        base = self.bases[idx]
        rd = core.decode(self.original, base)
        self.addr_lbl.config(
            text=f"запись #{idx} ({rd['when']}, сейчас {rd['reading']:.6g}) → "
                 f"два адреса: {base + core.F_READING:#08x} и {base + core.F_READING2:#08x}",
            foreground="#0a7")

    def _reload_table(self):
        self.tree.delete(*self.tree.get_children())
        seen = {}
        for idx, base in enumerate(self.bases):
            r = core.decode(self.original, base)
            seen[round(r["reading"], 6)] = seen.get(round(r["reading"], 6), 0) + 1
            self.tree.insert("", "end", iid=str(idx), values=(
                idx, r["when"], r["counter"], f"{r['reading']:.6f}",
                f"{r['temp1']:.2f}", f"{r['temp2']:.2f}"))
        top = sorted(seen.items(), key=lambda kv: -kv[1])[:5]
        self.info_lbl.config(
            text=f"{len(self.bases)} записей  |  показания: " +
                 ", ".join(f"{v}×{c}" for v, c in top))

    def _current_spec(self):
        mode = self.scope.get()
        if mode == "all":
            return "all"
        if mode == "current":
            return str(self._newest_index())
        sel = self.tree.selection()
        if not sel:
            raise ValueError("Не выбрана запись в таблице.")
        return sel[0]

    def apply_patch(self):
        if self.original is None:
            messagebox.showwarning("Нет файла", "Сначала откройте дамп.")
            return
        if self.scope.get() == "all":
            if not messagebox.askyesno(
                    "Внимание",
                    f"Будут перезаписаны показания во ВСЕХ {len(self.bases)} записях "
                    f"(вся история). Обычно нужно менять только текущее показание.\n\n"
                    "Точно менять все записи?"):
                return
        target_idx = self._target_index() if self.scope.get() != "all" else None
        old_val = (core.decode(self.original, self.bases[target_idx])["reading"]
                   if target_idx is not None else None)
        try:
            value = float(self.value_var.get().replace(",", "."))
            spec = self._current_spec()
            res = core.apply_field(self.original, "reading", value, spec)
        except (ValueError, core.PatchError) as e:
            messagebox.showerror("Патч отменён", str(e))
            return

        if res["ndiff"] == 0:
            messagebox.showinfo(
                "Без изменений",
                f"Показание уже равно {value} — менять нечего, ничего не изменено.")
            return

        # accept the patched buffer as the new working image
        self.original = bytes(res["buf"])
        self.dirty = True
        self._reload_table()
        self._select_current()
        self._update_addr_label()
        self.applied = True
        verify = "OK" if res["verify_ok"] else "ОШИБКА"
        self.status.set(
            f"✔ Показание → {value} в {res['changed']} зап.  |  "
            f"изменено {res['ndiff']} байт (только +0x0C/+0x1C)  |  "
            f"verify: {verify}  |  теперь нажмите «Сохранить как…»")
        if target_idx is not None:
            base = self.bases[target_idx]
            messagebox.showinfo(
                "Применено",
                f"Запись #{target_idx}:  {old_val:.6g} → {value}\n"
                f"адреса: {base + core.F_READING:#08x} и {base + core.F_READING2:#08x}\n\n"
                "Изменения пока только в памяти — нажмите «Сохранить как…», "
                "чтобы записать в файл.")

    def save_as(self):
        if self.original is None:
            messagebox.showwarning("Нет данных", "Нечего сохранять.")
            return
        if not self.dirty:
            if not messagebox.askyesno(
                    "Изменений нет",
                    "Вы ещё не применили ни одного изменения (кнопка «Применить →»), "
                    "или значение совпало с текущим.\n\n"
                    "Файл будет ИДЕНТИЧЕН исходному. Всё равно сохранить?"):
                return
        default = "patched.bin"
        if self.path:
            root, ext = os.path.splitext(os.path.basename(self.path))
            default = f"{root}_patched{ext or '.bin'}"
        out = filedialog.asksaveasfilename(
            title="Сохранить патченый дамп", defaultextension=".bin",
            initialfile=default, filetypes=[("Дампы", "*.bin"), ("Все файлы", "*.*")])
        if not out:
            return
        try:
            with open(out, "wb") as f:
                f.write(self.original)
        except Exception as e:                       # noqa: BLE001
            messagebox.showerror("Ошибка", str(e))
            return
        # confirm on disk: how many bytes really differ from the loaded file
        ndiff = sum(1 for i in range(len(self.original)) if self.original[i] != self.loaded[i])
        self.dirty = False
        self.status.set(f"Сохранено: {out} — отличий от исходного: {ndiff} байт.")
        messagebox.showinfo(
            "Готово",
            f"Записан файл:\n{out}\n\n"
            f"Отличий от исходного дампа: {ndiff} байт "
            f"({'изменения на месте' if ndiff else 'ВНИМАНИЕ: файл идентичен исходному!'}).\n\n"
            "Залейте его обратно в W25Q64V программатором CH341.")


def main():
    root = tk.Tk()
    root.title("W25Q64V Reading Patcher")
    root.geometry("760x520")
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
