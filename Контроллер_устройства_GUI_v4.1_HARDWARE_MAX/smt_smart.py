#!/usr/bin/env python3
"""
smt_smart — референс-библиотека протокола исследуемый прибор (для интероперабельного ПО).

Разработана по результатам авторизованного аудита прошивки. Позволяет писать
свой софт, который ПОНИМАЕТ данные и пакеты прибора:

  * разбор лог-записей измерений из дампа SPI-флеш;
  * разбор/сборка телеметрического CSV-пакета;
  * помощники CRC32 (аппаратный CRC STM32) и MD5 (как в прошивке).

Статус элементов:
  [OK]     формат лог-записи — подтверждён на реальных дампах.
  [OK]     поля телеметрического CSV — восстановлены из форматных строк прошивки.
  [CHECK]  параметры CRC32/MD5 — заданы по конфигурации STM32 по умолчанию;
           перед боевым использованием сверить с реальным пакетом прибора.
"""

from __future__ import annotations
import struct, hashlib, zlib
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

# --------------------------------------------------------------------------- #
# 1. Лог-запись измерения (SPI-флеш, 128-байтовая запись)
# --------------------------------------------------------------------------- #
RECORD_SIZE = 0x80
DATA_OFF = 0x40                     # блок данных внутри супер-записи
ANCHOR = struct.pack("<f", -35.0) * 3   # инвариант: три -35.0 подряд (DATA+0x30)

# смещения полей внутри блока данных
F_TS, F_CNT = 0x00, 0x08
F_READING, F_READING2 = 0x0C, 0x1C     # double, две зеркальные копии показания
F_TOTAL = 0x24                          # float32 накопленный итог
F_TEMP1, F_TEMP2 = 0x24, 0x2C           # float32 (в дампе температуры)


@dataclass
class Record:
    file_offset: int
    time_utc: str
    unix: int
    counter: int
    reading: float          # мгновенное значение (double, +0x0C)
    temp1: float
    temp2: float


def find_records(buf: bytes) -> list[int]:
    """Смещения блоков данных (по инварианту -35.0, устойчиво к правкам)."""
    bases, start, n = [], 0, len(buf)
    while True:
        i = buf.find(ANCHOR, start)
        if i < 0:
            break
        start = i + 1
        base = i - 0x30                 # anchor лежит на DATA+0x30
        if base < 0 or base + DATA_OFF > n:
            continue
        ts = struct.unpack_from("<I", buf, base + F_TS)[0]
        if 0x5E000000 <= ts <= 0x7A000000:      # 2020..2035
            bases.append(base)
    return bases


def decode_record(buf: bytes, base: int) -> Record:
    ts = struct.unpack_from("<I", buf, base + F_TS)[0]
    return Record(
        file_offset=base,
        time_utc=datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        unix=ts,
        counter=struct.unpack_from("<I", buf, base + F_CNT)[0],
        reading=struct.unpack_from("<d", buf, base + F_READING)[0],
        temp1=struct.unpack_from("<f", buf, base + F_TEMP1)[0],
        temp2=struct.unpack_from("<f", buf, base + F_TEMP2)[0],
    )


def read_log(path: str) -> list[Record]:
    buf = open(path, "rb").read()
    return [decode_record(buf, b) for b in find_records(buf)]


# --------------------------------------------------------------------------- #
# 2. Телеметрический пакет (CSV, как формирует прошивка sub_08019192)
# --------------------------------------------------------------------------- #
# Основной формат записи в пакете (форматная строка 0x080351F8):
#   "%d;%02d.%02d.%d,%02d:%02d:%02d;%llu;%0.2f;;%d;"
#   type ; DD.MM.YYYY,hh:mm:ss ; accumulator(u64) ; value(2 знака) ; ; flag
# Часовой срез (0x08035318): та же схема, время с ",hh:00:00".
# Архивная форма (0x08034F..): "[%llu,%0.4f,%0.2f,0,0]".

@dataclass
class TelemetryRecord:
    rtype: int
    dt: datetime
    accumulator: int        # %llu — накопленный итог (масштаб ×10000)
    value: float            # мгновенное значение
    flag: int

    def encode(self) -> str:
        d = self.dt
        return (f"{self.rtype};{d.day:02d}.{d.month:02d}.{d.year},"
                f"{d.hour:02d}:{d.minute:02d}:{d.second:02d};"
                f"{self.accumulator};{self.value:0.2f};;{self.flag};")

    @classmethod
    def decode(cls, s: str) -> "TelemetryRecord":
        p = s.strip().rstrip(";").split(";")
        rtype = int(p[0]); date, time = p[1].split(",")
        dd, mm, yy = (int(x) for x in date.split("."))
        hh, mi, ss = (int(x) for x in time.split(":"))
        return cls(rtype, datetime(yy, mm, dd, hh, mi, ss),
                   int(p[2]), float(p[3]), int(p[-1]))


# --------------------------------------------------------------------------- #
# 3. Целостность/крипто (как в прошивке)
# --------------------------------------------------------------------------- #
def crc32_stm32(data: bytes, init: int = 0xFFFFFFFF) -> int:
    """CRC32 в конфигурации аппаратного блока STM32 по умолчанию:
    poly 0x04C11DB7, init 0xFFFFFFFF, без реверса вход/выход, без финального XOR
    (эквивалент CRC-32/MPEG-2). Прибор считает CRC32 через HW-блок 0x40023000.
    [CHECK] сверить с реальным пакетом — прошивка могла включить REV_IN/REV_OUT."""
    crc = init
    for b in data:
        crc ^= b << 24
        for _ in range(8):
            crc = ((crc << 1) ^ 0x04C11DB7) & 0xFFFFFFFF if crc & 0x80000000 else (crc << 1) & 0xFFFFFFFF
    return crc


def md5_hex(data: bytes) -> str:
    """MD5 — прошивка содержит программную реализацию (sub_08031DFC).
    Применяется для аутентификации/хеша (напр. пароля/подписи). MD5 слаб —
    отражено в отчёте по безопасности."""
    return hashlib.md5(data).hexdigest()


# --------------------------------------------------------------------------- #
# самопроверка анализатора на дампе
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        recs = read_log(sys.argv[1])
        print(f"записей: {len(recs)}")
        for r in recs[:10]:
            print(f"  {r.time_utc}  cnt={r.counter}  value={r.reading}")
        # пример телеметрической строки
        tr = TelemetryRecord(1, datetime(2025, 10, 1, 11, 35, 8), 12800, 1.28, 0)
        line = tr.encode()
        print("\nтелеметрия encode:", line)
        print("телеметрия decode:", TelemetryRecord.decode(line))
