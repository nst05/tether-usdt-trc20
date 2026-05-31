import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import re, os

# ── Парсер SQL дампа ──────────────────────────────────────────────
def parse_sql(text):
    tables = {}
    # Найти все INSERT INTO
    pattern = re.compile(
        r"INSERT INTO\s+[`']?(\w+)[`']?\s+(?:\([^)]+\)\s+)?VALUES\s*(.+?)(?:;|$)",
        re.IGNORECASE | re.DOTALL
    )
    col_pattern = re.compile(
        r"CREATE TABLE\s+[`']?(\w+)[`']?\s*\((.+?)\);",
        re.IGNORECASE | re.DOTALL
    )

    # Колонки из CREATE TABLE
    col_map = {}
    for m in col_pattern.finditer(text):
        tname = m.group(1)
        body  = m.group(2)
        cols  = []
        for line in body.splitlines():
            line = line.strip().rstrip(",")
            if not line or line.upper().startswith(("PRIMARY","KEY","UNIQUE","INDEX","CONSTRAINT")):
                continue
            col = re.match(r"[`']?(\w+)[`']?", line)
            if col:
                cols.append(col.group(1))
        col_map[tname] = cols

    # Данные из INSERT INTO
    for m in pattern.finditer(text):
        tname = m.group(1)
        vals_str = m.group(2)
        rows = re.findall(r"\(([^)]+)\)", vals_str)
        if tname not in tables:
            tables[tname] = {"cols": col_map.get(tname, []), "rows": []}
        for row in rows:
            # Разбить значения учитывая строки в кавычках
            values = []
            current = ""
            in_str = False
            quote_char = None
            for ch in row:
                if in_str:
                    current += ch
                    if ch == quote_char:
                        in_str = False
                elif ch in ("'", '"'):
                    in_str = True
                    quote_char = ch
                    current += ch
                elif ch == "," :
                    values.append(current.strip().strip("'\""))
                    current = ""
                else:
                    current += ch
            if current.strip():
                values.append(current.strip().strip("'\""))
            tables[tname]["rows"].append(values)

    return tables


# ── GUI ───────────────────────────────────────────────────────────
class SQLViewer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SQL Viewer — Просмотр дампа базы данных")
        self.geometry("1200x700")
        self.configure(bg="#f0f2f5")
        self.tables = {}
        self.current_table = None
        self.all_rows = []
        self._build_ui()

    def _build_ui(self):
        # ── Верхняя панель ────────────────────────────────────────
        top = tk.Frame(self, bg="#1e3a6e", pady=8)
        top.pack(fill="x")
        tk.Label(top, text="  SQL VIEWER — Просмотр дампа БД",
                 bg="#1e3a6e", fg="white",
                 font=("Arial", 14, "bold")).pack(side="left")

        btn_frame = tk.Frame(top, bg="#1e3a6e")
        btn_frame.pack(side="right", padx=10)
        tk.Button(btn_frame, text="📂  Открыть файл", command=self._open_file,
                  bg="#2ecc71", fg="white", font=("Arial", 10, "bold"),
                  relief="flat", padx=12, pady=4).pack(side="left", padx=4)
        tk.Button(btn_frame, text="💾  Экспорт CSV", command=self._export_csv,
                  bg="#3498db", fg="white", font=("Arial", 10, "bold"),
                  relief="flat", padx=12, pady=4).pack(side="left", padx=4)

        # ── Поиск ─────────────────────────────────────────────────
        search_frame = tk.Frame(self, bg="#dde3ed", pady=6)
        search_frame.pack(fill="x")
        tk.Label(search_frame, text="  🔍 Поиск:", bg="#dde3ed",
                 font=("Arial", 10)).pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace("w", lambda *_: self._apply_filter())
        tk.Entry(search_frame, textvariable=self.search_var,
                 font=("Consolas", 10), width=40).pack(side="left", padx=6)

        # Фильтр по ключевым словам
        for kw in ["password", "email", "admin", "token", "secret"]:
            tk.Button(search_frame, text=kw,
                      command=lambda k=kw: self._quick_search(k),
                      bg="#e74c3c", fg="white", font=("Arial", 9),
                      relief="flat", padx=8).pack(side="left", padx=2)

        self.count_lbl = tk.Label(search_frame, text="", bg="#dde3ed",
                                   font=("Arial", 9), fg="#555")
        self.count_lbl.pack(side="right", padx=10)

        # ── Основная область ──────────────────────────────────────
        main = tk.Frame(self, bg="#f0f2f5")
        main.pack(fill="both", expand=True)

        # Список таблиц слева
        left = tk.Frame(main, bg="#2c3e50", width=200)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)

        tk.Label(left, text="ТАБЛИЦЫ", bg="#2c3e50", fg="#95a5a6",
                 font=("Arial", 9, "bold"), pady=8).pack(fill="x")

        self.table_list = tk.Listbox(left, bg="#2c3e50", fg="white",
                                      selectbackground="#3498db",
                                      font=("Consolas", 10),
                                      relief="flat", bd=0,
                                      activestyle="none")
        self.table_list.pack(fill="both", expand=True, padx=4)
        self.table_list.bind("<<ListboxSelect>>", self._on_table_select)

        self.row_count_lbl = tk.Label(left, text="", bg="#2c3e50", fg="#95a5a6",
                                       font=("Arial", 8), pady=4)
        self.row_count_lbl.pack()

        # Treeview справа
        right = tk.Frame(main, bg="#f0f2f5")
        right.pack(side="left", fill="both", expand=True)

        # Стиль таблицы
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("S.Treeview",
                         background="white",
                         foreground="#1a1a1a",
                         rowheight=24,
                         fieldbackground="white",
                         font=("Consolas", 9))
        style.configure("S.Treeview.Heading",
                         background="#1e3a6e",
                         foreground="white",
                         font=("Arial", 9, "bold"))
        style.map("S.Treeview",
                   background=[("selected", "#d0e8ff")],
                   foreground=[("selected", "#000")])

        self.tree = ttk.Treeview(right, style="S.Treeview",
                                  show="headings", selectmode="browse")
        vsb = ttk.Scrollbar(right, orient="vertical",   command=self.tree.yview)
        hsb = ttk.Scrollbar(right, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscroll=vsb.set, xscroll=hsb.set)

        vsb.pack(side="right",  fill="y")
        hsb.pack(side="bottom", fill="x")
        self.tree.pack(fill="both", expand=True)

        # Строка детали внизу
        self.detail = tk.Text(self, height=4,
                               font=("Consolas", 9),
                               bg="#1a1a2e", fg="#00e676",
                               relief="flat", wrap="word")
        self.detail.pack(fill="x", padx=0, pady=0)
        self.detail.insert("1.0", "  Выбери строку для просмотра деталей...")
        self.detail.configure(state="disabled")

        self.tree.bind("<<TreeviewSelect>>", self._on_row_select)
        self.tree.bind("<Button-3>", self._on_right_click)

        # Контекстное меню
        self.ctx = tk.Menu(self, tearoff=0)
        self.ctx.add_command(label="📋 Копировать ячейку", command=self._copy_cell)
        self.ctx.add_command(label="📋 Копировать всю строку", command=self._copy_row)
        self.ctx.add_separator()
        self.ctx.add_command(label="🔍 Найти похожие", command=self._find_similar)

        # Статус
        self.status = tk.Label(self, text="Открой SQL файл для начала работы",
                                bg="#1e3a6e", fg="white",
                                font=("Arial", 9), anchor="w", padx=10)
        self.status.pack(fill="x", side="bottom")

    # ── Открыть файл ──────────────────────────────────────────────
    def _open_file(self):
        path = filedialog.askopenfilename(
            title="Открыть SQL дамп",
            filetypes=[("SQL files", "*.sql"), ("All files", "*.*")]
        )
        if not path:
            return
        self.status.configure(text=f"Загрузка: {path}...")
        self.update()
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))
            return
        self.tables = parse_sql(text)
        self._populate_table_list()
        size_kb = os.path.getsize(path) // 1024
        self.status.configure(
            text=f"✓ Загружено: {os.path.basename(path)}  |  "
                 f"Размер: {size_kb} KB  |  Таблиц: {len(self.tables)}")

    def _populate_table_list(self):
        self.table_list.delete(0, "end")
        for name, data in self.tables.items():
            self.table_list.insert("end", f"  {name}  ({len(data['rows'])})")
        if self.tables:
            self.table_list.selection_set(0)
            self._load_table(list(self.tables.keys())[0])

    def _on_table_select(self, _):
        sel = self.table_list.curselection()
        if not sel:
            return
        name = list(self.tables.keys())[sel[0]]
        self._load_table(name)

    def _load_table(self, name):
        self.current_table = name
        data = self.tables[name]
        cols = data["cols"]
        rows = data["rows"]

        # Если колонки не определены — создать Col1, Col2...
        max_cols = max((len(r) for r in rows), default=0)
        if not cols or len(cols) < max_cols:
            cols = [f"Col{i+1}" for i in range(max_cols)]

        self.tree.delete(*self.tree.get_children())
        self.tree["columns"] = cols
        for c in cols:
            self.tree.heading(c, text=c,
                              command=lambda _c=c: self._sort_by(_c))
            self.tree.column(c, width=130, minwidth=60)

        self.all_rows = rows
        self._render_rows(rows)
        self.row_count_lbl.configure(
            text=f"{len(rows)} строк\n{len(cols)} столбцов")
        self.search_var.set("")

    def _render_rows(self, rows):
        self.tree.delete(*self.tree.get_children())
        # Подсветка строк с паролями/токенами
        sensitive_re = re.compile(
            r"(password|pass|token|secret|key|hash|admin|root)",
            re.I)
        for i, row in enumerate(rows):
            tag = "even" if i % 2 == 0 else "odd"
            row_str = " ".join(str(v) for v in row)
            if sensitive_re.search(row_str):
                tag = "sensitive"
            self.tree.insert("", "end", values=row, tags=(tag,))

        self.tree.tag_configure("even",      background="white")
        self.tree.tag_configure("odd",       background="#f7f9fc")
        self.tree.tag_configure("sensitive", background="#fff3cd",
                                             foreground="#7b4400")
        self.count_lbl.configure(text=f"Показано: {len(rows)} строк")

    def _apply_filter(self):
        kw = self.search_var.get().lower()
        if not kw:
            self._render_rows(self.all_rows)
            return
        filtered = [r for r in self.all_rows
                    if any(kw in str(v).lower() for v in r)]
        self._render_rows(filtered)

    def _quick_search(self, kw):
        self.search_var.set(kw)

    def _sort_by(self, col):
        cols = list(self.tree["columns"])
        if col not in cols:
            return
        idx = cols.index(col)
        self.all_rows.sort(key=lambda r: str(r[idx]) if idx < len(r) else "")
        self._render_rows(self.all_rows)

    def _on_row_select(self, _):
        sel = self.tree.focus()
        if not sel:
            return
        vals = self.tree.item(sel, "values")
        cols = self.tree["columns"]
        text = "\n".join(f"  {c}: {v}" for c, v in zip(cols, vals))
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", text)
        self.detail.configure(state="disabled")

    def _on_right_click(self, event):
        row = self.tree.identify_row(event.y)
        if row:
            self.tree.selection_set(row)
            self._ctx_row = self.tree.item(row, "values")
            col = self.tree.identify_column(event.x)
            col_idx = int(col.replace("#", "")) - 1
            self._ctx_cell = self._ctx_row[col_idx] if col_idx < len(self._ctx_row) else ""
            self.ctx.tk_popup(event.x_root, event.y_root)

    def _copy_cell(self):
        self.clipboard_clear()
        self.clipboard_append(getattr(self, "_ctx_cell", ""))

    def _copy_row(self):
        self.clipboard_clear()
        self.clipboard_append("\t".join(str(v) for v in getattr(self, "_ctx_row", [])))

    def _find_similar(self):
        cell = getattr(self, "_ctx_cell", "")
        if cell:
            self.search_var.set(cell[:20])

    def _export_csv(self):
        if not self.current_table:
            messagebox.showinfo("Инфо", "Сначала выбери таблицу")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile=f"{self.current_table}.csv",
            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        import csv
        cols = self.tree["columns"]
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for row in self.all_rows:
                w.writerow(row)
        messagebox.showinfo("Готово", f"Сохранено: {path}")
        self.status.configure(text=f"✓ Экспорт: {path}")


if __name__ == "__main__":
    app = SQLViewer()
    app.mainloop()
