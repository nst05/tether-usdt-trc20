// -*- coding: utf-8 -*-
// EEPROM-программатор на ESP32-S3-Touch-LCD-7 (Waveshare, 800x480, тач GT911).
// Дисплей/тач — библиотека ESP32_Display_Panel (пресет платы). EEPROM — на внешнем
// I2C-разъёме (порт 1). Вход по PIN + защита от перебора (стирание прошивки).
// Логика патчей проверена побайтово против оригинального Python.
// Требования к сборке: см. README.md.

#include <Arduino.h>
#include <Wire.h>

#include "esp_panel_drivers_conf.h"
#include "esp_panel_board_supported_conf.h"
#include <esp_display_panel.hpp>

#include "app_config.h"
#include "i2c_eeprom.h"
#include "simple_lvgl_port.h"
#include "security.h"
#include "ui_app.h"

using namespace esp_panel::drivers;
using namespace esp_panel::board;

static TwoWire  eepromWire(EEPROM_I2C_PORT);
static I2cEeprom eeprom(eepromWire);
static Board    *board = nullptr;

void setup() {
    Serial.begin(115200);
    delay(300);
    Serial.println("[EEPROM-PROG] starting");

    board = new Board();
    board->init();
    if (!board->begin()) {
        Serial.println("[EEPROM-PROG] ERROR: display board init failed");
        while (true) delay(1000);
    }

    if (!eeprom.begin(EEPROM_I2C_SDA, EEPROM_I2C_SCL, EEPROM_I2C_HZ)) {
        Serial.println("[EEPROM-PROG] ERROR: external I2C init failed");
        while (true) delay(1000);
    }

    security_begin();

    if (!programmer_lvgl_init(board->getLCD(), board->getTouch())) {
        Serial.println("[EEPROM-PROG] ERROR: LVGL init failed");
        while (true) delay(1000);
    }

    programmer_lvgl_lock(-1);
    programmer_ui_start(eeprom);   // экран входа по PIN → интерфейс
    programmer_lvgl_unlock();

    Serial.println("[EEPROM-PROG] ready. I2C: 3V3/GND/SDA(GPIO8)/SCL(GPIO9)");
}

void loop() {
    delay(1000);
}
