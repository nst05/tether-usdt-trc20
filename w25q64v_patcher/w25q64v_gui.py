#!/usr/bin/env python3
"""
W25Q64V patcher — GUI (tkinter, no external dependencies).

Open a flash dump, browse the decoded records, set the on-screen reading for
one / a range / all records, and save a patched .bin. The patch touches ONLY
the reading bytes; if anything else would change the save is aborted.

Run:  python3 w25q64v_gui.py
"""

import os
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
        self.original = None      # pristine bytes
        self.bases = []

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

        self.scope = tk.StringVar(value="all")
        ttk.Radiobutton(box, text="Все записи", variable=self.scope,
                        value="all").grid(row=0, column=2, padx=(12, 4))
        ttk.Radiobutton(box, text="Выделенная", variable=self.scope,
                        value="sel").grid(row=0, column=3, padx=4)
        ttk.Radiobutton(box, text="Диапазон:", variable=self.scope,
                        value="range").grid(row=0, column=4, padx=(12, 2))
        self.range_var = tk.StringVar(value="0-10")
        ttk.Entry(box, textvariable=self.range_var, width=12).grid(row=0, column=5)

        ttk.Button(box, text="Применить →", command=self.apply_patch).grid(
            row=0, column=6, padx=12)
        self.applied = False

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
        self.applied = False
        self._reload_table()
        self.status.set(f"Загружено: {os.path.basename(path)} — "
                        f"{len(bases)} записей.")

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
        if mode == "range":
            return self.range_var.get().strip()
        sel = self.tree.selection()
        if not sel:
            raise ValueError("Не выбрана запись в таблице.")
        return sel[0]

    def apply_patch(self):
        if self.original is None:
            messagebox.showwarning("Нет файла", "Сначала откройте дамп.")
            return
        try:
            value = float(self.value_var.get().replace(",", "."))
            spec = self._current_spec()
            res = core.apply_field(self.original, "reading", value, spec)
        except (ValueError, core.PatchError) as e:
            messagebox.showerror("Патч отменён", str(e))
            return
        # accept the patched buffer as the new working image
        self.original = bytes(res["buf"])
        self._reload_table()
        self.applied = True
        verify = "OK" if res["verify_ok"] else "ОШИБКА"
        self.status.set(
            f"Показание = {value} в {res['changed']} зап.  |  "
            f"изменено {res['ndiff']} байт (только показание, прочее не тронуто)  |  "
            f"verify: {verify}  |  не забудьте «Сохранить как…»")

    def save_as(self):
        if self.original is None:
            messagebox.showwarning("Нет данных", "Нечего сохранять.")
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
        self.status.set(f"Сохранено: {out} ({len(self.original)} байт).")
        messagebox.showinfo("Готово", f"Записан файл:\n{out}\n\n"
                            "Залейте его обратно в W25Q64V программатором CH341.")


def main():
    root = tk.Tk()
    root.title("W25Q64V Reading Patcher")
    root.geometry("760x520")
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
