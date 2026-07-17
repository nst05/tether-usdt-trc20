// -*- coding: utf-8 -*-
#include "gt911_touch.h"
#include "board_pins.h"
#include <Arduino.h>
#include <Wire.h>

// Регистры GT911
#define GT911_REG_STATUS   0x814E   // статус: bit7 = данные готовы, младшие 4 бита = число точек
#define GT911_REG_POINT1   0x8150   // первая точка: [track_id, xL, xH, yL, yH, sizeL, sizeH, resv]

static bool gt911_write_reg16(uint16_t reg, uint8_t val) {
    Wire.beginTransmission(GT911_ADDR);
    Wire.write((uint8_t)(reg >> 8));
    Wire.write((uint8_t)(reg & 0xFF));
    Wire.write(val);
    return Wire.endTransmission() == 0;
}

static int gt911_read_reg16(uint16_t reg, uint8_t *buf, int len) {
    Wire.beginTransmission(GT911_ADDR);
    Wire.write((uint8_t)(reg >> 8));
    Wire.write((uint8_t)(reg & 0xFF));
    if (Wire.endTransmission(false) != 0) return 0;   // repeated start
    int got = Wire.requestFrom((int)GT911_ADDR, len);
    for (int i = 0; i < got && i < len; i++) buf[i] = Wire.read();
    return got;
}

void gt911_begin() {
    pinMode(GT911_INT_PIN, INPUT);
    delay(10);
    // Сброс GT911 уже снят через CH422G. Сбросим регистр статуса.
    gt911_write_reg16(GT911_REG_STATUS, 0x00);
}

bool gt911_read(uint16_t *x, uint16_t *y) {
    uint8_t status = 0;
    if (gt911_read_reg16(GT911_REG_STATUS, &status, 1) != 1) return false;

    if (!(status & 0x80)) {
        // данные не готовы
        return false;
    }

    uint8_t points = status & 0x0F;
    bool touched = false;

    if (points > 0) {
        uint8_t p[8];
        if (gt911_read_reg16(GT911_REG_POINT1, p, 8) >= 5) {
            uint16_t px = (uint16_t)p[1] | ((uint16_t)p[2] << 8);
            uint16_t py = (uint16_t)p[3] | ((uint16_t)p[4] << 8);
            if (px < LCD_H_RES && py < LCD_V_RES) {
                *x = px;
                *y = py;
                touched = true;
            }
        }
    }

    // сбросить флаг готовности, чтобы контроллер подготовил новый кадр
    gt911_write_reg16(GT911_REG_STATUS, 0x00);
    return touched;
}
