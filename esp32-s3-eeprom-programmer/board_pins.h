// -*- coding: utf-8 -*-
// Карта выводов и параметры платы Waveshare ESP32-S3-Touch-LCD-7 (800x480, RGB).
// Источник: официальный демо-код Waveshare + независимая сверка (ESPHome/ESP3D).
#ifndef BOARD_PINS_H
#define BOARD_PINS_H

// ---------------- I2C (общая шина: тач GT911 + расширитель CH422G + внешняя EEPROM) ----------------
// На плате выведен разъём I2C — именно к нему подключается программируемая EEPROM.
#define I2C_SDA_PIN      8
#define I2C_SCL_PIN      9
#define I2C_FREQ_HZ      400000

// GT911 (ёмкостный тач). Адрес по умолчанию 0x5D (при INT=0 в момент сброса).
#define GT911_ADDR       0x5D
#define GT911_INT_PIN    4
// Сброс GT911 идёт через CH422G (EXIO1), отдельного GPIO нет.

// Расширитель CH422G (управляет сбросами LCD/тача и подсветкой).
#define CH422G_WR_SET    0x24   // регистр настроек (bit0=IO output enable)
#define CH422G_WR_IO     0x38   // выходы EXIO0..EXIO7
#define CH422G_IO_OUT_EN 0x01   // значение в WR_SET: включить выход EXIO
// Разводка EXIO на этой плате: EXIO1=TP_RST, EXIO2=Backlight, EXIO3=LCD_RST.
#define CH422G_BL_BIT    (1 << 2)  // EXIO2
#define CH422G_TPRST_BIT (1 << 1)  // EXIO1
#define CH422G_LCDRST_BIT (1 << 3) // EXIO3

// ---------------- RGB LCD 800x480 ----------------
#define LCD_H_RES        800
#define LCD_V_RES        480
#define LCD_PIXEL_CLOCK_HZ (16 * 1000 * 1000)

#define LCD_PIN_DE       5
#define LCD_PIN_VSYNC    3
#define LCD_PIN_HSYNC    46
#define LCD_PIN_PCLK     7

// Данные (порядок для 16-битного RGB565: [0..4]=B3..B7, [5..10]=G2..G7, [11..15]=R3..R7)
#define LCD_PIN_B3       14
#define LCD_PIN_B4       38
#define LCD_PIN_B5       18
#define LCD_PIN_B6       17
#define LCD_PIN_B7       10
#define LCD_PIN_G2       39
#define LCD_PIN_G3       0
#define LCD_PIN_G4       45
#define LCD_PIN_G5       48
#define LCD_PIN_G6       47
#define LCD_PIN_G7       21
#define LCD_PIN_R3       1
#define LCD_PIN_R4       2
#define LCD_PIN_R5       42
#define LCD_PIN_R6       41
#define LCD_PIN_R7       40

// Тайминги RGB (порядок: pulse_width, back_porch, front_porch)
#define LCD_HSYNC_PULSE_WIDTH  4
#define LCD_HSYNC_BACK_PORCH   8
#define LCD_HSYNC_FRONT_PORCH  8
#define LCD_VSYNC_PULSE_WIDTH  4
#define LCD_VSYNC_BACK_PORCH   16
#define LCD_VSYNC_FRONT_PORCH  16

#endif // BOARD_PINS_H
