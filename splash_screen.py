#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Экран загрузки integra101.

Кольцо прогресса вокруг иконки микросхемы: заполняется по мере готовности,
поверх идёт бегущий блик, сама иконка мягко пульсирует. Панель появляется и
уходит плавно.

Отдельно от заставки PyInstaller: та показывается ещё до старта Python и
закрывает распаковку onefile, а эта — уже инициализацию самого приложения.
"""

import math

from PyQt5 import QtCore, QtGui, QtWidgets

BG_TOP = "#161B22"
BG_BOTTOM = "#0D1117"
BORDER = "#30363D"
TRACK = "#21262D"
ARC_FROM = "#1F6FEB"
ARC_TO = "#3FB950"
GLINT = "#79C0FF"
TITLE = "#E6EDF3"
SUBTITLE = "#8B949E"
STATUS = "#58A6FF"

PANEL_W, PANEL_H = 420, 300
RING_D = 104
RING_W = 5
FPS_MS = 16

# Инициализация приложения занимает миллисекунды, и без этой задержки экран
# не успевает даже проявиться: плавное появление длится дольше, чем вся
# загрузка. Держим его на виду хотя бы столько.
MIN_VISIBLE_MS = 1100


class LoadingSplash(QtWidgets.QWidget):
    """
    Экран загрузки с кольцевым индикатором.

    Использование:
        splash = LoadingSplash()
        splash.start()
        splash.step("Загрузка интерфейса...", 40)
        ...
        splash.finish(main_window)
    """

    def __init__(self, icon: QtGui.QIcon = None, parent=None):
        super().__init__(parent)

        self.setWindowFlags(QtCore.Qt.FramelessWindowHint
                            | QtCore.Qt.WindowStaysOnTopHint
                            | QtCore.Qt.SplashScreen)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setFixedSize(PANEL_W, PANEL_H)

        self._progress = 0.0        # куда стремимся, 0..1
        self._shown = 0.0           # что реально нарисовано, догоняет плавно
        self._phase = 0.0           # фаза бегущего блика
        self._status = "Запуск..."
        self._alive = None          # сколько экран уже на виду

        self._icon = icon
        self._pixmap = None
        if icon is not None and not icon.isNull():
            self._pixmap = icon.pixmap(56, 56)

        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._tick)

        self._opacity = QtWidgets.QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)
        self._fade = QtCore.QPropertyAnimation(self._opacity, b"opacity", self)

        self._centre_on_screen()

    # ── Управление ────────────────────────────────────────────────────

    def start(self):
        """Показать экран с плавным появлением"""
        self._alive = QtCore.QElapsedTimer()
        self._alive.start()

        self.show()
        self._timer.start(FPS_MS)

        self._fade.stop()
        self._fade.setDuration(260)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.setEasingCurve(QtCore.QEasingCurve.OutCubic)
        self._fade.start()

        QtWidgets.QApplication.processEvents()

    def step(self, status: str, percent: float):
        """Обновить подпись и прогресс, прокрутив анимацию"""
        self._status = status
        self._progress = max(0.0, min(100.0, float(percent))) / 100.0
        self.repaint()
        QtWidgets.QApplication.processEvents()

    def finish(self, window: QtWidgets.QWidget = None, hold_ms: int = 260):
        """
        Довести кольцо до конца и плавно погасить экран.

        window: окно, которое показать после исчезновения.
        """
        self._progress = 1.0

        # Крутим настоящее время: и кольцо доходит до конца, и появление
        # успевает отработать. Без этого экран мелькает почти невидимым.
        deadline = QtCore.QElapsedTimer()
        deadline.start()
        while True:
            done = self._shown >= 0.999 and deadline.elapsed() >= 300
            waited_enough = (self._alive is None
                             or self._alive.elapsed() >= MIN_VISIBLE_MS)
            if (done and waited_enough) or deadline.elapsed() > 2500:
                break
            self.repaint()
            QtWidgets.QApplication.processEvents()
            QtCore.QThread.msleep(FPS_MS)

        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(hold_ms, loop.quit)
        loop.exec_()

        self._fade.stop()
        self._fade.setDuration(240)
        self._fade.setStartValue(self._opacity.opacity())
        self._fade.setEndValue(0.0)
        self._fade.setEasingCurve(QtCore.QEasingCurve.InCubic)
        self._fade.finished.connect(self.close)
        self._fade.start()

        if window is not None:
            window.show()
            window.raise_()
            window.activateWindow()

        while self._fade.state() == QtCore.QAbstractAnimation.Running:
            QtWidgets.QApplication.processEvents()

        self._timer.stop()

    # ── Внутреннее ────────────────────────────────────────────────────

    def _centre_on_screen(self):
        screen = QtWidgets.QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        self.move(area.center().x() - PANEL_W // 2,
                  area.center().y() - PANEL_H // 2)

    def _tick(self):
        self._phase = (self._phase + 0.022) % 1.0
        # Показанный прогресс догоняет заданный — рывки сглаживаются.
        self._shown += (self._progress - self._shown) * 0.14
        if abs(self._progress - self._shown) < 0.001:
            self._shown = self._progress
        self.update()

    # ── Отрисовка ─────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setRenderHint(QtGui.QPainter.TextAntialiasing)

        self._paint_panel(p)

        centre = QtCore.QPointF(PANEL_W / 2, 108)
        self._paint_glow(p, centre)
        self._paint_ring(p, centre)
        self._paint_icon(p, centre)
        self._paint_text(p)

        p.end()

    def _paint_panel(self, p):
        rect = QtCore.QRectF(0.5, 0.5, PANEL_W - 1, PANEL_H - 1)

        bg = QtGui.QLinearGradient(0, 0, 0, PANEL_H)
        bg.setColorAt(0.0, QtGui.QColor(BG_TOP))
        bg.setColorAt(1.0, QtGui.QColor(BG_BOTTOM))

        p.setPen(QtGui.QPen(QtGui.QColor(BORDER), 1))
        p.setBrush(bg)
        p.drawRoundedRect(rect, 14, 14)

    def _paint_glow(self, p, centre):
        """Мягкое свечение под иконкой, дышит в такт блику"""
        pulse = 0.5 + 0.5 * math.sin(self._phase * 2 * math.pi)
        radius = RING_D / 2 + 10 + pulse * 6

        glow = QtGui.QRadialGradient(centre, radius)
        colour = QtGui.QColor(ARC_FROM)
        colour.setAlpha(int(38 + pulse * 26))
        glow.setColorAt(0.55, colour)
        colour_edge = QtGui.QColor(ARC_FROM)
        colour_edge.setAlpha(0)
        glow.setColorAt(1.0, colour_edge)

        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(glow)
        p.drawEllipse(centre, radius, radius)

    def _paint_ring(self, p, centre):
        box = QtCore.QRectF(centre.x() - RING_D / 2, centre.y() - RING_D / 2,
                            RING_D, RING_D)

        # Дорожка.
        pen = QtGui.QPen(QtGui.QColor(TRACK), RING_W)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawEllipse(box)

        # Заполненная часть: от синего в начале к зелёному на переднем крае.
        if self._shown > 0.001:
            # QConicalGradient отсчитывает позицию ПРОТИВ часовой стрелки, а
            # дуга рисуется ПО часовой. Поэтому точке дуги t соответствует
            # позиция градиента 1 - t, и стопы кладутся зеркально — иначе
            # цвета идут задом наперёд.
            gradient = QtGui.QConicalGradient(centre, 90)
            gradient.setColorAt(1.0, QtGui.QColor(ARC_FROM))
            gradient.setColorAt(max(0.0, 1.0 - self._shown),
                                QtGui.QColor(ARC_TO))
            gradient.setColorAt(0.0, QtGui.QColor(ARC_TO))

            pen = QtGui.QPen(QtGui.QBrush(gradient), RING_W)
            pen.setCapStyle(QtCore.Qt.RoundCap)
            p.setPen(pen)
            # Qt меряет углы в 1/16 градуса, против часовой стрелки.
            p.drawArc(box, 90 * 16, -int(360 * 16 * self._shown))

        # Бегущий блик — показывает, что процесс жив, даже когда
        # прогресс какое-то время стоит на месте.
        head = self._phase * 360.0
        glint = QtGui.QColor(GLINT)
        glint.setAlpha(190)
        pen = QtGui.QPen(glint, RING_W)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(box, int((90 - head) * 16), -int(26 * 16))

    def _paint_icon(self, p, centre):
        if self._pixmap is None or self._pixmap.isNull():
            return
        w = self._pixmap.width() / self._pixmap.devicePixelRatio()
        h = self._pixmap.height() / self._pixmap.devicePixelRatio()
        p.drawPixmap(int(centre.x() - w / 2), int(centre.y() - h / 2),
                     self._pixmap)

    def _paint_text(self, p):
        title = QtGui.QFont()
        title.setPointSize(19)
        title.setBold(True)
        p.setFont(title)
        p.setPen(QtGui.QColor(TITLE))
        p.drawText(QtCore.QRect(0, 184, PANEL_W, 30),
                   QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter,
                   "integra101")

        sub = QtGui.QFont()
        sub.setPointSize(9)
        p.setFont(sub)
        p.setPen(QtGui.QColor(SUBTITLE))
        p.drawText(QtCore.QRect(0, 212, PANEL_W, 20),
                   QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter,
                   "Запись значений в EEPROM · CRC-16 CCITT")

        status = QtGui.QFont()
        status.setPointSize(9)
        status.setBold(True)
        p.setFont(status)
        p.setPen(QtGui.QColor(STATUS))
        p.drawText(QtCore.QRect(20, 244, PANEL_W - 40, 20),
                   QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter,
                   f"{self._status}   {int(round(self._shown * 100))}%")
