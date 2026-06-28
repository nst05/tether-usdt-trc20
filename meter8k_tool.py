# -*- coding: utf-8 -*-
"""
meter8k_tool — чтение/запись показаний T1/T2 для прибора с дампом 8192 байта.

РАСКРЫТЫЙ ФОРМАТ (подтверждён на дампах):
  Размер файла : 8192 байта
  Кодировка    : little-endian, целое 3 байта
  Коэффициент  : 100000  (1 единица = 0.00001; дисплей = raw / 100000)
  Регистры:
    T1  : 0x002F  (дубль 0x1A0F, смещение +0x19E0)
    T2  : 0x0034  (дубль 0x1A14, +0x19E0)
  Дисплей SUM = T1 + T2

ВНИМАНИЕ про CRC:
  В файле присутствуют контрольные суммы (CRC16, заголовок на 0x1E-0x1F и др.),
  алгоритм пока не подтверждён. Этот инструмент пишет ТОЛЬКО регистры и их дубли,
  CRC НЕ пересчитывает. Цель — проверить, проверяет ли прибор целостность при импорте.
  Если прибор файл НЕ примет — значит CRC обязателен, нужен контролируемый дамп
  «отличие в 1 байт» или прошивка, чтобы вычислить полином.

Использование:
  python meter8k_tool.py read  <file.bin>
  python meter8k_tool.py write <file.bin> --t1 100.00 --t2 50.00 [-o out.bin]
"""

import argparse
import os
import sys

COEF = 100000
VAL_LEN = 4                 # длина значения в слоте (слот 5 байт: значение + паддинг)
MIRROR_DELTA = 0x19E0       # смещение дубля

# Адреса регистров в основной копии
OFF_T1 = 0x002F
OFF_T2 = 0x0034

# Все физические адреса каждого регистра (основная копия + дубль)
def reg_offsets(base_off):
    return [base_off, base_off + MIRROR_DELTA]


def read_u_le(data, off, n=VAL_LEN):
    return int.from_bytes(data[off:off + n], "little")


def write_u_le(data, off, value, n=VAL_LEN):
    data[off:off + n] = int(value).to_bytes(n, "little")


def read_reading(data, base_off):
    """Вернёт (display_value, raw, дубль_совпадает)."""
    raw = read_u_le(data, base_off)
    raw_dup = read_u_le(data, base_off + MIRROR_DELTA)
    return raw / COEF, raw, (raw == raw_dup)


def cmd_read(path):
    data = open(path, "rb").read()
    if len(data) < 0x2000:
        print(f"Предупреждение: размер {len(data)} байт (ожидалось 8192)")
    t1, t1_raw, t1_ok = read_reading(data, OFF_T1)
    t2, t2_raw, t2_ok = read_reading(data, OFF_T2)
    print(f"Файл: {os.path.basename(path)} ({len(data)} байт)")
    print(f"  T1  = {t1:.5f}   (raw={t1_raw} @0x{OFF_T1:04X}; дубль {'OK' if t1_ok else 'РАСХОЖДЕНИЕ'})")
    print(f"  T2  = {t2:.5f}   (raw={t2_raw} @0x{OFF_T2:04X}; дубль {'OK' if t2_ok else 'РАСХОЖДЕНИЕ'})")
    print(f"  SUM = {t1 + t2:.5f}  (T1 + T2)")


def cmd_write(path, t1, t2, out):
    data = bytearray(open(path, "rb").read())
    if len(data) < 0x2000:
        print(f"Ошибка: файл слишком маленький ({len(data)} байт)")
        return 1

    changed = []
    for name, base_off, val in (("T1", OFF_T1, t1), ("T2", OFF_T2, t2)):
        if val is None:
            continue
        raw = int(round(val * COEF))
        if raw < 0 or raw >= (1 << (8 * VAL_LEN)):
            print(f"Ошибка: {name}={val} вне диапазона (0..{(1 << (8 * VAL_LEN)) - 1} в raw)")
            return 1
        for off in reg_offsets(base_off):
            write_u_le(data, off, raw)
        changed.append((name, val, raw))

    if not changed:
        print("Нечего писать: укажи --t1 и/или --t2")
        return 1

    if out is None:
        root, ext = os.path.splitext(path)
        tag = "_".join(f"{n}{v:.2f}" for n, v, _ in changed)
        out = f"{root}__patched_{tag}{ext or '.bin'}"

    with open(out, "wb") as f:
        f.write(data)

    for n, v, raw in changed:
        print(f"  {n} = {v:.5f}  (raw={raw}, записан в 0x{globals()['OFF_'+n]:04X} и дубль +0x{MIRROR_DELTA:04X})")
    print(f"Сохранено: {out}")
    print("ПРИМЕЧАНИЕ: CRC не пересчитан. Проверь, примет ли прибор файл.")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Чтение/запись T1/T2 для дампа 8192 байта")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_read = sub.add_parser("read", help="показать T1/T2/SUM")
    p_read.add_argument("file")

    p_write = sub.add_parser("write", help="записать T1/T2 (с дублями)")
    p_write.add_argument("file")
    p_write.add_argument("--t1", type=float, default=None, help="новое значение T1")
    p_write.add_argument("--t2", type=float, default=None, help="новое значение T2")
    p_write.add_argument("-o", "--out", default=None, help="выходной файл")

    args = ap.parse_args()
    if args.cmd == "read":
        cmd_read(args.file)
    elif args.cmd == "write":
        sys.exit(cmd_write(args.file, args.t1, args.t2, args.out))


if __name__ == "__main__":
    main()
