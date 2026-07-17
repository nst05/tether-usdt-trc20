// -*- coding: utf-8 -*-
// EEPROM-программатор на ESP32-S3-Touch-LCD-7 (Waveshare, 800x480, тач GT911).
//
// Дисплей и тач подняты через официальную библиотеку ESP32_Display_Panel
// (esp_display_panel) с пресетом платы Waveshare — это гарантирует рабочий тач.
// EEPROM подключается к внешнему I2C-разъёму (SDA=8, SCL=9) и обслуживается
// отдельным I2C-контроллером (порт 1).
//
// 6 программаторов (вкладки): 201, c101, new_1F, new_3F, ce6803b_p32, 200_MT.
// Вся логика CRC/BCD/патчей проверена побайтово против оригинальной Python-версии.
//
// Требования к сборке: см. README.md.

#include <Arduino.h>
#include <Wire.h>

#include "esp_panel_drivers_conf.h"
#include "esp_panel_board_supported_conf.h"
#include <esp_display_panel.hpp>

#include "app_config.h"
#include "eeprom_i2c.h"
#include "simple_lvgl_port.h"
#include "security.h"
#include "ui.h"

using namespace esp_panel::drivers;
using namespace esp_panel::board;

static TwoWire eepromWire(EEPROM_I2C_PORT);
static Board  *board = nullptr;

void setup() {
    Serial.begin(115200);
    delay(300);
    Serial.println("[EEPROM-PROG] starting");

    // 1) Дисплей + тач (библиотечный пресет платы).
    board = new Board();
    board->init();
    if (!board->begin()) {
        Serial.println("[EEPROM-PROG] ERROR: display board init failed");
        while (true) delay(1000);
    }

    // 2) Внешний I2C для EEPROM (отдельный контроллер, порт 1).
    eepromWire.begin(EEPROM_I2C_SDA, EEPROM_I2C_SCL, EEPROM_I2C_HZ);
    eeprom_i2c_set_wire(&eepromWire);

    // 3) Хранилище пароля/счётчика попыток (NVS).
    security_begin();

    // 4) LVGL (отдельная задача с блокировкой).
    if (!programmer_lvgl_init(board->getLCD(), board->getTouch())) {
        Serial.println("[EEPROM-PROG] ERROR: LVGL init failed");
        while (true) delay(1000);
    }

    // 5) Интерфейс — создаём под блокировкой LVGL.
    programmer_lvgl_lock(-1);
    ui_build();
    programmer_lvgl_unlock();

    Serial.println("[EEPROM-PROG] ready. I2C: 3V3/GND/SDA(GPIO8)/SCL(GPIO9)");
}

void loop() {
    // Вся отрисовка/тач — в задаче LVGL (см. simple_lvgl_port.cpp).
    delay(1000);
}
