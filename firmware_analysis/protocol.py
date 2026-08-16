#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
protocol.py — библиотека и утилита командной строки для общения с устройством
на микроконтроллере MSP430, прошивка которого разобрана в README.md.

Протокол (восстановлен по дизассемблированию, см. README.md):

    Кадр запроса/ответа:
        [A0 A1 A2 A3]  [CMD]  [DATA ...]  [CRC_lo CRC_hi]
         └─ адрес 4 б ─┘   1 б   0..N байт    Modbus CRC16 (poly 0xA001)

    * Адрес 4 байта сравнивается с адресом устройства (по умолчанию из
      info-flash: 04 A2 CB 71). Адрес 00 00 00 00 — широковещательный.
    * CMD: старший полубайт — группа команды (0x0..0x6),
           младший полубайт — индекс регистра внутри группы.
    * CRC16 (Modbus, init 0xFFFF, poly 0xA001, reflected) по всем
      предыдущим байтам, передаётся младшим байтом вперёд.
    * Минимальная длина кадра — 7 байт (4 адрес + 1 CMD + 2 CRC).

Порт UART: 9600 бод, 8 бит, без чётности, 1 стоп-бит (9600 8N1).
    (SMCLK = FLL+ 128×32768 ≈ 4.194 МГц, делитель UxBR = 436 → 9615 бод.)

Зависимости: pyserial (для реальной работы с COM-портом).
    pip install pyserial

Примеры:
    # просто собрать и показать кадр (без порта):
    python3 protocol.py --build --addr 04A2CB71 --cmd 0x40
    # прочитать регистр 0x40 через реальный порт:
    python3 protocol.py --port /dev/ttyUSB0 --addr 04A2CB71 --read 0x40
    # разобрать принятый дамп:
    python3 protocol.py --parse "04 A2 CB 71 40 12 34 9A 1B"
"""

import argparse
import sys
import time


# --------------------------------------------------------------- CRC16 Modbus

def crc16(data):
    """Modbus CRC16: init 0xFFFF, poly 0xA001 (отражённый). Точная копия
    подпрограммы crc16_modbus по адресу 0xE5B8 разобранной прошивки."""
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


# --------------------------------------------------------------- работа с кадром

DEFAULT_ADDR = bytes([0x04, 0xA2, 0xCB, 0x71])     # из info-flash 0x1008
BROADCAST = bytes([0x00, 0x00, 0x00, 0x00])

# Имена групп команд по таблице диспетчера (0xE722).
COMMAND_GROUPS = {
    0x0: 'групповое чтение серийных данных / запись во flash',
    0x1: 'чтение статуса / конфигурации',
    0x2: 'установка часов реального времени (RTC)',
    0x3: 'чтение часов реального времени (RTC)',
    0x4: 'чтение калибровочных/паспортных регистров',
    0x5: 'запись калибровочных/паспортных регистров',
    0x6: 'чтение счётчиков / буферов',
}


def parse_addr(text):
    """Принимает '04A2CB71', '04:A2:CB:71', '04 A2 CB 71' или 'broadcast'."""
    if text.lower() in ('broadcast', 'bc', 'all'):
        return BROADCAST
    clean = text.replace(':', ' ').replace('-', ' ')
    if ' ' in clean:
        parts = [int(x, 16) for x in clean.split()]
    else:
        clean = clean.replace('0x', '')
        parts = [int(clean[i:i + 2], 16) for i in range(0, len(clean), 2)]
    if len(parts) != 4:
        raise ValueError('адрес должен содержать 4 байта, получено %d' % len(parts))
    return bytes(parts)


def build_frame(addr, cmd, data=b''):
    """Собирает полный кадр: адрес + команда + данные + CRC16."""
    if isinstance(addr, str):
        addr = parse_addr(addr)
    if len(addr) != 4:
        raise ValueError('адрес — ровно 4 байта')
    body = bytes(addr) + bytes([cmd & 0xFF]) + bytes(data)
    c = crc16(body)
    return body + bytes([c & 0xFF, (c >> 8) & 0xFF])


def parse_frame(frame):
    """Разбирает принятый кадр. Возвращает словарь с полями и проверкой CRC."""
    frame = bytes(frame)
    if len(frame) < 7:
        raise ValueError('кадр короче 7 байт (%d)' % len(frame))
    addr = frame[:4]
    cmd = frame[4]
    data = frame[5:-2]
    crc_rx = frame[-2] | (frame[-1] << 8)
    crc_calc = crc16(frame[:-2])
    return {
        'addr': addr,
        'cmd': cmd,
        'group': cmd >> 4,
        'reg': cmd & 0x0F,
        'group_name': COMMAND_GROUPS.get(cmd >> 4, 'неизвестно'),
        'data': data,
        'crc_rx': crc_rx,
        'crc_calc': crc_calc,
        'crc_ok': crc_rx == crc_calc,
    }


def hexs(b):
    return ' '.join('%02X' % x for x in b)


def describe(info):
    lines = []
    lines.append('  адрес       : %s' % hexs(info['addr']))
    lines.append('  команда     : 0x%02X (группа 0x%X «%s», регистр %d)' %
                 (info['cmd'], info['group'], info['group_name'], info['reg']))
    lines.append('  данные (%2d) : %s' % (len(info['data']), hexs(info['data']) or '—'))
    lines.append('  CRC принят  : 0x%04X' % info['crc_rx'])
    lines.append('  CRC расчёт  : 0x%04X  [%s]' %
                 (info['crc_calc'], 'OK' if info['crc_ok'] else 'ОШИБКА'))
    return '\n'.join(lines)


# --------------------------------------------------------------- транспорт

class Device(object):
    """Обёртка над последовательным портом для обмена кадрами."""

    def __init__(self, port, baud=9600, addr=DEFAULT_ADDR,
                 timeout=1.0, inter_frame=0.05):
        import serial                          # локальный импорт: не нужен для --build
        if isinstance(addr, str):
            addr = parse_addr(addr)
        self.addr = addr
        self.inter_frame = inter_frame
        self.ser = serial.Serial(
            port=port, baudrate=baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=timeout,
        )

    def close(self):
        self.ser.close()

    def send(self, cmd, data=b''):
        frame = build_frame(self.addr, cmd, data)
        self.ser.reset_input_buffer()
        self.ser.write(frame)
        self.ser.flush()
        return frame

    def recv(self, expect=None):
        """Читает ответ. Кадр завершается тайм-аутом межсимвольного интервала
        (как и в прошивке: приём завершается по простою линии)."""
        self.ser.timeout = 0.02
        # ждём первый байт до общего тайм-аута
        deadline = time.time() + 1.0
        buf = bytearray()
        while time.time() < deadline and not buf:
            b = self.ser.read(1)
            if b:
                buf += b
        # дочитываем, пока идут байты
        while True:
            b = self.ser.read(1)
            if not b:
                break
            buf += b
            if expect and len(buf) >= expect:
                break
        return bytes(buf)

    def request(self, cmd, data=b''):
        """Отправляет команду и возвращает разобранный ответ (или None)."""
        self.send(cmd, data)
        time.sleep(self.inter_frame)
        raw = self.recv()
        if not raw:
            return None
        return parse_frame(raw)

    # удобные обёртки
    def read_reg(self, cmd):
        return self.request(cmd)

    def write_reg(self, cmd, data):
        return self.request(cmd, data)


# --------------------------------------------------------------- CLI

def main():
    ap = argparse.ArgumentParser(
        description='Обмен с устройством MSP430 по восстановленному протоколу.')
    ap.add_argument('--port', help='COM-порт (напр. /dev/ttyUSB0 или COM3)')
    ap.add_argument('--baud', type=int, default=9600)
    ap.add_argument('--addr', default='04A2CB71',
                    help='адрес устройства, 4 байта (или broadcast)')
    ap.add_argument('--cmd', help='байт команды, напр. 0x40')
    ap.add_argument('--data', default='', help='данные HEX, напр. "12 34"')
    ap.add_argument('--read', help='прочитать регистр (= --cmd для чтения)')
    ap.add_argument('--build', action='store_true',
                    help='только собрать и показать кадр, без порта')
    ap.add_argument('--parse', help='разобрать HEX-дамп кадра')
    args = ap.parse_args()

    if args.parse:
        raw = bytes(int(x, 16) for x in args.parse.replace(':', ' ').split())
        print('Разбор кадра (%d байт): %s\n' % (len(raw), hexs(raw)))
        print(describe(parse_frame(raw)))
        return

    cmd_txt = args.read or args.cmd
    if cmd_txt is None:
        ap.error('укажите --cmd/--read либо --parse')
    cmd = int(cmd_txt, 16) if isinstance(cmd_txt, str) else cmd_txt
    data = bytes(int(x, 16) for x in args.data.replace(':', ' ').split()) if args.data else b''

    if args.build or not args.port:
        frame = build_frame(args.addr, cmd, data)
        print('Собранный кадр (%d байт):\n  %s\n' % (len(frame), hexs(frame)))
        print(describe(parse_frame(frame)))
        if not args.port and not args.build:
            print('\n(порт не указан — кадр только сформирован; '
                  'добавьте --port для реального обмена)')
        return

    dev = Device(args.port, baud=args.baud, addr=args.addr)
    try:
        print('-> %s' % hexs(build_frame(args.addr, cmd, data)))
        resp = dev.request(cmd, data)
        if resp is None:
            print('<- (нет ответа / тайм-аут)')
        else:
            print('<- %s\n' % hexs(bytes(resp['addr']) + bytes([resp['cmd']]) +
                                   resp['data'] +
                                   bytes([resp['crc_rx'] & 0xFF, resp['crc_rx'] >> 8])))
            print(describe(resp))
    finally:
        dev.close()


if __name__ == '__main__':
    main()
