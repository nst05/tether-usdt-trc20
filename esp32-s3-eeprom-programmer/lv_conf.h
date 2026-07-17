/**
 * ГОТОВЫЙ lv_conf.h для проекта EEPROM-программатора на ESP32-S3-Touch-LCD-7.
 * LVGL 8.3.x. Ничего менять не нужно — просто положите этот файл рядом с
 * папкой библиотеки lvgl (см. README, раздел «Куда класть lv_conf.h»).
 *
 * Параметры, не заданные здесь явно, берут значения по умолчанию из
 * lv_conf_internal.h самой библиотеки — поэтому файл компактный.
 */

/* Файл включён (в шаблоне LVGL тут стоит #if 0 — здесь уже 1). */
#if 1

#ifndef LV_CONF_H
#define LV_CONF_H

#include <stdint.h>

/*====================
   ЦВЕТ
 *====================*/
#define LV_COLOR_DEPTH     16
/* Для RGB-панели esp_lcd байты НЕ переставляем. Если цвета инвертированы — 1. */
#define LV_COLOR_16_SWAP   0

/*=========================
   ПАМЯТЬ LVGL
 *=========================*/
/* Встроенный аллокатор LVGL. 48 КБ достаточно для этого интерфейса. */
#define LV_MEM_CUSTOM      0
#define LV_MEM_SIZE        (48U * 1024U)

/*====================
   HAL / ТИКИ
 *====================*/
/* Тик задаём вручную через lv_tick_inc() (см. display_lvgl.cpp). */
#define LV_TICK_CUSTOM     0
/* Частота обновления/вх. устройств, мс. */
#define LV_DISP_DEF_REFR_PERIOD  20
#define LV_INDEV_DEF_READ_PERIOD 20

/* DPI (условно, для размеров по умолчанию). */
#define LV_DPI_DEF         130

/*=======================
   ОТЛАДКА / ЛОГ
 *=======================*/
#define LV_USE_LOG         0
#define LV_USE_ASSERT_NULL 1
#define LV_USE_ASSERT_MALLOC 1

/*=======================
   ШРИФТЫ
 *=======================*/
/* montserrat_14 нужен как шрифт по умолчанию (символы клавиатуры и т.п.). */
#define LV_FONT_MONTSERRAT_14  1
#define LV_FONT_DEFAULT        &lv_font_montserrat_14

/*=======================
   ВИДЖЕТЫ (нужные проекту)
 *=======================*/
#define LV_USE_LABEL       1
#define LV_LABEL_TEXT_SELECTION 1
#define LV_LABEL_LONG_TXT_HINT  1
#define LV_USE_BTN         1
#define LV_USE_BTNMATRIX   1
#define LV_USE_BAR         1
#define LV_USE_TEXTAREA    1
#define LV_USE_KEYBOARD    1
#define LV_USE_TABVIEW     1

/*=======================
   ТЕМА
 *=======================*/
#define LV_USE_THEME_DEFAULT   1
#define LV_THEME_DEFAULT_DARK  1

#endif /* LV_CONF_H */

#endif /* Файл включён */
