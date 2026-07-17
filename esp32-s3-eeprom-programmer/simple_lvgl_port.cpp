#include "simple_lvgl_port.h"

#include <Arduino.h>
#include <esp_heap_caps.h>
#include <esp_timer.h>

using namespace esp_panel::drivers;

namespace {
constexpr uint32_t TICK_MS = 2;
constexpr uint32_t BUFFER_HEIGHT = 20;
constexpr uint32_t TASK_MIN_DELAY_MS = 2;
constexpr uint32_t TASK_MAX_DELAY_MS = 500;
constexpr uint32_t TASK_STACK = 8 * 1024;
constexpr UBaseType_t TASK_PRIORITY = 2;

SemaphoreHandle_t g_mutex = nullptr;
TaskHandle_t g_task = nullptr;
esp_timer_handle_t g_tickTimer = nullptr;

void tickCallback(void*) { lv_tick_inc(TICK_MS); }

void flushCallback(lv_disp_drv_t* drv, const lv_area_t* area, lv_color_t* colorMap) {
    auto* lcd = static_cast<LCD*>(drv->user_data);
    const int x1 = area->x1;
    const int y1 = area->y1;
    const int width = area->x2 - area->x1 + 1;
    const int height = area->y2 - area->y1 + 1;
    lcd->drawBitmap(x1, y1, width, height, reinterpret_cast<const uint8_t*>(colorMap));
    lv_disp_flush_ready(drv);
}

void touchRead(lv_indev_drv_t* drv, lv_indev_data_t* data) {
    auto* touch = static_cast<Touch*>(drv->user_data);
    TouchPoint point;
    const int count = touch->readPoints(&point, 1, 0);
    if (count > 0) {
        data->point.x = point.x;
        data->point.y = point.y;
        data->state = LV_INDEV_STATE_PRESSED;
    } else {
        data->state = LV_INDEV_STATE_RELEASED;
    }
}

void lvglTask(void*) {
    uint32_t delayMs = TASK_MAX_DELAY_MS;
    while (true) {
        if (programmer_lvgl_lock(-1)) {
            delayMs = lv_timer_handler();
            programmer_lvgl_unlock();
        }
        if (delayMs < TASK_MIN_DELAY_MS) delayMs = TASK_MIN_DELAY_MS;
        if (delayMs > TASK_MAX_DELAY_MS) delayMs = TASK_MAX_DELAY_MS;
        vTaskDelay(pdMS_TO_TICKS(delayMs));
    }
}
}

bool programmer_lvgl_init(LCD* lcd, Touch* touch) {
    if (!lcd || !lcd->getRefreshPanelHandle()) return false;

    lv_init();

    const esp_timer_create_args_t timerArgs = {
        .callback = &tickCallback,
        .name = "lvgl_tick",
    };
    if (esp_timer_create(&timerArgs, &g_tickTimer) != ESP_OK) return false;
    if (esp_timer_start_periodic(g_tickTimer, TICK_MS * 1000ULL) != ESP_OK) return false;

    const uint32_t width = lcd->getFrameWidth();
    const uint32_t height = lcd->getFrameHeight();
    const uint32_t pixelCount = width * BUFFER_HEIGHT;
    auto* buffer1 = static_cast<lv_color_t*>(heap_caps_malloc(pixelCount * sizeof(lv_color_t), MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
    auto* buffer2 = static_cast<lv_color_t*>(heap_caps_malloc(pixelCount * sizeof(lv_color_t), MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
    if (!buffer1 || !buffer2) return false;

    static lv_disp_draw_buf_t drawBuffer;
    lv_disp_draw_buf_init(&drawBuffer, buffer1, buffer2, pixelCount);

    static lv_disp_drv_t displayDriver;
    lv_disp_drv_init(&displayDriver);
    displayDriver.hor_res = width;
    displayDriver.ver_res = height;
    displayDriver.flush_cb = flushCallback;
    displayDriver.draw_buf = &drawBuffer;
    displayDriver.user_data = lcd;
    if (!lv_disp_drv_register(&displayDriver)) return false;

    if (touch) {
        static lv_indev_drv_t inputDriver;
        lv_indev_drv_init(&inputDriver);
        inputDriver.type = LV_INDEV_TYPE_POINTER;
        inputDriver.read_cb = touchRead;
        inputDriver.user_data = touch;
        if (!lv_indev_drv_register(&inputDriver)) return false;
    }

    g_mutex = xSemaphoreCreateRecursiveMutex();
    if (!g_mutex) return false;
    const BaseType_t created = xTaskCreatePinnedToCore(
        lvglTask, "lvgl", TASK_STACK, nullptr, TASK_PRIORITY, &g_task, tskNO_AFFINITY
    );
    return created == pdPASS;
}

bool programmer_lvgl_lock(int timeoutMs) {
    if (!g_mutex) return false;
    const TickType_t ticks = timeoutMs < 0 ? portMAX_DELAY : pdMS_TO_TICKS(timeoutMs);
    return xSemaphoreTakeRecursive(g_mutex, ticks) == pdTRUE;
}

void programmer_lvgl_unlock() {
    if (g_mutex) xSemaphoreGiveRecursive(g_mutex);
}
