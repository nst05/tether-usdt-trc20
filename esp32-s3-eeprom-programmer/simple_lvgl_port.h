#pragma once

#include <esp_display_panel.hpp>
#include <lvgl.h>

bool programmer_lvgl_init(esp_panel::drivers::LCD* lcd, esp_panel::drivers::Touch* touch);
bool programmer_lvgl_lock(int timeoutMs = -1);
void programmer_lvgl_unlock();
