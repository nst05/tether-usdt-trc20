// -*- coding: utf-8 -*-
// Построение интерфейса: экран входа по PIN + вкладки 6 программаторов.
#ifndef UI_H
#define UI_H

// Создаёт экраны и загружает экран входа.
// Вызывать после programmer_lvgl_init() (под блокировкой LVGL) и security_begin().
void ui_build();

#endif // UI_H
