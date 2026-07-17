// -*- coding: utf-8 -*-
#include "display_lvgl.h"
#include "board_pins.h"
#include "ch422g.h"
#include "gt911_touch.h"

#include <Arduino.h>
#include <lvgl.h>
#include "esp_lcd_panel_ops.h"
#include "esp_lcd_panel_rgb.h"
#include "esp_heap_caps.h"

static esp_lcd_panel_handle_t panel_handle = nullptr;

static lv_disp_draw_buf_t draw_buf;
static lv_disp_drv_t       disp_drv;
static lv_indev_drv_t      indev_drv;

// Высота полосы буфера отрисовки (в строках). Два буфера в PSRAM.
#define LVGL_BUF_LINES  60

static void lvgl_flush_cb(lv_disp_drv_t *drv, const lv_area_t *area, lv_color_t *color_p) {
    esp_lcd_panel_draw_bitmap(panel_handle,
                              area->x1, area->y1,
                              area->x2 + 1, area->y2 + 1,
                              color_p);
    lv_disp_flush_ready(drv);
}

static void lvgl_touch_cb(lv_indev_drv_t *drv, lv_indev_data_t *data) {
    uint16_t x, y;
    if (gt911_read(&x, &y)) {
        data->state = LV_INDEV_STATE_PR;
        data->point.x = x;
        data->point.y = y;
    } else {
        data->state = LV_INDEV_STATE_REL;
    }
}

static void rgb_panel_init() {
    esp_lcd_rgb_panel_config_t cfg = {};
    cfg.clk_src = LCD_CLK_SRC_DEFAULT;

    cfg.timings.pclk_hz           = LCD_PIXEL_CLOCK_HZ;
    cfg.timings.h_res             = LCD_H_RES;
    cfg.timings.v_res             = LCD_V_RES;
    cfg.timings.hsync_pulse_width = LCD_HSYNC_PULSE_WIDTH;
    cfg.timings.hsync_back_porch  = LCD_HSYNC_BACK_PORCH;
    cfg.timings.hsync_front_porch = LCD_HSYNC_FRONT_PORCH;
    cfg.timings.vsync_pulse_width = LCD_VSYNC_PULSE_WIDTH;
    cfg.timings.vsync_back_porch  = LCD_VSYNC_BACK_PORCH;
    cfg.timings.vsync_front_porch = LCD_VSYNC_FRONT_PORCH;
    cfg.timings.flags.pclk_active_neg = 1;

    cfg.data_width             = 16;
    cfg.bits_per_pixel         = 16;
    cfg.num_fbs                = 1;
    cfg.bounce_buffer_size_px  = LCD_H_RES * 10;
    // Выравнивание DMA не задаём явно (поле менялось между версиями IDF);
    // нулевое значение из zero-init использует значение по умолчанию драйвера.

    cfg.hsync_gpio_num = LCD_PIN_HSYNC;
    cfg.vsync_gpio_num = LCD_PIN_VSYNC;
    cfg.de_gpio_num    = LCD_PIN_DE;
    cfg.pclk_gpio_num  = LCD_PIN_PCLK;
    cfg.disp_gpio_num  = -1;

    const int data_pins[16] = {
        LCD_PIN_B3, LCD_PIN_B4, LCD_PIN_B5, LCD_PIN_B6, LCD_PIN_B7,
        LCD_PIN_G2, LCD_PIN_G3, LCD_PIN_G4, LCD_PIN_G5, LCD_PIN_G6, LCD_PIN_G7,
        LCD_PIN_R3, LCD_PIN_R4, LCD_PIN_R5, LCD_PIN_R6, LCD_PIN_R7
    };
    for (int i = 0; i < 16; i++) cfg.data_gpio_nums[i] = data_pins[i];

    cfg.flags.fb_in_psram = 1;

    ESP_ERROR_CHECK(esp_lcd_new_rgb_panel(&cfg, &panel_handle));
    ESP_ERROR_CHECK(esp_lcd_panel_reset(panel_handle));
    ESP_ERROR_CHECK(esp_lcd_panel_init(panel_handle));
}

void display_lvgl_init() {
    // 1) Снять сбросы LCD/тача и включить подсветку.
    ch422g_begin();

    // 2) RGB-панель.
    rgb_panel_init();

    // 3) Тач.
    gt911_begin();

    // 4) LVGL.
    lv_init();

    size_t buf_px = (size_t)LCD_H_RES * LVGL_BUF_LINES;
    lv_color_t *buf1 = (lv_color_t *)heap_caps_malloc(buf_px * sizeof(lv_color_t), MALLOC_CAP_SPIRAM);
    lv_color_t *buf2 = (lv_color_t *)heap_caps_malloc(buf_px * sizeof(lv_color_t), MALLOC_CAP_SPIRAM);
    lv_disp_draw_buf_init(&draw_buf, buf1, buf2, buf_px);

    lv_disp_drv_init(&disp_drv);
    disp_drv.hor_res  = LCD_H_RES;
    disp_drv.ver_res  = LCD_V_RES;
    disp_drv.flush_cb = lvgl_flush_cb;
    disp_drv.draw_buf = &draw_buf;
    lv_disp_drv_register(&disp_drv);

    lv_indev_drv_init(&indev_drv);
    indev_drv.type    = LV_INDEV_TYPE_POINTER;
    indev_drv.read_cb = lvgl_touch_cb;
    lv_indev_drv_register(&indev_drv);
}

void display_lvgl_pump() {
    static uint32_t last = 0;
    uint32_t now = millis();
    lv_tick_inc(now - last);
    last = now;
    lv_timer_handler();
}
