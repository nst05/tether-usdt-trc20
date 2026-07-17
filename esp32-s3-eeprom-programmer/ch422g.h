// -*- coding: utf-8 -*-
// Минимальный драйвер расширителя CH422G для снятия сбросов LCD/тача и включения подсветки.
#ifndef CH422G_H
#define CH422G_H

#include <Arduino.h>
#include <Wire.h>
#include "board_pins.h"

// Записать байт в один из регистров CH422G (адрес регистра = адрес устройства на шине).
static inline void ch422g_write(uint8_t reg, uint8_t value) {
    Wire.beginTransmission(reg);
    Wire.write(value);
    Wire.endTransmission();
}

// Инициализация: включить режим выхода EXIO и последовательность сброса.
// После вызова: LCD_RST и TP_RST сняты (высокий уровень), подсветка включена.
static inline void ch422g_begin() {
    ch422g_write(CH422G_WR_SET, CH422G_IO_OUT_EN);   // EXIO в режим выхода
    ch422g_write(CH422G_WR_IO, 0x00);                // всё в 0: держим сбросы, подсветка off
    delay(20);
    ch422g_write(CH422G_WR_IO, 0xFF);                // всё в 1: снять сбросы, подсветка on
    delay(100);                                      // ждём загрузку GT911
}

// Управление подсветкой (сохраняя остальные линии в высоком уровне).
static inline void ch422g_backlight(bool on) {
    ch422g_write(CH422G_WR_IO, on ? 0xFF : (uint8_t)(0xFF & ~CH422G_BL_BIT));
}

#endif // CH422G_H
