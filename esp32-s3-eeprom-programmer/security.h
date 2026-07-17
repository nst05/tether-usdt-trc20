// -*- coding: utf-8 -*-
// Защита входа: пароль (в NVS), защита от перебора со стиранием прошивки.
#ifndef SECURITY_H
#define SECURITY_H

// Инициализация хранилища (NVS). Вызывать в setup() до UI.
void security_begin();

// Проверить пароль. true — верный (счётчик сбрасывается).
// При неверном: счётчик неудач++ (хранится в NVS, переживает перезагрузку);
// при достижении лимита APP_MAX_ATTEMPTS прошивка СТИРАЕТСЯ и плата уходит в
// ребут (функция не возвращает управление).
bool security_check_password(const char *pw);

// Сколько попыток осталось до стирания.
int security_attempts_left();

// Сменить пароль. Требует верный текущий. Сбрасывает счётчик неудач.
// Возвращает true при успехе.
bool security_change_password(const char *old_pw, const char *new_pw);

#endif // SECURITY_H
