// -*- coding: utf-8 -*-
// Инициализация RGB-дисплея 800x480 + LVGL v8 + тач GT911 для ESP32-S3-Touch-LCD-7.
#ifndef DISPLAY_LVGL_H
#define DISPLAY_LVGL_H

// Полная инициализация: CH422G (сбросы/подсветка), RGB-панель, буферы LVGL, тач.
// Wire.begin(...) должен быть вызван ДО этого.
void display_lvgl_init();

// Вызывать в loop(): обновляет тик LVGL и обрабатывает таймеры/отрисовку.
void display_lvgl_pump();

#endif // DISPLAY_LVGL_H
