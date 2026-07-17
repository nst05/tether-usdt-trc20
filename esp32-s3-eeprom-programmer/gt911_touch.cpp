// -*- coding: utf-8 -*-
#include "gt911_touch.h"
#include "board_pins.h"
#include <Arduino.h>
#include <Wire.h>

// Регистры GT911
#define GT911_REG_PRODUCT  0x8140   // ID продукта ("911\0")
#define GT911_REG_STATUS   0x814E   // статус: bit7 = данные готовы, младшие 4 бита = число точек
#define GT911_REG_POINT1   0x8150   // первая точка: [track_id, xL, xH, yL, yH, sizeL, sizeH, resv]

// Реальный I2C-адрес определяется автоматически (0x5D или 0x14).
static uint8_t g_gt911_addr = GT911_ADDR;

static bool gt911_write_reg16(uint16_t reg, uint8_t val) {
    Wire.beginTransmission(g_gt911_addr);
    Wire.write((uint8_t)(reg >> 8));
    Wire.write((uint8_t)(reg & 0xFF));
    Wire.write(val);
    return Wire.endTransmission() == 0;
}

static int gt911_read_reg16(uint16_t reg, uint8_t *buf, int len) {
    Wire.beginTransmission(g_gt911_addr);
    Wire.write((uint8_t)(reg >> 8));
    Wire.write((uint8_t)(reg & 0xFF));
    if (Wire.endTransmission(false) != 0) return 0;   // repeated start
    int got = Wire.requestFrom((int)g_gt911_addr, len);
    for (int i = 0; i < got && i < len; i++) buf[i] = Wire.read();
    return got;
}

// Проверить, отвечает ли GT911 по указанному адресу (читаем ID продукта).
static bool gt911_probe(uint8_t addr) {
    Wire.beginTransmission(addr);
    Wire.write((uint8_t)(GT911_REG_PRODUCT >> 8));
    Wire.write((uint8_t)(GT911_REG_PRODUCT & 0xFF));
    if (Wire.endTransmission(false) != 0) return false;
    int got = Wire.requestFrom((int)addr, 4);
    if (got < 4) return false;
    while (Wire.available()) Wire.read();   // очистить буфер
    return true;
}

void gt911_begin() {
    pinMode(GT911_INT_PIN, INPUT);
    delay(50);

    // Автоопределение адреса: сначала 0x5D, затем 0x14.
    if (gt911_probe(0x5D)) {
        g_gt911_addr = 0x5D;
    } else if (gt911_probe(0x14)) {
        g_gt911_addr = 0x14;
    } else {
        g_gt911_addr = GT911_ADDR;   // не ответил — оставим значение по умолчанию
        Serial.println("[GT911] не отвечает ни на 0x5D, ни на 0x14 — проверьте сброс/подтяжки");
    }
    Serial.printf("[GT911] I2C addr = 0x%02X\n", g_gt911_addr);

    // Прочитать и вывести ID продукта для диагностики.
    uint8_t id[4] = {0};
    if (gt911_read_reg16(GT911_REG_PRODUCT, id, 4) == 4) {
        Serial.printf("[GT911] product id = %c%c%c%c\n", id[0], id[1], id[2], id[3]);
    }

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
