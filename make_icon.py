# -*- coding: utf-8 -*-
"""
Собирает icon.ico с логотипом «микросхема + точки».

Запуск:  python make_icon.py

Скрипт самодостаточен: логотип рисуется прямо здесь и не зависит ни от одной
из программ, поэтому его можно положить в любую папку (и к 201_drob_random,
и к all_tabs_ch341). Нужен только PyQt5 — Pillow не требуется.

Формат: размеры до 128 пишутся классическим DIB (BMP), 256 — PNG.
Так .ico понимают и старые инструменты, и Windows.
"""

import os
import struct
import sys

from PyQt5.QtCore import Qt, QBuffer, QRectF
from PyQt5.QtGui import (
    QImage, QPixmap, QPainter, QColor, QLinearGradient, QBrush,
)
from PyQt5.QtWidgets import QApplication

ROOT = os.path.dirname(os.path.abspath(__file__))
ICON_PATH = os.path.join(ROOT, "icon.ico")
SIZES = [16, 24, 32, 48, 64, 128, 256]
PNG_FROM = 256          # начиная с этого размера пишем PNG, ниже — DIB

LOGO_TOP = "#5c7cfa"
LOGO_BOTTOM = "#3b5bdb"


def paint_logo(painter, size):
    """Тот же логотип, что рисуют программы: микросхема с точками игральной кости."""
    sz = float(size)
    compact = size < 40
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(Qt.NoPen)

    gradient = QLinearGradient(0, 0, sz, sz)
    gradient.setColorAt(0.0, QColor(LOGO_TOP))
    gradient.setColorAt(1.0, QColor(LOGO_BOTTOM))
    painter.setBrush(QBrush(gradient))
    painter.drawRoundedRect(QRectF(0, 0, sz, sz), sz * 0.22, sz * 0.22)

    painter.setBrush(QColor("#ffffff"))
    if compact:
        margin, dot_r, dots = 0.21, 0.070, (0.355, 0.50, 0.645)
    else:
        margin, dot_r, dots = 0.26, 0.047, (0.385, 0.50, 0.615)
        pin_w, pin_h = sz * 0.11, sz * 0.055
        for center in (0.37, 0.50, 0.63):
            y = sz * center - pin_h / 2
            painter.drawRoundedRect(QRectF(sz * 0.17, y, pin_w, pin_h), pin_h / 2, pin_h / 2)
            painter.drawRoundedRect(QRectF(sz * 0.72, y, pin_w, pin_h), pin_h / 2, pin_h / 2)

    side = sz * (1 - 2 * margin)
    painter.drawRoundedRect(QRectF(sz * margin, sz * margin, side, side), sz * 0.08, sz * 0.08)

    painter.setBrush(QColor(LOGO_BOTTOM))
    r = sz * dot_r
    for center in dots:
        painter.drawEllipse(QRectF(center * sz - r, center * sz - r, 2 * r, 2 * r))


def logo_pixmap(size):
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    paint_logo(painter, size)
    painter.end()
    return pixmap


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


def build_ico(path):
    entries = []
    for size in SIZES:
        pixmap = logo_pixmap(size)
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

    entries = build_ico(ICON_PATH)

    print(f"Готово: {ICON_PATH}")
    for size, data in entries:
        kind = "PNG" if size >= PNG_FROM else "DIB"
        print(f"  {size:>3}x{size:<3} {kind}  {len(data):>7} байт")
    print(f"  всего {os.path.getsize(ICON_PATH)} байт")
    sys.stdout.flush()
    os._exit(0)      # выходим до разрушения Qt-объектов


if __name__ == "__main__":
    main()
