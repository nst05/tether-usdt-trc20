#include "ui_app.h"
#include "patch_logic.h"
#include "security.h"
#include "app_config.h"
#include <Arduino.h>
#include <math.h>
#include <esp_heap_caps.h>

namespace {
I2cEeprom* g_mem = nullptr;
I2cEeprom* g_pending = nullptr;      // память для построения UI после входа
lv_obj_t* g_keyboard = nullptr;

const lv_color_t C_OK = LV_COLOR_MAKE(70, 210, 115);
const lv_color_t C_ERR = LV_COLOR_MAKE(255, 90, 100);
const lv_color_t C_INFO = LV_COLOR_MAKE(205, 215, 235);
const lv_color_t C_BUSY = LV_COLOR_MAKE(255, 190, 70);

struct TabUi {
    EepromType type;
    uint16_t imageSize;
    lv_obj_t* input;
    lv_obj_t* status;
    lv_obj_t* progress;
    uint32_t counter;
    lv_obj_t* counterLabel;
    uint8_t mode;
};

TabUi tabs[6];

void setStatus(TabUi& t, const String& s, lv_color_t c = C_INFO) {
    lv_label_set_text(t.status, s.c_str());
    lv_obj_set_style_text_color(t.status, c, 0);
    lv_refr_now(nullptr);
}

void setProgress(TabUi& t, int value) {
    lv_bar_set_value(t.progress, value, LV_ANIM_OFF);
    lv_refr_now(nullptr);
}

bool parseValue(lv_obj_t* ta, double& value) {
    String s = lv_textarea_get_text(ta);
    s.replace(',', '.');
    if (!s.length()) return false;
    char* end = nullptr;
    value = strtod(s.c_str(), &end);
    return end && *end == 0 && isfinite(value) && value >= 0;
}

void keyboardEvent(lv_event_t* e) {
    const auto code = lv_event_get_code(e);
    if (code == LV_EVENT_READY || code == LV_EVENT_CANCEL)
        lv_obj_add_flag(g_keyboard, LV_OBJ_FLAG_HIDDEN);
}

void inputEvent(lv_event_t* e) {
    if (lv_event_get_code(e) == LV_EVENT_FOCUSED) {
        lv_keyboard_set_textarea(g_keyboard, (lv_obj_t*)lv_event_get_target(e));
        lv_obj_clear_flag(g_keyboard, LV_OBJ_FLAG_HIDDEN);
        lv_obj_move_foreground(g_keyboard);
    }
}

lv_obj_t* makeInput(lv_obj_t* parent, const char* initial) {
    auto* ta = lv_textarea_create(parent);
    lv_textarea_set_one_line(ta, true);
    lv_textarea_set_accepted_chars(ta, "0123456789.,");
    lv_textarea_set_max_length(ta, 18);
    lv_textarea_set_text(ta, initial);
    lv_obj_set_size(ta, 230, 52);
    lv_obj_add_event_cb(ta, inputEvent, LV_EVENT_FOCUSED, nullptr);
    return ta;
}

lv_obj_t* makeStatus(lv_obj_t* parent) {
    auto* l = lv_label_create(parent);
    lv_obj_set_width(l, lv_pct(100));
    lv_label_set_long_mode(l, LV_LABEL_LONG_WRAP);
    lv_obj_set_style_pad_all(l, 10, 0);
    lv_obj_set_style_bg_opa(l, LV_OPA_20, 0);
    lv_obj_set_style_radius(l, 8, 0);
    lv_label_set_text(l, "Ready");
    return l;
}

bool invalidDump(const uint8_t* data, size_t n) {
    bool ff = true, zz = true;
    for (size_t i = 0; i < n; ++i) {
        ff &= data[i] == 0xFF;
        zz &= data[i] == 0x00;
    }
    return ff || zz;
}

bool runImageTab(TabUi& t, double value) {
    uint8_t* image = (uint8_t*)heap_caps_malloc(t.imageSize, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!image) image = (uint8_t*)malloc(t.imageSize);
    if (!image) { setStatus(t, "Error: out of memory", C_ERR); return false; }

    setProgress(t, 5);
    setStatus(t, "Checking EEPROM...", C_BUSY);
    if (!g_mem->probe(t.type)) { setStatus(t, "Error: " + g_mem->lastError(), C_ERR); free(image); return false; }

    setStatus(t, "Reading dump...", C_BUSY);
    if (!g_mem->read(t.type, 0, image, t.imageSize)) {
        setStatus(t, "Read error: " + g_mem->lastError(), C_ERR); free(image); return false;
    }
    setProgress(t, 30);

    if (invalidDump(image, t.imageSize)) {
        setStatus(t, "Error: dump all 00/FF. Check wiring.", C_ERR); free(image); return false;
    }

    bool patched = false;
    uint8_t fraction = uint8_t(random(0, 100));
    switch (t.mode) {
        case 0: patched = patch201(image, t.imageSize, uint32_t(value), fraction); break;
        case 1: patched = patchC101(image, t.imageSize, value); break;
        case 2: patched = patch1F(image, t.imageSize, value); break;
        case 3: patched = patch3F(image, t.imageSize, value); break;
        case 4: patched = patchCE6803(image, t.imageSize, value); break;
    }
    if (!patched) { setStatus(t, "Error: value out of range", C_ERR); free(image); return false; }

    setProgress(t, 45);
    setStatus(t, "Writing EEPROM...", C_BUSY);
    if (!g_mem->write(t.type, 0, image, t.imageSize)) {
        setStatus(t, "Write error: " + g_mem->lastError(), C_ERR); free(image); return false;
    }

    setProgress(t, 80);
    setStatus(t, "Verifying...", C_BUSY);
    if (!g_mem->verify(t.type, 0, image, t.imageSize)) {
        setStatus(t, "Verify error: " + g_mem->lastError(), C_ERR); free(image); return false;
    }

    free(image);
    t.counter++;
    lv_label_set_text_fmt(t.counterLabel, "Programmed: %lu", (unsigned long)t.counter);
    setProgress(t, 100);
    if (t.mode == 0)
        setStatus(t, "OK: written " + String(uint32_t(value)) + "." +
                     (fraction < 10 ? "0" : "") + String(fraction), C_OK);
    else
        setStatus(t, "OK: verified", C_OK);
    return true;
}

void buttonEvent(lv_event_t* e) {
    if (lv_event_get_code(e) != LV_EVENT_CLICKED) return;
    const uint32_t index = (uint32_t)(uintptr_t)lv_event_get_user_data(e);
    TabUi& t = tabs[index];

    double value = 0;
    if (!parseValue(t.input, value)) { setStatus(t, "Error: enter a valid number", C_ERR); return; }

    lv_obj_add_flag(g_keyboard, LV_OBJ_FLAG_HIDDEN);
    setProgress(t, 0);

    if (t.mode < 5) { runImageTab(t, value); return; }

    uint8_t expected[4];
    double actual = 0;
    const uint8_t fraction = uint8_t(random(1, 100));
    if (!make200MT(value, fraction, expected, actual)) { setStatus(t, "Error: value out of range", C_ERR); return; }

    setStatus(t, "Checking 24C16...", C_BUSY);
    if (!g_mem->probe(EepromType::C24C16)) { setStatus(t, "Error: " + g_mem->lastError(), C_ERR); return; }
    setProgress(t, 20);

    uint8_t before[4];
    if (!g_mem->read(EepromType::C24C16, 0x40, before, 4)) { setStatus(t, "Read error: " + g_mem->lastError(), C_ERR); return; }

    setProgress(t, 45);
    setStatus(t, "Writing 0x0040...", C_BUSY);
    if (!g_mem->write(EepromType::C24C16, 0x40, expected, 4)) { setStatus(t, "Write error: " + g_mem->lastError(), C_ERR); return; }

    setProgress(t, 80);
    if (!g_mem->verify(EepromType::C24C16, 0x40, expected, 4)) { setStatus(t, "Verify error: " + g_mem->lastError(), C_ERR); return; }

    t.counter++;
    lv_label_set_text_fmt(t.counterLabel, "Programmed: %lu", (unsigned long)t.counter);
    setProgress(t, 100);
    setStatus(t, "OK: written " + String(actual, 2), C_OK);
    lv_textarea_set_text(t.input, "");
}

lv_obj_t* createTab(lv_obj_t* tab, uint8_t index, const char* title,
                    const char* hint, const char* initial,
                    EepromType type, uint16_t imageSize, uint8_t mode) {
    lv_obj_set_flex_flow(tab, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(tab, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_set_style_pad_all(tab, 12, 0);
    lv_obj_set_style_pad_row(tab, 8, 0);
    lv_obj_set_scroll_dir(tab, LV_DIR_VER);

    auto* h = lv_label_create(tab);
    lv_label_set_text(h, title);
    lv_obj_set_style_text_font(h, &lv_font_montserrat_20, 0);

    auto* desc = lv_label_create(tab);
    lv_label_set_text(desc, hint);
    lv_obj_set_width(desc, lv_pct(95));
    lv_label_set_long_mode(desc, LV_LABEL_LONG_WRAP);
    lv_obj_set_style_text_align(desc, LV_TEXT_ALIGN_CENTER, 0);

    tabs[index] = {type, imageSize, nullptr, nullptr, nullptr, 0, nullptr, mode};
    tabs[index].input = makeInput(tab, initial);

    auto* btn = lv_btn_create(tab);
    lv_obj_set_size(btn, 390, 58);
    auto* bl = lv_label_create(btn);
    lv_label_set_text(bl, "PROGRAM  &  VERIFY");
    lv_obj_center(bl);
    lv_obj_add_event_cb(btn, buttonEvent, LV_EVENT_CLICKED, (void*)(uintptr_t)index);

    tabs[index].progress = lv_bar_create(tab);
    lv_obj_set_size(tabs[index].progress, lv_pct(90), 24);
    lv_bar_set_range(tabs[index].progress, 0, 100);
    lv_bar_set_value(tabs[index].progress, 0, LV_ANIM_OFF);

    tabs[index].counterLabel = lv_label_create(tab);
    lv_label_set_text(tabs[index].counterLabel, "Programmed: 0");
    tabs[index].status = makeStatus(tab);
    return tab;
}

// ---------------- Вкладка смены PIN ----------------
lv_obj_t* pin_old = nullptr;
lv_obj_t* pin_new = nullptr;
lv_obj_t* pin_status = nullptr;

lv_obj_t* makePinInput(lv_obj_t* parent, const char* ph) {
    auto* ta = lv_textarea_create(parent);
    lv_textarea_set_one_line(ta, true);
    lv_textarea_set_password_mode(ta, true);
    lv_textarea_set_accepted_chars(ta, "0123456789");
    lv_textarea_set_max_length(ta, 16);
    lv_textarea_set_placeholder_text(ta, ph);
    lv_obj_set_size(ta, 260, 52);
    lv_obj_add_event_cb(ta, inputEvent, LV_EVENT_FOCUSED, nullptr);
    return ta;
}

void pinSaveEvent(lv_event_t* e) {
    if (lv_event_get_code(e) != LV_EVENT_CLICKED) return;
    const char* o = lv_textarea_get_text(pin_old);
    const char* n = lv_textarea_get_text(pin_new);
    if (!n || !n[0]) {
        lv_label_set_text(pin_status, "Enter new PIN");
        lv_obj_set_style_text_color(pin_status, C_ERR, 0);
        return;
    }
    if (security_change_password(o, n)) {
        lv_label_set_text(pin_status, "PIN changed");
        lv_obj_set_style_text_color(pin_status, C_OK, 0);
        lv_textarea_set_text(pin_old, "");
        lv_textarea_set_text(pin_new, "");
    } else {
        lv_label_set_text(pin_status, "Wrong current PIN");
        lv_obj_set_style_text_color(pin_status, C_ERR, 0);
    }
    lv_obj_add_flag(g_keyboard, LV_OBJ_FLAG_HIDDEN);
}

void createPinTab(lv_obj_t* tab) {
    lv_obj_set_flex_flow(tab, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(tab, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_set_style_pad_all(tab, 12, 0);
    lv_obj_set_style_pad_row(tab, 10, 0);

    auto* h = lv_label_create(tab);
    lv_label_set_text(h, "Change PIN");
    lv_obj_set_style_text_font(h, &lv_font_montserrat_20, 0);

    pin_old = makePinInput(tab, "current PIN");
    pin_new = makePinInput(tab, "new PIN");

    auto* btn = lv_btn_create(tab);
    lv_obj_set_size(btn, 260, 56);
    auto* bl = lv_label_create(btn);
    lv_label_set_text(bl, "SAVE PIN");
    lv_obj_center(bl);
    lv_obj_add_event_cb(btn, pinSaveEvent, LV_EVENT_CLICKED, nullptr);

    pin_status = lv_label_create(tab);
    lv_label_set_text(pin_status, "");
}

// ---------------- Построение основного интерфейса ----------------
void build_programmer_ui(I2cEeprom& eeprom) {
    g_mem = &eeprom;
    randomSeed(esp_random());

    lv_obj_t* screen = lv_scr_act();
    lv_obj_set_style_bg_color(screen, LV_COLOR_MAKE(16, 19, 26), 0);
    lv_obj_set_style_text_color(screen, lv_color_white(), 0);

    lv_obj_t* tv = lv_tabview_create(screen, LV_DIR_TOP, 55);
    lv_obj_set_size(tv, lv_pct(100), lv_pct(100));

    createTab(lv_tabview_add_tab(tv, "201"), 0, "201 RANDOM - 24C16",
              "Enter integer part. Fraction 00-99 is added automatically.",
              "575", EepromType::C24C16, 2048, 0);
    createTab(lv_tabview_add_tab(tv, "c101"), 1, "ENERGOMERA C101 - 24C04",
              "Patch frames 0x00F8 and 0x00FC, then verify whole dump.",
              "3558.00", EepromType::C24C04, 512, 1);
    createTab(lv_tabview_add_tab(tv, "1F"), 2, "NEW 1F - AT24C1024",
              "Read and write the first 0x200 bytes.",
              "2941.44", EepromType::AT24C1024, 512, 2);
    createTab(lv_tabview_add_tab(tv, "3F"), 3, "NEW 3F - AT24C1024",
              "Read and write the first 0x200 bytes.",
              "2941.44", EepromType::AT24C1024, 512, 3);
    createTab(lv_tabview_add_tab(tv, "6803"), 4, "CE6803B P32 - 24C04",
              "Patch head frames and static tail.",
              "3558.00", EepromType::C24C04, 512, 4);
    createTab(lv_tabview_add_tab(tv, "200_MT"), 5, "200_MT - 24C16",
              "Write 4 bytes at 0x0040. Fraction 01-99 is added automatically.",
              "3456", EepromType::C24C16, 4, 5);
    createPinTab(lv_tabview_add_tab(tv, "PIN"));

    g_keyboard = lv_keyboard_create(screen);
    lv_keyboard_set_mode(g_keyboard, LV_KEYBOARD_MODE_NUMBER);
    lv_obj_set_size(g_keyboard, lv_pct(100), 210);
    lv_obj_align(g_keyboard, LV_ALIGN_BOTTOM_MID, 0, 0);
    lv_obj_add_event_cb(g_keyboard, keyboardEvent, LV_EVENT_ALL, nullptr);
    lv_obj_add_flag(g_keyboard, LV_OBJ_FLAG_HIDDEN);
}

// ---------------- Экран входа по PIN ----------------
lv_obj_t* lock_pw = nullptr;
lv_obj_t* lock_err = nullptr;
lv_obj_t* lock_att = nullptr;

void updateAttempts() {
    lv_label_set_text_fmt(lock_att, "Attempts left: %d", security_attempts_left());
}

void doUnlockAsync(void*) {
    lv_obj_clean(lv_scr_act());
    build_programmer_ui(*g_pending);
}

void tryUnlock() {
    const char* pw = lv_textarea_get_text(lock_pw);
    if (security_check_password(pw)) {          // при превышении лимита не вернётся (стирание)
        lv_async_call(doUnlockAsync, nullptr);  // перестроить экран после события
    } else {
        lv_obj_clear_flag(lock_err, LV_OBJ_FLAG_HIDDEN);
        lv_textarea_set_text(lock_pw, "");
        updateAttempts();
    }
}

void lockKbEvent(lv_event_t* e) {
    if (lv_event_get_code(e) == LV_EVENT_READY) tryUnlock();
}
void unlockBtnEvent(lv_event_t* e) {
    if (lv_event_get_code(e) == LV_EVENT_CLICKED) tryUnlock();
}

void build_lock_screen() {
    lv_obj_t* screen = lv_scr_act();
    lv_obj_set_style_bg_color(screen, LV_COLOR_MAKE(16, 19, 26), 0);
    lv_obj_set_style_text_color(screen, lv_color_white(), 0);

    lv_obj_t* card = lv_obj_create(screen);
    lv_obj_set_size(card, 560, 300);
    lv_obj_align(card, LV_ALIGN_TOP_MID, 0, 24);
    lv_obj_set_flex_flow(card, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(card, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_set_style_pad_row(card, 10, 0);
    lv_obj_set_style_bg_color(card, LV_COLOR_MAKE(23, 28, 38), 0);

    auto* title = lv_label_create(card);
    lv_label_set_text(title, APP_TITLE);
    lv_obj_set_style_text_font(title, &lv_font_montserrat_20, 0);

    auto* sub = lv_label_create(card);
    lv_label_set_text(sub, "Enter PIN to unlock");

    lock_pw = lv_textarea_create(card);
    lv_textarea_set_one_line(lock_pw, true);
    lv_textarea_set_password_mode(lock_pw, true);
    lv_textarea_set_accepted_chars(lock_pw, "0123456789");
    lv_textarea_set_max_length(lock_pw, 16);
    lv_textarea_set_placeholder_text(lock_pw, "PIN");
    lv_obj_set_size(lock_pw, 300, 52);
    lv_obj_add_event_cb(lock_pw, lockKbEvent, LV_EVENT_READY, nullptr);

    lock_err = lv_label_create(card);
    lv_label_set_text(lock_err, "Wrong PIN");
    lv_obj_set_style_text_color(lock_err, C_ERR, 0);
    lv_obj_add_flag(lock_err, LV_OBJ_FLAG_HIDDEN);

    lock_att = lv_label_create(card);
    updateAttempts();

    auto* btn = lv_btn_create(card);
    lv_obj_set_size(btn, 220, 56);
    auto* bl = lv_label_create(btn);
    lv_label_set_text(bl, "UNLOCK");
    lv_obj_center(bl);
    lv_obj_add_event_cb(btn, unlockBtnEvent, LV_EVENT_CLICKED, nullptr);

    auto* kb = lv_keyboard_create(screen);
    lv_keyboard_set_mode(kb, LV_KEYBOARD_MODE_NUMBER);
    lv_keyboard_set_textarea(kb, lock_pw);
    lv_obj_set_size(kb, lv_pct(100), 160);
    lv_obj_align(kb, LV_ALIGN_BOTTOM_MID, 0, 0);
}
}  // namespace

void programmer_ui_start(I2cEeprom& eeprom) {
    g_pending = &eeprom;
    build_lock_screen();
}
