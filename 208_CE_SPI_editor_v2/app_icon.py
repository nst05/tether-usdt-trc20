"""Иконка приложения CE208 — генерация и установка в окно.

Иконка рисуется кодом (без внешних библиотек): стальная пластина, корпус
микросхемы с выводами и импульс энергии. Готовые файлы лежат в ``assets/``
и пересоздаются командой ``python app_icon.py``; если файлов нет, иконка
строится прямо в памяти, поэтому приложение никогда не остаётся без значка.
"""

from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
ICO_PATH = ASSETS_DIR / "ce208.ico"
PNG_PATH = ASSETS_DIR / "ce208.png"

# Цвета знака (согласованы с палитрой ui_theme).
_PLATE_TOP = (0x3D, 0x50, 0x63)
_PLATE_BOTTOM = (0x24, 0x33, 0x3E)
_EDGE = (0x62, 0x84, 0xA1)
_CHIP = (0x3E, 0x7C, 0xA6)
_CHIP_EDGE = (0xB4, 0xCF, 0xE1)
_PIN = (0xC9, 0xD6, 0xE0)
_BOLT = (0xF2, 0xC5, 0x6B)


# ═══════════════════════════════════════════════════════════════════════════
#  Растеризация знака
# ═══════════════════════════════════════════════════════════════════════════

def _rounded(x: float, y: float, x0: float, y0: float, x1: float, y1: float, radius: float) -> bool:
    """Точка внутри прямоугольника со скруглёнными углами (координаты 0..1)."""
    if x < x0 or x > x1 or y < y0 or y > y1:
        return False
    cx = min(max(x, x0 + radius), x1 - radius)
    cy = min(max(y, y0 + radius), y1 - radius)
    dx, dy = x - cx, y - cy
    return dx * dx + dy * dy <= radius * radius


def _in_polygon(x: float, y: float, points: list[tuple[float, float]]) -> bool:
    inside = False
    count = len(points)
    for index in range(count):
        x0, y0 = points[index]
        x1, y1 = points[(index + 1) % count]
        if (y0 > y) != (y1 > y):
            t = (y - y0) / (y1 - y0)
            if x < x0 + t * (x1 - x0):
                inside = not inside
    return inside


# Молния целиком помещается внутрь корпуса микросхемы.
_BOLT_POINTS = [
    (0.538, 0.285), (0.377, 0.526), (0.483, 0.526), (0.433, 0.715),
    (0.619, 0.463), (0.504, 0.463), (0.598, 0.285),
]

_PINS = [(0.03, 0.235 + index * 0.175, 0.155, 0.305 + index * 0.175) for index in range(4)]
_PINS += [(0.845, 0.235 + index * 0.175, 0.97, 0.305 + index * 0.175) for index in range(4)]


def _sample(x: float, y: float) -> tuple[int, int, int, int] | None:
    """Цвет знака в точке (x, y) ∈ [0,1]² или None — прозрачно."""
    # Выводы микросхемы — под пластиной по краям
    for x0, y0, x1, y1 in _PINS:
        if x0 <= x <= x1 and y0 <= y <= y1:
            return (*_PIN, 255)

    if not _rounded(x, y, 0.055, 0.055, 0.945, 0.945, 0.20):
        return None

    # Кромка пластины
    if not _rounded(x, y, 0.085, 0.085, 0.915, 0.915, 0.17):
        return (*_EDGE, 255)

    # Корпус микросхемы
    if _rounded(x, y, 0.215, 0.215, 0.785, 0.785, 0.09):
        if not _rounded(x, y, 0.255, 0.255, 0.745, 0.745, 0.07):
            return (*_CHIP_EDGE, 255)
        if _in_polygon(x, y, _BOLT_POINTS):
            return (*_BOLT, 255)
        return (*_CHIP, 255)

    if _in_polygon(x, y, _BOLT_POINTS):
        return (*_BOLT, 255)

    # Вертикальный градиент стальной пластины
    ratio = (y - 0.085) / 0.83
    ratio = min(1.0, max(0.0, ratio))
    color = tuple(round(a + (b - a) * ratio) for a, b in zip(_PLATE_TOP, _PLATE_BOTTOM))
    return (*color, 255)


def render_rgba(size: int, supersample: int = 3) -> list[list[tuple[int, int, int, int]]]:
    """Матрица RGBA size×size со сглаживанием краёв."""
    rows: list[list[tuple[int, int, int, int]]] = []
    step = 1.0 / (size * supersample)
    for py in range(size):
        row: list[tuple[int, int, int, int]] = []
        for px in range(size):
            r = g = b = a = 0
            for sy in range(supersample):
                y = (py * supersample + sy + 0.5) * step
                for sx in range(supersample):
                    x = (px * supersample + sx + 0.5) * step
                    sample = _sample(x, y)
                    if sample is not None:
                        r += sample[0]
                        g += sample[1]
                        b += sample[2]
                        a += 255
            total = supersample * supersample
            if a == 0:
                row.append((0, 0, 0, 0))
                continue
            covered = a // 255
            row.append((r // covered, g // covered, b // covered, a // total))
        rows.append(row)
    return rows


# ═══════════════════════════════════════════════════════════════════════════
#  Файлы: PNG и ICO без внешних библиотек
# ═══════════════════════════════════════════════════════════════════════════

def png_bytes(size: int = 256) -> bytes:
    rows = render_rgba(size, supersample=2 if size > 128 else 3)
    raw = bytearray()
    for row in rows:
        raw.append(0)  # фильтр «none»
        for r, g, b, a in row:
            raw.extend((r, g, b, a))

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))


def _dib_bytes(size: int) -> bytes:
    """32-битный DIB (BGRA, снизу вверх) + пустая маска — формат внутри ICO."""
    rows = render_rgba(size, supersample=3)
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, size * size * 4, 0, 0, 0, 0)
    pixels = bytearray()
    for row in reversed(rows):
        for r, g, b, a in row:
            pixels.extend((b, g, r, a))
    mask_row = ((size + 31) // 32) * 4
    return header + bytes(pixels) + bytes(mask_row * size)


def ico_bytes(sizes: tuple[int, ...] = (16, 24, 32, 48, 64, 128)) -> bytes:
    images = [(size, _dib_bytes(size)) for size in sizes]
    offset = 6 + 16 * len(images)
    directory = bytearray(struct.pack("<HHH", 0, 1, len(images)))
    payload = bytearray()
    for size, data in images:
        directory.extend(struct.pack(
            "<BBBBHHII",
            size if size < 256 else 0, size if size < 256 else 0,
            0, 0, 1, 32, len(data), offset,
        ))
        payload.extend(data)
        offset += len(data)
    return bytes(directory) + bytes(payload)


def write_assets(target: Path | None = None) -> tuple[Path, Path]:
    """Создаёт assets/ce208.ico и assets/ce208.png."""
    directory = Path(target) if target else ASSETS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    ico = directory / "ce208.ico"
    png = directory / "ce208.png"
    ico.write_bytes(ico_bytes())
    png.write_bytes(png_bytes(256))
    return ico, png


# ═══════════════════════════════════════════════════════════════════════════
#  Установка иконки окна
# ═══════════════════════════════════════════════════════════════════════════

def _photo_from_pixels(size: int = 48):
    """Резервный путь: PhotoImage, заполненный построчно (без файлов)."""
    import tkinter as tk

    rows = render_rgba(size, supersample=2)
    photo = tk.PhotoImage(width=size, height=size)
    # Фон под прозрачностью — цвет стали, чтобы край не выглядел рваным.
    for y, row in enumerate(rows):
        line = []
        for r, g, b, a in row:
            if a < 24:
                line.append("#31414F")
            else:
                line.append("#%02X%02X%02X" % (r, g, b))
        photo.put("{" + " ".join(line) + "}", to=(0, y))
    return photo


def set_window_icon(window) -> object | None:
    """Ставит иконку окна. Возвращает PhotoImage (его нужно сохранить в поле).

    Порядок: .ico (даёт значок в панели задач Windows), затем .png через Tk 8.6,
    затем построение в памяти. Каждый шаг необязателен — сбой не мешает запуску.
    """
    import tkinter as tk

    if ICO_PATH.exists():
        try:
            window.iconbitmap(default=str(ICO_PATH))
        except Exception:
            try:
                window.iconbitmap(str(ICO_PATH))
            except Exception:
                pass

    photo = None
    if PNG_PATH.exists():
        try:
            photo = tk.PhotoImage(file=str(PNG_PATH))
            # 256×256 в iconphoto избыточна — уменьшаем целым коэффициентом.
            if photo.width() >= 128:
                photo = photo.subsample(max(1, photo.width() // 64))
        except Exception:
            photo = None
    if photo is None:
        try:
            photo = _photo_from_pixels(48)
        except Exception:
            return None
    try:
        window.iconphoto(True, photo)
    except Exception:
        return None
    return photo


if __name__ == "__main__":
    ico, png = write_assets()
    print(f"Записано: {ico} ({ico.stat().st_size} б), {png} ({png.stat().st_size} б)")
    sys.exit(0)
