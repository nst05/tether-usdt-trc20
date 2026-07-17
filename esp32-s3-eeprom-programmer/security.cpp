// -*- coding: utf-8 -*-
#include "security.h"
#include "app_config.h"
#include <Arduino.h>
#include <Preferences.h>
#include <string.h>
#include "esp_system.h"
#include "esp_ota_ops.h"
#include "esp_partition.h"

static Preferences prefs;

void security_begin() {
    prefs.begin("eeprogsec", false);
}

static String get_pw()      { return prefs.getString("pw", APP_DEFAULT_PASSWORD); }
static int    get_fails()   { return prefs.getInt("fails", 0); }
static void   set_fails(int f) { prefs.putInt("fails", f); }

int security_attempts_left() {
    int left = APP_MAX_ATTEMPTS - get_fails();
    return left < 0 ? 0 : left;
}

// Стереть прошивку (running app partition) и перезагрузиться.
// После этого плата не загрузится, пока не будет прошита заново.
static void security_wipe() {
    // Сначала стираем сохранённые пароль/счётчик (пока flash ещё цел).
    prefs.clear();
    prefs.end();

    const esp_partition_t *run = esp_ota_get_running_partition();
    if (run) {
        esp_partition_erase_range(run, 0, run->size);
    }
    // Код возврата уже стёрт — это приведёт к исключению и ребуту.
    esp_restart();
    while (true) { }  // на всякий случай
}

bool security_check_password(const char *pw) {
    if (pw && get_pw() == String(pw)) {
        set_fails(0);
        return true;
    }
    int f = get_fails() + 1;
    set_fails(f);
    if (f >= APP_MAX_ATTEMPTS) {
        security_wipe();   // не вернётся
    }
    return false;
}

bool security_change_password(const char *old_pw, const char *new_pw) {
    if (!(old_pw && get_pw() == String(old_pw))) return false;
    if (!new_pw || strlen(new_pw) < 1) return false;
    prefs.putString("pw", new_pw);
    set_fails(0);
    return true;
}
