// -*- coding: utf-8 -*-
// Минимальный драйвер ёмкостного тач-контроллера GT911 (одна точка касания).
#ifndef GT911_TOUCH_H
#define GT911_TOUCH_H

#include <stdint.h>
#include <stdbool.h>

// Инициализация тача (Wire уже должен быть запущен).
void gt911_begin();

// Прочитать текущее касание. Возвращает true, если палец на экране,
// и заполняет *x, *y (в координатах панели 0..799 / 0..479).
bool gt911_read(uint16_t *x, uint16_t *y);

#endif // GT911_TOUCH_H
