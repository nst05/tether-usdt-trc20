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

# Полная карта команд (сверена с отчётом руководителя по mycode.hex и
# подтверждена таблицей диспетчера 0xE722). Формат:
#   код: (описание, режим, длина ответа|None)
#   режим: 'read' | 'write' | 'discovery'
# ВНИМАНИЕ: команды режима 'write' изменяют ID/калибровку/конфигурацию или
# внешнюю память и могут быть НЕОБРАТИМЫ. Не отправлять без резервной копии.
COMMANDS = {
    0x53: ('Найти прибор (запросить его ID)',            'discovery', 4),
    0x50: ('Прочитать заводской код',                    'read', 2),
    0x51: ('Прочитать калибровку напряжения и тока',     'read', 4),
    0x55: ('Прочитать флаги и режимы работы',            'read', 2),
    0x63: ('Прочитать показания: напряжение, ток, энергию', 'read', 7),
    0x65: ('Прочитать флаги и режимы работы',            'read', 2),
    0x66: ('Прочитать дату и версию прошивки',           'read', 3),
    0x27: ('Прочитать внешнюю память (EEPROM)',          'read', 4),
    0x28: ('Прочитать дополнительную конфигурацию',      'read', 6),
    0x54: ('Прочитать рабочий параметр',                 'read', 1),
    0x00: ('Записать новый ID прибора',                  'write', None),
    0x40: ('Записать заводские данные',                  'write', None),
    0x41: ('Записать калибровку напряжения и тока',      'write', None),
    0x43: ('Записать во внешнюю память (EEPROM)',        'write', None),
    0x44: ('Записать рабочий параметр',                  'write', None),
    0x46: ('Записать флаги и режимы работы',             'write', None),
    0x47: ('Записать дату и версию прошивки',            'write', None),
}

# Технические адреса регистров для каждой команды (для справки/README).
COMMAND_REGS = {
    0x50: '0x1000..0x1001', 0x51: '0x1002..0x1005', 0x55: '0x1006..0x1007',
    0x63: 'текущие измерения', 0x65: '0x1006..0x1007', 0x66: '0x100C..0x100E',
    0x28: '0x1080', 0x00: 'ID 0x1008', 0x40: '0x1000', 0x41: '0x1002..0x1005',
    0x46: '0x1006..0x1007', 0x47: '0x100C..0x100E', 0x53: 'ID 0x1008',
}

# Человеческое пояснение: что именно делает команда.
COMMAND_HELP = {
    0x53: 'Широковещательный запрос: прибор в ответ сообщает свой ID. '
          'С него начинают работу, если ID заранее неизвестен.',
    0x50: 'Возвращает заводской идентификационный код прибора (2 байта).',
    0x51: 'Возвращает калибровочные коэффициенты каналов напряжения и тока '
          '(масштабы, используемые при расчёте RMS).',
    0x55: 'Возвращает байты флагов и режимов работы прибора.',
    0x63: 'Основная измерительная команда: мгновенные напряжение, ток и '
          'накопленная энергия (7 байт, упакованный BCD).',
    0x65: 'Ещё одно чтение байтов флагов/режимов (дублирует 0x55).',
    0x66: 'Возвращает дату изготовления и версию прошивки (3 байта).',
    0x27: 'Читает данные из внешней микросхемы памяти EEPROM (24Cxx), '
          'подключённой по программному интерфейсу.',
    0x28: 'Читает дополнительную конфигурационную запись из INFO Flash.',
    0x54: 'Читает один рабочий (runtime) параметр прибора.',
    0x00: 'ОПАСНО: перезаписывает идентификатор (ID) прибора. После смены ID '
          'обращаться к прибору нужно будет по новому адресу.',
    0x40: 'ОПАСНО: перезапись заводских данных в INFO Flash.',
    0x41: 'ОПАСНО: смена калибровочных коэффициентов напряжения и тока. '
          'Меняет точность измерений — только с эталоном и резервной копией.',
    0x43: 'ОПАСНО: запись во внешнюю память EEPROM.',
    0x44: 'ОПАСНО: изменение рабочего (runtime) параметра.',
    0x46: 'ОПАСНО: перезапись флагов и режимов работы прибора.',
    0x47: 'ОПАСНО: перезапись даты/версии в INFO Flash.',
}


def cmd_help(cmd):
    return COMMAND_HELP.get(cmd, 'Пользовательская команда — назначение уточните '
                                 'по таблице команд (README, раздел 9).')


# Смысл групп (старший полубайт команды) по таблице диспетчера 0xE722.
COMMAND_GROUPS = {
    0x0: 'запись во flash / групповые операции',
    0x1: 'статус / конфигурация',
    0x2: 'установка часов реального времени (RTC)',
    0x3: 'чтение часов реального времени (RTC)',
    0x4: 'ЗАПИСЬ паспортных/калибровочных регистров',
    0x5: 'ЧТЕНИЕ паспортных/калибровочных регистров',
    0x6: 'чтение счётчиков / текущих измерений',
}


def is_write(cmd):
    """True для команд, изменяющих память прибора (опасных)."""
    info = COMMANDS.get(cmd)
    return info[1] == 'write' if info else (cmd >> 4) in (0x0, 0x4)


def cmd_name(cmd):
    info = COMMANDS.get(cmd)
    return info[0] if info else 'команда группы 0x%X' % (cmd >> 4)


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


def bcd(b):
    """Распаковка packed-BCD последовательности байт в целое число."""
    v = 0
    for x in b:
        v = v * 100 + (x >> 4) * 10 + (x & 0x0F)
    return v


def decode_live(data):
    """Разбор 7 байт ответа команды 0x63: напряжение(2), ток(2), энергия(3).

    Поля — packed BCD (см. отчёт). Точное положение десятичной точки требует
    стендовой сверки, поэтому здесь приводится «сырое» BCD-значение и
    вероятная величина напряжения (÷10, напр. 2305 -> 230.5 В)."""
    if len(data) != 7:
        return None
    v_raw = bcd(data[0:2])
    i_raw = bcd(data[2:4])
    e_raw = bcd(data[4:7])
    return {
        'voltage_bcd': v_raw, 'voltage_V': v_raw / 10.0,
        'current_bcd': i_raw,
        'energy_bcd': e_raw,
    }


def describe(info):
    lines = []
    lines.append('  адрес       : %s' % hexs(info['addr']))
    lines.append('  команда     : 0x%02X — %s%s' %
                 (info['cmd'], cmd_name(info['cmd']),
                  '  [ЗАПИСЬ!]' if is_write(info['cmd']) else ''))
    lines.append('  группа      : 0x%X «%s», регистр %d' %
                 (info['group'], info['group_name'], info['reg']))
    lines.append('  данные (%2d) : %s' % (len(info['data']), hexs(info['data']) or '—'))
    lines.append('  CRC принят  : 0x%04X' % info['crc_rx'])
    lines.append('  CRC расчёт  : 0x%04X  [%s]' %
                 (info['crc_calc'], 'OK' if info['crc_ok'] else 'ОШИБКА'))
    if info['cmd'] == 0x63:
        m = decode_live(info['data'])
        if m:
            lines.append('  измерения   : U≈%.1f В (BCD %d), I(BCD)=%d, '
                         'E(BCD)=%d' % (m['voltage_V'], m['voltage_bcd'],
                                        m['current_bcd'], m['energy_bcd']))
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

    def request(self, cmd, data=b'', allow_write=False):
        """Отправляет команду и возвращает разобранный ответ (или None).

        Для команд записи (изменяющих память прибора) требуется явный
        allow_write=True — защита от случайной необратимой операции."""
        if is_write(cmd) and not allow_write:
            raise PermissionError(
                'команда 0x%02X (%s) изменяет память прибора; '
                'передайте allow_write=True осознанно' % (cmd, cmd_name(cmd)))
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
        return self.request(cmd, data, allow_write=True)

    def discover(self):
        """Широковещательный поиск устройства (команда 0x53).
        Возвращает 4-байтовый ID найденного прибора или None."""
        saved = self.addr
        try:
            self.addr = BROADCAST
            resp = self.request(0x53)
        finally:
            self.addr = saved
        if resp and resp['crc_ok']:
            return bytes(resp['addr'])
        return None


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
    ap.add_argument('--write', action='store_true',
                    help='разрешить команду записи (изменяет память прибора!)')
    ap.add_argument('--discover', action='store_true',
                    help='широковещательный поиск устройства (команда 0x53)')
    ap.add_argument('--build', action='store_true',
                    help='только собрать и показать кадр, без порта')
    ap.add_argument('--parse', help='разобрать HEX-дамп кадра')
    ap.add_argument('--list-commands', action='store_true',
                    help='показать карту команд и выйти')
    args = ap.parse_args()

    if args.list_commands:
        print('Карта команд (см. README.md, раздел 9):\n')
        for c in sorted(COMMANDS):
            name, mode, n = COMMANDS[c]
            tag = {'read': 'чтение', 'write': 'ЗАПИСЬ ', 'discovery': 'поиск '}[mode]
            print('  0x%02X  [%s]  %s%s' %
                  (c, tag, name, '' if n is None else '  (ответ %d б)' % n))
        return

    if args.discover:
        if not args.port:
            print('Discovery-кадр: %s' % hexs(build_frame(BROADCAST, 0x53)))
            print('(добавьте --port для реального поиска)')
            return
        dev = Device(args.port, baud=args.baud)
        try:
            found = dev.discover()
            print('Найден прибор ID: %s' % (hexs(found) if found else '(не найден)'))
        finally:
            dev.close()
        return

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

    if is_write(cmd) and not args.write:
        ap.error('команда 0x%02X (%s) изменяет память прибора — '
                 'добавьте --write, если это действительно нужно'
                 % (cmd, cmd_name(cmd)))

    dev = Device(args.port, baud=args.baud, addr=args.addr)
    try:
        print('-> %s' % hexs(build_frame(args.addr, cmd, data)))
        resp = dev.request(cmd, data, allow_write=args.write)
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
