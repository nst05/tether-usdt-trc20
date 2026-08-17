# Реверс-инжиниринг прошивки MSP430F249

Инструменты дизассемблирования, анализа и программное обеспечение для обмена с
исследуемым встроенным устройством. Полный разбор — в [`REPORT.md`](REPORT.md).

## Структура

```
fw-re/
├── razbor.hex            # исходная прошивка (Intel HEX)
├── razbor.lst            # дизассемблированный листинг (генерируется)
├── REPORT.md             # отчёт по задачам дипломной работы
├── tools/                # средства реверс-инжиниринга
│   ├── ihex.py           #   разбор Intel HEX, карта памяти
│   ├── msp430.py         #   дизассемблер MSP430 (все форматы команд)
│   ├── analyze.py        #   обход кода, функции, векторы, xref
│   ├── listing.py        #   генерация листинга
│   └── strings_scan.py   #   поиск строк и таблиц
└── host/                 # ПО обмена с устройством
    ├── protocol.py       #   кадр, CRC-16/Modbus, команды
    ├── device.py         #   клиент поверх UART (pyserial)
    ├── emulator.py       #   программный эмулятор устройства
    ├── cli.py            #   утилита командной строки
    └── tests/            #   экспериментальная проверка (10 тестов)
```

## Быстрый старт

```bash
# Анализ прошивки
python3 tools/analyze.py razbor.hex
python3 tools/listing.py razbor.hex razbor.lst

# Проверка восстановленного протокола (без устройства)
python3 host/tests/test_protocol.py

# Демонстрация команд через эмулятор
python3 host/cli.py cal-read  --emulate --addr 1 --param 0
python3 host/cli.py cal-write --emulate --addr 1 --param 0 --value 0x0180

# Работа с реальным устройством
python3 host/cli.py read --port /dev/ttyUSB0 --addr 1 --index 5 --len 2
```

## Ключевые результаты

- Архитектура: **MSP430F249**, 60 КБ flash, код `0x1100–0xFFDF`.
- 16 077 команд, 168 функций, покрытие 97.8 %.
- Протокол: Modbus RTU-совместимый кадр `[addr][func][data][CRC-16/Modbus]`,
  9 функций (`0x00–0x08`), включая чтение/запись параметров и калибровок.
- CRC-16/Modbus (таблицы `0xFB3C/0xFC3C`) — подтверждён экспериментально.
- Кнопки: порт P2.6, три обработчика нажатий.

Зависимости: Python 3 (стандартная библиотека). Для реального UART —
`pyserial` (`pip install pyserial`).
