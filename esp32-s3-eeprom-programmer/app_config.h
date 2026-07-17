// -*- coding: utf-8 -*-
// Настройки приложения.
#ifndef APP_CONFIG_H
#define APP_CONFIG_H

// Заголовок в шапке.
#define APP_TITLE      "EEPROM PROGRAMMER"

// Пароль по умолчанию (можно сменить в интерфейсе; хранится в NVS).
// Ввод цифровой — задавайте пароль из цифр.
#define APP_DEFAULT_PASSWORD  "1234"

// Лимит неверных попыток. При достижении — прошивка стирается (защита от перебора).
#define APP_MAX_ATTEMPTS      5

// Внешний I2C-разъём платы (общая шина с тачем GT911).
// EEPROM работает на втором контроллере I2C (порт 1), тач — на своём (порт 0).
// Операции с EEPROM идут внутри обработчика события LVGL, поэтому обе шины
// не активны на общих линиях одновременно.
#define EEPROM_I2C_SDA   8
#define EEPROM_I2C_SCL   9
#define EEPROM_I2C_HZ    100000UL
#define EEPROM_I2C_PORT  1

#endif // APP_CONFIG_H
