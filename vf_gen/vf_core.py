# -*- coding: utf-8 -*-
"""
Математика генератора ce101 r5 145 — без Qt, поэтому легко проверяется тестами.

Формат прошивки
───────────────
В EEPROM пишутся два блока по 512 байт:

  0x1E000  базовый блок — повторяющийся триплет [b1, b3, b2]  (b2 и b3 переставлены!)
  0x1E200  дробный блок — N триплетов «01 00 00», остальное нули

Показание прибора:

  R = 0.85 * idx(b1)
    + 435.20 * (b2 // 2) + 5.95 * (b2 & 1)
    + 111411.20 * (b3 // 2) + 2.55 * (b3 & 1)
    + 0.03 * N_дробных

  idx(b1) = (b1 & ~0x06) + 256*(бит 0x04) + 65536*(бит 0x02)

Всё это кратно 0.01, поэтому внутри модуля считаем в сотых долях (целыми),
чтобы не накапливать ошибку float:

  R_сотых = 85 * U + 3 * N,  где U = idx + 512*(b2>>1) + 7*(b2&1)
                                     + 131072*(b3>>1) + 3*(b3&1)

Почему исходная программа «не все числа» выдаёт
───────────────────────────────────────────────
1. Без дробного блока показание всегда кратно 0.85, а из-за структуры b1
   достижимы только 75% значений U (пропущены остатки 2, 5, 6 по модулю 8).
   Точно попасть в целое число удаётся лишь в ~6% случаев, средняя ошибка
   0.36, максимальная 1.20.
2. Дробный блок (шаг 0.03) в интерфейсе был скрыт — а именно он позволяет
   попасть в цель точно: 0.85 и 0.03 взаимно просты в сотых долях (85 и 3),
   поэтому подбором N = 0..170 цель берётся ровно.
3. Перебор был ограничен b3 <= 0x0F, что срезало диапазон на 891 292.15.
   Полный b3 поднимает потолок до 14 260 636.15.
4. Старый решатель брал только floor/ceil от idx и, если оба значения
   оказывались недопустимыми, пропускал вариант целиком.
"""

import bisect

# ── Параметры прошивки ────────────────────────────────────────────────────────
BASE_ADDR = 0x1E000
FRAC_ADDR = 0x1E200
BLOCK_SIZE = 512
TRIPLET_LEN = 3
TRIP_COUNT = BLOCK_SIZE // TRIPLET_LEN      # 170 дробных триплетов

FRAC_STEP_C = 3         # 0.03 в сотых
UNIT_C = 85             # 0.85 в сотых
B3_MAX_ORIGINAL = 0x0F  # ограничение старой программы
B3_MAX_FULL = 0xFF


# ── Соответствие b1 <-> idx ───────────────────────────────────────────────────

def _idx_from_b1(b1):
    base = b1 & ~0x06
    return base + (256 if b1 & 0x04 else 0) + (65536 if b1 & 0x02 else 0)


_IDX_TO_B1 = {}
for _b1 in range(256):
    _IDX_TO_B1.setdefault(_idx_from_b1(_b1), _b1)
IDX_VALUES = sorted(_IDX_TO_B1)             # 256 достижимых idx, максимум 66041


def b1_from_idx(idx):
    return _IDX_TO_B1.get(idx)


# ── Показание ─────────────────────────────────────────────────────────────────

def units(b1, b2, b3):
    """U — показание в единицах по 0.85 (без дробного блока)."""
    return (_idx_from_b1(b1)
            + 512 * (b2 >> 1) + 7 * (b2 & 1)
            + 131072 * (b3 >> 1) + 3 * (b3 & 1))


def reading_centi(b1, b2, b3, n_frac=0):
    """Показание в сотых долях (целое число)."""
    return UNIT_C * units(b1, b2, b3) + FRAC_STEP_C * n_frac


def reading(b1, b2, b3, n_frac=0):
    """Показание как число с плавающей точкой."""
    return reading_centi(b1, b2, b3, n_frac) / 100.0


def max_reading(b3_max=B3_MAX_FULL):
    """Максимум, который вообще можно записать при заданном пределе b3."""
    return reading(0xFF, 0xFF, b3_max, TRIP_COUNT if b3_max >= 0 else 0)


# ── Подбор ────────────────────────────────────────────────────────────────────

class Candidate:
    """Один вариант прошивки."""

    __slots__ = ('b1', 'b2', 'b3', 'n_frac', 'centi', 'target_centi')

    def __init__(self, b1, b2, b3, n_frac, centi, target_centi):
        self.b1 = b1
        self.b2 = b2
        self.b3 = b3
        self.n_frac = n_frac
        self.centi = centi
        self.target_centi = target_centi

    @property
    def value(self):
        return self.centi / 100.0

    @property
    def base_value(self):
        """Показание без дробного блока."""
        return (self.centi - FRAC_STEP_C * self.n_frac) / 100.0

    @property
    def error(self):
        return abs(self.centi - self.target_centi) / 100.0

    @property
    def exact(self):
        return self.centi == self.target_centi

    def triplet(self):
        """Байты так, как они лежат в файле: b1, b3, b2."""
        return bytes((self.b1, self.b3, self.b2))

    def __repr__(self):
        return ('Candidate(b1=%02X b2=%02X b3=%02X n=%d -> %.2f, err=%.2f)'
                % (self.b1, self.b2, self.b3, self.n_frac, self.value, self.error))


def solve(target, use_frac=True, b3_max=B3_MAX_ORIGINAL, max_results=3, idx_window=8):
    """Подбирает варианты для заданного показания.

    target     — желаемое значение (float или строка с числом);
    use_frac   — разрешить дробный блок 0.03 (именно он даёт точное попадание);
    b3_max     — верхний предел b3 (0x0F — как в старой программе, 0xFF — полный);
    Возвращает список Candidate, отсортированный по ошибке.
    """
    target_c = int(round(float(target) * 100))
    if target_c < 0:
        raise ValueError('Значение не может быть отрицательным.')

    frac_max = TRIP_COUNT if use_frac else 0
    best = {}

    for b3 in range(0, min(255, b3_max) + 1):
        t3 = 131072 * (b3 >> 1) + 3 * (b3 & 1)
        if UNIT_C * t3 > target_c + UNIT_C * IDX_VALUES[-1]:
            break
        for b2 in range(256):
            t = t3 + 512 * (b2 >> 1) + 7 * (b2 & 1)
            rest_c = target_c - UNIT_C * t
            if rest_c < -UNIT_C * IDX_VALUES[-1]:
                continue

            # Идеальный idx: дробный блок только прибавляет, поэтому целимся
            # чуть ниже цели и добираем остаток шагами по 0.03.
            ideal = rest_c / UNIT_C
            pos = bisect.bisect_left(IDX_VALUES, ideal)

            for k in range(pos - idx_window, pos + idx_window + 1):
                if not 0 <= k < len(IDX_VALUES):
                    continue
                idx = IDX_VALUES[k]
                base_c = UNIT_C * (t + idx)
                if base_c < 0:
                    continue

                n = 0
                if frac_max:
                    n = (target_c - base_c) // FRAC_STEP_C
                    n = max(0, min(frac_max, n))

                for n_try in {n, min(frac_max, n + 1)}:
                    centi = base_c + FRAC_STEP_C * n_try
                    b1 = _IDX_TO_B1[idx]
                    key = (b1, b2, b3, n_try)
                    if key not in best:
                        best[key] = Candidate(b1, b2, b3, n_try, centi, target_c)

    if not best:
        return []

    ranked = sorted(
        best.values(),
        # при равной ошибке предпочитаем меньше дробных триплетов и меньший b3
        key=lambda c: (abs(c.centi - target_c), c.n_frac, c.b3, c.b2, c.b1),
    )

    # Оставляем варианты с разным результатом, чтобы список не дублировался.
    result, seen = [], set()
    for cand in ranked:
        if cand.centi in seen:
            continue
        seen.add(cand.centi)
        result.append(cand)
        if len(result) >= max_results:
            break
    return result


# ── Сборка блоков и Intel HEX ─────────────────────────────────────────────────

def make_base_block(b1, b2, b3):
    """Базовый блок: повтор триплета [b1, b3, b2] (b2 и b3 переставлены)."""
    trip = bytes((b1 & 0xFF, b3 & 0xFF, b2 & 0xFF))
    reps = BLOCK_SIZE // TRIPLET_LEN + 2
    return (trip * reps)[:BLOCK_SIZE]


def make_frac_block(n_ones):
    """Дробный блок: N триплетов «01 00 00», дальше нули."""
    n = max(0, min(TRIP_COUNT, int(n_ones)))
    blob = bytes((0x01, 0x00, 0x00)) * n
    return blob.ljust(BLOCK_SIZE, b'\x00')[:BLOCK_SIZE]


def _record(count, addr, rectype, payload):
    body = [count, (addr >> 8) & 0xFF, addr & 0xFF, rectype] + list(payload)
    checksum = (~(sum(body) & 0xFF) + 1) & 0xFF
    return ':' + ''.join('%02X' % b for b in body) + '%02X' % checksum


def build_ihex(blocks):
    """blocks — список (адрес, данные). Возвращает текст Intel HEX."""
    lines = []
    current_ela = None

    for addr_base, data in blocks:
        ela = (addr_base >> 16) & 0xFFFF
        if ela != current_ela:
            lines.append(_record(2, 0x0000, 0x04, bytes(((ela >> 8) & 0xFF, ela & 0xFF))))
            current_ela = ela
        base16 = addr_base & 0xFFFF
        for off in range(0, len(data), 16):
            chunk = data[off:off + 16]
            lines.append(_record(len(chunk), base16 + off, 0x00, chunk))

    lines.append(':00000001FF')
    return '\n'.join(lines) + '\n'


def build_hex_for(candidate, base_addr=BASE_ADDR, frac_addr=FRAC_ADDR):
    """Готовый Intel HEX для варианта: базовый блок + дробный, если он нужен."""
    blocks = [(base_addr, make_base_block(candidate.b1, candidate.b2, candidate.b3))]
    if candidate.n_frac > 0:
        blocks.append((frac_addr, make_frac_block(candidate.n_frac)))
    return build_ihex(blocks)


def parse_ihex(text):
    """Разбор Intel HEX обратно в {адрес: байт} — для самопроверки."""
    memory = {}
    ela = 0
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith(':'):
            continue
        raw = bytes.fromhex(line[1:])
        if (sum(raw) & 0xFF) != 0:
            raise ValueError('Неверная контрольная сумма строки: %s' % line)
        count, addr, rectype = raw[0], (raw[1] << 8) | raw[2], raw[3]
        payload = raw[4:4 + count]
        if rectype == 0x04:
            ela = (payload[0] << 8) | payload[1]
        elif rectype == 0x00:
            for i, byte in enumerate(payload):
                memory[(ela << 16) + addr + i] = byte
        elif rectype == 0x01:
            break
    return memory


def format_value(value):
    """7035.0 -> «7035», 7034.6 -> «7034.6» — для имени файла и таблицы."""
    text = ('%.2f' % value).rstrip('0').rstrip('.')
    return text if text else '0'
