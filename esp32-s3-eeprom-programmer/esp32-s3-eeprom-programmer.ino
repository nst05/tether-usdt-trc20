// -*- coding: utf-8 -*-
// EEPROM-программатор на ESP32-S3-Touch-LCD-7 (Waveshare, 800x480, тач GT911).
// Порт настольной PyQt5+CH341 утилиты на автономный сенсорный интерфейс LVGL.
//
// 6 программаторов (вкладки):
//   201_drob_random (24C16), c101 (24C04), new_1F (AT24C1024),
//   new_3F (AT24C1024), ce6803b_p32 (24C04), 200_MT (24C16).
//
// EEPROM подключается к тому же I2C-разъёму, что и тач (SDA=8, SCL=9).
// Вход в приложение — по паролю (см. app_config.h).
//
// Требования к сборке: см. README.md (Arduino-ESP32 v3.x, LVGL 8.3, lv_conf.h).

#include <Arduino.h>
#include <Wire.h>

#include "board_pins.h"
#include "display_lvgl.h"
#include "ui.h"

void setup() {
    Serial.begin(115200);
    delay(200);
    Serial.println("[EEPROM-PROG] boot");

    // Общая I2C-шина: тач GT911 + расширитель CH422G + внешняя EEPROM.
    Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN, I2C_FREQ_HZ);

    // Дисплей + LVGL + тач.
    display_lvgl_init();

    // Интерфейс: экран входа + вкладки программаторов.
    ui_build();

    Serial.println("[EEPROM-PROG] ready");
}

void loop() {
    display_lvgl_pump();
    delay(5);
}
