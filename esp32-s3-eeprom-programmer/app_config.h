#pragma once

// Внешний I2C-разъём Waveshare ESP32-S3-Touch-LCD-7 (общая шина с тачем GT911).
#define EEPROM_I2C_SDA 8
#define EEPROM_I2C_SCL 9
#define EEPROM_I2C_HZ  100000UL

// Второй контроллер I2C для EEPROM (тач обслуживается своим).
#define EEPROM_I2C_PORT 1
#define EEPROM_BASE_ADDR 0x50

// ---- Вход по PIN / защита от перебора ----
#define APP_TITLE             "EEPROM PROGRAMMER"
#define APP_DEFAULT_PASSWORD  "1234"   // можно сменить в интерфейсе (хранится в NVS)
#define APP_MAX_ATTEMPTS      5        // при превышении — стирание прошивки
