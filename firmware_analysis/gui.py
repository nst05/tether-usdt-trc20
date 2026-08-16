#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gui.py — графический интерфейс для общения с устройством MSP430
по восстановленному протоколу (см. README.md и protocol.py).

Запуск:
    python3 gui.py

Работает и без оборудования: если порт не открыт, кнопка «Отправить»
показывает собранный кадр и его разбор («режим просмотра»). Для реального
обмена нужен pyserial (pip install pyserial) и подключённый USB-UART.

GUI построен на tkinter — он входит в стандартную библиотеку Python,
поэтому дополнительные пакеты для интерфейса не требуются.
"""

import threading
import queue
import time
import tkinter as tk
from tkinter import ttk, messagebox

import protocol as P


# Готовые команды: (подпись, байт команды, есть ли поле данных для записи)
PRESETS = [
    ('Чтение статуса/конфигурации (0x10)', 0x10, False),
    ('Установка часов RTC (0x20)',          0x20, True),
    ('Чтение часов RTC (0x30)',             0x30, False),
    ('Чтение паспортных данных (0x40)',     0x40, False),
    ('Запись паспортных данных (0x50)',     0x50, True),
    ('Чтение счётчиков/буферов (0x60)',     0x60, False),
]


def list_ports():
    """Список доступных COM-портов (если pyserial установлен)."""
    try:
        from serial.tools import list_ports
        return [p.device for p in list_ports.comports()]
    except Exception:
        return []


class App(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=10)
        self.grid(sticky='nsew')
        master.title('MSP430 — обмен по последовательному порту')
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.dev = None                 # объект protocol.Device
        self.rx_queue = queue.Queue()   # очередь сообщений от фонового потока

        self._build_connection()
        self._build_command()
        self._build_log()

        self.after(100, self._drain_queue)

    # ---------------------------------------------------------- блок «Соединение»
    def _build_connection(self):
        box = ttk.LabelFrame(self, text='Соединение', padding=8)
        box.grid(row=0, column=0, sticky='ew', pady=(0, 8))
        for c in range(6):
            box.columnconfigure(c, weight=1 if c in (1, 3) else 0)

        ttk.Label(box, text='Порт:').grid(row=0, column=0, sticky='w')
        self.port_var = tk.StringVar()
        self.port_cb = ttk.Combobox(box, textvariable=self.port_var,
                                    values=list_ports(), width=18)
        self.port_cb.grid(row=0, column=1, sticky='ew', padx=4)
        ttk.Button(box, text='⟳', width=3,
                   command=self._refresh_ports).grid(row=0, column=2, padx=(0, 8))

        ttk.Label(box, text='Скорость:').grid(row=0, column=3, sticky='e')
        self.baud_var = tk.StringVar(value='9600')
        ttk.Combobox(box, textvariable=self.baud_var, width=8,
                     values=['9600', '4800', '19200', '38400', '57600', '115200']
                     ).grid(row=0, column=4, sticky='w', padx=4)

        ttk.Label(box, text='Адрес (4 байта):').grid(row=1, column=0, sticky='w',
                                                     pady=(6, 0))
        self.addr_var = tk.StringVar(value='04 A2 CB 71')
        ttk.Entry(box, textvariable=self.addr_var, width=18).grid(
            row=1, column=1, sticky='ew', padx=4, pady=(6, 0))
        ttk.Button(box, text='Широковещательный',
                   command=lambda: self.addr_var.set('00 00 00 00')).grid(
            row=1, column=2, columnspan=2, sticky='w', pady=(6, 0))

        self.conn_btn = ttk.Button(box, text='Открыть порт',
                                   command=self._toggle_connection)
        self.conn_btn.grid(row=1, column=4, sticky='ew', padx=4, pady=(6, 0))

        self.status_var = tk.StringVar(value='Порт закрыт — режим просмотра кадров')
        ttk.Label(box, textvariable=self.status_var, foreground='#888').grid(
            row=2, column=0, columnspan=6, sticky='w', pady=(6, 0))

    # ---------------------------------------------------------- блок «Команда»
    def _build_command(self):
        box = ttk.LabelFrame(self, text='Команда', padding=8)
        box.grid(row=1, column=0, sticky='ew', pady=(0, 8))
        box.columnconfigure(1, weight=1)

        ttk.Label(box, text='Готовая команда:').grid(row=0, column=0, sticky='w')
        self.preset_var = tk.StringVar(value=PRESETS[3][0])
        preset_cb = ttk.Combobox(box, textvariable=self.preset_var,
                                 values=[p[0] for p in PRESETS],
                                 state='readonly')
        preset_cb.grid(row=0, column=1, columnspan=2, sticky='ew', padx=4)
        preset_cb.bind('<<ComboboxSelected>>', self._on_preset)

        ttk.Label(box, text='Байт команды (hex):').grid(row=1, column=0, sticky='w',
                                                        pady=(6, 0))
        self.cmd_var = tk.StringVar(value='40')
        ttk.Entry(box, textvariable=self.cmd_var, width=8).grid(
            row=1, column=1, sticky='w', padx=4, pady=(6, 0))

        ttk.Label(box, text='Данные для записи (hex):').grid(row=2, column=0,
                                                            sticky='w', pady=(6, 0))
        self.data_var = tk.StringVar()
        self.data_entry = ttk.Entry(box, textvariable=self.data_var)
        self.data_entry.grid(row=2, column=1, columnspan=2, sticky='ew',
                             padx=4, pady=(6, 0))

        self.send_btn = ttk.Button(box, text='Отправить', command=self._on_send)
        self.send_btn.grid(row=3, column=1, sticky='w', padx=4, pady=(8, 0))
        ttk.Button(box, text='Очистить журнал',
                   command=self._clear_log).grid(row=3, column=2, sticky='e',
                                                 pady=(8, 0))

    # ---------------------------------------------------------- блок «Журнал»
    def _build_log(self):
        box = ttk.LabelFrame(self, text='Журнал обмена', padding=8)
        box.grid(row=2, column=0, sticky='nsew')
        self.rowconfigure(2, weight=1)
        box.columnconfigure(0, weight=1)
        box.rowconfigure(0, weight=1)

        self.log = tk.Text(box, height=16, wrap='word', font=('monospace', 10))
        self.log.grid(row=0, column=0, sticky='nsew')
        sb = ttk.Scrollbar(box, command=self.log.yview)
        sb.grid(row=0, column=1, sticky='ns')
        self.log['yscrollcommand'] = sb.set

        self.log.tag_config('tx', foreground='#0a58ca')
        self.log.tag_config('rx', foreground='#198754')
        self.log.tag_config('err', foreground='#dc3545')
        self.log.tag_config('info', foreground='#888')
        self.log.configure(state='disabled')

    # ---------------------------------------------------------- обработчики
    def _refresh_ports(self):
        ports = list_ports()
        self.port_cb['values'] = ports
        if ports and not self.port_var.get():
            self.port_var.set(ports[0])
        if not ports:
            self._append('Порты не найдены (или не установлен pyserial).\n', 'info')

    def _on_preset(self, _evt=None):
        for label, cmd, has_data in PRESETS:
            if label == self.preset_var.get():
                self.cmd_var.set('%02X' % cmd)
                state = 'normal' if has_data else 'disabled'
                self.data_entry.configure(state=state)
                if not has_data:
                    self.data_var.set('')
                break

    def _toggle_connection(self):
        if self.dev is not None:
            self._disconnect()
            return
        port = self.port_var.get().strip()
        if not port:
            messagebox.showwarning('Порт не выбран',
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
        if not t:
            return b''
        return bytes(int(x, 16) for x in t.split())

    def _on_send(self):
        try:
            addr = self._addr()
            cmd = self._cmd()
            data = self._data()
            frame = P.build_frame(addr, cmd, data)
        except Exception as e:
            messagebox.showerror('Ошибка ввода', str(e))
            return

        info = P.parse_frame(frame)
        self._append('→ %s\n' % P.hexs(frame), 'tx')
        self._append(self._fmt_info(info) + '\n', 'info')

        if self.dev is None:
            self._append('(порт закрыт — кадр только сформирован)\n\n', 'info')
            return

        # реальный обмен в фоне, чтобы не морозить окно
        self.send_btn.configure(state='disabled')
        threading.Thread(target=self._worker, args=(cmd, data), daemon=True).start()

    def _worker(self, cmd, data):
        try:
            resp = self.dev.request(cmd, data)
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
        return ('    адрес %s | команда 0x%02X (группа 0x%X «%s», рег. %d) | '
                'данные [%s] | CRC 0x%04X %s' % (
                    P.hexs(info['addr']), info['cmd'], info['group'],
                    info['group_name'], info['reg'],
                    P.hexs(info['data']) or '—', info['crc_calc'],
                    'OK' if info['crc_ok'] else 'ОШИБКА'))

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
    root.minsize(640, 560)
    root.mainloop()


if __name__ == '__main__':
    main()
