# -*- coding: utf-8 -*-
"""
Собирает icon.ico из логотипа, нарисованного в 201_drob_random.py.

Запуск:  python make_icon.py

Дополнительных библиотек не нужно — только PyQt5, который и так требуется
программе. Файл .ico подхватывается сборкой (см. 201_drob_random.spec).

Формат: размеры до 128 пишутся классическим DIB (BMP), 256 — PNG.
Так .ico понимают и старые инструменты, и Windows.
"""

import importlib.util
import os
import struct
import sys

from PyQt5.QtCore import QBuffer
from PyQt5.QtGui import QImage
from PyQt5.QtWidgets import QApplication

ROOT = os.path.dirname(os.path.abspath(__file__))
ICON_PATH = os.path.join(ROOT, "icon.ico")
SIZES = [16, 24, 32, 48, 64, 128, 256]
PNG_FROM = 256          # начиная с этого размера пишем PNG, ниже — DIB


def load_app_module():
    """Имя модуля начинается с цифры, обычный import не годится."""
    spec = importlib.util.spec_from_file_location(
        "tool", os.path.join(ROOT, "201_drob_random.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def png_bytes(pixmap):
    # QBuffer без аргументов держит массив внутри себя. Если передать
    # QByteArray() прямо в конструктор, временный объект тут же разрушится
    # и Qt упадёт на записи.
    buffer = QBuffer()
    buffer.open(QBuffer.ReadWrite)
    pixmap.save(buffer, "PNG")
    data = bytes(buffer.data())
    buffer.close()
    return data


def dib_bytes(pixmap):
    """BITMAPINFOHEADER + пиксели BGRA снизу вверх + пустая AND-маска."""
    image = pixmap.toImage().convertToFormat(QImage.Format_ARGB32)
    width, height = image.width(), image.height()

    pointer = image.constBits()
    pointer.setsize(image.byteCount())
    raw = bytes(pointer)
    stride = image.bytesPerLine()

    rows = [raw[y * stride:y * stride + width * 4] for y in range(height)]
    pixels = b"".join(reversed(rows))               # DIB хранится снизу вверх

    mask_stride = ((width + 31) // 32) * 4          # 1 бит на пиксель, до 4 байт
    mask = b"\x00" * (mask_stride * height)

    header = struct.pack(
        "<IiiHHIIiiII",
        40,                 # размер заголовка
        width,
        height * 2,         # XOR + AND вместе
        1,                  # плоскости
        32,                 # бит на пиксель
        0,                  # без сжатия
        len(pixels) + len(mask),
        0, 0, 0, 0,
    )
    return header + pixels + mask


def build_ico(module, path):
    entries = []
    for size in SIZES:
        pixmap = module.logo_pixmap(size)
        data = png_bytes(pixmap) if size >= PNG_FROM else dib_bytes(pixmap)
        entries.append((size, data))

    offset = 6 + 16 * len(entries)
    directory = b""
    payload = b""
    for size, data in entries:
        directory += struct.pack(
            "<BBBBHHII",
            size if size < 256 else 0,   # 0 означает 256
            size if size < 256 else 0,
            0, 0, 1, 32,
            len(data), offset,
        )
        payload += data
        offset += len(data)

    with open(path, "wb") as f:
        f.write(struct.pack("<HHH", 0, 1, len(entries)))
        f.write(directory)
        f.write(payload)
    return entries


def main():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    # QApplication держим в глобальной переменной: если он будет разрушен
    # раньше созданных QPixmap, Qt падает при выходе.
    global _app
    _app = QApplication(sys.argv)

    module = load_app_module()
    entries = build_ico(module, ICON_PATH)

    print(f"Готово: {ICON_PATH}")
    for size, data in entries:
        kind = "PNG" if size >= PNG_FROM else "DIB"
        print(f"  {size:>3}x{size:<3} {kind}  {len(data):>7} байт")
    print(f"  всего {os.path.getsize(ICON_PATH)} байт")
    sys.stdout.flush()
    os._exit(0)      # выходим до разрушения Qt-объектов


if __name__ == "__main__":
    main()
