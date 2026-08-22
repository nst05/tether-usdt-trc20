#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генератор иконки integra101.

Рисует иконку через QPainter и собирает многоразмерный .ico вручную.
Qt умеет писать ico, но только одной картинкой — Windows потом сам её
уменьшает, и на 16px получается каша. Поэтому каждый размер рисуется
отдельно, кодируется в PNG и укладывается в контейнер ICO.

Запуск:
    python make_icon.py

Создаёт icon.ico (7 размеров), icon.png (256px) и splash.png —
статическую заставку PyInstaller.
"""

import struct
import sys

from PyQt5 import QtCore, QtGui

# Размеры внутри .ico. 256 идёт последним — Windows берёт его для крупных
# представлений, мелкие рисуются отдельно и потому остаются читаемыми.
SIZES = (16, 24, 32, 48, 64, 128, 256)

# Палитры под тёмные темы приложений. Программы две, акценты у них разные,
# и иконки должны различаться в панели задач.
THEMES = {
    "integra101": {
        "bg_top": "#161B22", "bg_bottom": "#0D1117", "border": "#30363D",
        "chip_top": "#58A6FF", "chip_bottom": "#1F6FEB",
        "pin": "#8B949E", "mark": "#0D1117", "accent": "#3FB950",
        "title": "integra101",
        "subtitle": "Запись значений в EEPROM · CRC-16 CCITT",
        "prefix": "icon",
    },
    "srt": {
        "bg_top": "#151A27", "bg_bottom": "#0F1115", "border": "#2A2F3A",
        "chip_top": "#7C8FE0", "chip_bottom": "#3A4A7A",
        "pin": "#8B93A6", "mark": "#0F1115", "accent": "#5D74C5",
        "title": "MERK-3F",
        "subtitle": "Правка показаний напрямую в SPI FRAM",
        "prefix": "icon_srt",
    },
}

THEME = THEMES["integra101"]

BG_TOP = THEME["bg_top"]
BG_BOTTOM = THEME["bg_bottom"]
BORDER = THEME["border"]
CHIP_TOP = THEME["chip_top"]
CHIP_BOTTOM = THEME["chip_bottom"]
PIN = THEME["pin"]
MARK = THEME["mark"]
ACCENT = THEME["accent"]


def use_theme(name: str):
    """Переключить палитру перед отрисовкой"""
    global THEME, BG_TOP, BG_BOTTOM, BORDER, CHIP_TOP, CHIP_BOTTOM, PIN, MARK, ACCENT
    THEME = THEMES[name]
    BG_TOP = THEME["bg_top"]
    BG_BOTTOM = THEME["bg_bottom"]
    BORDER = THEME["border"]
    CHIP_TOP = THEME["chip_top"]
    CHIP_BOTTOM = THEME["chip_bottom"]
    PIN = THEME["pin"]
    MARK = THEME["mark"]
    ACCENT = THEME["accent"]


def draw_icon(size: int) -> QtGui.QImage:
    """Нарисовать иконку заданного размера"""
    image = QtGui.QImage(size, size, QtGui.QImage.Format_ARGB32)
    image.fill(QtCore.Qt.transparent)

    p = QtGui.QPainter(image)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)

    s = float(size)

    # ── Подложка ──────────────────────────────────────────────────────
    bg = QtGui.QLinearGradient(0, 0, 0, s)
    bg.setColorAt(0.0, QtGui.QColor(BG_TOP))
    bg.setColorAt(1.0, QtGui.QColor(BG_BOTTOM))

    radius = s * 0.22
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(bg)
    p.drawRoundedRect(QtCore.QRectF(0, 0, s, s), radius, radius)

    # Рамка тонкая: на мелких размерах она съедает пиксели, поэтому
    # рисуем её только начиная с 32px.
    if size >= 32:
        pen = QtGui.QPen(QtGui.QColor(BORDER))
        pen.setWidthF(max(1.0, s * 0.012))
        p.setPen(pen)
        p.setBrush(QtCore.Qt.NoBrush)
        inset = pen.widthF() / 2
        p.drawRoundedRect(
            QtCore.QRectF(inset, inset, s - 2 * inset, s - 2 * inset),
            radius - inset, radius - inset)

    # ── Ножки микросхемы ──────────────────────────────────────────────
    # На мелких размерах три тонкие ножки сливаются в грязь, поэтому там
    # корпус крупнее, а ножек две и они толще. На 16px ножек нет совсем —
    # остаётся один чёткий силуэт.
    if size >= 32:
        chip = QtCore.QRectF(s * 0.28, s * 0.28, s * 0.44, s * 0.44)
        pin_count, pin_len, pin_thick = 3, s * 0.10, s * 0.075
    elif size >= 24:
        chip = QtCore.QRectF(s * 0.30, s * 0.24, s * 0.40, s * 0.52)
        pin_count, pin_len, pin_thick = 2, s * 0.13, s * 0.13
    else:
        chip = QtCore.QRectF(s * 0.22, s * 0.22, s * 0.56, s * 0.56)
        pin_count = 0
        pin_len = pin_thick = 0.0

    p.setPen(QtCore.Qt.NoPen)

    if pin_count:
        p.setBrush(QtGui.QColor(PIN))
        pin_gap = chip.height() / pin_count
        for i in range(pin_count):
            y = chip.top() + pin_gap * (i + 0.5) - pin_thick / 2
            # Целые координаты: иначе тонкая ножка размазывается на два
            # пикселя и теряет контраст.
            y = round(y)
            p.drawRoundedRect(
                QtCore.QRectF(round(chip.left() - pin_len), y,
                              pin_len, pin_thick),
                pin_thick / 2, pin_thick / 2)
            p.drawRoundedRect(
                QtCore.QRectF(round(chip.right()), y, pin_len, pin_thick),
                pin_thick / 2, pin_thick / 2)

    # ── Корпус микросхемы ─────────────────────────────────────────────
    body = QtGui.QLinearGradient(chip.left(), chip.top(),
                                 chip.left(), chip.bottom())
    body.setColorAt(0.0, QtGui.QColor(CHIP_TOP))
    body.setColorAt(1.0, QtGui.QColor(CHIP_BOTTOM))

    p.setBrush(body)
    chip_radius = chip.width() * 0.16
    p.drawRoundedRect(chip, chip_radius, chip_radius)

    # Метка первой ножки — тёмная точка в углу корпуса.
    dot = chip.width() * (0.20 if size < 32 else 0.125)
    p.setBrush(QtGui.QColor(MARK))
    p.drawEllipse(QtCore.QRectF(chip.left() + chip.width() * 0.15,
                                chip.top() + chip.height() * 0.15,
                                dot, dot))

    # ── Зелёный индикатор ─────────────────────────────────────────────
    # На 16px он сливается с корпусом, поэтому только от 24px.
    if size >= 24:
        led = s * 0.13
        p.setBrush(QtGui.QColor(ACCENT))
        p.drawEllipse(QtCore.QRectF(s - led - s * 0.13,
                                    s - led - s * 0.13, led, led))

    p.end()
    return image


def to_png(image: QtGui.QImage) -> bytes:
    """Закодировать изображение в PNG"""
    buffer = QtCore.QBuffer()
    buffer.open(QtCore.QIODevice.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise RuntimeError("не удалось закодировать PNG")
    return bytes(buffer.data())


def build_ico(images) -> bytes:
    """
    Собрать контейнер ICO из готовых PNG.

    Структура: ICONDIR (6 байт), затем по ICONDIRENTRY (16 байт) на каждый
    размер, затем сами картинки. В поле размера 0 означает 256.
    """
    payloads = [to_png(image) for image in images]

    header = struct.pack("<HHH", 0, 1, len(payloads))
    offset = len(header) + 16 * len(payloads)

    entries = []
    for image, payload in zip(images, payloads):
        side = image.width()
        entries.append(struct.pack(
            "<BBBBHHII",
            0 if side >= 256 else side,   # ширина
            0 if side >= 256 else side,   # высота
            0,                            # палитра не используется
            0,                            # зарезервировано
            1,                            # плоскостей
            32,                           # бит на пиксель
            len(payload),
            offset,
        ))
        offset += len(payload)

    return header + b"".join(entries) + b"".join(payloads)




# ═══════════════════════════════════════════════════════════════════════════
#  Заставка для PyInstaller
# ═══════════════════════════════════════════════════════════════════════════
#
# Показывается сразу при запуске exe, ещё до старта Python, и закрывает
# распаковку onefile — самую заметную паузу. Статическая: анимировать её
# нечем, движок заставки умеет только менять текст.

SPLASH_W, SPLASH_H = 420, 240


def draw_splash() -> QtGui.QImage:
    """Нарисовать статическую заставку под стиль экрана загрузки"""
    image = QtGui.QImage(SPLASH_W, SPLASH_H, QtGui.QImage.Format_ARGB32)
    image.fill(QtCore.Qt.transparent)

    p = QtGui.QPainter(image)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.setRenderHint(QtGui.QPainter.TextAntialiasing)

    rect = QtCore.QRectF(0.5, 0.5, SPLASH_W - 1, SPLASH_H - 1)
    bg = QtGui.QLinearGradient(0, 0, 0, SPLASH_H)
    bg.setColorAt(0.0, QtGui.QColor(BG_TOP))
    bg.setColorAt(1.0, QtGui.QColor(BG_BOTTOM))
    p.setPen(QtGui.QPen(QtGui.QColor(BORDER), 1))
    p.setBrush(bg)
    p.drawRoundedRect(rect, 14, 14)

    # Иконка по центру сверху.
    icon = draw_icon(72)
    p.drawImage(int(SPLASH_W / 2 - 36), 34, icon)

    # Незаполненное кольцо — намёк на то, что идёт загрузка.
    centre = QtCore.QPointF(SPLASH_W / 2, 70)
    box = QtCore.QRectF(centre.x() - 52, centre.y() - 52, 104, 104)
    pen = QtGui.QPen(QtGui.QColor("#21262D"), 5)
    pen.setCapStyle(QtCore.Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(QtCore.Qt.NoBrush)
    p.drawEllipse(box)
    pen = QtGui.QPen(QtGui.QColor(CHIP_TOP), 5)
    pen.setCapStyle(QtCore.Qt.RoundCap)
    p.setPen(pen)
    p.drawArc(box, 90 * 16, -70 * 16)

    font = QtGui.QFont()
    font.setPointSize(19)
    font.setBold(True)
    p.setFont(font)
    p.setPen(QtGui.QColor("#E6EDF3"))
    p.drawText(QtCore.QRect(0, 140, SPLASH_W, 30),
               QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter, THEME["title"])

    font = QtGui.QFont()
    font.setPointSize(9)
    p.setFont(font)
    p.setPen(QtGui.QColor("#8B949E"))
    p.drawText(QtCore.QRect(0, 168, SPLASH_W, 20),
               QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter,
               THEME["subtitle"])

    p.end()
    return image


def build_theme(name: str):
    """Нарисовать иконку и заставку для одной темы"""
    use_theme(name)
    prefix = THEME["prefix"]
    splash_name = "splash.png" if prefix == "icon" else prefix + "_splash.png"

    images = [draw_icon(size) for size in SIZES]
    with open(prefix + ".ico", "wb") as f:
        f.write(build_ico(images))
    images[-1].save(prefix + ".png", "PNG")
    draw_splash().save(splash_name, "PNG")

    # Вывод только ASCII: скрипт запускается из .bat, а на англоязычной
    # Windows перенаправленный stdout берёт кодировку локали (cp437/cp1252),
    # и кириллица валится с UnicodeEncodeError.
    print(prefix + ".ico   sizes: " + ", ".join(str(s) for s in SIZES))
    print(prefix + ".png   256x256")
    print("%s %dx%d, PyInstaller splash" % (splash_name, SPLASH_W, SPLASH_H))


def main():
    app = QtGui.QGuiApplication.instance()
    if app is None:
        app = QtGui.QGuiApplication(sys.argv)

    names = sys.argv[1:] or list(THEMES)
    for name in names:
        if name not in THEMES:
            print("unknown theme: %s; known: %s" % (name, ", ".join(THEMES)))
            return 1
        build_theme(name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
