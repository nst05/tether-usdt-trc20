#!/usr/bin/env python3
"""
smt_state — парсер чекпоинта состояния исследуемый прибор из дампа W25Q64.

По результатам авторизованного аудита. Постоянное хранилище состояния прибора —
две половины по 8 КБ (пинг-понг) в самом верху флешки:
    0x7FC000 и 0x7FE000
Активна та, у которой в начале записи НЕ 0xFFFFFFFF. Внутри — кольцо из
64 записей по 128 байт; каждая запись = почасовой снимок прибора.

Раскладка записи (128 байт), подтверждена на реальном дампе:
    +0x00 float64  показания (накопленный объём, м³)   ← то, что на экране
    +0x08 float64  второй накопитель (реверс/резерв)
    +0x10 float64  копия показаний (контроль целостности)
    +0x18 float32  температура №1 (среды), °C
    +0x20 float32  температура №2 (среды), °C
    +0x24/28/2C float32 x3  каналы давления (−35.0 = «не настроено»)
    +0x38 u32      слово статуса/режима
    +0x40 u32      порядковый номер записи
    +0x5C u32      маркер записи 0xA5A5.... (признак валидности)
    +0x60 float32  поправочный коэффициент
    +0x74 u32      метка времени Unix (кратна часу)

Кроме чекпоинта, тот же формат (со сдвинутым заголовком) используется в главном
архиве 0x000000..0x128000 — режим --archive.

Использование:
    python3 smt_state.py dump.bin            # разобрать активную половину чекпоинта
    python3 smt_state.py dump.bin 0x7FC000   # принудительно указать половину
    python3 smt_state.py dump.bin --archive  # разобрать главный архив 0x000000
"""

import sys, struct, datetime

HALVES = (0x7FE000, 0x7FC000)   # порядок предпочтения; активна — с валидным началом
REC = 0x80                       # размер записи
NREC = 0x2000 // REC             # 64 записи в половине


def _u32(b, o): return struct.unpack_from("<I", b, o)[0]
def _f32(b, o): return struct.unpack_from("<f", b, o)[0]
def _f64(b, o): return struct.unpack_from("<d", b, o)[0]


def pick_half(data, forced=None):
    if forced is not None:
        return forced
    for base in HALVES:
        if _u32(data, base) != 0xFFFFFFFF:
            return base
    raise ValueError("обе половины пусты (0xFF) — состояние не найдено")


def parse_record(data, off):
    marker = _u32(data, off + 0x5C)
    valid = (marker >> 16) == 0xA5A5      # маркер 0xA5A5 в старших 16 битах
    ts = _u32(data, off + 0x74)
    try:
        dt = datetime.datetime.utcfromtimestamp(ts) if 1e8 < ts < 4e9 else None
    except Exception:
        dt = None
    return dict(
        offset=off,
        volume=_f64(data, off + 0x00),
        volume_copy=_f64(data, off + 0x10),
        accumulator2=_f64(data, off + 0x08),
        temp1=_f32(data, off + 0x18),
        temp2=_f32(data, off + 0x20),
        pressure=[_f32(data, off + 0x24), _f32(data, off + 0x28), _f32(data, off + 0x2C)],
        status=_u32(data, off + 0x38),
        index=_u32(data, off + 0x40),
        coeff=_f32(data, off + 0x60),
        unixtime=ts,
        datetime=dt,
        marker=marker,
        valid=valid,
    )


def parse_dump(data, forced=None):
    base = pick_half(data, forced)
    recs = []
    for i in range(NREC):
        off = base + i * REC
        if _u32(data, off) == 0xFFFFFFFF:      # пустой слот кольца
            continue
        recs.append(parse_record(data, off))
    return base, recs


def parse_archive(data, base=0x40, end=0x128000, stride=REC):
    """Главный архив: заголовок впереди (время +0x00, индекс +0x08, показания +0x0C)."""
    recs = []
    for o in range(base, min(end, len(data)) - stride, stride):
        ts = _u32(data, o)
        if ts == 0xFFFFFFFF or not (1e9 < ts < 2e9):   # пусто или явно битый слот
            continue
        try:
            dt = datetime.datetime.utcfromtimestamp(ts)
        except Exception:
            continue
        recs.append(dict(
            offset=o, unixtime=ts, datetime=dt,
            index=_u32(data, o + 0x08),
            volume=_f64(data, o + 0x0C),
            volume_copy=_f64(data, o + 0x1C),
            temp1=_f32(data, o + 0x24),
            temp2=_f32(data, o + 0x2C),
        ))
    return recs



def analyse_timeline(records, tolerance=1e-9):
    """Enrich parsed history with objective integrity/sequence anomalies.

    The function does not guess consumption limits. It flags only verifiable
    inconsistencies: mirrored value mismatch, time rollback, index rollback and
    accumulated-volume decrease. Returns (enriched_records, summary).
    """
    out = []
    previous = None
    counters = {"copy_mismatch": 0, "time_back": 0, "index_back": 0,
                "volume_back": 0, "anomalies": 0}
    for source in records:
        row = dict(source)
        marks = []
        copy_value = row.get("volume_copy")
        volume = row.get("volume")
        integrity_ok = True
        if copy_value is not None and volume is not None:
            integrity_ok = abs(float(volume) - float(copy_value)) <= tolerance
            if not integrity_ok:
                marks.append("копия показания не совпала")
                counters["copy_mismatch"] += 1
        if previous is not None:
            if row.get("unixtime") and previous.get("unixtime") and row["unixtime"] < previous["unixtime"]:
                marks.append("время назад")
                counters["time_back"] += 1
            if row.get("index") is not None and previous.get("index") is not None and row["index"] < previous["index"]:
                marks.append("индекс назад")
                counters["index_back"] += 1
            if volume is not None and previous.get("volume") is not None and float(volume) < float(previous["volume"]) - tolerance:
                marks.append("показание уменьшилось")
                counters["volume_back"] += 1
        row["integrity_ok"] = integrity_ok
        row["anomaly"] = "; ".join(marks)
        counters["anomalies"] += bool(marks)
        out.append(row)
        previous = row
    summary = dict(counters)
    summary["count"] = len(out)
    summary["first_datetime"] = out[0].get("datetime") if out else None
    summary["last_datetime"] = out[-1].get("datetime") if out else None
    summary["first_volume"] = out[0].get("volume") if out else None
    summary["last_volume"] = out[-1].get("volume") if out else None
    summary["delta_volume"] = (float(out[-1]["volume"]) - float(out[0]["volume"])) if len(out) >= 2 else 0.0
    return out, summary

def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    data = open(sys.argv[1], "rb").read()

    if "--archive" in sys.argv[2:]:
        recs = parse_archive(data)
        print(f"[smt_state] главный архив 0x000000, валидных записей: {len(recs)}")
        print(f"{'#':>5} {'время (UTC)':<19} {'показания':>13} {'t1':>7} {'t2':>7}")
        for r in recs[:40]:
            print(f"{r['index']:>5} {r['datetime'].strftime('%Y-%m-%d %H:%M'):<19} "
                  f"{r['volume']:>13.6f} {r['temp1']:>7.2f} {r['temp2']:>7.2f}")
        if len(recs) > 40:
            print(f"  … ещё {len(recs)-40} записей")
        vols = {}
        for r in recs:
            if 0 <= abs(r['volume']) < 1e9:
                vols[round(r['volume'], 6)] = vols.get(round(r['volume'], 6), 0) + 1
        top = sorted(vols.items(), key=lambda x: -x[1])[:8]
        print("\nЧастые значения показаний (значение: сколько записей):")
        for v, c in top:
            print(f"  {v:>13.6f}: {c}")
        return

    forced = int(sys.argv[2], 0) if len(sys.argv) > 2 else None
    base, recs = parse_dump(data, forced)
    print(f"[smt_state] активная половина 0x{base:06X}, записей: {len(recs)}")
    print(f"{'#':>3} {'время (UTC)':<19} {'показания':>12} {'t1':>7} {'t2':>7} {'вал.':>5}")
    for r in recs:
        t = r['datetime'].strftime('%Y-%m-%d %H:%M') if r['datetime'] else '—'
        ok = 'да' if (r['valid'] and abs(r['volume'] - r['volume_copy']) < 1e-9) else 'НЕТ'
        print(f"{r['index']:>3} {t:<19} {r['volume']:>12.6f} "
              f"{r['temp1']:>7.2f} {r['temp2']:>7.2f} {ok:>5}")
    if recs:
        last = max(recs, key=lambda r: r['unixtime'])
        print(f"\nПоследние показания: {last['volume']:.6f} м³ "
              f"(запись #{last['index']}, {last['datetime']})")


if __name__ == "__main__":
    main()
