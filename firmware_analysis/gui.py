#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gui.py — графический интерфейс для общения с прибором MSP430FE427
по восстановленному протоколу (см. README.md и protocol.py).

Запуск:
    python3 gui.py           (или  python gui.py  в Windows)

Работает и без оборудования: если порт не открыт, кнопка «Отправить»
показывает собранный кадр и его разбор («режим просмотра»). Для реального
обмена нужен pyserial (pip install pyserial) и подключённый USB-UART (TTL 3.3 В).

Интерфейс на tkinter — он входит в стандартную библиотеку Python,
дополнительные пакеты для окна не требуются.
"""

import threading
import queue
import tkinter as tk
from tkinter import ttk, messagebox

import protocol as P


# Порядок вывода команд в выпадающем списке (сначала безопасные чтения).
CMD_ORDER = [0x53, 0x50, 0x51, 0x55, 0x63, 0x65, 0x66, 0x27, 0x28, 0x54,
             0x00, 0x40, 0x41, 0x43, 0x44, 0x46, 0x47]

MODE_TAG = {'read': '[ЧТЕНИЕ]', 'write': '[ЗАПИСЬ]', 'discovery': '[ПОИСК] '}


def preset_items():
    """Список пунктов выпадающего меню: (подпись, код, режим)."""
    out = []
    for c in CMD_ORDER:
        if c in P.COMMANDS:
            name, mode, _ = P.COMMANDS[c]
            out.append(('%s  0x%02X — %s' % (MODE_TAG[mode], c, name), c, mode))
    return out


def list_ports():
    try:
        from serial.tools import list_ports
        return [p.device for p in list_ports.comports()]
    except Exception:
        return []


class App(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=12)
        self.grid(sticky='nsew')
        master.title('MSP430FE427 — обмен по последовательному порту')
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.dev = None
        self.rx_queue = queue.Queue()
        self.presets = preset_items()
        self.label_to_cmd = {lbl: (c, m) for lbl, c, m in self.presets}

        self._build_connection()
        self._build_command()
        self._build_log()

        self.after(100, self._drain_queue)
        self._on_preset()  # инициализировать поля под первую команду

    # ---------------------------------------------------------- Соединение
    def _build_connection(self):
        box = ttk.LabelFrame(self, text='1. Соединение', padding=8)
        box.grid(row=0, column=0, sticky='ew', pady=(0, 8))
        box.columnconfigure(1, weight=1)
        box.columnconfigure(4, weight=0)

        ttk.Label(box, text='COM-порт:').grid(row=0, column=0, sticky='w')
        self.port_var = tk.StringVar()
        self.port_cb = ttk.Combobox(box, textvariable=self.port_var,
                                    values=list_ports(), width=16)
        self.port_cb.grid(row=0, column=1, sticky='ew', padx=4)
        ttk.Button(box, text='Обновить', width=9,
                   command=self._refresh_ports).grid(row=0, column=2, padx=(0, 12))

        ttk.Label(box, text='Скорость:').grid(row=0, column=3, sticky='e')
        self.baud_var = tk.StringVar(value='9600')
        ttk.Combobox(box, textvariable=self.baud_var, width=8,
                     values=['9600', '4800', '19200', '38400', '57600', '115200']
                     ).grid(row=0, column=4, sticky='w', padx=4)

        ttk.Label(box, text='Адрес прибора:').grid(row=1, column=0, sticky='w',
                                                   pady=(8, 0))
        self.addr_var = tk.StringVar(value='04 A2 CB 71')
        ttk.Entry(box, textvariable=self.addr_var).grid(
            row=1, column=1, sticky='ew', padx=4, pady=(8, 0))
        ttk.Button(box, text='Найти прибор', command=self._on_discover).grid(
            row=1, column=2, sticky='ew', pady=(8, 0))

        self.conn_btn = ttk.Button(box, text='Открыть порт',
                                   command=self._toggle_connection)
        self.conn_btn.grid(row=1, column=3, columnspan=2, sticky='ew',
                           padx=4, pady=(8, 0))

        self.status_var = tk.StringVar(value='Порт закрыт — режим просмотра кадров')
        st = ttk.Label(box, textvariable=self.status_var, foreground='#c07000')
        st.grid(row=2, column=0, columnspan=5, sticky='w', pady=(8, 0))

    # ---------------------------------------------------------- Команда
    def _build_command(self):
        box = ttk.LabelFrame(self, text='2. Команда', padding=8)
        box.grid(row=1, column=0, sticky='ew', pady=(0, 8))
        box.columnconfigure(1, weight=1)

        # --- главный выпадающий список команд ---
        ttk.Label(box, text='Выберите команду:').grid(row=0, column=0, sticky='w')
        self.preset_var = tk.StringVar(value=self.presets[0][0])
        self.preset_cb = ttk.Combobox(
            box, textvariable=self.preset_var, state='readonly',
            values=[lbl for lbl, _c, _m in self.presets],
            height=len(self.presets), font=('TkDefaultFont', 10))
        self.preset_cb.grid(row=0, column=1, columnspan=2, sticky='ew', padx=4)
        self.preset_cb.bind('<<ComboboxSelected>>', self._on_preset)

        # --- пояснение к выбранной команде ---
        self.help_var = tk.StringVar(value='')
        self.help_lbl = ttk.Label(box, textvariable=self.help_var,
                                  wraplength=560, justify='left',
                                  foreground='#555')
        self.help_lbl.grid(row=1, column=0, columnspan=3, sticky='w',
                           padx=4, pady=(4, 0))

        # --- ручной ввод байта команды ---
        ttk.Label(box, text='Байт команды (hex):').grid(row=2, column=0,
                                                        sticky='w', pady=(8, 0))
        self.cmd_var = tk.StringVar(value='53')
        cmd_entry = ttk.Entry(box, textvariable=self.cmd_var, width=8)
        cmd_entry.grid(row=2, column=1, sticky='w', padx=4, pady=(8, 0))
        cmd_entry.bind('<KeyRelease>', self._on_cmd_typed)

        # --- данные для записи ---
        ttk.Label(box, text='Данные (hex, для записи):').grid(
            row=3, column=0, sticky='w', pady=(8, 0))
        self.data_var = tk.StringVar()
        self.data_entry = ttk.Entry(box, textvariable=self.data_var)
        self.data_entry.grid(row=3, column=1, columnspan=2, sticky='ew',
                             padx=4, pady=(8, 0))

        # --- строка предпросмотра кадра ---
        self.preview_var = tk.StringVar(value='')
        ttk.Label(box, text='Кадр:').grid(row=4, column=0, sticky='w', pady=(8, 0))
        ttk.Label(box, textvariable=self.preview_var,
                  font=('monospace', 10), foreground='#0a58ca').grid(
            row=4, column=1, columnspan=2, sticky='w', padx=4, pady=(8, 0))

        # --- кнопки ---
        btns = ttk.Frame(box)
        btns.grid(row=5, column=0, columnspan=3, sticky='ew', pady=(10, 0))
        self.send_btn = ttk.Button(btns, text='▶  Отправить',
                                   command=self._on_send)
        self.send_btn.pack(side='left')
        ttk.Button(btns, text='Очистить журнал',
                   command=self._clear_log).pack(side='right')

        # обновлять предпросмотр при любом изменении полей
        for var in (self.cmd_var, self.data_var, self.addr_var):
            var.trace_add('write', lambda *_: self._update_preview())

    # ---------------------------------------------------------- Журнал
    def _build_log(self):
        box = ttk.LabelFrame(self, text='3. Журнал обмена', padding=8)
        box.grid(row=2, column=0, sticky='nsew')
        self.rowconfigure(2, weight=1)
        box.columnconfigure(0, weight=1)
        box.rowconfigure(0, weight=1)

        self.log = tk.Text(box, height=15, wrap='word', font=('monospace', 10))
        self.log.grid(row=0, column=0, sticky='nsew')
        sb = ttk.Scrollbar(box, command=self.log.yview)
        sb.grid(row=0, column=1, sticky='ns')
        self.log['yscrollcommand'] = sb.set

        self.log.tag_config('tx', foreground='#0a58ca')
        self.log.tag_config('rx', foreground='#198754')
        self.log.tag_config('err', foreground='#dc3545')
        self.log.tag_config('info', foreground='#888')
        self.log.tag_config('warn', foreground='#c07000')
        self.log.configure(state='disabled')

    # ---------------------------------------------------------- обработчики
    def _refresh_ports(self):
        ports = list_ports()
        self.port_cb['values'] = ports
        if ports and not self.port_var.get():
            self.port_var.set(ports[0])
        if not ports:
            self._append('Порты не найдены (или не установлен pyserial: '
                         'pip install pyserial).\n', 'info')

    def _on_preset(self, _evt=None):
        cmd, mode = self.label_to_cmd.get(self.preset_var.get(), (0x53, 'read'))
        self.cmd_var.set('%02X' % cmd)
        writable = (mode == 'write')
        self.data_entry.configure(state='normal' if writable else 'disabled')
        if not writable:
            self.data_var.set('')
        self._update_help(cmd)
        self._update_preview()

    def _update_help(self, cmd):
        text = P.cmd_help(cmd)
        self.help_var.set(text)
        # опасные команды — оранжевым, обычные — серым
        self.help_lbl.configure(
            foreground='#c07000' if P.is_write(cmd) else '#555')

    def _on_cmd_typed(self, _evt=None):
        """Если пользователь ввёл байт команды вручную — синхронизировать список."""
        try:
            cmd = int(self.cmd_var.get().strip(), 16)
        except ValueError:
            return
        for lbl, c, mode in self.presets:
            if c == cmd:
                self.preset_var.set(lbl)
                self.data_entry.configure(
                    state='normal' if mode == 'write' else 'disabled')
                break
        self._update_help(cmd)
        self._update_preview()

    def _update_preview(self):
        try:
            frame = P.build_frame(self._addr(), self._cmd(), self._data())
            self.preview_var.set(P.hexs(frame))
        except Exception:
            self.preview_var.set('(проверьте адрес / команду / данные)')

    def _toggle_connection(self):
        if self.dev is not None:
            self._disconnect()
            return
        port = self.port_var.get().strip()
        if not port:
            messagebox.showwarning(
                'Порт не выбран',
                'Укажите COM-порт или работайте в режиме просмотра.')
            return
        try:
            self.dev = P.Device(port, baud=int(self.baud_var.get()),
                                addr=self._addr())
        except Exception as e:
            self.dev = None
            messagebox.showerror('Не удалось открыть порт', str(e))
            self._append('Ошибка открытия порта: %s\n' % e, 'err')
            return
        self.conn_btn.configure(text='Закрыть порт')
        self.status_var.set('Порт %s открыт, %s бод, 8N1' %
                            (port, self.baud_var.get()))
        self._append('Порт %s открыт (%s 8N1).\n' % (port, self.baud_var.get()),
                     'info')

    def _disconnect(self):
        try:
            self.dev.close()
        except Exception:
            pass
        self.dev = None
        self.conn_btn.configure(text='Открыть порт')
        self.status_var.set('Порт закрыт — режим просмотра кадров')
        self._append('Порт закрыт.\n', 'info')

    def _addr(self):
        return P.parse_addr(self.addr_var.get())

    def _cmd(self):
        return int(self.cmd_var.get().strip(), 16)

    def _data(self):
        t = self.data_var.get().strip().replace(':', ' ')
        return bytes(int(x, 16) for x in t.split()) if t else b''

    def _on_discover(self):
        frame = P.build_frame(P.BROADCAST, 0x53)
        self._append('→ %s   (поиск прибора)\n' % P.hexs(frame), 'tx')
        if self.dev is None:
            self._append('(порт закрыт — кадр только сформирован)\n\n', 'info')
            return
        self.send_btn.configure(state='disabled')
        threading.Thread(target=self._worker,
                         args=(0x53, b'', True), daemon=True).start()

    def _on_send(self):
        try:
            cmd = self._cmd()
            frame = P.build_frame(self._addr(), cmd, self._data())
        except Exception as e:
            messagebox.showerror('Ошибка ввода', str(e))
            return

        # предупреждение для команд записи
        if P.is_write(cmd):
            if not messagebox.askyesno(
                    'Команда записи',
                    'Команда 0x%02X (%s) ИЗМЕНЯЕТ память прибора и может быть '
                    'необратимой.\n\nОтправить?' % (cmd, P.cmd_name(cmd)),
                    icon='warning', default='no'):
                self._append('Отправка команды записи 0x%02X отменена.\n\n' % cmd,
                             'warn')
                return

        info = P.parse_frame(frame)
        self._append('→ %s\n' % P.hexs(frame), 'tx')
        self._append(self._fmt_info(info) + '\n', 'info')

        if self.dev is None:
            self._append('(порт закрыт — кадр только сформирован)\n\n', 'info')
            return

        self.send_btn.configure(state='disabled')
        threading.Thread(target=self._worker,
                         args=(cmd, self._data(), P.is_write(cmd)),
                         daemon=True).start()

    def _worker(self, cmd, data, allow_write):
        try:
            resp = self.dev.request(cmd, data, allow_write=allow_write)
            self.rx_queue.put(('resp', resp))
        except Exception as e:
            self.rx_queue.put(('error', str(e)))

    def _drain_queue(self):
        try:
            while True:
                kind, payload = self.rx_queue.get_nowait()
                if kind == 'resp':
                    self._show_response(payload)
                elif kind == 'error':
                    self._append('Ошибка обмена: %s\n\n' % payload, 'err')
                self.send_btn.configure(state='normal')
        except queue.Empty:
            pass
        self.after(100, self._drain_queue)

    def _show_response(self, resp):
        if resp is None:
            self._append('← (нет ответа / тайм-аут)\n\n', 'err')
            return
        raw = (bytes(resp['addr']) + bytes([resp['cmd']]) + resp['data'] +
               bytes([resp['crc_rx'] & 0xFF, resp['crc_rx'] >> 8]))
        self._append('← %s\n' % P.hexs(raw), 'rx')
        self._append(self._fmt_info(resp) + '\n\n',
                     'rx' if resp['crc_ok'] else 'err')

    @staticmethod
    def _fmt_info(info):
        lines = ['    команда 0x%02X — %s' %
                 (info['cmd'], P.cmd_name(info['cmd']))]
        lines.append('    адрес %s | данные [%s] | CRC 0x%04X %s' % (
            P.hexs(info['addr']), P.hexs(info['data']) or '—',
            info['crc_calc'], 'OK' if info['crc_ok'] else 'ОШИБКА CRC'))
        if info['cmd'] == 0x63:
            m = P.decode_live(info['data'])
            if m:
                lines.append('    измерения: U≈%.1f В (BCD %d), I(BCD)=%d, '
                             'E(BCD)=%d' % (m['voltage_V'], m['voltage_bcd'],
                                            m['current_bcd'], m['energy_bcd']))
        return '\n'.join(lines)

    def _append(self, text, tag='info'):
        self.log.configure(state='normal')
        self.log.insert('end', text, tag)
        self.log.see('end')
        self.log.configure(state='disabled')

    def _clear_log(self):
        self.log.configure(state='normal')
        self.log.delete('1.0', 'end')
        self.log.configure(state='disabled')


def main():
    root = tk.Tk()
    try:
        root.tk.call('tk', 'scaling', 1.2)
    except Exception:
        pass
    App(root)
    root.minsize(680, 600)
    root.mainloop()


if __name__ == '__main__':
    main()
