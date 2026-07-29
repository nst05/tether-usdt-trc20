#!/usr/bin/env python3
"""Графический интерфейс контроллера SMT v4.19.0.

Визуальный модуль содержит только построение Tk-интерфейса и обработку событий.
Транспорт и фоновые операции вынесены в ``smt_backend``/``smt_core``.
"""
from __future__ import annotations

import contextlib
import csv
import datetime
import json
import os
import queue
import struct
import sys

from smt_backend import Backend
from smt_diagnostics import DiagnosticRecorder, InstrumentedQueue, rotate_diagnostics
from smt_gui_support import (  # noqa: F401
    AUTH_CREDS, HERE, LEVELS, READING_COMMANDS, STATUS_BITS, STATUS_COLORS,
    STATUS_NAMES, TELEMETRY_DB_PATH, TeleServer,
    CommandHistory,
    access_at_level, access_human, build_actions, build_critical,
    build_telemetry_packet, classify_secret, classify_send, clean_desc,
    decode_status_bits, directions, evlog_mod, hexdump, load_catalog,
    load_settings, parse_reading, pretty, reading_text, save_settings, sc, srv, state_mod,
    suggested_port, tele_send, tele_store_mod, tools_mod, value_options,
)
from smt_logging import configure_logging

# Команды, чей каталог заявляет простой тип (enum/цел/f), но чей обработчик в
# прошивке реально читает/пишет СОСТАВНОЕ значение из нескольких чисел
# (найдено smt_catalog_audit.py, подтверждено разбором дизассемблера).
# Запись всегда идёт через ';' (число полей проверяется прошивкой строго —
# отправка одного числа для этих команд не пройдёт). Чтение отдаёт через ','
# либо ';' в зависимости от обработчика — парсер ниже пробует оба варианта.
# Там, где обработчик не даёт стопроцентной уверенности в смысле поля,
# подпись честно помечена как предположительная — читайте текущее значение
# и сверяйте с реальным расписанием/порогами на приборе.
COMPOUND_FIELDS: dict[str, list[str]] = {
    "MODE_TRANSFER": [
        "Режим передачи (0 = по расписанию, 1 = по событию)",
        "День передачи №1 (число месяца)",
        "День передачи №2 (число месяца)",
        "День передачи №3 (число месяца)",
        "Час передачи (0–23)",
    ],
    "ArcNumRecords": [
        "Дубль расписания — значение 1 (см. MODE_TRANSFER)",
        "Дубль расписания — значение 2",
        "Дубль расписания — значение 3",
        "Дубль расписания — значение 4",
    ],
    "SELF_BORDER": [
        "Порог датчика №1 (доля от 0.0 до 1.0)",
        "Порог датчика №2 (доля от 0.0 до 1.0)",
        "Порог датчика №3 (доля от 0.0 до 1.0)",
    ],
    "EXT_MAX_TEMP": [
        "Верхняя граница (наибольшее число)",
        "Средняя граница (меньше верхней)",
        "Нижняя граница (меньше средней)",
    ],
    "REV_FL_OFF_PER_S": [
        "Верхний порог времени, сек",
        "Нижний порог времени, сек",
        "Третье значение (меньше верхнего)",
    ],
    "N_GasLMesTime": [
        "Номер измерения",
        "Флаг состояния",
        "Показание №1",
        "Показание №2",
        "Показание №3",
    ],
    "KALMAN_BORDER_L": [
        "Граница фильтра — канал 1", "Граница фильтра — канал 2",
        "Граница фильтра — канал 3", "Граница фильтра — канал 4",
        "Граница фильтра — канал 5", "Граница фильтра — канал 6",
    ],
}

# Команды, где точный смысл каждого поля не подтверждён живым тестом на
# приборе (порядок и границы значений — да, конкретное назначение — нет).
# Показываем предупреждение прямо в GUI, а не прячем неопределённость в код.
COMPOUND_FIELDS_UNCERTAIN = {
    "ArcNumRecords", "EXT_MAX_TEMP", "REV_FL_OFF_PER_S", "N_GasLMesTime",
}


def _split_compound(text: str) -> list[str]:
    """Разбирает ответ прибора на составные поля: пробует ';', затем ','."""
    text = (text or "").strip()
    if text.startswith("="):
        text = text[1:]
    sep = ";" if ";" in text else ","
    return [p.strip() for p in text.split(sep) if p.strip() != ""]


def build_app(root, selftest=False):
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext, ttk

    catalog = load_catalog()
    critical = build_critical(catalog)
    actions = build_actions(catalog)
    out_q = queue.Queue()
    diag_folder = os.path.join(HERE, "diagnostics")
    rotate_diagnostics(diag_folder, max_files=50, max_total_mb=200.0)
    diagnostic = DiagnosticRecorder(
        diag_folder, application="gui", version="4.19.0",
        live_sink=lambda event: out_q.put(("diag_event", event)),
    )
    task_q = InstrumentedQueue(queue.Queue(), diagnostic, component="gui")
    backend = Backend(task_q, out_q, critical, actions, catalog, diagnostic=diagnostic); backend.start()

    root.title("Контроллер устройства 4.19.0 · 160 команд · AUTH-MODEL/KFACTOR/телеметрия")
    # Окно не должно вылезать за экран (иначе лог внизу обрезается) — размер
    # считается от фактического разрешения, а не берётся фиксированным.
    _sw, _sh = root.winfo_screenwidth(), root.winfo_screenheight()
    _win_w, _win_h = min(1220, _sw - 40), min(850, _sh - 80)
    root.geometry(f"{_win_w}x{_win_h}+{max(0, (_sw - _win_w) // 2)}+{max(0, (_sh - _win_h) // 2)}")
    root.minsize(min(900, _win_w), min(560, _win_h))

    state = {"selected": None, "connected": False, "expert": False,
             "mode": "off", "current_snapshot": {}, "loaded_snapshot": {},
             "monitoring": False, "monitor_rows": [],
             "provider_verified": False, "provider_verified_at": 0.0,
             "diagnostic": diagnostic, "diagnostic_events": [],
             "diagnostic_file": diagnostic.jsonl_path}
    settings = load_settings()
    cmd_history = CommandHistory()

    # ── шапка: реальные транспорты ─────────────────────────────────────
    top = ttk.Frame(root, padding=6); top.pack(fill="x")
    ttk.Label(top, text="Транспорт:").pack(side="left")
    transport_var = tk.StringVar(value=settings.get("transport", "Оптопорт / Serial"))
    transport_cb = ttk.Combobox(top, textvariable=transport_var, state="readonly", width=18,
                                values=["Оптопорт / Serial", "TCP-шлюз", "GSM / SMS"])
    transport_cb.pack(side="left", padx=(3, 8))
    conn_btn = ttk.Button(top, text="Подключить"); conn_btn.pack(side="left")
    status_lbl = ttk.Label(top, text="● отключено", foreground="#b00"); status_lbl.pack(side="left", padx=10)

    def list_ports():
        try:
            from serial.tools import list_ports
            ports = list(list_ports.comports())
            if not ports:
                messagebox.showinfo("Порты", "Serial-порты не найдены.\nПодключи USB-оптоголовку или GSM-модем.")
                return
            lines = []
            for item in ports:
                details = item.description or "serial"
                if item.vid is not None and item.pid is not None:
                    details += f" · VID:PID={item.vid:04X}:{item.pid:04X}"
                lines.append(f"{item.device} — {details}")
            candidates = [item.device for item in ports if any(
                hint in ((item.device or "") + " " + (item.description or "")).lower()
                for hint in ("ttyusb", "ttyacm", "usbserial", "usbmodem", "ch340", "cp210", "ftdi", "com")
            )]
            if len(candidates) == 1:
                port_var.set(candidates[0])
            messagebox.showinfo("Физические serial-порты", "\n".join(lines) +
                                (f"\n\nАвтовыбран: {candidates[0]}" if len(candidates) == 1 else ""))
        except Exception as e:
            messagebox.showerror("Порты", str(e))
    ttk.Button(top, text="Порты…", command=list_ports).pack(side="left")

    def do_dump():
        path = filedialog.askopenfilename(filetypes=[("dump W25Q64", "*.bin"), ("все", "*.*")])
        if path:
            hist_load_path(path); main_nb.select(tab_hist)
    ttk.Button(top, text="Открыть flash-дамп…", command=do_dump).pack(side="right")

    conn = ttk.LabelFrame(root, text="Параметры физического подключения", padding=(6, 3))
    conn.pack(fill="x", padx=6, pady=(0, 4))
    for col in range(14): conn.columnconfigure(col, weight=0)

    # Serial / оптопорт
    ttk.Label(conn, text="Serial:").grid(row=0, column=0, sticky="w")
    port_var = tk.StringVar(value=suggested_port(settings.get("port")))
    port_ent = ttk.Entry(conn, textvariable=port_var, width=15); port_ent.grid(row=0, column=1, padx=2)
    baud_var = tk.StringVar(value=str(settings.get("baud", "9600")))
    baud_cb = ttk.Combobox(conn, textvariable=baud_var, width=7, values=[
        "300", "600", "1200", "2400", "4800", "9600", "19200", "38400", "57600", "115200", "230400"
    ])
    baud_cb.grid(row=0, column=2, padx=2)
    fr_var = tk.StringVar(value=settings.get("framing", "auto"))
    fr_cb = ttk.Combobox(conn, textvariable=fr_var, width=7, state="readonly",
                         values=["auto"] + list(sc.FRAMINGS.keys())); fr_cb.grid(row=0, column=3, padx=2)
    bits_var = tk.StringVar(value=str(settings.get("bytesize", "8")))
    bits_cb = ttk.Combobox(conn, textvariable=bits_var, width=3, state="readonly", values=["5","6","7","8"]); bits_cb.grid(row=0,column=4,padx=2)
    parity_var = tk.StringVar(value=settings.get("parity", "N"))
    parity_cb = ttk.Combobox(conn, textvariable=parity_var, width=3, state="readonly", values=["N","E","O","M","S"]); parity_cb.grid(row=0,column=5,padx=2)
    stop_var = tk.StringVar(value=str(settings.get("stopbits", "1")))
    stop_cb = ttk.Combobox(conn, textvariable=stop_var, width=4, state="readonly", values=["1","1.5","2"]); stop_cb.grid(row=0,column=6,padx=2)
    ttk.Label(conn, text="таймаут:").grid(row=0,column=7,sticky="e")
    resp_timeout_var = tk.StringVar(value=str(settings.get("response_timeout", "2.5")))
    resp_timeout_ent = ttk.Entry(conn,textvariable=resp_timeout_var,width=5); resp_timeout_ent.grid(row=0,column=8,padx=2)
    ttk.Label(conn, text="пауза:").grid(row=0,column=9,sticky="e")
    idle_gap_var = tk.StringVar(value=str(settings.get("idle_gap", "0.25")))
    idle_gap_ent = ttk.Entry(conn,textvariable=idle_gap_var,width=5); idle_gap_ent.grid(row=0,column=10,padx=2)
    ttk.Label(conn, text="повторы READ:").grid(row=0,column=11,sticky="e")
    retries_var = tk.StringVar(value=str(settings.get("read_retries", "1")))
    retries_ent = ttk.Entry(conn,textvariable=retries_var,width=3); retries_ent.grid(row=0,column=12,padx=2)

    flow = ttk.Frame(conn); flow.grid(row=0,column=13,sticky="w")
    xon_var=tk.BooleanVar(value=bool(settings.get("xonxoff",False)))
    rtscts_var=tk.BooleanVar(value=bool(settings.get("rtscts",False)))
    dsrdtr_var=tk.BooleanVar(value=bool(settings.get("dsrdtr",False)))
    dtr_var=tk.BooleanVar(value=bool(settings.get("dtr",False)))
    rts_var=tk.BooleanVar(value=bool(settings.get("rts",False)))
    for text,var in (("XON",xon_var),("RTS/CTS",rtscts_var),("DSR/DTR",dsrdtr_var),("DTR=1",dtr_var),("RTS=1",rts_var)):
        ttk.Checkbutton(flow,text=text,variable=var).pack(side="left")

    # TCP
    ttk.Label(conn, text="TCP:").grid(row=1,column=0,sticky="w")
    tcp_host_var=tk.StringVar(value=settings.get("tcp_host","127.0.0.1"))
    tcp_host_ent=ttk.Entry(conn,textvariable=tcp_host_var,width=20); tcp_host_ent.grid(row=1,column=1,columnspan=2,sticky="ew",padx=2)
    tcp_port_var=tk.StringVar(value=str(settings.get("tcp_port","40000")))
    tcp_port_ent=ttk.Entry(conn,textvariable=tcp_port_var,width=7); tcp_port_ent.grid(row=1,column=3,padx=2)
    term_var=tk.StringVar(value=settings.get("terminator","CRLF"))
    term_cb=ttk.Combobox(conn,textvariable=term_var,width=6,state="readonly",values=["нет","CR","LF","CRLF"]); term_cb.grid(row=1,column=4,padx=2)
    tcp_timeout_var=tk.StringVar(value=str(settings.get("tcp_timeout","3.0")))
    ttk.Label(conn,text="таймаут:").grid(row=1,column=5,sticky="e")
    tcp_timeout_ent=ttk.Entry(conn,textvariable=tcp_timeout_var,width=5); tcp_timeout_ent.grid(row=1,column=6,padx=2)

    # GSM/SMS
    ttk.Label(conn, text="SMS:").grid(row=2,column=0,sticky="w")
    modem_port_var=tk.StringVar(value=settings.get("modem_port", suggested_port()))
    modem_port_ent=ttk.Entry(conn,textvariable=modem_port_var,width=15); modem_port_ent.grid(row=2,column=1,padx=2)
    modem_baud_var=tk.StringVar(value=str(settings.get("modem_baud","115200")))
    modem_baud_cb=ttk.Combobox(conn,textvariable=modem_baud_var,width=7,values=["9600","19200","38400","57600","115200"]); modem_baud_cb.grid(row=2,column=2,padx=2)
    phone_var=tk.StringVar(value=settings.get("phone",""))
    phone_ent=ttk.Entry(conn,textvariable=phone_var,width=18); phone_ent.grid(row=2,column=3,columnspan=2,padx=2,sticky="ew")
    sms_prefix_var=tk.StringVar(value=settings.get("sms_prefix",""))
    sms_prefix_ent=ttk.Entry(conn,textvariable=sms_prefix_var,width=18); sms_prefix_ent.grid(row=2,column=5,columnspan=2,padx=2,sticky="ew")
    sms_timeout_var=tk.StringVar(value=str(settings.get("sms_timeout","20")))
    ttk.Label(conn,text="таймаут:").grid(row=2,column=7,sticky="e")
    sms_timeout_ent=ttk.Entry(conn,textvariable=sms_timeout_var,width=5); sms_timeout_ent.grid(row=2,column=8,padx=2)
    ttk.Label(conn,text="номер / префикс команды").grid(row=2,column=9,columnspan=4,sticky="w")

    serial_widgets=[port_ent,baud_cb,fr_cb,bits_cb,parity_cb,stop_cb,resp_timeout_ent,idle_gap_ent,retries_ent]
    tcp_widgets=[tcp_host_ent,tcp_port_ent,term_cb,tcp_timeout_ent]
    sms_widgets=[modem_port_ent,modem_baud_cb,phone_ent,sms_prefix_ent,sms_timeout_ent]
    def update_transport_fields(*_):
        mode=transport_var.get()
        def set_group(items,enabled):
            for w in items:
                try: w.state(["!disabled"] if enabled else ["disabled"])
                except Exception: w.configure(state="normal" if enabled else "disabled")
        set_group(serial_widgets, mode.startswith("Оптопорт"))
        set_group(tcp_widgets, mode.startswith("TCP"))
        set_group(sms_widgets, mode.startswith("GSM"))
    transport_cb.bind("<<ComboboxSelected>>", update_transport_fields)

    def do_connect():
        if state["connected"]:
            task_q.put({"op":"disconnect"}); return
        label=transport_var.get()
        try:
            common={"op":"connect", "idle_gap":float(idle_gap_var.get() or 0.25)}
            if label.startswith("Оптопорт"):
                selected={**common,"transport":"serial","port":port_var.get().strip(),
                    "baud":int(baud_var.get()),"framing":fr_var.get(),"bytesize":int(bits_var.get()),
                    "parity":parity_var.get(),"stopbits":float(stop_var.get()),
                    "response_timeout":float(resp_timeout_var.get()),"read_retries":int(retries_var.get()),
                    "xonxoff":xon_var.get(),"rtscts":rtscts_var.get(),"dsrdtr":dsrdtr_var.get(),
                    "dtr":dtr_var.get(),"rts":rts_var.get()}
            elif label.startswith("TCP"):
                selected={**common,"transport":"tcp","host":tcp_host_var.get().strip(),
                    "tcp_port":int(tcp_port_var.get()),"terminator":term_var.get(),
                    "tcp_timeout":float(tcp_timeout_var.get())}
            else:
                selected={**common,"transport":"sms","modem_port":modem_port_var.get().strip(),
                    "modem_baud":int(modem_baud_var.get()),"phone":phone_var.get().strip(),
                    "sms_prefix":sms_prefix_var.get(),"sms_timeout":float(sms_timeout_var.get())}
        except ValueError:
            messagebox.showerror("Подключение","Проверь числовые параметры транспорта."); return
        saved={k:v for k,v in selected.items() if k!="op"}
        merged = load_settings()
        merged.update(saved)
        merged["transport"] = label
        save_settings(merged); task_q.put(selected)
    conn_btn.config(command=do_connect)
    update_transport_fields()

    # ── второй ряд: уровень доступа / аутентификация / экспертный режим ──
    top2 = ttk.Frame(root, padding=(6, 0, 6, 6)); top2.pack(fill="x")
    ttk.Label(top2, text="Уровень:").pack(side="left")
    level_var = tk.StringVar(value=LEVELS[0])
    ttk.Combobox(top2, textvariable=level_var, values=LEVELS, state="readonly",
                 width=15).pack(side="left", padx=(2, 12))
    ttk.Label(top2, text="Логин:").pack(side="left")
    cred_var = tk.StringVar(value=AUTH_CREDS[0])
    ttk.Combobox(top2, textvariable=cred_var, values=AUTH_CREDS, state="readonly",
                 width=18).pack(side="left", padx=2)
    pw_var = tk.StringVar()
    ttk.Entry(top2, textvariable=pw_var, width=12, show="•").pack(side="left", padx=2)

    def do_auth():
        task_q.put({"op": "auth", "cred": cred_var.get(), "value": pw_var.get()})
    ttk.Button(top2, text="Аутентифицировать", command=do_auth).pack(side="left", padx=6)
    auth_lbl = ttk.Label(top2, text="○ Provider не подтверждён", foreground="#777")
    auth_lbl.pack(side="left", padx=(2, 8))

    expert_var = tk.BooleanVar(value=False)
    def toggle_expert():
        from tkinter import messagebox
        if expert_var.get():
            ok = messagebox.askyesno(
                "Экспертный режим — подтверждение",
                "Включить отправку КРИТИЧНЫХ команд на прибор?\n\n"
                "Разблокирует запись/действия для: АКТУАТОР, СЕРВИС/объём, "
                "флаги ВМЕШАТЕЛЬСТВА, ПАРОЛИ, СБРОС/перезагрузка.\n\n"
                "На реальном приборе это влияет на рабочую безопасность и сервисию "
                "(единство измерений). Отправляй только то, на что есть право и "
                "штатное основание. Продолжить?")
            if not ok:
                expert_var.set(False)
        state["expert"] = expert_var.get()
        exp_lbl.config(text=("● ЭКСПЕРТ ВКЛ" if state["expert"] else "○ эксперт выкл"),
                       foreground=("#c0392b" if state["expert"] else "#777"))
        with contextlib.suppress(Exception):
            on_select()
    ttk.Checkbutton(top2, text="Экспертный режим", variable=expert_var,
                    command=toggle_expert).pack(side="left", padx=(16, 2))
    exp_lbl = ttk.Label(top2, text="○ эксперт выкл", foreground="#777")
    exp_lbl.pack(side="left")

    # ── верхний нотбук: «Команды» и «Телеметрия» ────────────────────────
    main_nb = ttk.Notebook(root)
    tab_cmd = ttk.Frame(main_nb)
    tab_terminal = ttk.Frame(main_nb, padding=6)
    tab_tele = ttk.Frame(main_nb, padding=6)
    tab_hist = ttk.Frame(main_nb, padding=6)
    tab_lab = ttk.Frame(main_nb, padding=6)
    tab_service = ttk.Frame(main_nb, padding=6)
    tab_dump = ttk.Frame(main_nb, padding=6)
    tab_audit = ttk.Frame(main_nb, padding=6)
    main_nb.add(tab_cmd, text="Команды (160)")
    main_nb.add(tab_terminal, text="Транспорт · RAW · SMS")
    main_nb.add(tab_tele, text="Телеметрия")
    main_nb.add(tab_hist, text="История")
    main_nb.add(tab_lab, text="Снимки · сценарии · мониторинг")
    main_nb.add(tab_service, text="Сервис · статус · бэкап")
    main_nb.add(tab_dump, text="Дамп W25Q64 · пароли")
    main_nb.add(tab_audit, text="Аудит · Pentest")
    main_nb.pack(fill="both", expand=True)

    # ── тело вкладки «Команды»: слева каталог, справа детали+запись ──────
    body = ttk.Panedwindow(tab_cmd, orient="horizontal"); body.pack(fill="both", expand=True)

    left = ttk.Frame(body, padding=4); body.add(left, weight=3)
    filt = ttk.Frame(left); filt.pack(fill="x")
    ttk.Label(filt, text="Поиск:").pack(side="left")
    search_var = tk.StringVar()
    ttk.Entry(filt, textvariable=search_var).pack(side="left", fill="x", expand=True, padx=4)
    groups = ["(все группы)"] + sorted({c["group"] for c in catalog})
    grp_var = tk.StringVar(value=groups[0])
    ttk.Combobox(filt, textvariable=grp_var, values=groups, state="readonly", width=26).pack(side="left")

    cols = ("name", "desc", "type", "prov", "user", "prot")
    tree = ttk.Treeview(left, columns=cols, show="headings", selectmode="browse")
    for c, txt, w, stretch in (("name", "Команда", 175, False),
                               ("desc", "Что делает", 300, True),
                               ("type", "Тип", 78, False),
                               ("prov", "П", 56, False), ("user", "О", 56, False),
                               ("prot", "запись", 84, False)):
        tree.heading(c, text=txt); tree.column(c, width=w, anchor="w", stretch=stretch)
    tree.tag_configure("prot", foreground="#c0392b")
    ysb = ttk.Scrollbar(left, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=ysb.set)
    tree.pack(side="left", fill="both", expand=True, pady=4)
    ysb.pack(side="left", fill="y")
    count_lbl = ttk.Label(left, text="")
    count_lbl.pack(anchor="w")

    def refill(*_):
        q = search_var.get().lower().strip()
        g = grp_var.get()
        tree.delete(*tree.get_children())
        n = 0
        for c in catalog:
            if g != "(все группы)" and c["group"] != g:
                continue
            if q and q not in c["name"].lower() and q not in c["desc"].lower():
                continue
            is_critical = c["name"] in critical
            prot = "эксперт" if is_critical else "обычная"
            tags = ("prot",) if is_critical else ()
            tree.insert("", "end", iid=c["name"],
                        values=(c["name"], clean_desc(c["desc"], 70), c["type"],
                                access_human(c["prov"]), access_human(c["user"]), prot),
                        tags=tags)
            n += 1
        count_lbl.config(text=f"Показано: {n} из {len(catalog)} команд "
                              f"· красным — экспертная запись/действие")
    search_var.trace_add("write", refill)
    grp_var.trace_add("write", refill)

    # ── правая панель ───────────────────────────────────────────────────
    right = ttk.Frame(body, padding=4); body.add(right, weight=2)
    det = ttk.LabelFrame(right, text="Выбранная команда", padding=6); det.pack(fill="x")
    det_txt = tk.Text(det, height=8, wrap="word"); det_txt.pack(fill="x")
    det_txt.configure(state="disabled")

    io = ttk.LabelFrame(right, text="Чтение / запись / действие", padding=6); io.pack(fill="x", pady=6)
    io.columnconfigure(1, weight=1)
    hint_lbl = ttk.Label(io, text="—", foreground="#555", wraplength=360, justify="left")
    hint_lbl.grid(row=0, column=0, columnspan=3, sticky="w")
    ttk.Label(io, text="Значение:").grid(row=1, column=0, sticky="w")
    val_var = tk.StringVar()
    val_ent = ttk.Entry(io, textvariable=val_var)
    val_ent.grid(row=1, column=1, sticky="ew", padx=4)
    opt_cb = ttk.Combobox(io, width=15, state="readonly", values=[])
    opt_cb.grid(row=1, column=2, sticky="e")
    opt_cb.bind("<<ComboboxSelected>>",
                lambda e: val_var.set(opt_cb.get().split(" ", 1)[0]) if opt_cb.get() else None)

    # Составные команды (MODE_TRANSFER и др.) — вместо одной строки показываем
    # по подписанному полю на каждое числовое значение (см. COMPOUND_FIELDS).
    compound_frame = ttk.Frame(io)
    compound_frame.grid(row=1, column=0, columnspan=3, sticky="ew", padx=4)
    compound_frame.grid_remove()
    compound_entries: list[tuple[ttk.Label, ttk.Entry, tk.StringVar]] = []
    for _i in range(max(len(v) for v in COMPOUND_FIELDS.values())):
        _var = tk.StringVar()
        _lbl = ttk.Label(compound_frame, text="", width=34, anchor="w")
        _lbl.grid(row=_i, column=0, sticky="w", pady=1)
        _ent = ttk.Entry(compound_frame, textvariable=_var, width=14)
        _ent.grid(row=_i, column=1, sticky="w", padx=4, pady=1)
        compound_entries.append((_lbl, _ent, _var))

    def show_compound_fields(name: str | None):
        labels = COMPOUND_FIELDS.get(name) if name else None
        if not labels:
            compound_frame.grid_remove()
            val_ent.grid()
            opt_cb.grid()
            return
        val_ent.grid_remove()
        opt_cb.grid_remove()
        for i, (lbl, ent, _var) in enumerate(compound_entries):
            if i < len(labels):
                lbl.config(text=labels[i])
                lbl.grid(); ent.grid()
            else:
                lbl.grid_remove(); ent.grid_remove()
        compound_frame.grid()

    def compound_value_to_write() -> str:
        labels = COMPOUND_FIELDS.get(state["selected"]["name"], [])
        return ";".join(compound_entries[i][2].get().strip() for i in range(len(labels)))

    def fill_compound_from_reading(name: str, value: str):
        labels = COMPOUND_FIELDS.get(name)
        if not labels:
            return
        parts = _split_compound(value)
        for i, part in enumerate(parts[:len(labels)]):
            compound_entries[i][2].set(part)

    now_btn = ttk.Button(io, text="сейчас", width=8,
        command=lambda: val_var.set(datetime.datetime.now().strftime("%d.%m.%y,%H:%M:%S")))
    now_btn.grid(row=2, column=2, sticky="e")
    read_btn = ttk.Button(io, text="Прочитать (get)")
    read_btn.grid(row=2, column=0, sticky="ew", pady=4)
    write_btn = ttk.Button(io, text="Записать (set)")
    write_btn.grid(row=2, column=1, sticky="ew", pady=4, padx=4)
    act_btn = ttk.Button(io, text="Выполнить (действие)")
    act_btn.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(0, 4))
    prot_note = ttk.Label(io, text="", foreground="#c0392b", wraplength=360, justify="left")
    prot_note.grid(row=4, column=0, columnspan=3, sticky="w")

    provider_box = ttk.LabelFrame(right, text="Provider · прямая запись показаний", padding=6)
    provider_box.pack(fill="x", pady=(0, 6))
    ttk.Label(provider_box, foreground="#8a4b08", wraplength=360, justify="left",
              text="После штатной Provider-авторизации отправляется прямой SET. "
                   "Проверочное чтение можно отключить. CLEAR_ARHIVE остаётся обычной "
                   "самостоятельной критической командой каталога.").pack(anchor="w")
    provider_readback_var = tk.BooleanVar(value=True)
    ttk.Checkbutton(provider_box, text="Проверить значение чтением после SET",
                    variable=provider_readback_var).pack(anchor="w", pady=(6, 0))
    provider_box.pack_forget()

    free = ttk.LabelFrame(right, text="Свободная команда (сырой протокол)", padding=6)
    free.pack(fill="x")
    free_var = tk.StringVar()
    free_cb = ttk.Combobox(free, textvariable=free_var, values=cmd_history.combined())
    free_cb.pack(side="left", fill="x", expand=True)
    def _refresh_history():
        free_cb.config(values=cmd_history.combined())
    def do_send_free():
        txt = free_var.get().strip()
        if txt.startswith("★ "):
            txt = txt[2:]
            free_var.set(txt)
        if txt:
            cmd_history.add(txt)
            _refresh_history()
            task_q.put({"op": "send", "text": txt, "expert": state["expert"]})
    def _toggle_favorite():
        txt = free_var.get().strip()
        if txt.startswith("★ "):
            txt = txt[2:]
        if txt:
            is_fav = cmd_history.toggle_favorite(txt)
            _refresh_history()
            append("ok", f"[★] {'Добавлено в избранное' if is_fav else 'Удалено из избранного'}: {txt}")
    ttk.Button(free, text="Отправить", command=do_send_free).pack(side="left", padx=6)
    ttk.Button(free, text="★", width=2, command=_toggle_favorite).pack(side="left")

    quick = ttk.LabelFrame(right, text="Быстрые действия", padding=6); quick.pack(fill="x")
    quick.columnconfigure(0, weight=1); quick.columnconfigure(1, weight=1)
    _qa = [
        ("Пре-флайт", lambda: task_q.put({"op": "preflight"})),
        ("Паспорт", lambda: task_q.put({"op": "passport"})),
        ("Auth-scan", lambda: task_q.put({"op": "authscan"})),
        ("Показания", lambda: [task_q.put({"op": "read", "name": n}) for n in
                               ("Volume", "VOLUME_GLOB", "VOLUME_INST", "VOLUME_COMMIS")]),
    ]
    for _i, (_t, _cmd) in enumerate(_qa):
        ttk.Button(quick, text=_t, command=_cmd).grid(
            row=_i // 2, column=_i % 2, sticky="ew", padx=2, pady=2)

    def on_select(_=None):
        sel = tree.focus()
        if not sel:
            return
        c = next((x for x in catalog if x["name"] == sel), None)
        if not c:
            return
        state["selected"] = c
        det_txt.configure(state="normal"); det_txt.delete("1.0", "end")
        det_txt.insert("end", f"{c['name']}   ({c['type']})\n", "h")
        det_txt.insert("end", f"Группа: {c['group']}\n")
        det_txt.insert("end", f"Доступ  П={c['prov']} ({access_human(c['prov'])})  "
                              f"О={c['user']} ({access_human(c['user'])})\n")
        acc, _, can_w_access = access_at_level(c, level_var.get())
        det_txt.insert("end", f"На уровне «{level_var.get()}»: {acc}\n")
        det_txt.insert("end", f"Обработчик: {c['handler']}\n")
        det_txt.insert("end", f"\n{clean_desc(c['desc'])}\n")
        det_txt.tag_configure("h", font=("TkDefaultFont", 11, "bold"))
        det_txt.configure(state="disabled")
        typ = c["type"] or ""
        is_action = c["name"] in actions
        can_r, can_w_dir, can_a = directions(c, is_action)
        hint_text = (f"Тип: {typ}  ·  доступ П={c['prov']} О={c['user']}  ·  "
                     + ("действие (кнопка «Выполнить»)" if is_action
                        else "работает в обе стороны: чтение и запись"))
        if c["name"] in COMPOUND_FIELDS_UNCERTAIN:
            hint_text += ("\n⚠ Названия полей ниже — предположение по коду прошивки, "
                          "не проверено на живом приборе. Сначала нажмите «Прочитать», "
                          "сверьте значения с реальным поведением, потом меняйте.")
        hint_lbl.config(text=hint_text)
        opts = value_options(c)
        opt_cb.config(values=opts); opt_cb.set("")
        show_compound_fields(c["name"])
        now_btn.grid() if ("дата" in typ and c["name"] not in COMPOUND_FIELDS) else now_btn.grid_remove()
        read_btn.state(["!disabled"] if can_r else ["disabled"])
        write_btn.state(["!disabled"] if (can_w_dir and can_w_access) else ["disabled"])
        act_btn.state(["!disabled"] if can_a else ["disabled"])
        if c["name"] in READING_COMMANDS:
            write_btn.config(text="Записать напрямую (Provider)")
            provider_box.pack(fill="x", pady=(0, 6), before=free)
        else:
            write_btn.config(text="Записать (set)")
            provider_box.pack_forget()
        val_ent.state(["disabled"] if is_action else ["!disabled"])
        if c["name"] in critical:
            if state["expert"]:
                prot_note.config(text="⚠ КРИТИЧНАЯ + Экспертный режим ВКЛ — отправка "
                                      "выполнится (актуатор/сервис/пароли/сброс). "
                                      "Устройство проверит уровень.")
            else:
                prot_note.config(text="⚠ Критичная команда — запись/действие "
                                      "заблокированы. Включи «Экспертный режим» для отправки.")
        else:
            prot_note.config(text="Обычная команда — читается и пишется свободно "
                                  "(при нужном уровне доступа на приборе).")
    tree.bind("<<TreeviewSelect>>", on_select)
    level_var.trace_add("write", lambda *a: on_select())

    def do_read():
        if state["selected"]:
            task_q.put({"op": "read", "name": state["selected"]["name"]})
    def do_write():
        if not state["selected"]:
            return
        name = state["selected"]["name"]
        if name in COMPOUND_FIELDS:
            val_var.set(compound_value_to_write())
        if name in READING_COMMANDS:
            if not state["expert"]:
                messagebox.showwarning("Запись показаний", "Включи Экспертный режим.")
                return
            if not state.get("provider_verified"):
                messagebox.showwarning(
                    "Запись показаний",
                    "Сначала выполни PASSWORD_PROVIDER и дождись статуса «Provider подтверждён».\n\n"
                    "Для низкоуровневой отправки без локальной проверки можно использовать свободную команду.")
                return
            new_value = val_var.get().strip()
            try:
                new_value = reading_text(new_value)
            except ValueError as exc:
                messagebox.showerror("Запись показаний", str(exc))
                return
            verify = bool(provider_readback_var.get())
            detail = "с последующим read-back" if verify else "без read-back"
            if not messagebox.askyesno(
                    "Прямая Provider-запись",
                    f"Отправить {name}={new_value} {detail}?\n\n"
                    "Архив этой операцией не изменяется.", parent=root):
                return
            task_q.put({"op": "write_reading_provider", "name": name, "val": new_value,
                        "expert": state["expert"], "verify": verify})
            return
        task_q.put({"op": "write", "name": name,
                    "val": val_var.get(), "expert": state["expert"]})

    def do_action():
        if state["selected"]:
            task_q.put({"op": "send", "text": state["selected"]["name"],
                        "expert": state["expert"]})
    read_btn.config(command=do_read)
    write_btn.config(command=do_write)
    act_btn.config(command=do_action)

    # ── вкладка «Транспорт · RAW · SMS» ────────────────────────────────
    ttk.Label(tab_terminal, wraplength=1160, foreground="#555", justify="left",
              text="Работа только с реальным подключением. Командный терминал использует "
                   "каталожное кадрирование и экспертный гейт; RAW HEX передаёт точные байты "
                   "без добавления CR/LF/скобок; AT и приём SMS доступны при GSM-подключении.").pack(anchor="w")

    term_cmd = ttk.LabelFrame(tab_terminal, text="Командный терминал", padding=6)
    term_cmd.pack(fill="x", pady=(6, 3)); term_cmd.columnconfigure(1, weight=1)
    ttk.Label(term_cmd, text="Команда:").grid(row=0,column=0,sticky="w")
    terminal_cmd_var=tk.StringVar()
    terminal_cmd_cb=ttk.Combobox(term_cmd,textvariable=terminal_cmd_var,values=cmd_history.combined())
    terminal_cmd_cb.grid(row=0,column=1,sticky="ew",padx=5)
    def terminal_send():
        text=terminal_cmd_var.get().strip()
        if text.startswith("★ "):
            text = text[2:]
            terminal_cmd_var.set(text)
        if text:
            cmd_history.add(text)
            free_cb.config(values=cmd_history.combined())
            terminal_cmd_cb.config(values=cmd_history.combined())
            task_q.put({"op":"send","text":text,"expert":state["expert"]})
    ttk.Button(term_cmd,text="Отправить",command=terminal_send).grid(row=0,column=2)
    terminal_cmd_cb.bind("<Return>",lambda _e: terminal_send())
    ttk.Label(term_cmd,text="Примеры: DevInfo · SERVER_URL=host:port · VALVE_OPEN",
              foreground="#777").grid(row=1,column=1,sticky="w")

    raw_box = ttk.LabelFrame(tab_terminal, text="Точный RAW HEX-обмен (Serial/TCP)", padding=6)
    raw_box.pack(fill="both", expand=True, pady=3)
    raw_top=ttk.Frame(raw_box); raw_top.pack(fill="x")
    ttk.Label(raw_top,text="Таймаут ответа, с:").pack(side="left")
    raw_timeout_var=tk.StringVar(value="2.5")
    ttk.Entry(raw_top,textvariable=raw_timeout_var,width=6).pack(side="left",padx=4)
    ttk.Label(raw_top,text="HEX допускает пробелы: 2F 3F 44 65 76 49 6E 66 6F 21 0D 0A",
              foreground="#777").pack(side="left",padx=8)
    raw_hex_text=scrolledtext.ScrolledText(raw_box,height=6,wrap="word",font=("TkFixedFont",10))
    raw_hex_text.pack(fill="both",expand=True,pady=4)
    raw_buttons=ttk.Frame(raw_box); raw_buttons.pack(fill="x")
    def raw_send():
        task_q.put({"op":"raw_hex","hex":raw_hex_text.get("1.0","end"),
                    "timeout":raw_timeout_var.get(), "expert":state["expert"]})
    ttk.Button(raw_buttons,text="Передать точные байты",command=raw_send).pack(side="left")
    ttk.Button(raw_buttons,text="DevInfo / IEC HEX",command=lambda:(
        raw_hex_text.delete("1.0","end"),
        raw_hex_text.insert("1.0","2F 3F 44 65 76 49 6E 66 6F 21 0D 0A"))).pack(side="left",padx=4)
    ttk.Button(raw_buttons,text="Очистить",command=lambda:raw_hex_text.delete("1.0","end")).pack(side="left")

    sms_box=ttk.LabelFrame(tab_terminal,text="GSM-модем / SMS",padding=6)
    sms_box.pack(fill="both",expand=True,pady=3)
    sms_top=ttk.Frame(sms_box); sms_top.pack(fill="x")
    at_var=tk.StringVar(value="AT+CSQ")
    ttk.Label(sms_top,text="AT:").pack(side="left")
    ttk.Entry(sms_top,textvariable=at_var,width=28).pack(side="left",padx=4)
    ttk.Button(sms_top,text="Выполнить AT",command=lambda:task_q.put(
        {"op":"modem_at","text":at_var.get()})).pack(side="left")
    sms_delete_var=tk.BooleanVar(value=False)
    ttk.Checkbutton(sms_top,text="удалить после чтения",variable=sms_delete_var).pack(side="left",padx=10)
    ttk.Button(sms_top,text="Получить непрочитанные SMS",command=lambda:task_q.put(
        {"op":"sms_receive","delete":sms_delete_var.get()})).pack(side="left")
    sms_text=scrolledtext.ScrolledText(sms_box,height=6,wrap="word",font=("TkFixedFont",9))
    sms_text.pack(fill="both",expand=True,pady=(4,0))

    # ── вкладка «Телеметрия»: ПРИЁМ + ОТПРАВКА (обе стороны) ─────────────
    state.setdefault("readings", {}); state.setdefault("tele_srv", None)

    ttk.Label(tab_tele, wraplength=1150, foreground="#555", justify="left",
              text="Телеметрия в обе стороны (GPRS/TCP). ПРИЁМ: слушать порт — поймать "
                   "сессию прибора, разобрать, ответить ACK. ОТПРАВКА: собрать пакет из "
                   "снятых показаний и реально отправить на host:port. + CRC16-скан и auth/MD5."
              ).pack(anchor="w")

    rxb = ttk.Frame(tab_tele); rxb.pack(fill="x", pady=(4, 0))
    ttk.Label(rxb, text="ПРИЁМ — порт:").pack(side="left")
    rx_port = tk.StringVar(value="40000")
    ttk.Entry(rxb, textvariable=rx_port, width=7).pack(side="left", padx=2)
    listen_status = ttk.Label(rxb, text="○ не слушаю", foreground="#777")

    def do_listen():
        if state.get("tele_srv"):
            return
        try:
            port = int(rx_port.get())
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            append("err", "[приём] TCP-порт должен быть от 1 до 65535.")
            return
        s = TeleServer(port, out_q, diagnostic=diagnostic); state["tele_srv"] = s; s.start()
        listen_status.config(text=f"● слушаю :{port}", foreground="#0a7d0a")

    def do_stop():
        s = state.get("tele_srv")
        if s:
            s.stop(); state["tele_srv"] = None
        listen_status.config(text="○ не слушаю", foreground="#777")
    ttk.Button(rxb, text="Слушать", command=do_listen).pack(side="left", padx=(6, 2))
    ttk.Button(rxb, text="Стоп", command=do_stop).pack(side="left")
    listen_status.pack(side="left", padx=8)

    txb = ttk.Frame(tab_tele); txb.pack(fill="x", pady=(2, 0))
    ttk.Label(txb, text="ОТПРАВКА → host:").pack(side="left")
    tx_host = tk.StringVar(value="127.0.0.1")
    ttk.Entry(txb, textvariable=tx_host, width=14).pack(side="left", padx=2)
    ttk.Label(txb, text="порт:").pack(side="left")
    tx_port = tk.StringVar(value="40000")
    ttk.Entry(txb, textvariable=tx_port, width=7).pack(side="left", padx=2)

    def do_send():
        data = tele_in.get("1.0", "end").strip().encode("latin1", "replace")
        if not data:
            append("warn", "[отправка] пусто — сначала «Собрать пакет» или вставь пакет."); return
        try:
            tele_send(tx_host.get().strip(), int(tx_port.get()), data, out_q, diagnostic=diagnostic)
            append("ok", f"[отправка] отправляю {len(data)} байт → {tx_host.get()}:{tx_port.get()}")
        except ValueError:
            append("err", "[отправка] неверный порт.")
    ttk.Button(txb, text="Отправить", command=do_send).pack(side="left", padx=6)

    dab = ttk.Frame(tab_tele); dab.pack(fill="x", pady=(2, 4))

    def do_build():
        pkt = build_telemetry_packet(state.get("readings", {}))
        tele_in.delete("1.0", "end"); tele_in.insert("1.0", pkt)
        _tele_parse()
    ttk.Button(dab, text="Собрать пакет (из показаний)", command=do_build).pack(side="left")
    ttk.Button(dab, text="Снять по оптопорту",
               command=lambda: task_q.put({"op": "tele_read"})).pack(side="left", padx=6)

    def _tele_load():
        p = filedialog.askopenfilename(filetypes=[("session log", "*.log"), ("все", "*.*")])
        if p:
            tele_in.delete("1.0", "end")
            tele_in.insert("1.0", open(p, "rb").read().decode("latin1", "replace"))
    ttk.Button(dab, text="Загрузить .log…", command=_tele_load).pack(side="left")
    ttk.Button(dab, text="Разобрать", command=lambda: _tele_parse()).pack(side="left", padx=6)

    tele_in = scrolledtext.ScrolledText(tab_tele, height=4, wrap="none", font=("TkFixedFont", 9))
    tele_in.pack(fill="x")
    tpan = ttk.Panedwindow(tab_tele, orient="horizontal"); tpan.pack(fill="both", expand=True, pady=4)
    trf = ttk.Frame(tpan); tpan.add(trf, weight=3)
    ttk.Label(trf, text="Записи пакета:").pack(anchor="w")
    rec_cols = ("type", "dt", "acc", "val", "flag")
    rec_tree = ttk.Treeview(trf, columns=rec_cols, show="headings", height=8)
    for c, t, w in (("type", "Тип", 50), ("dt", "Дата/время", 155),
                    ("acc", "Накопитель ×10000", 140), ("val", "Значение", 90),
                    ("flag", "Флаг", 50)):
        rec_tree.heading(c, text=t); rec_tree.column(c, width=w, anchor="w")
    rsb = ttk.Scrollbar(trf, orient="vertical", command=rec_tree.yview)
    rec_tree.configure(yscrollcommand=rsb.set)
    rec_tree.pack(side="left", fill="both", expand=True); rsb.pack(side="left", fill="y")
    tsf = ttk.Frame(tpan); tpan.add(tsf, weight=2)
    ttk.Label(tsf, text="Заголовок · CRC16 · auth:").pack(anchor="w")
    tele_sum = scrolledtext.ScrolledText(tsf, wrap="word", font=("TkFixedFont", 9), height=8)
    tele_sum.pack(fill="both", expand=True)

    dbf = ttk.LabelFrame(tab_tele, text="Накопленная телеметрия · SQLite", padding=5)
    dbf.pack(fill="both", expand=True, pady=(2, 0))
    dbbar = ttk.Frame(dbf); dbbar.pack(fill="x")
    tele_db_info = ttk.Label(dbbar, text="—", foreground="#555")
    tele_db_info.pack(side="left")
    tele_anomaly_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(dbbar, text="только аномалии", variable=tele_anomaly_var,
                    command=lambda: refresh_telemetry_db()).pack(side="left", padx=8)
    tele_device_var = tk.StringVar(value="(все устройства)")
    tele_device_cb = ttk.Combobox(dbbar, textvariable=tele_device_var, state="readonly",
                                  width=20, values=["(все устройства)"])
    tele_device_cb.pack(side="left", padx=3)
    tele_device_cb.bind("<<ComboboxSelected>>", lambda _e: refresh_telemetry_db())
    ttk.Button(dbbar, text="Обновить", command=lambda: refresh_telemetry_db()).pack(side="left", padx=3)

    def export_telemetry_db():
        if tele_store_mod is None:
            messagebox.showerror("Телеметрия", "Модуль smt_telemetry_store.py не найден")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv",
                                             filetypes=[("CSV", "*.csv")],
                                             initialfile="telemetry_history.csv")
        if not path:
            return
        try:
            count = tele_store_mod.export_csv(TELEMETRY_DB_PATH, path)
            append("ok", f"[телеметрия] экспортировано {count} записей → {path}")
        except Exception as exc:
            messagebox.showerror("Телеметрия", str(exc))
    ttk.Button(dbbar, text="Экспорт CSV…", command=export_telemetry_db).pack(side="left", padx=3)

    db_cols = ("rx", "device", "dt", "acc", "value", "flag", "anomaly", "ip")
    tele_db_tree = ttk.Treeview(dbf, columns=db_cols, show="headings", height=7)
    for c, title, width in (("rx", "Получено UTC", 145), ("device", "ID64", 135),
                            ("dt", "Время прибора", 145), ("acc", "Накопитель, м³", 120),
                            ("value", "Значение", 85), ("flag", "Флаг", 50),
                            ("anomaly", "Аномалия", 220), ("ip", "Источник", 105)):
        tele_db_tree.heading(c, text=title); tele_db_tree.column(c, width=width, anchor="w")
    tele_db_tree.tag_configure("bad", foreground="#c0392b")
    dbsb = ttk.Scrollbar(dbf, orient="vertical", command=tele_db_tree.yview)
    tele_db_tree.configure(yscrollcommand=dbsb.set)
    tele_db_tree.pack(side="left", fill="both", expand=True, pady=(4, 0))
    dbsb.pack(side="left", fill="y", pady=(4, 0))

    def refresh_telemetry_db():
        tele_db_tree.delete(*tele_db_tree.get_children())
        if tele_store_mod is None:
            tele_db_info.config(text="База недоступна: smt_telemetry_store.py не найден",
                                foreground="#c0392b")
            return
        try:
            stat = tele_store_mod.stats(TELEMETRY_DB_PATH)
            devices = tele_store_mod.devices(TELEMETRY_DB_PATH)
            selected = tele_device_var.get()
            values = ["(все устройства)"] + devices
            tele_device_cb.config(values=values)
            if selected not in values:
                tele_device_var.set("(все устройства)")
                selected = "(все устройства)"
            rows = tele_store_mod.recent_records(
                TELEMETRY_DB_PATH, 1000, anomalies_only=tele_anomaly_var.get(),
                id64="" if selected == "(все устройства)" else selected)
            for r in rows:
                anomaly = r.get("anomaly", "")
                tele_db_tree.insert("", "end", values=(
                    r.get("received_utc", ""), r.get("id64", ""),
                    r.get("device_datetime", ""),
                    "" if r.get("accumulator_m3") is None else f"{r['accumulator_m3']:.4f}",
                    r.get("value", ""), r.get("flag", ""), anomaly, r.get("source_ip", "")),
                    tags=("bad",) if anomaly else ())
            tele_db_info.config(
                text=(f"Пакетов: {stat['packets']} · записей: {stat['records']} · "
                      f"устройств: {stat['devices']} · аномалий: {stat['anomalies']} · "
                      f"показано: {len(rows)}"),
                foreground="#c0392b" if stat["anomalies"] else "#0a7d0a")
        except Exception as exc:
            tele_db_info.config(text=f"Ошибка базы: {exc}", foreground="#c0392b")

    refresh_telemetry_db()

    # ── Автоматическая периодическая отправка телеметрии ───────────────
    auto_frame = ttk.LabelFrame(tab_tele, text="Автоматическая отправка телеметрии", padding=5)
    auto_frame.pack(fill="x", pady=(4, 2))
    auto_bar = ttk.Frame(auto_frame); auto_bar.pack(fill="x")
    ttk.Label(auto_bar, text="Сервер:").pack(side="left")
    auto_host_var = tk.StringVar(value="127.0.0.1")
    ttk.Entry(auto_bar, textvariable=auto_host_var, width=14).pack(side="left", padx=2)
    ttk.Label(auto_bar, text="порт:").pack(side="left")
    auto_port_var = tk.StringVar(value="40000")
    ttk.Entry(auto_bar, textvariable=auto_port_var, width=7).pack(side="left", padx=2)
    ttk.Label(auto_bar, text="интервал, мин:").pack(side="left", padx=(8, 2))
    auto_interval_var = tk.StringVar(value="5")
    ttk.Entry(auto_bar, textvariable=auto_interval_var, width=5).pack(side="left", padx=2)
    state["tele_auto_active"] = False
    state["tele_auto_count"] = 0
    auto_status_lbl = ttk.Label(auto_bar, text="○ остановлено", foreground="#777")

    def _auto_tele_tick():
        if not state.get("tele_auto_active"):
            return
        if not state["connected"]:
            append("warn", "[автотелеметрия] Нет подключения — пропускаю цикл.")
        else:
            try:
                host = auto_host_var.get().strip()
                port = int(auto_port_var.get())
                task_q.put({"op": "tele_auto_cycle", "host": host, "port": port})
            except ValueError:
                append("err", "[автотелеметрия] Неверный порт.")
        try:
            interval_min = max(0.1, float(auto_interval_var.get().replace(",", ".")))
        except ValueError:
            interval_min = 5.0
        ms = int(interval_min * 60 * 1000)
        state["tele_auto_after"] = root.after(ms, _auto_tele_tick)

    def _auto_tele_start():
        if state.get("tele_auto_active"):
            return
        state["tele_auto_active"] = True
        state["tele_auto_count"] = 0
        auto_status_lbl.config(text="● активно (0 отправок)", foreground="#0a7d0a")
        append("ok", "[автотелеметрия] Запущена.")
        _auto_tele_tick()

    def _auto_tele_stop():
        state["tele_auto_active"] = False
        aid = state.pop("tele_auto_after", None)
        if aid:
            with contextlib.suppress(Exception):
                root.after_cancel(aid)
        auto_status_lbl.config(text="○ остановлено", foreground="#777")
        append("ok", "[автотелеметрия] Остановлена.")

    ttk.Button(auto_bar, text="Запустить", command=_auto_tele_start).pack(side="left", padx=6)
    ttk.Button(auto_bar, text="Остановить", command=_auto_tele_stop).pack(side="left")
    auto_status_lbl.pack(side="left", padx=8)
    ttk.Label(auto_frame, foreground="#555", wraplength=1100, justify="left",
              text="Каждые N минут снимает показания с прибора через активный оптопорт, "
                   "собирает телеметрический пакет и отправляет на указанный TCP-сервер."
              ).pack(anchor="w")

    # ── График телеметрии ─────────────────────────────────────────────
    chart_frame = ttk.LabelFrame(tab_tele, text="График телеметрии — накопитель и расход", padding=5)
    chart_frame.pack(fill="both", expand=True, pady=(2, 0))
    chart_bar = ttk.Frame(chart_frame); chart_bar.pack(fill="x")
    chart_device_var = tk.StringVar(value="(все устройства)")
    chart_device_cb = ttk.Combobox(chart_bar, textvariable=chart_device_var,
                                    state="readonly", width=20,
                                    values=["(все устройства)"])
    chart_device_cb.pack(side="left", padx=(0, 6))

    try:
        chart_canvas_widget = tk.Canvas(chart_frame, height=180, bg="white",
                                         highlightthickness=0)
    except Exception:
        chart_canvas_widget = None

    def _draw_chart():
        if chart_canvas_widget is None or tele_store_mod is None:
            return
        chart_canvas_widget.delete("all")
        w = chart_canvas_widget.winfo_width()
        h = chart_canvas_widget.winfo_height()
        if w < 100 or h < 60:
            return
        sel = chart_device_var.get()
        id64_filter = "" if sel == "(все устройства)" else sel
        rows = tele_store_mod.chart_data(TELEMETRY_DB_PATH, id64=id64_filter, limit=2000)
        if not rows:
            chart_canvas_widget.create_text(w // 2, h // 2, text="Нет данных",
                                             fill="#777", font=("TkDefaultFont", 11))
            return
        acc_vals = [r.get("accumulator_m3") for r in rows if r.get("accumulator_m3") is not None]
        flow_vals = [r.get("value") for r in rows if r.get("value") is not None]
        margin_l, margin_r, margin_t, margin_b = 70, 20, 15, 30
        plot_w = w - margin_l - margin_r
        plot_h = h - margin_t - margin_b
        if plot_w < 10 or plot_h < 10:
            return
        chart_canvas_widget.create_rectangle(margin_l, margin_t,
                                              w - margin_r, h - margin_b,
                                              outline="#ccc")
        if acc_vals:
            mn, mx = min(acc_vals), max(acc_vals)
            if mn == mx:
                mx = mn + 1
            rng = mx - mn
            points = []
            for i, v in enumerate(acc_vals):
                x = margin_l + (i / max(1, len(acc_vals) - 1)) * plot_w
                y = h - margin_b - ((v - mn) / rng) * plot_h
                points.append((x, y))
            if len(points) >= 2:
                flat = [coord for pt in points for coord in pt]
                chart_canvas_widget.create_line(*flat, fill="#2980b9", width=2, smooth=True)
            chart_canvas_widget.create_text(margin_l - 4, margin_t, anchor="ne",
                                             text=f"{mx:.2f}", fill="#2980b9",
                                             font=("TkFixedFont", 8))
            chart_canvas_widget.create_text(margin_l - 4, h - margin_b, anchor="se",
                                             text=f"{mn:.2f}", fill="#2980b9",
                                             font=("TkFixedFont", 8))
            chart_canvas_widget.create_text(margin_l + 4, margin_t + 2, anchor="nw",
                                             text="Накопитель, м³", fill="#2980b9",
                                             font=("TkFixedFont", 8))
        if flow_vals:
            mn2, mx2 = min(flow_vals), max(flow_vals)
            if mn2 == mx2:
                mx2 = mn2 + 1
            rng2 = mx2 - mn2
            points2 = []
            for i, v in enumerate(flow_vals):
                x = margin_l + (i / max(1, len(flow_vals) - 1)) * plot_w
                y = h - margin_b - ((v - mn2) / rng2) * plot_h
                points2.append((x, y))
            if len(points2) >= 2:
                flat2 = [coord for pt in points2 for coord in pt]
                chart_canvas_widget.create_line(*flat2, fill="#e67e22", width=1,
                                                 dash=(4, 2), smooth=True)
            chart_canvas_widget.create_text(w - margin_r - 4, margin_t + 2, anchor="ne",
                                             text=f"Расход (макс {mx2:.2f})", fill="#e67e22",
                                             font=("TkFixedFont", 8))
        n_pts = max(len(acc_vals), len(flow_vals))
        chart_canvas_widget.create_text(w // 2, h - 4, anchor="s",
                                         text=f"Точек: {n_pts}", fill="#777",
                                         font=("TkFixedFont", 8))

    def _refresh_chart():
        if tele_store_mod is not None:
            devs = tele_store_mod.devices(TELEMETRY_DB_PATH)
            vals = ["(все устройства)"] + devs
            chart_device_cb.config(values=vals)
        _draw_chart()

    ttk.Button(chart_bar, text="Обновить график", command=_refresh_chart).pack(side="left")
    if chart_canvas_widget is not None:
        chart_canvas_widget.pack(fill="both", expand=True, pady=(4, 0))
        chart_canvas_widget.bind("<Configure>", lambda _e: _draw_chart())
    chart_device_cb.bind("<<ComboboxSelected>>", lambda _e: _draw_chart())

    def _tele_render(rep):
        rec_tree.delete(*rec_tree.get_children())
        tele_sum.delete("1.0", "end")
        for r in rep.get("records", []):
            rec_tree.insert("", "end", values=(r["type"], r["dt"], r["accumulator"],
                                               r["value"], r["flag"]))
        h = rep.get("header")
        if h:
            tele_sum.insert("end", f"Заголовок:\n  имя = {h['name']}\n"
                                   f"  CRC16 (3 поля) = {', '.join(h['crc16'])}\n"
                                   f"  ID64 = {h['id64']}\n\nCRC16-скан:\n")
            for c in h["crc16"]:
                hits = srv.crc16_scan(rep["text"], c) if srv else []
                s = ", ".join(f"{x['variant']}[{x['window'][0]}:{x['window'][1]}]"
                              for x in hits) or "нет совпадений"
                tele_sum.insert("end", f"  {c}: {s}\n")
        else:
            tele_sum.insert("end", "Заголовок не распознан (проверь формат кадра).\n")
        tele_sum.insert("end", f"\nГрупп: {len(rep.get('groups', []))}, "
                               f"записей: {len(rep.get('records', []))}\n")
        if rep.get("auth"):
            tele_sum.insert("end", f"\nauth = {rep['auth']}\n")
            for a in (srv.auth_check(rep["text"], rep["auth"]) if srv else []):
                mark = " ✓ совпало" if a["match"] else ""
                tele_sum.insert("end", f"  MD5({a['input']}) = {a['md5']}{mark}\n")

    def _tele_parse():
        if srv is None:
            tele_sum.delete("1.0", "end")
            tele_sum.insert("end", "Модуль разбора smt_server.py не найден рядом с GUI.")
            return
        raw = tele_in.get("1.0", "end").strip().encode("latin1", "replace")
        if not raw:
            rec_tree.delete(*rec_tree.get_children()); tele_sum.delete("1.0", "end")
            tele_sum.insert("end", "Пусто. Собери пакет («Собрать пакет») или загрузи session_*.log.")
            return
        _tele_render(srv.parse_frame(raw))

    # ── вкладка «История»: разбор физического flash-дампа ─────────────────
    ttk.Label(tab_hist, wraplength=1150, foreground="#555", justify="left",
              text="История показывает только реальные данные прибора из дампа W25Q64: "
                   "чекпоинт 0x7FE000/0x7FC000, главный архив до 0x128000 и аудит 0x15E000. "
                   "Provider-запись показаний не очищает архив автоматически. CLEAR_ARHIVE "
                   "доступна отдельной подтверждаемой операцией; локальный журнал корректировок не ведётся."
              ).pack(anchor="w")
    hctl = ttk.Frame(tab_hist); hctl.pack(fill="x", pady=4)
    ttk.Button(hctl, text="Загрузить дамп…", command=lambda: hist_load()).pack(side="left")
    ttk.Button(hctl, text="Сравнить с другим дампом…", command=lambda: hist_compare()).pack(side="left", padx=4)
    ttk.Button(hctl, text="Экспорт разбора CSV…", command=lambda: hist_export()).pack(side="left", padx=4)
    hist_path = ttk.Label(hctl, text="дамп не загружен", foreground="#777")
    hist_path.pack(side="left", padx=8)

    hpan = ttk.Panedwindow(tab_hist, orient="vertical"); hpan.pack(fill="both", expand=True)

    cpf = ttk.Labelframe(hpan, text="История показаний — чекпоинт", padding=4); hpan.add(cpf, weight=1)
    cp_info = ttk.Label(cpf, text="—", foreground="#555"); cp_info.pack(anchor="w")
    cp_tree = ttk.Treeview(cpf, columns=("idx", "dt", "vol", "t1", "t2", "ok"),
                           show="headings", height=6)
    for c, t, w in (("idx", "#", 50), ("dt", "Время (UTC)", 150), ("vol", "Показания, м³", 140),
                    ("t1", "t1 °C", 70), ("t2", "t2 °C", 70), ("ok", "Целостн.", 80)):
        cp_tree.heading(c, text=t); cp_tree.column(c, width=w, anchor="w")
    cp_tree.tag_configure("bad", foreground="#c0392b")
    cpsb = ttk.Scrollbar(cpf, orient="vertical", command=cp_tree.yview)
    cp_tree.configure(yscrollcommand=cpsb.set)
    cp_tree.pack(side="left", fill="both", expand=True); cpsb.pack(side="left", fill="y")

    evf = ttk.Labelframe(hpan, text="Журнал событий / аудит", padding=4); hpan.add(evf, weight=1)
    ev_info = ttk.Label(evf, text="—", foreground="#555"); ev_info.pack(anchor="w")
    ev_tree = ttk.Treeview(evf, columns=("cnt", "dt", "code", "val", "note"),
                           show="headings", height=6)
    for c, t, w in (("cnt", "#", 50), ("dt", "Время (UTC)", 150), ("code", "Код", 70),
                    ("val", "Значение", 150), ("note", "Что это", 320)):
        ev_tree.heading(c, text=t); ev_tree.column(c, width=w, anchor="w")
    evsb = ttk.Scrollbar(evf, orient="vertical", command=ev_tree.yview)
    ev_tree.configure(yscrollcommand=evsb.set)
    ev_tree.pack(side="left", fill="both", expand=True); evsb.pack(side="left", fill="y")

    arf = ttk.Labelframe(hpan, text="Главный архив измерений", padding=4); hpan.add(arf, weight=1)
    ar_head = ttk.Frame(arf); ar_head.pack(fill="x")
    ar_info = ttk.Label(ar_head, text="—", foreground="#555"); ar_info.pack(side="left")
    ar_anomaly_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(ar_head, text="только аномалии", variable=ar_anomaly_var,
                    command=lambda: refresh_archive_tree()).pack(side="right")
    ar_tree = ttk.Treeview(arf, columns=("idx", "dt", "vol", "t1", "t2", "integrity", "anomaly"),
                           show="headings", height=6)
    for c, t, w in (("idx", "#", 55), ("dt", "Время (UTC)", 155),
                    ("vol", "Показания, м³", 125), ("t1", "t1 °C", 70),
                    ("t2", "t2 °C", 70), ("integrity", "Копия", 70),
                    ("anomaly", "Аномалия", 250)):
        ar_tree.heading(c, text=t); ar_tree.column(c, width=w, anchor="w")
    ar_tree.tag_configure("bad", foreground="#c0392b")
    arsb = ttk.Scrollbar(arf, orient="vertical", command=ar_tree.yview)
    ar_tree.configure(yscrollcommand=arsb.set)
    ar_tree.pack(side="left", fill="both", expand=True); arsb.pack(side="left", fill="y")
    state["history_checkpoint"] = []; state["history_archive"] = []; state["history_events"] = []
    state["history_archive_summary"] = {}

    def refresh_archive_tree():
        ar_tree.delete(*ar_tree.get_children())
        rows = state.get("history_archive", [])
        if ar_anomaly_var.get():
            rows = [r for r in rows if r.get("anomaly")]
        visible = rows[-2000:]
        for r in visible:
            dt = r["datetime"].strftime("%Y-%m-%d %H:%M:%S") if r.get("datetime") else "—"
            anomaly = r.get("anomaly", "")
            ar_tree.insert("", "end", values=(r.get("index", ""), dt,
                                               f"{r.get('volume', 0):.6f}",
                                               f"{r.get('temp1', 0):.2f}",
                                               f"{r.get('temp2', 0):.2f}",
                                               "да" if r.get("integrity_ok", True) else "НЕТ",
                                               anomaly),
                           tags=("bad",) if anomaly else ())
        summary = state.get("history_archive_summary", {})
        if summary:
            ar_info.config(text=(f"Записей: {summary.get('count',0)} · Δ={summary.get('delta_volume',0):.6f} м³ · "
                                 f"аномалий: {summary.get('anomalies',0)} · показано: {len(visible)}"),
                           foreground="#c0392b" if summary.get("anomalies") else "#0a7d0a")

    def hist_fill(data):
        cp_tree.delete(*cp_tree.get_children()); ev_tree.delete(*ev_tree.get_children())
        ar_tree.delete(*ar_tree.get_children())
        if state_mod:
            try:
                base, recs = state_mod.parse_dump(data)
                for r in recs:
                    t = r['datetime'].strftime('%Y-%m-%d %H:%M') if r['datetime'] else '—'
                    ok = r['valid'] and abs(r['volume'] - r['volume_copy']) <= 1e-9
                    cp_tree.insert("", "end",
                                   values=(r['index'], t, f"{r['volume']:.6f}",
                                           f"{r['temp1']:.2f}", f"{r['temp2']:.2f}",
                                           "да" if ok else "НЕТ"),
                                   tags=() if ok else ("bad",))
                state["history_checkpoint"] = recs
                cp_info.config(text=f"Активная половина 0x{base:06X} · записей: {len(recs)}")
            except Exception as e:
                cp_info.config(text=f"Чекпоинт не найден в дампе: {e}")
        if evlog_mod:
            try:
                seen = evlog_mod.parse(data)
                for cnt, (t, code, txt) in sorted(seen.items()):
                    dt = datetime.datetime.utcfromtimestamp(t).strftime('%Y-%m-%d %H:%M:%S')
                    note = evlog_mod.KNOWN.get(txt) or evlog_mod.CODE_NAMES.get(code, "")
                    ev_tree.insert("", "end", values=(cnt, dt, f"0x{code:04X}", txt, note))
                state["history_events"] = sorted(seen.items())
                ev_info.config(text=f"Журнал 0x15E000 · записей: {len(seen)}")
            except Exception as e:
                ev_info.config(text=f"Журнал не разобран: {e}")
        if state_mod:
            try:
                archive = state_mod.parse_archive(data)
                archive, summary = state_mod.analyse_timeline(archive)
                state["history_archive"] = archive
                state["history_archive_summary"] = summary
                refresh_archive_tree()
            except Exception as e:
                ar_info.config(text=f"Главный архив не разобран: {e}")

    def hist_load_path(p):
        try:
            data = open(p, "rb").read()
        except Exception as e:
            hist_path.config(text=f"ошибка: {e}"); return
        hist_path.config(text=f"{os.path.basename(p)} · {len(data)} байт")
        hist_fill(data)

    def hist_load():
        p = filedialog.askopenfilename(filetypes=[("dump W25Q64", "*.bin"), ("все", "*.*")])
        if p:
            hist_load_path(p)

    def hist_export():
        if not (state.get("history_checkpoint") or state.get("history_archive") or
                state.get("history_events")):
            append("warn", "[история] нет данных для экспорта."); return
        p = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")],
                                         initialfile="history_export.csv")
        if not p:
            return
        with open(p, "w", encoding="utf-8-sig", newline="") as stream:
            w = csv.writer(stream)
            w.writerow(["section", "index", "datetime_utc", "value", "temp1", "temp2", "code", "note"])
            for r in state.get("history_checkpoint", []):
                dt = r["datetime"].isoformat(sep=" ") if r.get("datetime") else ""
                ok = r.get("valid") and abs(r.get("volume", 0) - r.get("volume_copy", 0)) <= 1e-9
                w.writerow(["checkpoint", r.get("index"), dt, r.get("volume"),
                            r.get("temp1"), r.get("temp2"), "", "integrity=ok" if ok else "integrity=bad"])
            for r in state.get("history_archive", []):
                dt = r["datetime"].isoformat(sep=" ") if r.get("datetime") else ""
                w.writerow(["archive", r.get("index"), dt, r.get("volume"),
                            r.get("temp1"), r.get("temp2"), "", ""])
            for cnt, (ts, code, txt) in state.get("history_events", []):
                dt = datetime.datetime.utcfromtimestamp(ts).isoformat(sep=" ")
                note = (evlog_mod.KNOWN.get(txt) or evlog_mod.CODE_NAMES.get(code, "")) if evlog_mod else ""
                w.writerow(["event", cnt, dt, txt, "", "", f"0x{code:04X}", note])
        append("ok", f"[история] экспортировано → {p}")

    def hist_compare():
        """Сравнить текущий загруженный дамп со вторым дампом."""
        if not state.get("history_archive"):
            append("warn", "[история] сначала загрузи основной дамп.")
            return
        p = filedialog.askopenfilename(
            title="Выбери второй дамп для сравнения",
            filetypes=[("dump W25Q64", "*.bin"), ("все", "*.*")])
        if not p:
            return
        try:
            data2 = open(p, "rb").read()
        except Exception as e:
            append("err", f"[сравнение] ошибка чтения: {e}"); return
        if state_mod is None:
            append("err", "[сравнение] модуль smt_state.py не найден"); return
        try:
            archive2 = state_mod.parse_archive(data2)
            archive2, summary2 = state_mod.analyse_timeline(archive2)
        except Exception as e:
            append("err", f"[сравнение] ошибка разбора второго дампа: {e}"); return
        base_archive = state.get("history_archive", [])
        base_by_idx = {r.get("index"): r for r in base_archive}
        diff_count = 0; added = 0; removed = 0
        compare_win = tk.Toplevel(root)
        compare_win.title(f"Сравнение архивов · {os.path.basename(p)}")
        compare_win.geometry("1000x500")
        cmp_cols = ("idx", "dt_base", "vol_base", "dt_cmp", "vol_cmp", "status")
        cmp_tree = ttk.Treeview(compare_win, columns=cmp_cols, show="headings")
        for c, t, w in (("idx", "#", 55), ("dt_base", "Время (основной)", 155),
                        ("vol_base", "Показания (осн.)", 120),
                        ("dt_cmp", "Время (сравн.)", 155),
                        ("vol_cmp", "Показания (ср.)", 120),
                        ("status", "Статус", 100)):
            cmp_tree.heading(c, text=t); cmp_tree.column(c, width=w, anchor="w")
        cmp_tree.tag_configure("changed", foreground="#c0392b")
        cmp_tree.tag_configure("added", foreground="#0a7d0a")
        cmp_tree.tag_configure("removed", foreground="#999")
        csb = ttk.Scrollbar(compare_win, orient="vertical", command=cmp_tree.yview)
        cmp_tree.configure(yscrollcommand=csb.set)
        cmp_tree.pack(side="left", fill="both", expand=True)
        csb.pack(side="right", fill="y")
        cmp_by_idx = {r.get("index"): r for r in archive2}
        all_idx = sorted(set(base_by_idx.keys()) | set(cmp_by_idx.keys()))
        for idx in all_idx:
            b = base_by_idx.get(idx)
            c = cmp_by_idx.get(idx)
            dt_b = b["datetime"].strftime("%Y-%m-%d %H:%M:%S") if b and b.get("datetime") else "—"
            dt_c = c["datetime"].strftime("%Y-%m-%d %H:%M:%S") if c and c.get("datetime") else "—"
            vol_b = f"{b.get('volume', 0):.6f}" if b else "—"
            vol_c = f"{c.get('volume', 0):.6f}" if c else "—"
            if b and c:
                if abs(b.get("volume", 0) - c.get("volume", 0)) > 1e-6:
                    status = "ИЗМЕНЕНО"; diff_count += 1; tag = ("changed",)
                else:
                    status = "совпадает"; tag = ()
            elif b and not c:
                status = "только осн."; removed += 1; tag = ("removed",)
            else:
                status = "только ср."; added += 1; tag = ("added",)
            cmp_tree.insert("", "end", values=(idx, dt_b, vol_b, dt_c, vol_c, status), tags=tag)
        ttk.Label(compare_win,
                  text=f"Записей: основной {len(base_archive)}, сравниваемый {len(archive2)} · "
                       f"изменено: {diff_count} · только в осн.: {removed} · "
                       f"только в ср.: {added}",
                  foreground="#c0392b" if diff_count else "#0a7d0a").pack(fill="x", pady=4)
        append("ok", f"[сравнение] загружен {os.path.basename(p)}: "
                     f"{len(archive2)} записей, различий: {diff_count}")

    # ── вкладка «Снимки · сценарии · мониторинг» ───────────────────────
    ttk.Label(tab_lab, wraplength=1160, foreground="#555", justify="left",
              text="Инженерная работа с реальным прибором: полный READ-аудит каталога, "
                   "экспорт и сравнение снимков, проверяемые пакетные сценарии и "
                   "периодический мониторинг параметров по активному физическому каналу."
              ).pack(anchor="w")

    lab_pan = ttk.Panedwindow(tab_lab, orient="horizontal"); lab_pan.pack(fill="both", expand=True, pady=4)
    snap_frame = ttk.Labelframe(lab_pan, text="Снимок всех 160 команд", padding=5)
    lab_pan.add(snap_frame, weight=3)
    work_frame = ttk.Frame(lab_pan, padding=(5, 0, 0, 0)); lab_pan.add(work_frame, weight=2)

    snap_bar = ttk.Frame(snap_frame); snap_bar.pack(fill="x")
    scan_btn = ttk.Button(snap_bar, text="Аудит всех 160 команд",
                          command=lambda: task_q.put({"op": "scan_all"}))
    scan_btn.pack(side="left")
    ttk.Button(snap_bar, text="Стоп", command=backend.cancel_current).pack(side="left", padx=3)
    scan_var = tk.DoubleVar(value=0)
    scan_progress = ttk.Progressbar(snap_bar, variable=scan_var, maximum=max(1, len(catalog)))
    scan_progress.pack(side="left", fill="x", expand=True, padx=6)
    scan_label = ttk.Label(snap_bar, text="0/160"); scan_label.pack(side="left")

    snap_cols = ("name", "current", "reference", "status")
    snap_tree = ttk.Treeview(snap_frame, columns=snap_cols, show="headings", height=16)
    for c, t, w in (("name", "Команда", 170), ("current", "Текущий снимок", 180),
                    ("reference", "Эталон / загруженный", 180), ("status", "Сравнение", 90)):
        snap_tree.heading(c, text=t); snap_tree.column(c, width=w, anchor="w")
    snap_tree.tag_configure("changed", foreground="#c0392b")
    snap_tree.tag_configure("same", foreground="#0a7d0a")
    snap_tree.tag_configure("error", foreground="#b00")
    snap_sb = ttk.Scrollbar(snap_frame, orient="vertical", command=snap_tree.yview)
    snap_tree.configure(yscrollcommand=snap_sb.set)
    snap_tree.pack(side="left", fill="both", expand=True, pady=5); snap_sb.pack(side="left", fill="y", pady=5)

    snap_actions = ttk.Frame(snap_frame); snap_actions.pack(fill="x", side="bottom")
    loaded_lbl = ttk.Label(snap_actions, text="эталон не загружен", foreground="#777")
    loaded_lbl.pack(side="left")

    def refresh_snapshot_tree():
        snap_tree.delete(*snap_tree.get_children())
        current = state.get("current_snapshot", {})
        reference = state.get("loaded_snapshot", {})
        names = sorted(set(current) | set(reference))
        for name in names:
            a = current.get(name, "<нет>"); b = reference.get(name, "<нет>")
            if not reference:
                status = "—"; tags = ("error",) if str(a).startswith("<err:") else ()
            elif str(a) == str(b):
                status = "совпадает"; tags = ("same",)
            else:
                status = "ИЗМЕНЕНО"; tags = ("changed",)
            snap_tree.insert("", "end", values=(name, a, b if reference else "", status), tags=tags)

    def save_snapshot(ext):
        values = state.get("current_snapshot", {})
        if not values:
            append("warn", "[снимок] сначала выполни полный опрос."); return
        if tools_mod is None:
            append("err", "[снимок] smt_tools.py не найден."); return
        p = filedialog.asksaveasfilename(defaultextension=ext,
                                         filetypes=[("JSON", "*.json"), ("CSV", "*.csv")],
                                         initialfile=f"snapshot_{datetime.datetime.now():%Y%m%d_%H%M%S}{ext}")
        if not p:
            return
        if p.lower().endswith(".csv"):
            tools_mod.save_snapshot_csv(p, values)
        else:
            tools_mod.save_snapshot_json(p, values, source=state.get("mode", "unknown"),
                                         meta={"catalog_count": len(catalog)})
        append("ok", f"[снимок] сохранено {len(values)} параметров → {p}")

    def load_reference():
        if tools_mod is None:
            append("err", "[снимок] smt_tools.py не найден."); return
        p = filedialog.askopenfilename(filetypes=[("Снимки", "*.json *.csv"), ("все", "*.*")])
        if not p:
            return
        try:
            state["loaded_snapshot"] = tools_mod.load_snapshot(p)
            loaded_lbl.config(text=f"эталон: {os.path.basename(p)} · {len(state['loaded_snapshot'])}")
            refresh_snapshot_tree()
            append("ok", f"[снимок] загружен эталон: {p}")
        except Exception as exc:
            append("err", f"[снимок] ошибка загрузки: {exc}")

    def export_coverage():
        values = state.get("current_snapshot", {})
        if not values:
            append("warn", "[покрытие] сначала выполни полный опрос."); return
        if tools_mod is None:
            append("err", "[покрытие] smt_tools.py не найден."); return
        matrix = tools_mod.build_coverage_matrix(catalog, values, actions)
        summary = tools_mod.coverage_summary(matrix)
        p = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV", "*.csv")],
            initialfile=f"coverage_{datetime.datetime.now():%Y%m%d_%H%M%S}.csv")
        if p:
            tools_mod.export_coverage_csv(p, matrix)
            append("ok", f"[покрытие] {summary['ok']}/{summary['total']} команд "
                         f"({summary['coverage_pct']}%) → {p}")

    ttk.Button(snap_actions, text="Матрица покрытия…", command=export_coverage).pack(side="right")
    ttk.Button(snap_actions, text="Экспорт JSON…", command=lambda: save_snapshot(".json")).pack(side="right")
    ttk.Button(snap_actions, text="Экспорт CSV…", command=lambda: save_snapshot(".csv")).pack(side="right", padx=3)
    ttk.Button(snap_actions, text="Загрузить эталон…", command=load_reference).pack(side="right", padx=3)

    # Пакетные сценарии
    batch_frame = ttk.Labelframe(work_frame, text="Пакетный сценарий", padding=5)
    batch_frame.pack(fill="both", expand=True)
    batch_text = scrolledtext.ScrolledText(batch_frame, height=11, wrap="none", font=("TkFixedFont", 9))
    batch_text.pack(fill="both", expand=True)
    batch_text.insert("1.0", """# Пример сценария работы с прибором v4.6
READ DevInfo
READ DEVICE_SN
STORE sn=DEVICE_SN
PRINT Серийник: ${sn}

# Циклический опрос: 5 раз через 1 секунду
LOOP 5
  READ Volume
  READ STATUS_SYSTEM
  SLEEP 1000
ENDLOOP

# Повтор одной команды
REPEAT 3
READ VOLUME_INST

# Условная логика по значению переменной
STORE vol=Volume
IF ${vol} > 100
  PRINT Показание высокое: ${vol}
ELSE
  PRINT Показание: ${vol}
ENDIF

# Критические ACTION/SET — только в Экспертном режиме
# SET LCD_TIME=15
# ACTION VALVE_OPEN
""")
    batch_status = ttk.Label(batch_frame, text="готов", foreground="#555"); batch_status.pack(anchor="w")
    batch_bar = ttk.Frame(batch_frame); batch_bar.pack(fill="x")
    ttk.Button(batch_bar, text="Проверить", command=lambda: task_q.put(
        {"op": "batch", "text": batch_text.get("1.0", "end"), "expert": state["expert"],
         "dry_run": True})).pack(side="left")
    ttk.Button(batch_bar, text="Выполнить", command=lambda: task_q.put(
        {"op": "batch", "text": batch_text.get("1.0", "end"), "expert": state["expert"],
         "dry_run": False})).pack(side="left", padx=3)
    ttk.Button(batch_bar, text="Стоп", command=backend.cancel_current).pack(side="left")

    def batch_load():
        p = filedialog.askopenfilename(filetypes=[("SMT script", "*.smt *.txt"), ("все", "*.*")])
        if p:
            batch_text.delete("1.0", "end"); batch_text.insert("1.0", open(p, encoding="utf-8").read())
    def batch_save():
        p = filedialog.asksaveasfilename(defaultextension=".smt", filetypes=[("SMT script", "*.smt")])
        if p:
            open(p, "w", encoding="utf-8").write(batch_text.get("1.0", "end"))
    ttk.Button(batch_bar, text="Открыть…", command=batch_load).pack(side="right")
    ttk.Button(batch_bar, text="Сохранить…", command=batch_save).pack(side="right", padx=3)

    # Мониторинг
    mon_frame = ttk.Labelframe(work_frame, text="Периодический мониторинг", padding=5)
    mon_frame.pack(fill="both", expand=True, pady=(6, 0))
    mon_ctl = ttk.Frame(mon_frame); mon_ctl.pack(fill="x")
    mon_names_var = tk.StringVar(value="Volume,VOLUME_INST,STATUS_SYSTEM,STATUS_ALARM")
    ttk.Entry(mon_ctl, textvariable=mon_names_var).pack(side="left", fill="x", expand=True)
    ttk.Label(mon_ctl, text="интервал, с:").pack(side="left", padx=(5, 1))
    mon_interval_var = tk.StringVar(value="2")
    ttk.Entry(mon_ctl, textvariable=mon_interval_var, width=5).pack(side="left")
    mon_status = ttk.Label(mon_ctl, text="○", foreground="#777"); mon_status.pack(side="left", padx=4)

    mon_tree = ttk.Treeview(mon_frame, columns=("ts", "name", "value"), show="headings", height=7)
    for c, t, w in (("ts", "Время", 145), ("name", "Параметр", 140), ("value", "Значение", 170)):
        mon_tree.heading(c, text=t); mon_tree.column(c, width=w, anchor="w")
    mon_tree.pack(fill="both", expand=True, pady=4)

    def monitor_tick():
        if not state.get("monitoring"):
            return
        for name in state.get("monitor_names", []):
            task_q.put({"op": "read", "name": name})
        try:
            ms = max(250, int(float(mon_interval_var.get().replace(",", ".")) * 1000))
        except ValueError:
            ms = 2000
        state["monitor_after"] = root.after(ms, monitor_tick)

    def monitor_start():
        names = [x.strip() for x in mon_names_var.get().replace(";", ",").split(",") if x.strip()]
        if not names:
            append("warn", "[мониторинг] укажи хотя бы один параметр."); return
        bad = [name for name in names if name in actions]
        if bad:
            append("err", "[мониторинг] действия нельзя опрашивать циклически: " + ", ".join(bad)); return
        state["monitor_names"] = names; state["monitoring"] = True
        mon_status.config(text="●", foreground="#0a7d0a")
        monitor_tick()

    def monitor_stop():
        state["monitoring"] = False; mon_status.config(text="○", foreground="#777")
        aid = state.pop("monitor_after", None)
        if aid:
            with contextlib.suppress(Exception): root.after_cancel(aid)

    def monitor_export():
        if not state.get("monitor_rows"):
            append("warn", "[мониторинг] данных пока нет."); return
        p = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if p:
            with open(p, "w", encoding="utf-8-sig", newline="") as stream:
                w = csv.writer(stream); w.writerow(["timestamp", "command", "value"])
                w.writerows(state["monitor_rows"])
            append("ok", f"[мониторинг] экспорт → {p}")

    mon_buttons = ttk.Frame(mon_frame); mon_buttons.pack(fill="x")
    ttk.Button(mon_buttons, text="Старт", command=monitor_start).pack(side="left")
    ttk.Button(mon_buttons, text="Стоп", command=monitor_stop).pack(side="left", padx=3)
    ttk.Button(mon_buttons, text="Экспорт CSV…", command=monitor_export).pack(side="right")
    ttk.Button(mon_buttons, text="Очистить", command=lambda: (
        mon_tree.delete(*mon_tree.get_children()), state["monitor_rows"].clear())).pack(side="right", padx=3)

    # ── вкладка «Сервис · статус · бэкап» ────────────────────────────────
    svc_pan = ttk.Panedwindow(tab_service, orient="vertical")
    svc_pan.pack(fill="both", expand=True)

    # ── 1. Панель статусов устройства ──────────────────────────────────
    status_frame = ttk.Labelframe(svc_pan, text="Статус устройства — расшифровка регистров", padding=5)
    svc_pan.add(status_frame, weight=2)
    status_bar = ttk.Frame(status_frame); status_bar.pack(fill="x")
    ttk.Button(status_bar, text="Считать статусы",
               command=lambda: task_q.put({"op": "read_status"})).pack(side="left")
    ttk.Button(status_bar, text="Очистить вид",
               command=lambda: _status_clear()).pack(side="left", padx=4)

    def _do_clear_all_alarms():
        if not state["expert"]:
            messagebox.showwarning("Сброс тревог", "Включи Экспертный режим.")
            return
        if not messagebox.askyesno(
                "Сброс всех тревог",
                "Отправить на прибор:\n"
                "  WARNING_CLEAR\n  ALARM_CLEAR\n  CRASH_CLEAR\n\n"
                "Все активные флаги будут сброшены. Продолжить?",
                parent=root):
            return
        for cmd in ("WARNING_CLEAR", "ALARM_CLEAR", "CRASH_CLEAR"):
            task_q.put({"op": "send", "text": cmd, "expert": True})
        root.after(1500, lambda: task_q.put({"op": "read_status"}))

    ttk.Button(status_bar, text="Сбросить все тревоги",
               command=_do_clear_all_alarms).pack(side="left", padx=6)
    status_summary_lbl = ttk.Label(status_bar, text="—", foreground="#555")
    status_summary_lbl.pack(side="left", padx=10)

    status_panels = {}
    status_grid = ttk.Frame(status_frame); status_grid.pack(fill="both", expand=True, pady=4)
    for col_idx in range(4):
        status_grid.columnconfigure(col_idx, weight=1)
    status_grid.rowconfigure(0, weight=1)

    status_titles = {"STATUS_SYSTEM": "SYSTEM", "STATUS_WARNING": "WARNING",
                     "STATUS_ALARM": "ALARM", "STATUS_CRASH": "CRASH"}
    for col_idx, sname in enumerate(STATUS_NAMES):
        frame = ttk.Labelframe(status_grid, text=status_titles[sname], padding=3)
        frame.grid(row=0, column=col_idx, sticky="nsew", padx=2)
        val_lbl = ttk.Label(frame, text="—", font=("TkFixedFont", 10, "bold"))
        val_lbl.pack(anchor="w")
        bits_frame = ttk.Frame(frame)
        bits_frame.pack(fill="both", expand=True)
        status_panels[sname] = {"val_lbl": val_lbl, "bits_frame": bits_frame, "bit_labels": []}

    def _status_clear():
        for sname, panel in status_panels.items():
            panel["val_lbl"].config(text="—", foreground="#555")
            for w in panel["bit_labels"]:
                w.destroy()
            panel["bit_labels"].clear()
        status_summary_lbl.config(text="—", foreground="#555")

    def _status_render(data):
        total_active = 0
        max_severity = "ok"
        for sname, panel in status_panels.items():
            for w in panel["bit_labels"]:
                w.destroy()
            panel["bit_labels"].clear()
            raw_val = data.get(sname, "")
            if raw_val.startswith("<err:"):
                panel["val_lbl"].config(text=raw_val, foreground="#c0392b")
                continue
            panel["val_lbl"].config(text=f"0x{raw_val}" if raw_val else "—",
                                    foreground="#555")
            bits = decode_status_bits(sname, raw_val)
            for bit, label, severity, is_set in bits:
                color = STATUS_COLORS.get(severity if is_set else "ok", "#555")
                marker = "●" if is_set else "○"
                lbl = ttk.Label(panel["bits_frame"],
                                text=f"{marker} {bit}: {label}",
                                foreground=color)
                lbl.pack(anchor="w")
                panel["bit_labels"].append(lbl)
                if is_set:
                    total_active += 1
                    if severity == "err":
                        max_severity = "err"
                    elif severity == "warn" and max_severity != "err":
                        max_severity = "warn"
        if total_active == 0:
            status_summary_lbl.config(text="Все регистры в норме", foreground="#0a7d0a")
        else:
            status_summary_lbl.config(
                text=f"Активных флагов: {total_active}",
                foreground=STATUS_COLORS.get(max_severity, "#555"))

    # ── 1b. Редактор KFACTOR ─────────────────────────────────────────────
    kf_frame = ttk.Labelframe(svc_pan, text="KFACTOR — поправочный коэффициент расхода", padding=5)
    svc_pan.add(kf_frame, weight=1)
    kf_bar = ttk.Frame(kf_frame); kf_bar.pack(fill="x")
    ttk.Label(kf_bar, text="Текущий:").pack(side="left")
    kf_current_lbl = ttk.Label(kf_bar, text="—", font=("TkFixedFont", 10, "bold"),
                                foreground="#555")
    kf_current_lbl.pack(side="left", padx=4)
    ttk.Button(kf_bar, text="Считать",
               command=lambda: task_q.put({"op": "read", "name": "KFACTOR"})
               ).pack(side="left", padx=6)
    ttk.Label(kf_bar, text="Новое значение:").pack(side="left", padx=(12, 2))
    kf_val_var = tk.StringVar(value="1.0")
    ttk.Entry(kf_bar, textvariable=kf_val_var, width=12).pack(side="left", padx=2)

    def _do_write_kfactor():
        if not state["expert"]:
            messagebox.showwarning("KFACTOR", "Включи Экспертный режим.")
            return
        if not state.get("provider_verified"):
            messagebox.showwarning("KFACTOR",
                "Сначала выполни авторизацию Provider (PASSWORD_PROVIDER).")
            return
        val = kf_val_var.get().strip()
        if not val:
            return
        if not messagebox.askyesno(
                "Запись KFACTOR",
                f"Записать KFACTOR = {val}?\n\n"
                "Поправочный коэффициент пересчёта импульсов в объём.\n"
                "После записи будет выполнен read-back для подтверждения.",
                parent=root):
            return
        task_q.put({"op": "write_kfactor", "value": val, "expert": True})

    ttk.Button(kf_bar, text="Записать (Provider)", command=_do_write_kfactor
               ).pack(side="left", padx=6)
    kf_status_lbl = ttk.Label(kf_bar, text="", foreground="#555")
    kf_status_lbl.pack(side="left", padx=6)
    # ── ползунок: как меняется расход при изменении KFACTOR ──────────────
    kf_calc = ttk.Frame(kf_frame); kf_calc.pack(fill="x", pady=(6, 0))
    ttk.Label(kf_calc, text="Базовый KFACTOR:").pack(side="left")
    kf_base_var = tk.StringVar(value="1.0")
    kf_base_ent = ttk.Entry(kf_calc, textvariable=kf_base_var, width=10)
    kf_base_ent.pack(side="left", padx=2)
    ttk.Button(kf_calc, text="← Текущий",
               command=lambda: kf_base_var.set(kf_current_lbl.cget("text"))
                               if kf_current_lbl.cget("text") not in ("—", "")
                               else None).pack(side="left", padx=2)

    kf_slider_frame = ttk.Frame(kf_frame); kf_slider_frame.pack(fill="x", pady=(2, 0))
    kf_slider_var = tk.DoubleVar(value=0.0)
    kf_pct_lbl = ttk.Label(kf_slider_frame, text="Изменение: 0.00%",
                            font=("TkFixedFont", 11, "bold"), foreground="#555",
                            width=22)
    kf_pct_lbl.pack(side="left")
    kf_new_lbl = ttk.Label(kf_slider_frame, text="→ KFACTOR = 1.000000",
                            font=("TkFixedFont", 10), foreground="#555")
    kf_new_lbl.pack(side="left", padx=8)
    kf_flow_lbl = ttk.Label(kf_slider_frame, text="",
                             font=("TkFixedFont", 9), foreground="#555")
    kf_flow_lbl.pack(side="left", padx=8)
    ttk.Button(kf_slider_frame, text="→ Записать это",
               command=lambda: kf_val_var.set(kf_new_lbl.cget("text").split("= ")[-1])
               ).pack(side="right")

    kf_slider = tk.Scale(kf_frame, from_=-50.0, to=50.0, resolution=0.01,
                          orient="horizontal", variable=kf_slider_var,
                          showvalue=False, length=400)
    kf_slider.pack(fill="x", pady=(0, 2))

    kf_marks = ttk.Frame(kf_frame); kf_marks.pack(fill="x")
    for pct_text, anchor in (("−50%", "w"), ("−25%", "w"), ("0%", "center"),
                              ("+25%", "e"), ("+50%", "e")):
        ttk.Label(kf_marks, text=pct_text, foreground="#999",
                  font=("TkFixedFont", 7)).pack(side="left", expand=True, anchor=anchor)

    def _kf_slider_update(*_):
        pct = kf_slider_var.get()
        try:
            base = float(kf_base_var.get().replace(",", ".").strip().rstrip(";"))
        except (ValueError, AttributeError):
            base = 1.0
        if base <= 0:
            base = 1.0
        new_kf = base * (1.0 + pct / 100.0)
        if new_kf < 0:
            new_kf = 0.0
        if pct > 0:
            color = "#c0392b"
            arrow = "▲"
        elif pct < 0:
            color = "#2980b9"
            arrow = "▼"
        else:
            color = "#0a7d0a"
            arrow = "—"
        kf_pct_lbl.config(text=f"Изменение: {pct:+.2f}%", foreground=color)
        kf_new_lbl.config(text=f"→ KFACTOR = {new_kf:.6f}", foreground=color)
        example_vol = 1000.0
        new_vol = example_vol * (1.0 + pct / 100.0)
        kf_flow_lbl.config(
            text=f"{arrow} Было 1000 м³ → станет {new_vol:.2f} м³ (Δ {new_vol - example_vol:+.2f})",
            foreground=color)

    kf_slider_var.trace_add("write", _kf_slider_update)
    kf_base_var.trace_add("write", _kf_slider_update)
    _kf_slider_update()

    ttk.Label(kf_frame, foreground="#8a4b08", wraplength=1100, justify="left",
              text="Ползунок показывает влияние изменения KFACTOR на расход в %. "
                   "Формула: Объём = Импульсы × KFACTOR. Кнопка «→ Записать это» "
                   "переносит рассчитанное значение в поле записи. "
                   "Также доступен KALMAN_K (фильтр Калмана) — через вкладку «Команды»."
              ).pack(anchor="w", pady=(3, 0))

    # ── 2. Чтение архива по оптопорту ──────────────────────────────────
    arc_frame = ttk.Labelframe(svc_pan, text="Архив устройства — чтение по оптопорту", padding=5)
    svc_pan.add(arc_frame, weight=3)
    arc_bar = ttk.Frame(arc_frame); arc_bar.pack(fill="x")
    ttk.Label(arc_bar, text="Последних записей:").pack(side="left")
    arc_count_var = tk.StringVar(value="20")
    ttk.Entry(arc_bar, textvariable=arc_count_var, width=6).pack(side="left", padx=3)
    ttk.Button(arc_bar, text="Считать архив",
               command=lambda: task_q.put({"op": "read_archive_port",
                                           "count": int(arc_count_var.get() or 20)})
               ).pack(side="left", padx=4)
    ttk.Button(arc_bar, text="Стоп", command=backend.cancel_current).pack(side="left")
    arc_progress_lbl = ttk.Label(arc_bar, text="—", foreground="#555")
    arc_progress_lbl.pack(side="left", padx=8)

    def arc_export():
        rows = state.get("archive_port_records", [])
        if not rows:
            append("warn", "[архив] нет данных для экспорта."); return
        p = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV", "*.csv")],
            initialfile=f"archive_{datetime.datetime.now():%Y%m%d_%H%M%S}.csv")
        if not p:
            return
        with open(p, "w", encoding="utf-8-sig", newline="") as stream:
            w = csv.writer(stream)
            w.writerow(["index", "data"])
            for r in rows:
                w.writerow([r.get("index", ""), r.get("data", "")])
        append("ok", f"[архив] экспортировано {len(rows)} записей → {p}")

    ttk.Button(arc_bar, text="Экспорт CSV…", command=arc_export).pack(side="right")

    arc_tree = ttk.Treeview(arc_frame, columns=("idx", "data"), show="headings", height=8)
    arc_tree.heading("idx", text="#"); arc_tree.column("idx", width=60, anchor="w")
    arc_tree.heading("data", text="Данные записи"); arc_tree.column("data", width=900, anchor="w")
    arc_tree.tag_configure("err", foreground="#c0392b")
    arc_sb = ttk.Scrollbar(arc_frame, orient="vertical", command=arc_tree.yview)
    arc_tree.configure(yscrollcommand=arc_sb.set)
    arc_tree.pack(side="left", fill="both", expand=True, pady=4)
    arc_sb.pack(side="left", fill="y", pady=4)
    state["archive_port_records"] = []

    def _arc_render(data):
        arc_tree.delete(*arc_tree.get_children())
        records = data.get("records", [])
        state["archive_port_records"] = records
        for r in records:
            tags = ("err",) if str(r.get("data", "")).startswith("<err:") else ()
            arc_tree.insert("", "end", values=(r.get("index", ""), r.get("data", "")), tags=tags)
        total = data.get("total", 0)
        arc_progress_lbl.config(
            text=f"Записей в архиве: {total} · показано: {len(records)}",
            foreground="#0a7d0a" if records else "#555")

    # ── 3. Резервное копирование и восстановление ──────────────────────
    bak_frame = ttk.Labelframe(svc_pan, text="Резервное копирование / восстановление параметров", padding=5)
    svc_pan.add(bak_frame, weight=2)
    bak_bar = ttk.Frame(bak_frame); bak_bar.pack(fill="x")
    ttk.Button(bak_bar, text="Считать все параметры",
               command=lambda: task_q.put({"op": "backup"})).pack(side="left")
    ttk.Button(bak_bar, text="Стоп", command=backend.cancel_current).pack(side="left", padx=3)
    bak_progress_lbl = ttk.Label(bak_bar, text="—", foreground="#555")
    bak_progress_lbl.pack(side="left", padx=8)
    state["backup_params"] = {}

    def bak_save():
        params = state.get("backup_params", {})
        if not params:
            append("warn", "[бэкап] сначала считай параметры с прибора."); return
        p = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON backup", "*.json")],
            initialfile=f"backup_{datetime.datetime.now():%Y%m%d_%H%M%S}.json")
        if not p:
            return
        backup = {
            "type": "smt_backup",
            "version": "4.10.0",
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
            "count": len(params),
            "params": params,
        }
        with open(p, "w", encoding="utf-8") as stream:
            json.dump(backup, stream, ensure_ascii=False, indent=2)
        append("ok", f"[бэкап] сохранено {len(params)} параметров → {p}")

    def bak_load_and_restore():
        if not state["expert"]:
            messagebox.showwarning("Восстановление", "Включи Экспертный режим.")
            return
        p = filedialog.askopenfilename(filetypes=[("JSON backup", "*.json"), ("все", "*.*")])
        if not p:
            return
        try:
            with open(p, encoding="utf-8") as stream:
                data = json.load(stream)
        except Exception as exc:
            append("err", f"[восстановление] ошибка чтения: {exc}"); return
        params = data.get("params", {})
        if not params:
            append("warn", "[восстановление] файл не содержит параметров."); return
        if not messagebox.askyesno(
                "Восстановление параметров",
                f"Записать {len(params)} параметров из файла?\n{os.path.basename(p)}\n\n"
                "Критичные параметры (пароли, объёмы, актуатор) будут записаны "
                "только при наличии экспертного режима и авторизации.",
                parent=root):
            return
        task_q.put({"op": "restore", "params": params, "expert": state["expert"]})

    ttk.Button(bak_bar, text="Сохранить в файл…", command=bak_save).pack(side="right")
    ttk.Button(bak_bar, text="Загрузить и восстановить…",
               command=bak_load_and_restore).pack(side="right", padx=3)

    bak_tree = ttk.Treeview(bak_frame, columns=("name", "value"), show="headings", height=8)
    bak_tree.heading("name", text="Параметр"); bak_tree.column("name", width=200, anchor="w")
    bak_tree.heading("value", text="Значение"); bak_tree.column("value", width=500, anchor="w")
    bak_sb = ttk.Scrollbar(bak_frame, orient="vertical", command=bak_tree.yview)
    bak_tree.configure(yscrollcommand=bak_sb.set)
    bak_tree.pack(side="left", fill="both", expand=True, pady=4)
    bak_sb.pack(side="left", fill="y", pady=4)

    def _bak_render(params):
        bak_tree.delete(*bak_tree.get_children())
        state["backup_params"] = params
        for name in sorted(params):
            bak_tree.insert("", "end", values=(name, params[name]))
        bak_progress_lbl.config(text=f"Считано {len(params)} параметров",
                                foreground="#0a7d0a")

    # ── 4. Настройка GSM-модема (APN/GPRS) ──────────────────────────────
    gsm_frame = ttk.Labelframe(svc_pan, text="Настройка GSM-модема — APN / GPRS", padding=5)
    svc_pan.add(gsm_frame, weight=2)
    gsm_bar = ttk.Frame(gsm_frame); gsm_bar.pack(fill="x")
    ttk.Label(gsm_bar, text="APN:").pack(side="left")
    gsm_apn_var = tk.StringVar(value="internet")
    ttk.Entry(gsm_bar, textvariable=gsm_apn_var, width=18).pack(side="left", padx=2)
    ttk.Label(gsm_bar, text="логин:").pack(side="left", padx=(6, 2))
    gsm_user_var = tk.StringVar()
    ttk.Entry(gsm_bar, textvariable=gsm_user_var, width=12).pack(side="left", padx=2)
    ttk.Label(gsm_bar, text="пароль:").pack(side="left", padx=(6, 2))
    gsm_pass_var = tk.StringVar()
    ttk.Entry(gsm_bar, textvariable=gsm_pass_var, width=12, show="•").pack(side="left", padx=2)

    def _do_gsm_init():
        if state.get("mode") != "sms":
            messagebox.showwarning("GSM", "Сначала подключись через GSM/SMS транспорт.")
            return
        apn = gsm_apn_var.get().strip()
        if not apn:
            messagebox.showwarning("GSM", "Укажи имя точки доступа (APN).")
            return
        task_q.put({"op": "gsm_init_apn", "apn": apn,
                    "user": gsm_user_var.get().strip(),
                    "password": gsm_pass_var.get()})

    ttk.Button(gsm_bar, text="Инициализировать GPRS",
               command=_do_gsm_init).pack(side="left", padx=8)
    gsm_status_lbl = ttk.Label(gsm_bar, text="", foreground="#555")
    gsm_status_lbl.pack(side="left", padx=4)

    gsm_tree = ttk.Treeview(gsm_frame, columns=("cmd", "desc", "resp", "status"),
                             show="headings", height=6)
    for c, t, w in (("cmd", "AT-команда", 250), ("desc", "Описание", 200),
                    ("resp", "Ответ", 350), ("status", "Статус", 60)):
        gsm_tree.heading(c, text=t); gsm_tree.column(c, width=w, anchor="w")
    gsm_tree.tag_configure("fail", foreground="#c0392b")
    gsm_sb = ttk.Scrollbar(gsm_frame, orient="vertical", command=gsm_tree.yview)
    gsm_tree.configure(yscrollcommand=gsm_sb.set)
    gsm_tree.pack(side="left", fill="both", expand=True, pady=4)
    gsm_sb.pack(side="left", fill="y", pady=4)
    ttk.Label(gsm_frame, foreground="#555", wraplength=1100, justify="left",
              text="Последовательность: AT → SIM → CSTT (APN) → CIICR (PDP) → CIFSR (IP) → "
                   "CSQ (сигнал) → CREG (сеть) → CGATT (GPRS). "
                   "Типичные APN: internet, internet.mts.ru, internet.beeline.ru, internet.tele2.ru"
              ).pack(anchor="w", side="bottom")

    def _gsm_render(results):
        gsm_tree.delete(*gsm_tree.get_children())
        ok_count = sum(1 for r in results if r.get("ok"))
        for r in results:
            tags = () if r.get("ok") else ("fail",)
            gsm_tree.insert("", "end", values=(
                r.get("cmd", ""), r.get("desc", ""),
                r.get("response", ""), "OK" if r.get("ok") else "ОШИБКА"), tags=tags)
        gsm_status_lbl.config(
            text=f"Выполнено {ok_count}/{len(results)} шагов",
            foreground="#0a7d0a" if ok_count == len(results) else "#c47f00")

    # ── лог: вкладки «Журнал» и «Сырые байты (hex)» ─────────────────────
    nb = ttk.Notebook(root); nb.pack(fill="both", expand=False)
    tab_log = ttk.Frame(nb, padding=2); nb.add(tab_log, text="Журнал сессии")
    log = scrolledtext.ScrolledText(tab_log, height=12, wrap="word", font=("TkFixedFont", 9))
    log.pack(fill="both", expand=True)
    for tag, col in (("ok", "#0a7d0a"), ("err", "#b00"), ("warn", "#c47f00")):
        log.tag_configure(tag, foreground=col)

    tab_hex = ttk.Frame(nb, padding=2)
    nb.add(tab_hex, text="Сырые байты (hex) — для сверки кадра/CRC")
    hexlog = scrolledtext.ScrolledText(tab_hex, height=12, wrap="none", font=("TkFixedFont", 9))
    hexlog.pack(fill="both", expand=True)
    hexlog.tag_configure("tx", foreground="#0a5"); hexlog.tag_configure("rx", foreground="#05a")

    # Полный диагностический журнал: все UI-действия, фоновые задачи, TX/RX и ошибки.
    tab_diag = ttk.Frame(nb, padding=3)
    nb.add(tab_diag, text="Диагностика · все действия")
    diag_filter = ttk.Frame(tab_diag); diag_filter.pack(fill="x", pady=(0, 3))
    ttk.Label(diag_filter, text="Фильтр:").pack(side="left")
    diag_filter_var = tk.StringVar()
    diag_filter_ent = ttk.Entry(diag_filter, textvariable=diag_filter_var, width=36)
    diag_filter_ent.pack(side="left", padx=3)
    diag_count_lbl = ttk.Label(diag_filter, text="0 событий")
    diag_count_lbl.pack(side="left", padx=6)
    diag_path_lbl = ttk.Label(diag_filter, text=diagnostic.jsonl_path, foreground="#555")
    diag_path_lbl.pack(side="right")

    diag_pane = ttk.Panedwindow(tab_diag, orient="vertical"); diag_pane.pack(fill="both", expand=True)
    diag_top = ttk.Frame(diag_pane); diag_bottom = ttk.Frame(diag_pane)
    diag_pane.add(diag_top, weight=3); diag_pane.add(diag_bottom, weight=2)
    diag_tree = ttk.Treeview(
        diag_top, columns=("seq", "ts", "component", "action", "status", "duration"),
        show="headings", height=8)
    for col, title, width in (
        ("seq", "#", 62), ("ts", "Время", 185), ("component", "Компонент", 105),
        ("action", "Действие", 220), ("status", "Статус", 80), ("duration", "мс", 80)):
        diag_tree.heading(col, text=title); diag_tree.column(col, width=width, anchor="w")
    diag_scroll = ttk.Scrollbar(diag_top, orient="vertical", command=diag_tree.yview)
    diag_tree.configure(yscrollcommand=diag_scroll.set)
    diag_tree.pack(side="left", fill="both", expand=True); diag_scroll.pack(side="right", fill="y")
    diag_detail = scrolledtext.ScrolledText(diag_bottom, height=7, wrap="none", font=("TkFixedFont", 9))
    diag_detail.pack(fill="both", expand=True)

    def diag_matches(event):
        query = diag_filter_var.get().strip().lower()
        if not query:
            return True
        return query in json.dumps(event, ensure_ascii=False).lower()

    def diag_render_event(event):
        iid = str(event.get("seq", len(state["diagnostic_events"]) + 1))
        duration = event.get("duration_ms", "")
        diag_tree.insert("", "end", iid=iid, values=(
            event.get("seq", ""), event.get("ts", ""), event.get("component", ""),
            event.get("action", ""), event.get("status", ""), duration))

    def diag_rebuild(*_):
        diag_tree.delete(*diag_tree.get_children())
        for event in state.get("diagnostic_events", []):
            if diag_matches(event):
                diag_render_event(event)
        diag_count_lbl.config(text=f"{len(state.get('diagnostic_events', []))} событий")

    def diag_select(_event=None):
        selected = diag_tree.selection()
        if not selected:
            return
        seq = int(selected[0])
        event = next((x for x in state.get("diagnostic_events", []) if int(x.get("seq", -1)) == seq), None)
        if event is None:
            return
        diag_detail.delete("1.0", "end")
        diag_detail.insert("1.0", json.dumps(event, ensure_ascii=False, indent=2))

    diag_tree.bind("<<TreeviewSelect>>", diag_select)
    diag_filter_var.trace_add("write", diag_rebuild)

    def diag_export_csv():
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV", "*.csv")],
            initialfile=f"diagnostic_{datetime.date.today()}.csv")
        if not path:
            return
        try:
            rows = diagnostic.export_csv(path)
            append("ok", f"[диагностика] экспортировано {rows} событий → {path}")
        except Exception as exc:
            append("err", f"[диагностика] ошибка экспорта: {exc}")

    def diag_save_jsonl_copy():
        path = filedialog.asksaveasfilename(
            defaultextension=".jsonl", filetypes=[("JSON Lines", "*.jsonl")],
            initialfile=os.path.basename(diagnostic.jsonl_path))
        if path:
            import shutil
            shutil.copy2(diagnostic.jsonl_path, path)
            append("ok", f"[диагностика] копия JSONL → {path}")

    def diag_clear_view():
        diag_tree.delete(*diag_tree.get_children()); diag_detail.delete("1.0", "end")
        state["diagnostic_events"].clear()
        diag_count_lbl.config(text="0 событий (файл продолжает записываться)")
        diagnostic.emit("gui", "diagnostic.view.clear", status="ok")

    ttk.Button(diag_filter, text="Экспорт CSV…", command=diag_export_csv).pack(side="right", padx=3)
    ttk.Button(diag_filter, text="Копия JSONL…", command=diag_save_jsonl_copy).pack(side="right", padx=3)
    ttk.Button(diag_filter, text="Очистить вид", command=diag_clear_view).pack(side="right", padx=3)

    # ── статистика сессии TX/RX ───────────────────────────────────
    stats_bar = ttk.Frame(root, padding=(6, 2)); stats_bar.pack(fill="x")
    stats_lbl = ttk.Label(stats_bar, text="TX: 0 · RX: 0 · ошибок: 0 · avg: 0 мс", foreground="#555")
    stats_lbl.pack(side="left")

    def _update_stats(data):
        tx = data.get("tx_bytes", 0)
        rx = data.get("rx_bytes", 0)
        errs = data.get("errors", 0)
        avg = data.get("latency_avg_ms", 0)
        mx = data.get("latency_max_ms", 0)
        n = data.get("tx_count", 0)
        up = int(data.get("uptime_s", 0))
        m, s = divmod(up, 60)
        h, m = divmod(m, 60)
        time_str = f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
        stats_lbl.config(
            text=f"TX: {tx} б ({n} ком.) · RX: {rx} б · ошибок: {errs} · "
                 f"avg {avg:.0f} мс · max {mx:.0f} мс · {time_str}",
            foreground="#c0392b" if errs else "#555")

    logbar = ttk.Frame(root); logbar.pack(fill="x")
    def save_log():
        p = filedialog.asksaveasfilename(defaultextension=".txt",
                                         initialfile=f"session_{datetime.date.today()}.txt")
        if p:
            open(p, "w", encoding="utf-8").write(log.get("1.0", "end"))
    def save_hex():
        p = filedialog.asksaveasfilename(defaultextension=".txt",
                                         initialfile=f"hex_{datetime.date.today()}.txt")
        if p:
            open(p, "w", encoding="utf-8").write(hexlog.get("1.0", "end"))
    ttk.Button(logbar, text="Сохранить лог…", command=save_log).pack(side="right")
    ttk.Button(logbar, text="Сохранить hex…", command=save_hex).pack(side="right", padx=6)
    ttk.Button(logbar, text="Очистить", command=lambda: (log.delete("1.0", "end"),
               hexlog.delete("1.0", "end"))).pack(side="right")

    # ── вкладка «Дамп W25Q64 · пароли» ───────────────────────────────────
    dump_pan = ttk.Panedwindow(tab_dump, orient="vertical")
    dump_pan.pack(fill="both", expand=True)

    # Вспомогательные функции для работы с дампом
    EVT_R0, EVT_R1 = 0x15E000, 0x171000
    EVENT_CODES = {
        0x020F: ("PASSWORD_PROVIDER", "пароль провайдера", "password"),
        0x0220: ("PASSWORD_OMEGA", "пароль omega", "password"),
        0x02B7: ("PASSWORD_OMEGA", "пароль omega", "password"),
        0x023C: ("ACCESS_LEVEL", "байт уровня доступа", "level"),
        0x026B: ("ACCESS_LEVEL", "байт уровня доступа", "level"),
    }
    LEVEL_CODES = {"f": 0x66, "F": 0x66, "U": 0x55, "u": 0x55, "0": 0x00}
    LEVEL_NAMES = {0x66: "заводской (f)", 0x55: "omega (U)", 0x00: "гость"}

    def u32(data, offset):
        return struct.unpack_from("<I", data, offset)[0]

    def u16(data, offset):
        return struct.unpack_from("<H", data, offset)[0]

    def _iter_journal(data):
        """Единый обход журнала (как в smt_eventlog.parse): при валидной записи
        шаг 0x10, при промахе — 0x04 с ПОВТОРНЫМ выравниванием. И чтение, и запись
        обязаны использовать один обход, иначе запись «уезжает» из фазы и не
        попадает в реальные записи. Отдаёт (offset, ts, cnt, code, val_start, val_end).
        """
        o = EVT_R0
        limit = min(EVT_R1, len(data))
        while o < limit - 16:
            try:
                ts = u32(data, o)
                cnt = u32(data, o + 0x08)
            except struct.error:
                o += 4
                continue
            if not (100_000_000 < ts < 4_000_000_000) or cnt >= 100000:
                o += 4
                continue
            code = u16(data, o + 0x0C)
            vs = o + 0x0E
            ve = data.find(b"\0", vs, min(limit, vs + 48))
            if ve < 0:
                ve = min(limit, vs + 48)
            yield o, ts, cnt, code, vs, ve
            o += 0x10

    def _write_value_inplace(data, vs, ve, new_bytes):
        """Безопасно заменяет значение записи на месте: пишет new_bytes + \\0 и
        обнуляет остаток СТАРОГО значения только в пределах [vs, ve) — не заходя
        в следующую запись."""
        n = len(new_bytes)
        for i, b in enumerate(new_bytes):
            if vs + i < len(data):
                data[vs + i] = b
        if vs + n < len(data):
            data[vs + n] = 0                      # терминатор
        for i in range(vs + n + 1, ve):           # затираем хвост старого значения
            if i < len(data):
                data[i] = 0

    def scan_dump_journal(dump):
        """Сканирует журнал событий и возвращает пароли и уровни."""
        passwords, levels = [], []
        for o, ts, cnt, code, vs, ve in _iter_journal(dump):
            raw = bytes(dump[vs:ve])
            text = raw.decode("ascii", errors="replace") if raw else ""
            if code in EVENT_CODES:
                cmd, human, kind = EVENT_CODES[code]
                entry = {"offset": o, "timestamp": ts, "counter": cnt, "code": code,
                         "command": cmd, "value": text, "kind": kind}
                if kind == "password":
                    passwords.append(entry)
                elif kind == "level":
                    try:
                        level_byte = int(text)
                        entry["level_byte"] = level_byte
                        entry["level_name"] = LEVEL_NAMES.get(level_byte, "?")
                        levels.append(entry)
                    except ValueError:
                        pass
        return passwords, levels

    def set_password_dump(dump, command, new_password):
        """Меняет пароль ВО ВСЕХ записях журнала (для omega — оба кода)."""
        if not new_password:
            raise ValueError("Пароль не задан")
        if len(new_password) > 48:
            raise ValueError("Пароль не должен быть длиннее 48 символов")
        target_codes = {code for code, (cmd, _, _) in EVENT_CODES.items() if cmd == command}
        if not target_codes:
            raise ValueError(f"Команда {command} не найдена")
        data = bytearray(dump)
        nb = new_password.encode("ascii")
        changed = 0
        for o, ts, cnt, code, vs, ve in _iter_journal(data):
            if code in target_codes:
                _write_value_inplace(data, vs, ve, nb)
                changed += 1
        return bytes(data), changed

    def set_level_dump(dump, level_char):
        """Меняет уровень доступа во всех записях журнала."""
        if level_char not in LEVEL_CODES:
            raise ValueError(f"Неизвестный уровень: {level_char}. Допустимы: f, U, 0")
        level_byte = LEVEL_CODES[level_char]
        data = bytearray(dump)
        nb = str(level_byte).encode("ascii")
        changed = 0
        for o, ts, cnt, code, vs, ve in _iter_journal(data):
            if code in (0x023C, 0x026B):
                _write_value_inplace(data, vs, ve, nb)
                changed += 1
        return bytes(data), changed

    def deep_search_omega(dump):
        """Ищет ОТКРЫТУЮ omega по всему образу, а не только в кольце журнала.

        Проходит весь файл и собирает записи с кодами omega (0x0220/0x02B7)
        с валидными меткой времени/счётчиком, отбирая значения без звёздочек.
        Возвращает (открытые_значения, всего_записей_omega).
        """
        clear, total = [], 0
        limit = len(dump)
        o = 0
        while o < limit - 16:
            try:
                code = u16(dump, o + 0x0C)
                if code in (0x0220, 0x02B7):
                    ts = u32(dump, o)
                    cnt = u32(dump, o + 0x08)
                    if 100_000_000 < ts < 4_000_000_000 and cnt < 100000:
                        total += 1
                        vs = o + 0x0E
                        ve = dump.find(b"\0", vs, min(limit, vs + 48))
                        if ve < 0:
                            ve = min(limit, vs + 48)
                        val = dump[vs:ve].decode("ascii", errors="replace")
                        if val and "*" not in val and val not in clear:
                            clear.append(val)
            except (struct.error, ValueError):
                pass
            o += 4  # плотный проход по всему образу
        return clear, total

    # ── UI для работы с дампом ─────────────────────────────────────────────
    steps_frame = ttk.Frame(dump_pan)
    dump_pan.add(steps_frame, weight=0)
    ttk.Label(steps_frame, foreground="#2c3e50", justify="left", wraplength=1080,
        font=("TkDefaultFont", 9),
        text="Порядок работы:  1) «Обзор…» выбери файл дампа  →  2) «Загрузить»  →  "
             "3) смотри, что нашлось  →  4) впиши новый пароль или выбери уровень  →  "
             "5) «Применить изменения»  →  6) «Сохранить дамп…».\n"
             "Всё текстом, вручную байты вводить не нужно. Работаем с файлом .bin, "
             "прибор при этом не трогается."
        ).pack(anchor="w", padx=2, pady=(2, 4))

    dump_file_frame = ttk.Labelframe(dump_pan, text="Шаг 1–2. Файл дампа", padding=5)
    dump_pan.add(dump_file_frame, weight=0)

    dump_file_bar = ttk.Frame(dump_file_frame)
    dump_file_bar.pack(fill="x")
    dump_file_var = tk.StringVar(value="")
    dump_file_ent = ttk.Entry(dump_file_bar, textvariable=dump_file_var)
    dump_file_ent.pack(side="left", fill="x", expand=True, padx=2)

    def browse_dump():
        path = filedialog.askopenfilename(filetypes=[("W25Q64 dump", "*.bin"), ("все", "*.*")])
        if path:
            dump_file_var.set(path)
            dump_state["path"] = path
            dump_state["data"] = None
            dump_state["modified"] = False
            refresh_dump_display()

    ttk.Button(dump_file_bar, text="Обзор…", command=browse_dump).pack(side="left", padx=2)

    def load_dump_file():
        path = dump_file_var.get().strip()
        if not path or not os.path.exists(path):
            messagebox.showerror("Дамп", "Укажи путь к файлу дампа.")
            return
        try:
            with open(path, "rb") as f:
                dump_state["data"] = f.read()
            dump_state["modified"] = False
            refresh_dump_display()
            append("ok", f"[дамп] загружен {len(dump_state['data'])} байт из {path}")
        except Exception as e:
            messagebox.showerror("Дамп", f"Ошибка загрузки: {e}")

    ttk.Button(dump_file_bar, text="Загрузить", command=load_dump_file).pack(side="left", padx=2)

    dump_state = {"path": "", "data": None, "modified": False}

    # ── результаты сканирования ───────────────────────────────────────────
    result_frame = ttk.Labelframe(dump_pan, text="Шаг 3. Что нашлось в дампе", padding=5)
    dump_pan.add(result_frame, weight=2)

    result_text = scrolledtext.ScrolledText(result_frame, height=12, wrap="word")
    result_text.pack(fill="both", expand=True)
    result_text.configure(state="disabled")

    def refresh_dump_display():
        result_text.configure(state="normal")
        result_text.delete("1.0", "end")
        if dump_state["data"] is None:
            result_text.insert("end", "Дамп не загружен. Укажи путь и нажми «Загрузить».", "io")
            result_text.configure(state="disabled")
            return
        try:
            pwds, lvls = scan_dump_journal(dump_state["data"])

            # значение считаем «замаскированным», если в нём есть звёздочки
            def _masked(v):
                return bool(v) and "*" in v
            def _clear(v):
                return bool(v) and "*" not in v

            # Заполняем «Сейчас в дампе». Для omega предпочитаем ОТКРЫТУЮ копию;
            # если открытой нет, честно пишем, что прибор хранит её замаскированной.
            prov_vals = [p["value"] for p in pwds if p["command"] == "PASSWORD_PROVIDER" and p["value"]]
            omega_all = [p["value"] for p in pwds if p["command"] == "PASSWORD_OMEGA" and p["value"]]
            omega_clear = [v for v in omega_all if _clear(v)]
            omega_masked = [v for v in omega_all if _masked(v)]
            with contextlib.suppress(Exception):
                cur_provider_var.set(prov_vals[0] if prov_vals else "не найдено")
                if omega_clear:
                    cur_omega_var.set(omega_clear[0])
                elif omega_masked:
                    cur_omega_var.set("скрыт прибором (******)")
                else:
                    cur_omega_var.set("не найдено")
                cur_level_var.set(lvls[0]["level_name"] if lvls else "не найдено")

            result_text.insert("end", "Что нашлось в журнале образа (это уже в дампе):\n\n", "ok")
            if pwds:
                result_text.insert("end", f"🔑 Пароли — {len(pwds)} записей в журнале:\n", "ok")
                shown = set()
                for pwd in pwds:
                    key = (pwd["command"], pwd["value"])
                    if key in shown:
                        continue
                    shown.add(key)
                    human = {"PASSWORD_PROVIDER": "провайдера", "PASSWORD_OMEGA": "omega"}.get(
                        pwd["command"], pwd["command"])
                    note = "   ← скрыт самим прибором" if _masked(pwd["value"]) else ""
                    result_text.insert("end",
                        f"   пароль {human:10} = {pwd['value']!r}{note}\n", "io")
                if omega_all and not omega_clear:
                    result_text.insert("end",
                        "\n   ⓘ omega хранится в журнале ЗАМАСКИРОВАННОЙ (******) — это делает "
                        "сама прошивка,\n      открытого значения в дампе нет, восстановить его из "
                        "образа нельзя.\n      Пароль провайдера (выше) прибор пишет открыто. "
                        "Можно задать новую omega\n      ниже — она запишется открытым текстом.\n", "warn")
            else:
                result_text.insert("end", "🔑 Пароли не найдены (возможно, template-дамп без конфига)\n", "warn")

            if lvls:
                result_text.insert("end", f"\n🛡 Уровень доступа — {len(lvls)} записей:\n", "ok")
                shown = set()
                for lev in lvls:
                    if lev["level_name"] in shown:
                        continue
                    shown.add(lev["level_name"])
                    result_text.insert("end", f"   уровень = {lev['level_name']}\n", "io")
            else:
                result_text.insert("end", "\n🛡 Уровень доступа не найден\n", "warn")

            if dump_state["modified"]:
                result_text.insert("end",
                    "\n⚠ В памяти есть несохранённые изменения — нажми «Сохранить дамп…»", "err")
        except Exception as e:
            result_text.insert("end", f"Ошибка сканирования: {e}", "err")
        result_text.configure(state="disabled")

    result_text.tag_config("ok", foreground="#0a7d0a")
    result_text.tag_config("warn", foreground="#c47f00")
    result_text.tag_config("err", foreground="#c0392b")
    result_text.tag_config("io", foreground="#555")

    # ── редактирование паролей и уровня (по-человечески, без байтов) ──────
    edit_frame = ttk.Labelframe(
        dump_pan, text="Шаг 4–5. Что можно изменить (понятным языком)", padding=6)
    dump_pan.add(edit_frame, weight=0)

    ttk.Label(edit_frame, foreground="#555", wraplength=1080, justify="left",
        text="Здесь меняются только те значения, что прибор реально хранит в журнале "
             "образа. Вводишь текст в обычные поля — байты/адреса программа проставит сама. "
             "Пустое поле = не менять. Адрес сервера и APN тут НЕ правятся (их нет в дампе) — "
             "они меняются на подключённом приборе во вкладке «Команды»."
        ).pack(anchor="w", pady=(0, 4))
    ttk.Label(edit_frame, foreground="#c0392b", wraplength=1080, justify="left",
        text="⚠ Заводской ПАРОЛЬ (PASSWORD_FABRIC) в дампе НЕ хранится (прошивка не пишет его "
             "в журнал) — офлайн его сменить нельзя, только на живом приборе: «Команды» → "
             "PASSWORD_FABRIC. Ниже «Уровень доступа» со словом «заводской» — это НЕ пароль, "
             "а один байт уровня."
        ).pack(anchor="w", pady=(0, 6))

    # Текущие значения из дампа (заполняются при сканировании)
    cur_provider_var = tk.StringVar(value="—")
    cur_omega_var = tk.StringVar(value="—")
    cur_level_var = tk.StringVar(value="—")

    edit_grid = ttk.Frame(edit_frame)
    edit_grid.pack(fill="x", pady=2)
    edit_grid.columnconfigure(2, weight=1)

    # шапка колонок
    ttk.Label(edit_grid, text="Параметр", font=("TkDefaultFont", 9, "bold")
              ).grid(row=0, column=0, sticky="w", padx=2)
    ttk.Label(edit_grid, text="Сейчас в дампе", font=("TkDefaultFont", 9, "bold")
              ).grid(row=0, column=1, sticky="w", padx=6)
    ttk.Label(edit_grid, text="Новое значение", font=("TkDefaultFont", 9, "bold")
              ).grid(row=0, column=2, sticky="w", padx=2)

    def _mk_row(r, title, cur_var, hint):
        ttk.Label(edit_grid, text=title).grid(row=r, column=0, sticky="w", padx=2, pady=(4, 0))
        ttk.Label(edit_grid, textvariable=cur_var, foreground="#0a7d0a",
                  font=("TkFixedFont", 9)).grid(row=r, column=1, sticky="w", padx=6, pady=(4, 0))
        ttk.Label(edit_grid, text=hint, foreground="#999", wraplength=1040, justify="left"
                  ).grid(row=r + 1, column=0, columnspan=3, sticky="w", padx=2)

    # Пароль провайдера
    _mk_row(1, "🔑 Пароль провайдера", cur_provider_var,
            "Что вписывать: РОВНО 6 символов — обычно 6 цифр, например  123456  или  000111. "
            "Это новый сервисный пароль, запишется открытым текстом во все копии журнала.")
    provider_var = tk.StringVar()
    prov_box = ttk.Frame(edit_grid); prov_box.grid(row=1, column=2, sticky="w", padx=2, pady=(4, 0))
    ttk.Entry(prov_box, textvariable=provider_var, width=16).pack(side="left")
    prov_len_lbl = ttk.Label(prov_box, text="0/6", foreground="#999", width=5)
    prov_len_lbl.pack(side="left", padx=3)

    # Пароль omega
    _mk_row(3, "🔑 Пароль omega", cur_omega_var,
            "Что вписывать: РОВНО 6 символов — цифры и/или латинские буквы, например  654321  или  AB12CD. "
            "Старую omega прибор хранит скрытой (******) и показать её нельзя — но ты можешь задать "
            "здесь НОВУЮ, она запишется открытым текстом.")
    omega_var = tk.StringVar()
    omega_box = ttk.Frame(edit_grid); omega_box.grid(row=3, column=2, sticky="w", padx=2, pady=(4, 0))
    ttk.Entry(omega_box, textvariable=omega_var, width=16).pack(side="left")
    omega_len_lbl = ttk.Label(omega_box, text="0/6", foreground="#999", width=5)
    omega_len_lbl.pack(side="left", padx=3)

    # живой счётчик длины: зелёный при ровно 6 символах
    def _upd_len(var, lbl):
        n = len(var.get().strip())
        lbl.config(text=f"{n}/6", foreground="#0a7d0a" if n == 6 else ("#999" if n == 0 else "#c47f00"))
    provider_var.trace_add("write", lambda *_: _upd_len(provider_var, prov_len_lbl))
    omega_var.trace_add("write", lambda *_: _upd_len(omega_var, omega_len_lbl))

    # Уровень доступа — выбор из списка, без байтов
    _mk_row(5, "🛡 Уровень доступа (это НЕ пароль)", cur_level_var,
            "Один байт: каким уровнем прибор «представляется» по умолчанию. "
            "Полный (f) / Расширенный (omega, U) / Только чтение (гость). Это не пароль, "
            "а уровень — выбираешь из списка, байт проставится сам.")
    level_edit_var = tk.StringVar(value="(не менять)")
    ttk.Combobox(edit_grid, textvariable=level_edit_var, state="readonly", width=26,
                 values=["(не менять)", "Полный — f (заводской уровень)",
                         "Расширенный — U (omega)", "Только чтение — гость"]
                 ).grid(row=5, column=2, sticky="w", padx=2, pady=(4, 0))

    # выбор уровня из списка → символ кода уровня
    _LEVEL_LABEL_TO_CODE = {
        "Полный — f (заводской уровень)": "f",
        "Расширенный — U (omega)": "U",
        "Только чтение — гость": "0",
    }

    def apply_changes():
        if dump_state["data"] is None:
            messagebox.showwarning("Дамп", "Сначала загрузи файл дампа.")
            return

        # Собираем план изменений в человеческом виде для подтверждения
        plan = []          # (краткое_описание, действие)
        new_provider = provider_var.get().strip()
        new_omega = omega_var.get().strip()
        level_choice = level_edit_var.get()
        level_code = _LEVEL_LABEL_TO_CODE.get(level_choice)

        # Прошивка принимает пароль ровно из 6 символов — проверяем заранее
        for label, val in (("провайдера", new_provider), ("omega", new_omega)):
            if val and len(val) != 6:
                messagebox.showwarning(
                    "Проверь длину пароля",
                    f"Пароль {label} = {val!r} содержит {len(val)} символов.\n\n"
                    "Нужно РОВНО 6 символов (цифры и/или латинские буквы),\n"
                    "например 123456 или AB12CD.\n\n"
                    "Прибор пароль другой длины не примет. Исправь и попробуй снова.")
                return

        if new_provider:
            plan.append((f"Пароль провайдера:  {cur_provider_var.get()}  →  {new_provider}",
                         ("password", "PASSWORD_PROVIDER", new_provider)))
        if new_omega:
            plan.append((f"Пароль omega:  {cur_omega_var.get()}  →  {new_omega}",
                         ("password", "PASSWORD_OMEGA", new_omega)))
        if level_code:
            new_level_name = LEVEL_NAMES.get(LEVEL_CODES[level_code], "?")
            plan.append((f"Уровень доступа:  {cur_level_var.get()}  →  {new_level_name}",
                         ("level", level_code, None)))

        if not plan:
            messagebox.showinfo("Дамп",
                "Ничего не выбрано для изменения.\n\n"
                "Впиши новый пароль в поле или выбери уровень из списка.")
            return

        # Подтверждение с понятным «что произойдёт»
        if not messagebox.askyesno(
                "Подтверждение изменений дампа",
                "Будут изменены значения ВО ВСЕХ копиях журнала образа:\n\n"
                + "\n".join(f"  • {desc}" for desc, _ in plan)
                + "\n\nСам прибор не затрагивается — меняется только файл. "
                  "После этого нужно нажать «Сохранить дамп…».\n\nПродолжить?",
                parent=root):
            return

        data = dump_state["data"]
        changed_items = []
        total_changed = 0
        try:
            for desc, (kind, arg, val) in plan:
                if kind == "password":
                    data, changed = set_password_dump(data, arg, val)
                    append("ok", f"[дамп] {arg} изменён в {changed} копиях")
                else:
                    data, changed = set_level_dump(data, arg)
                    append("ok", f"[дамп] уровень доступа изменён в {changed} копиях")
                dump_state["data"] = data
                total_changed += changed
                mark = "" if changed else "  ⚠ НЕ найдено записей!"
                changed_items.append(f"{desc}   ({changed} копий){mark}")

            if total_changed == 0:
                # ничего не совпало — не вводим в заблуждение «успехом»
                dump_state["data"] = data
                refresh_dump_display()
                messagebox.showwarning("Ничего не изменено",
                    "В журнале образа не нашлось ни одной записи для правки:\n\n"
                    + "\n".join(f"  • {c}" for c in changed_items)
                    + "\n\nВозможно, это template-дамп без сохранённого конфига, "
                      "или значения хранятся вне журнала. Файл не менялся.")
                return

            dump_state["modified"] = True
            # очистим поля ввода, чтобы не применить повторно
            provider_var.set(""); omega_var.set(""); level_edit_var.set("(не менять)")
            refresh_dump_display()
            messagebox.showinfo("Готово — изменения внесены в память",
                "Изменено:\n\n" + "\n".join(f"  • {c}" for c in changed_items)
                + "\n\n⚠ Файл ещё не записан на диск — нажми «Сохранить дамп…».")
        except Exception as e:
            messagebox.showerror("Дамп — ошибка", f"Ошибка при применении: {e}")

    def do_deep_omega():
        if dump_state["data"] is None:
            messagebox.showwarning("Дамп", "Сначала загрузи файл дампа.")
            return
        clear, total = deep_search_omega(dump_state["data"])
        if clear:
            cur_omega_var.set(clear[0])
            append("ok", f"[дамп] глубокий поиск: открытая omega = {clear[0]!r}")
            messagebox.showinfo("Поиск omega по всему образу",
                "Найдены ОТКРЫТЫЕ значения omega в образе:\n\n"
                + "\n".join(f"  • {v}" for v in clear)
                + f"\n\nВсего записей omega просмотрено: {total}.")
        else:
            append("warn", f"[дамп] глубокий поиск: открытая omega не найдена ({total} записей, все ******)")
            messagebox.showwarning("Поиск omega по всему образу",
                f"Открытого значения omega в образе нет.\n\n"
                f"Просмотрено записей omega: {total} — все замаскированы прибором (******).\n\n"
                "Прошивка НЕ хранит omega открытым текстом, поэтому восстановить старый "
                "пароль из дампа невозможно. Пароль провайдера при этом читается открыто.\n\n"
                "Выход: задать НОВУЮ omega в поле выше и «Применить» — она запишется открыто.")

    def do_dump_diag():
        """Диагностика прямо в GUI: где лежит пароль, есть ли копии вне журнала,
        меняется ли значение round-trip. Ничего не портит — работает на копии."""
        if dump_state["data"] is None:
            messagebox.showwarning("Дамп", "Сначала загрузи файл дампа.")
            return
        data = dump_state["data"]
        lines = []
        lines.append(f"Файл: {dump_file_var.get()}")
        lines.append(f"Размер: {len(data)} (0x{len(data):X})")
        lines.append("")
        # 1) записи журнала
        pwds, lvls = scan_dump_journal(data)
        lines.append("── 1) ЗАПИСИ В ЖУРНАЛЕ (адрес · код · значение) ──")
        if not pwds and not lvls:
            lines.append("   (ничего не найдено — возможно, template-дамп)")
        prov_clear = None
        for p in pwds:
            mark = " (скрыт ******)" if "*" in p["value"] else ""
            lines.append(f"   0x{p['offset']:06X}  {p['command']:17} = {p['value']!r}{mark}")
            if p["command"] == "PASSWORD_PROVIDER" and "*" not in p["value"] and prov_clear is None:
                prov_clear = p["value"]
        for lv in lvls:
            lines.append(f"   0x{lv['offset']:06X}  ACCESS_LEVEL      = {lv['level_name']}")
        # 2) поиск пароля по всему образу
        lines.append("")
        lines.append("── 2) ПОИСК ПАРОЛЯ ПРОВАЙДЕРА ПО ВСЕМУ ОБРАЗУ ──")
        if prov_clear:
            needle = prov_clear.encode("ascii")
            hits, start = [], 0
            while True:
                i = data.find(needle, start)
                if i < 0:
                    break
                hits.append(i); start = i + 1
            inside = [i for i in hits if EVT_R0 <= i < EVT_R1]
            outside = [i for i in hits if not (EVT_R0 <= i < EVT_R1)]
            lines.append(f"   Значение {prov_clear!r}: всего вхождений {len(hits)} "
                         f"(в журнале {len(inside)}, ВНЕ журнала {len(outside)})")
            for i in outside[:20]:
                lines.append(f"     0x{i:06X}  ← ВНЕ журнала (конфиг?) — правка журнала это НЕ меняет!")
            if outside:
                lines.append("   ⚠ Есть копии вне журнала — вот почему при перечтении/на приборе "
                             "пароль остаётся старым.")
            else:
                lines.append("   ✓ Копий вне журнала нет — правки журнала достаточно.")
        else:
            lines.append("   Открытый пароль провайдера в журнале не найден.")
        # 3) тест записи round-trip на копии
        lines.append("")
        lines.append("── 3) ТЕСТ ЗАПИСИ (на копии, файл не трогаю) ──")
        try:
            test, changed = set_password_dump(data, "PASSWORD_PROVIDER", "000111")
            after = sorted({p["value"] for p in scan_dump_journal(test)[0]
                            if p["command"] == "PASSWORD_PROVIDER"})
            lines.append(f"   Заменено копий в журнале: {changed}")
            lines.append(f"   Значения провайдера после замены: {after}")
            lines.append("   → если тут ['000111'] — запись в журнал работает; проблема во "
                         "внешней копии (п.2) либо в том, что прибор читает не из журнала.")
        except Exception as exc:
            lines.append(f"   Ошибка теста: {exc}")

        # показать в отдельном окне с выделяемым текстом
        win = tk.Toplevel(root)
        win.title("Диагностика дампа W25Q64")
        win.geometry("820x520")
        txt = scrolledtext.ScrolledText(win, wrap="word", font=("TkFixedFont", 9))
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", "\n".join(lines))
        txt.configure(state="normal")
        ttk.Button(win, text="Закрыть", command=win.destroy).pack(pady=4)
        append("ok", "[дамп] диагностика выполнена (см. отдельное окно)")

    btn_frame = ttk.Frame(edit_frame)
    btn_frame.pack(fill="x", pady=(8, 2))
    ttk.Button(btn_frame, text="✓ Применить изменения (в память)",
               command=apply_changes).pack(side="left", padx=2)
    ttk.Button(btn_frame, text="🔍 Искать omega по всему образу",
               command=do_deep_omega).pack(side="left", padx=2)
    ttk.Button(btn_frame, text="🔬 Диагностика (где пароль, почему не меняется)",
               command=do_dump_diag).pack(side="left", padx=2)

    def save_dump_file():
        if dump_state["data"] is None:
            messagebox.showwarning("Дамп", "Нечего сохранять.")
            return
        path = dump_file_var.get().strip()
        if not path:
            path = filedialog.asksaveasfilename(defaultextension=".bin",
                filetypes=[("W25Q64 dump", "*.bin"), ("все", "*.*")],
                initialfile="dump_modified.bin")
            if not path:
                return
        try:
            with open(path, "wb") as f:
                f.write(dump_state["data"])
            dump_state["modified"] = False
            dump_file_var.set(path)
            append("ok", f"[дамп] сохранён {len(dump_state['data'])} байт → {path}")
            messagebox.showinfo("Дамп", f"Сохранено: {path}")
        except Exception as e:
            messagebox.showerror("Дамп", f"Ошибка сохранения: {e}")

    ttk.Button(btn_frame, text="Сохранить дамп…", command=save_dump_file).pack(side="left", padx=2)

    # ── вкладка «Аудит · Pentest» ─────────────────────────────────────────
    # Операционализация методологии «живого» пентеста без дампа: чек-лист шагов,
    # кнопки запускают УЖЕ существующие безопасные проверки backend (Recon-чтения,
    # Auth-scan на утечку секрета, полный опрос гостём), находки сводятся в отчёт.
    ttk.Label(tab_audit, foreground="#c0392b", wraplength=1150, justify="left",
        font=("TkDefaultFont", 9, "bold"),
        text="⚠ Только для АВТОРИЗОВАННОГО тестирования своего/переданного оборудования "
             "(договор, RoE). Все авто-действия здесь — штатные чтения и предъявление "
             "учётных данных, ничего разрушительного."
        ).pack(anchor="w", pady=(0, 4))

    audit_bar = ttk.Frame(tab_audit); audit_bar.pack(fill="x", pady=(0, 4))
    audit_conn_lbl = ttk.Label(audit_bar, text="○ прибор не подключён", foreground="#b00")
    audit_conn_lbl.pack(side="left")

    # Прокручиваемая область с шагами
    audit_canvas = tk.Canvas(tab_audit, highlightthickness=0)
    audit_scroll = ttk.Scrollbar(tab_audit, orient="vertical", command=audit_canvas.yview)
    audit_inner = ttk.Frame(audit_canvas)
    audit_inner.bind("<Configure>",
        lambda e: audit_canvas.configure(scrollregion=audit_canvas.bbox("all")))
    audit_canvas.create_window((0, 0), window=audit_inner, anchor="nw")
    audit_canvas.configure(yscrollcommand=audit_scroll.set)
    audit_canvas.pack(side="left", fill="both", expand=True)
    audit_scroll.pack(side="right", fill="y")

    _SEV = {"crit": ("КРИТ", "#c0392b"), "high": ("ВЫС", "#e67e22"),
            "med": ("СРЕД", "#d4a017"), "info": ("ИНФО", "#2980b9")}
    audit_rows = []   # список dict: title, sev, status_var, notes_var

    def _recon():
        if not state.get("connected"):
            messagebox.showwarning("Аудит", "Нет подключения к прибору.")
            return
        for name in ("DEVICE_SN", "HW_VERSION", "DATETIME", "Volume"):
            task_q.put({"op": "read", "name": name})
        append("ok", "[аудит] Recon: запрошены DEVICE_SN/HW_VERSION/DATETIME/Volume (см. журнал)")

    def _try_default(pwd):
        # Предъявляем дефолтный пароль провайдера штатным путём авторизации
        cred_var.set("PASSWORD_PROVIDER"); pw_var.set(pwd)
        do_auth()
        append("warn", f"[аудит] проба дефолтного пароля провайдера: {pwd} (см. статус авторизации)")

    def _open_tab(tab):
        main_nb.select(tab)

    # Определение шагов методики. auto — функция или None (ручной шаг).
    AUDIT_STEPS = [
        ("info", "1. Recon / отпечаток",
         "Гостём прочитать то, что отдаётся без авторизации: DEVICE_SN, HW_VERSION, "
         "DATETIME, показания. Цель — версия прошивки и что отвечает без пароля.",
         [("▶ Выполнить Recon", _recon)]),
        ("high", "2. Дефолтные пароли провайдера",
         "Проверить типовые заводские: 123456, 000000, 111111, 112233. Успех = "
         "дефолт не сменён (частый реальный вход).",
         [("123456", lambda: _try_default("123456")),
          ("000000", lambda: _try_default("000000")),
          ("111111", lambda: _try_default("111111")),
          ("112233", lambda: _try_default("112233"))]),
        ("crit", "3. Auth-scan — утечка секрета открытым текстом",
         "Гостём запросить PASSWORD_PROVIDER/OMEGA и др. Если прибор отдаёт значение "
         "в ответе — пароль виден без авторизации (критичная утечка F7).",
         [("▶ Запустить Auth-scan", lambda: task_q.put({"op": "authscan"}))]),
        ("crit", "4. Broken access control — матрица гостём",
         "Полный опрос всех команд гостём. Отметить: чувствительные ЧТЕНИЯ, отдающие "
         "данные, и любые ЗАПИСИ/действия, принятые прибором без авторизации.",
         [("▶ Полный опрос (гость)", lambda: task_q.put({"op": "scan_all"}))]),
        ("high", "5. Брутфорс и лок-аут",
         "Провайдер 6 знаков. Проверить: есть ли задержка/блокировка после N неверных, "
         "сбрасывается ли счётчик по питанию, отличается ли ответ «неверный» vs «нет "
         "доступа» (оракул). Проводится вручную/наблюдением.",
         []),
        ("high", "6. GSM/SMS — удалённая поверхность",
         "Принимает ли команды по SMS и с какой авторизацией? Фильтрует ли номер "
         "отправителя (белый список)? Что в APN_*, SERVER_URL, BALANCE_PHONE.",
         [("Открыть SMS-вкладку", lambda: _open_tab(tab_terminal))]),
        ("high", "7. Телеметрия — подмена сервера / MD5",
         "Поднять свой (rogue) TCP-сервер, проверить примет ли прибор ответы, стойкость "
         "MD5-ключа, replay пакетов, влияние ответа сервера на поведение.",
         [("Открыть Телеметрию", lambda: _open_tab(tab_tele))]),
        ("crit", "8. Физика: флеш / RDP",
         "При физдоступе: снять W25Q64 по SPI или через SWD; проверить RDP level STM32 "
         "(RDP0 = чтение прошивки открыто). Полученный дамп → вкладка «Дамп W25Q64».",
         [("Открыть вкладку Дамп", lambda: _open_tab(tab_dump))]),
    ]

    for sev, title, desc, actions in AUDIT_STEPS:
        row = ttk.Labelframe(audit_inner, padding=(8, 4))
        row.pack(fill="x", expand=True, padx=2, pady=3)
        head = ttk.Frame(row); head.pack(fill="x")
        sev_txt, sev_col = _SEV[sev]
        tk.Label(head, text=f" {sev_txt} ", bg=sev_col, fg="white",
                 font=("TkDefaultFont", 8, "bold")).pack(side="left", padx=(0, 6))
        ttk.Label(head, text=title, font=("TkDefaultFont", 10, "bold")).pack(side="left")
        status_var = tk.StringVar(value="не проверено")
        ttk.Combobox(head, textvariable=status_var, state="readonly", width=14,
                     values=["не проверено", "пройдено (OK)", "НАЙДЕНО (уязвимо)", "неприменимо"]
                     ).pack(side="right")
        ttk.Label(head, text="Статус:").pack(side="right", padx=4)
        ttk.Label(row, text=desc, foreground="#555", wraplength=1000, justify="left"
                  ).pack(anchor="w", pady=(2, 2))
        act = ttk.Frame(row); act.pack(fill="x")
        for label, cmd in actions:
            ttk.Button(act, text=label, command=cmd).pack(side="left", padx=2)
        notes_var = tk.StringVar()
        ttk.Label(act, text="Находка/заметка:").pack(side="left", padx=(12, 2))
        ttk.Entry(act, textvariable=notes_var).pack(side="left", fill="x", expand=True, padx=2)
        audit_rows.append({"title": title, "sev": sev_txt,
                           "status": status_var, "notes": notes_var})

    def audit_export():
        lines = ["# Отчёт пентеста — SMT Smart (контроллер СГМ)",
                 f"_Сформировано: {datetime.datetime.now():%Y-%m-%d %H:%M}_", ""]
        found = 0
        for r in audit_rows:
            st = r["status"].get()
            note = r["notes"].get().strip()
            if "НАЙДЕНО" in st:
                found += 1
            lines.append(f"## [{r['sev']}] {r['title']}")
            lines.append(f"- Статус: **{st}**")
            if note:
                lines.append(f"- Находка: {note}")
            lines.append("")
        lines.insert(2, f"**Подтверждённых уязвимостей: {found}**\n")
        path = filedialog.asksaveasfilename(
            defaultextension=".md", filetypes=[("Markdown", "*.md"), ("текст", "*.txt")],
            initialfile=f"pentest_report_{datetime.date.today()}.md")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        append("ok", f"[аудит] отчёт сохранён → {path} (найдено уязвимостей: {found})")
        messagebox.showinfo("Аудит", f"Отчёт сохранён:\n{path}\n\nПодтверждённых уязвимостей: {found}")

    ttk.Button(audit_bar, text="📄 Выгрузить отчёт (Markdown)…",
               command=audit_export).pack(side="right")

    def append(tag, text):
        diagnostic.emit("gui", "journal.line", status=tag, details={"tag": tag, "text": text})
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        log.insert("end", f"[{ts}] ", "io")
        log.insert("end", text + "\n", tag if tag in ("ok", "err", "warn") else "io")
        log.see("end")

    def append_hex(text):
        diagnostic.emit("gui", "hex.line", status="ok", details={"text": text})
        tag = "tx" if text.startswith("TX") else "rx" if text.startswith("RX") else ""
        hexlog.insert("end", text + "\n", tag)
        hexlog.see("end")

    # ── насос очереди результатов ───────────────────────────────────────
    def pump():
        try:
            while True:
                kind, payload = out_q.get_nowait()
                try:
                    if kind == "log":
                        append(*payload)
                    elif kind == "hex":
                        append_hex(payload)
                    elif kind == "reading":
                        name, value, ts = payload
                        if name == "KFACTOR" and value:
                            kf_current_lbl.config(text=value, foreground="#333")
                        if (name in COMPOUND_FIELDS and state["selected"]
                                and state["selected"]["name"] == name):
                            fill_compound_from_reading(name, value)
                        if state.get("monitoring") and name in state.get("monitor_names", []):
                            row = (ts, name, value)
                            state["monitor_rows"].append(row)
                            if len(state["monitor_rows"]) > 500:
                                state["monitor_rows"] = state["monitor_rows"][-500:]
                            mon_tree.insert("", 0, values=row)
                            while len(mon_tree.get_children()) > 500:
                                mon_tree.delete(mon_tree.get_children()[-1])
                    elif kind == "scan_progress":
                        index, total, name, value = payload
                        scan_var.set(index)
                        scan_label.config(text=f"{index}/{total} · {name}")
                    elif kind == "snapshot":
                        values, mode = payload
                        state["current_snapshot"] = values
                        state["mode"] = mode
                        refresh_snapshot_tree()
                        main_nb.select(tab_lab)
                    elif kind == "batch_progress":
                        index, total, source = payload
                        batch_status.config(text=f"{index}/{total}: {source}")
                    elif kind == "batch_done":
                        ok, done, message = payload
                        batch_status.config(text=f"{message} · шагов {done}",
                                            foreground="#0a7d0a" if ok else "#c47f00")
                    elif kind == "reading_write_done":
                        state.setdefault("readings", {})[payload.get("command", "Volume")] = payload.get("new_value", "")
                        if payload.get("verified"):
                            append("ok", "[Provider] прямой SET выполнен; read-back совпал.")
                        else:
                            append("ok", "[Provider] прямой SET отправлен без read-back.")
                    elif kind == "auth_state":
                        level = payload.get("level", "guest")
                        verified = bool(payload.get("verified"))
                        is_master = bool(payload.get("master"))
                        state["provider_verified"] = verified and level in ("provider", "fabric", "omega")
                        state["provider_verified_at"] = payload.get("verified_at", 0.0)
                        _auth_map = {
                            "fabric": ("Заводской (f)", "● Заводской (f) — мастер-ключ", "#d4a017"),
                            "omega":  ("Omega (О)",     "● Omega (U) — мастер-ключ",     "#0a7d0a"),
                            "provider":("Провайдер (П)","● Provider — нумерованный доступ","#2980b9"),
                        }
                        if verified and level in _auth_map:
                            lbl_text, auth_text, color = _auth_map[level]
                            level_var.set(lbl_text)
                            auth_lbl.config(text=auth_text, foreground=color)
                        else:
                            level_var.set("Гость")
                            auth_lbl.config(text="○ уровень не подтверждён", foreground="#777")
                    elif kind == "tele_log":
                        append(*payload)
                    elif kind == "tele_reading":
                        state["readings"] = payload
                        append("ok", "[тел] показания сняты — можно «Собрать пакет».")
                    elif kind == "tele_rx":
                        raw, rep, ip, n = payload
                        tele_in.delete("1.0", "end"); tele_in.insert("1.0", raw)
                        _tele_render(rep)
                        refresh_telemetry_db()
                        main_nb.select(tab_tele)
                        append("ok", f"[приём] пакет от {ip}: {n} записей → ACK DATA ACCEPT:{n}")
                    elif kind == "tele_state":
                        if payload == "off":
                            state["tele_srv"] = None
                            listen_status.config(text="○ не слушаю", foreground="#777")
                    elif kind == "diag_event":
                        state["diagnostic_events"].append(payload)
                        if diag_matches(payload):
                            diag_render_event(payload)
                            with contextlib.suppress(Exception):
                                diag_tree.see(str(payload.get("seq", "")))
                        diag_count_lbl.config(text=f"{len(state['diagnostic_events'])} событий")
                    elif kind == "session_stats":
                        _update_stats(payload)
                    elif kind == "status_panel":
                        _status_render(payload)
                        main_nb.select(tab_service)
                    elif kind == "archive_data":
                        _arc_render(payload)
                        main_nb.select(tab_service)
                    elif kind == "archive_progress":
                        i, total = payload
                        arc_progress_lbl.config(text=f"Чтение {i}/{total}…")
                    elif kind == "backup_data":
                        _bak_render(payload)
                        main_nb.select(tab_service)
                    elif kind == "backup_progress":
                        i, total, name = payload
                        bak_progress_lbl.config(text=f"{i}/{total}: {name}")
                    elif kind == "restore_progress":
                        i, total, name = payload
                        bak_progress_lbl.config(text=f"Запись {i}/{total}: {name}")
                    elif kind == "restore_done":
                        ok = payload.get("ok", 0)
                        total = payload.get("total", 0)
                        bak_progress_lbl.config(
                            text=f"Восстановлено {ok}/{total} параметров",
                            foreground="#0a7d0a" if ok == total else "#c47f00")
                    elif kind == "kfactor_done":
                        val = payload.get("value", "")
                        kf_current_lbl.config(text=val, foreground="#0a7d0a")
                        kf_status_lbl.config(text="Записано, read-back OK",
                                             foreground="#0a7d0a")
                    elif kind == "tele_auto_sent":
                        state["tele_auto_count"] = state.get("tele_auto_count", 0) + 1
                        n = state["tele_auto_count"]
                        ok = payload.get("ok", False)
                        auto_status_lbl.config(
                            text=f"● активно ({n} отправок)" if ok
                                 else f"● ошибка ({n} попыток)",
                            foreground="#0a7d0a" if ok else "#c47f00")
                        refresh_telemetry_db()
                    elif kind == "gsm_init_done":
                        _gsm_render(payload)
                        main_nb.select(tab_service)
                    elif kind == "session_file":
                        state["session_file"] = payload
                    elif kind == "password":
                        cred, value = payload
                        pw_var.set(value)
                        if cred in AUTH_CREDS:
                            cred_var.set(cred)
                        append("ok", f"[auto] Значение из {cred} подставлено в поле "
                                     "аутентификации (в журнале скрыто).")
                    elif kind == "raw_result":
                        raw = payload
                        append("ok", f"[RAW] получено {len(raw)} байт")
                        main_nb.select(tab_terminal)
                    elif kind == "sms_messages":
                        sms_text.delete("1.0", "end")
                        for item in payload:
                            sms_text.insert("end", f"#{item.get('index')} {item.get('header')}\n{item.get('text')}\n\n")
                        if not payload:
                            sms_text.insert("end", "Непрочитанных SMS нет.")
                        main_nb.select(tab_terminal)
                    elif kind == "status":
                        st, endpoint = payload
                        state["connected"] = st in ("serial", "tcp", "sms")
                        state["mode"] = st if state["connected"] else "off"
                        if state["connected"]:
                            names={"serial":"ОПТОПОРТ","tcp":"TCP","sms":"GSM/SMS"}
                            status_lbl.config(text=f"● {names.get(st,st)} {endpoint}", foreground="#0a7d0a")
                            conn_btn.config(text="Отключить")
                            transport_cb.state(["disabled"])
                            audit_conn_lbl.config(text=f"● подключён ({names.get(st,st)} {endpoint})",
                                                  foreground="#0a7d0a")
                        else:
                            monitor_stop()
                            state["provider_verified"] = False
                            state["provider_verified_at"] = 0.0
                            auth_lbl.config(text="○ Provider не подтверждён", foreground="#777")
                            level_var.set("Гость")
                            status_lbl.config(text="● отключено", foreground="#b00")
                            conn_btn.config(text="Подключить")
                            transport_cb.state(["!disabled"])
                            audit_conn_lbl.config(text="○ прибор не подключён", foreground="#b00")
                            update_transport_fields()
                    elif kind == "connect_error":
                        messagebox.showerror("Подключение не удалось", str(payload))
                except Exception:
                    import traceback
                    traceback.print_exc()
        except queue.Empty:
            pass
        root.after(80, pump)

    # ── меню «Сессия»: экспорт журнала работы с прибором ──
    def _open_sessions_folder():
        folder = os.path.join(HERE, "sessions")
        os.makedirs(folder, exist_ok=True)
        try:
            if sys.platform.startswith("win"):
                os.startfile(folder)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                os.system(f'open "{folder}"')
            else:
                os.system(f'xdg-open "{folder}" >/dev/null 2>&1 &')
        except Exception:
            append("warn", f"[сессия] папка журналов: {folder}")

    def _open_diagnostics_folder():
        folder = os.path.join(HERE, "diagnostics")
        os.makedirs(folder, exist_ok=True)
        diagnostic.emit("gui", "diagnostic.folder.open", status="start", details={"folder": folder})
        try:
            if sys.platform.startswith("win"):
                os.startfile(folder)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                os.system(f'open "{folder}"')
            else:
                os.system(f'xdg-open "{folder}" >/dev/null 2>&1 &')
        except Exception as exc:
            diagnostic.emit("gui", "diagnostic.folder.open", status="error", details={"folder": folder}, error=exc)
            append("warn", f"[диагностика] папка журналов: {folder}")

    def _export_session_csv():
        if not state.get("session_file"):
            append("warn", "[сессия] нет активной сессии — сначала подключись к прибору.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV", "*.csv")],
            title="Экспорт сессии в CSV")
        if path:
            task_q.put({"op": "export_session", "path": path})

    try:
        menubar = tk.Menu(root)
        sess_menu = tk.Menu(menubar, tearoff=0)
        sess_menu.add_command(label="Экспорт сессии в CSV…", command=_export_session_csv)
        sess_menu.add_command(label="Открыть папку sessions", command=_open_sessions_folder)
        sess_menu.add_separator()
        sess_menu.add_command(label="Экспорт полного диагностического CSV…", command=diag_export_csv)
        sess_menu.add_command(label="Открыть папку diagnostics", command=_open_diagnostics_folder)
        menubar.add_cascade(label="Сессия", menu=sess_menu)
        root.config(menu=menubar)
    except Exception:
        pass

    def _widget_info(widget):
        try:
            keys = set(widget.keys()) if hasattr(widget, "keys") else set()
            return {
                "path": str(widget),
                "class": widget.winfo_class(),
                "text": str(widget.cget("text")) if "text" in keys else "",
                "value": str(widget.get()) if hasattr(widget, "get") else "",
            }
        except Exception:
            return {"path": str(widget)}

    def _diag_mouse(event):
        diagnostic.emit("gui", "ui.click", status="ok", details={
            "widget": _widget_info(event.widget), "button": getattr(event, "num", 1),
            "x": getattr(event, "x", None), "y": getattr(event, "y", None),
            "x_root": getattr(event, "x_root", None), "y_root": getattr(event, "y_root", None),
        })

    def _diag_key(event):
        diagnostic.emit("gui", "ui.key", status="ok", details={
            "widget": _widget_info(event.widget), "keysym": getattr(event, "keysym", ""),
            "keycode": getattr(event, "keycode", None), "char": getattr(event, "char", ""),
            "state": getattr(event, "state", None),
        })

    def _diag_selection(event):
        diagnostic.emit("gui", "ui.selection", status="ok", details={"widget": _widget_info(event.widget)})

    root.bind_all("<ButtonRelease-1>", _diag_mouse, add="+")
    root.bind_all("<KeyPress>", _diag_key, add="+")
    root.bind_all("<<ComboboxSelected>>", _diag_selection, add="+")
    diagnostic.emit("gui", "window.ready", status="ok", details={"geometry": root.geometry(), "commands": len(catalog)})

    refill()
    root.after(80, pump)

    def on_close():
        state["monitoring"] = False
        state["tele_auto_active"] = False
        for _aid_key in ("monitor_after", "tele_auto_after"):
            aid = state.pop(_aid_key, None)
            if aid:
                with contextlib.suppress(Exception):
                    root.after_cancel(aid)
        s = state.get("tele_srv")
        if s:
            s.stop()
        task_q.put({"op": "quit"})
        backend.join(timeout=2.0)
        diagnostic.emit("gui", "window.close", status="ok")
        diagnostic.close()
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_close)

    return {"root": root, "task_q": task_q, "log": log, "state": state}


def run_selftest(port):
    """Headless read-only проверка физического порта через Backend."""
    import tkinter as tk
    root = tk.Tk(); root.withdraw()
    app = build_app(root, selftest=True)
    task_q = app["task_q"]
    steps = [
        {"op": "connect", "transport": "serial", "port": port, "baud": 9600,
         "framing": "auto", "bytesize": 8, "parity": "N", "stopbits": 1},
        {"op": "preflight"},
        {"op": "read", "name": "DEVICE_SN"},
        {"op": "read", "name": "VER_PO"},
        {"op": "read", "name": "STATUS_SYSTEM"},
    ]
    for index, task in enumerate(steps):
        root.after(200 + index * 900, lambda task=task: task_q.put(task))

    def finish():
        print("===== PHYSICAL READ-ONLY SELFTEST =====")
        print(app["log"].get("1.0", "end").rstrip())
        print("===== catalog:", len(load_catalog()), "команд =====")
        task_q.put({"op": "quit"})
        root.after(150, root.quit)

    root.after(9000, finish)
    root.mainloop()
    with contextlib.suppress(Exception):
        root.destroy()


def main():
    configure_logging()
    if "--selftest" in sys.argv:
        idx = sys.argv.index("--selftest")
        if idx + 1 >= len(sys.argv):
            print("--selftest requires a port argument", file=sys.stderr)
            return
        run_selftest(sys.argv[idx + 1]); return
    try:
        import tkinter as tk
    except Exception as e:
        sys.exit(f"Нужен tkinter (напр. пакет python3-tk): {e}")
    root = tk.Tk()
    build_app(root)
    root.mainloop()


if __name__ == "__main__":
    main()
