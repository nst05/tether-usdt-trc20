// -*- coding: utf-8 -*-
#include "ui.h"
#include "app_config.h"
#include "meters.h"
#include "security.h"
#include <lvgl.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>

// Кастомные ASCII-шрифты (генерируются lv_font_conv из DejaVuSans).
LV_FONT_DECLARE(ui_font_18);
LV_FONT_DECLARE(ui_font_24);
LV_FONT_DECLARE(ui_font_34);

// -------- Палитра (тёмная тема) --------
#define COL_BG      lv_color_hex(0x0E1116)
#define COL_CARD    lv_color_hex(0x171C26)
#define COL_CARD2   lv_color_hex(0x1E2430)
#define COL_ACCENT  lv_color_hex(0x3F6DF6)
#define COL_ACCENT2 lv_color_hex(0x5B84FF)
#define COL_TEXT    lv_color_hex(0xF2F4F8)
#define COL_MUTED   lv_color_hex(0x97A2B6)
#define COL_OK      lv_color_hex(0x2FC46F)
#define COL_ERR     lv_color_hex(0xFF5A6F)
#define COL_BORDER  lv_color_hex(0x2A3342)

// -------- Типы программаторов --------
enum MeterType { M_201, M_C101, M_1F, M_3F, M_6803, M_200MT };

struct TabCtx {
    MeterType type;
    lv_obj_t *ta;
    lv_obj_t *bar;
    lv_obj_t *status;
    lv_obj_t *counter;
    int       count;
};

static TabCtx  g_tabs[6];
static TabCtx *g_running = nullptr;

static lv_obj_t *scr_lock = nullptr, *scr_main = nullptr;
static lv_obj_t *kb_lock = nullptr, *kb_main = nullptr;
static lv_obj_t *lock_pw = nullptr, *lock_err = nullptr, *lock_att = nullptr;
static lv_obj_t *modal = nullptr, *m_old = nullptr, *m_new = nullptr, *m_status = nullptr;

// -------- Стили --------
static lv_style_t st_card, st_btn, st_btn_pr, st_input, st_input_focus, st_bar_bg, st_bar_ind, st_btn2;

static void init_styles() {
    lv_style_init(&st_card);
    lv_style_set_bg_color(&st_card, COL_CARD);
    lv_style_set_bg_opa(&st_card, LV_OPA_COVER);
    lv_style_set_radius(&st_card, 18);
    lv_style_set_border_color(&st_card, COL_BORDER);
    lv_style_set_border_width(&st_card, 1);
    lv_style_set_pad_all(&st_card, 20);
    lv_style_set_shadow_width(&st_card, 24);
    lv_style_set_shadow_color(&st_card, lv_color_hex(0x000000));
    lv_style_set_shadow_opa(&st_card, LV_OPA_40);

    lv_style_init(&st_btn);
    lv_style_set_bg_color(&st_btn, COL_ACCENT);
    lv_style_set_bg_grad_color(&st_btn, COL_ACCENT2);
    lv_style_set_bg_grad_dir(&st_btn, LV_GRAD_DIR_VER);
    lv_style_set_bg_opa(&st_btn, LV_OPA_COVER);
    lv_style_set_radius(&st_btn, 14);
    lv_style_set_border_width(&st_btn, 0);
    lv_style_set_text_color(&st_btn, COL_TEXT);
    lv_style_set_text_font(&st_btn, &ui_font_24);
    lv_style_set_pad_all(&st_btn, 14);

    lv_style_init(&st_btn_pr);
    lv_style_set_bg_color(&st_btn_pr, lv_color_hex(0x345ACB));
    lv_style_set_bg_grad_color(&st_btn_pr, lv_color_hex(0x345ACB));

    lv_style_init(&st_btn2);   // второстепенная кнопка
    lv_style_set_bg_color(&st_btn2, COL_CARD2);
    lv_style_set_bg_opa(&st_btn2, LV_OPA_COVER);
    lv_style_set_radius(&st_btn2, 12);
    lv_style_set_border_color(&st_btn2, COL_BORDER);
    lv_style_set_border_width(&st_btn2, 1);
    lv_style_set_text_color(&st_btn2, COL_MUTED);
    lv_style_set_text_font(&st_btn2, &ui_font_18);
    lv_style_set_pad_all(&st_btn2, 10);

    lv_style_init(&st_input);
    lv_style_set_bg_color(&st_input, COL_CARD2);
    lv_style_set_bg_opa(&st_input, LV_OPA_COVER);
    lv_style_set_radius(&st_input, 12);
    lv_style_set_border_color(&st_input, COL_BORDER);
    lv_style_set_border_width(&st_input, 2);
    lv_style_set_text_color(&st_input, COL_TEXT);
    lv_style_set_text_font(&st_input, &ui_font_24);
    lv_style_set_pad_all(&st_input, 14);

    lv_style_init(&st_input_focus);
    lv_style_set_border_color(&st_input_focus, COL_ACCENT2);

    lv_style_init(&st_bar_bg);
    lv_style_set_bg_color(&st_bar_bg, COL_CARD2);
    lv_style_set_bg_opa(&st_bar_bg, LV_OPA_COVER);
    lv_style_set_radius(&st_bar_bg, 8);
    lv_style_set_border_color(&st_bar_bg, COL_BORDER);
    lv_style_set_border_width(&st_bar_bg, 1);

    lv_style_init(&st_bar_ind);
    lv_style_set_bg_color(&st_bar_ind, COL_ACCENT);
    lv_style_set_bg_grad_color(&st_bar_ind, COL_ACCENT2);
    lv_style_set_bg_grad_dir(&st_bar_ind, LV_GRAD_DIR_HOR);
    lv_style_set_bg_opa(&st_bar_ind, LV_OPA_COVER);
    lv_style_set_radius(&st_bar_ind, 8);
}

// -------- Хелперы --------
static lv_obj_t *make_label(lv_obj_t *parent, const char *txt, const lv_font_t *font, lv_color_t color) {
    lv_obj_t *l = lv_label_create(parent);
    lv_label_set_text(l, txt);
    lv_obj_set_style_text_font(l, font, 0);
    lv_obj_set_style_text_color(l, color, 0);
    return l;
}

static lv_obj_t *make_button(lv_obj_t *parent, const char *txt, lv_style_t *style) {
    lv_obj_t *b = lv_btn_create(parent);
    lv_obj_remove_style_all(b);
    lv_obj_add_style(b, style, 0);
    if (style == &st_btn) lv_obj_add_style(b, &st_btn_pr, LV_STATE_PRESSED);
    lv_obj_t *l = lv_label_create(b);
    lv_label_set_text(l, txt);
    lv_obj_center(l);
    return b;
}

static lv_obj_t *make_input(lv_obj_t *parent, bool password, const char *placeholder) {
    lv_obj_t *ta = lv_textarea_create(parent);
    lv_obj_remove_style_all(ta);
    lv_obj_add_style(ta, &st_input, 0);
    lv_obj_add_style(ta, &st_input_focus, LV_STATE_FOCUSED);
    lv_textarea_set_one_line(ta, true);
    lv_textarea_set_password_mode(ta, password);
    lv_textarea_set_max_length(ta, 16);
    if (placeholder) lv_textarea_set_placeholder_text(ta, placeholder);
    return ta;
}

// ============================================================
//  ПРОГРАММАТОРЫ (вкладки)
// ============================================================
static void set_status(TabCtx *t, const char *msg, int state) {
    lv_label_set_text(t->status, msg);
    lv_color_t c = (state == 1) ? COL_OK : (state == 2) ? COL_ERR : COL_MUTED;
    lv_obj_set_style_text_color(t->status, c, 0);
}

static void progress_cb(int pct) {
    if (g_running && g_running->bar) {
        lv_bar_set_value(g_running->bar, pct, LV_ANIM_OFF);
        lv_refr_now(NULL);
    }
}

static void run_meter(TabCtx *t) {
    const char *txt = lv_textarea_get_text(t->ta);
    if (txt == nullptr || txt[0] == '\0') { set_status(t, "Enter value first.", 2); return; }
    char buf[32];
    strncpy(buf, txt, sizeof(buf) - 1);
    buf[sizeof(buf) - 1] = '\0';
    for (char *p = buf; *p; p++) if (*p == ',') *p = '.';
    double value = atof(buf);

    g_running = t;
    lv_bar_set_value(t->bar, 0, LV_ANIM_OFF);
    set_status(t, "Working...", 0);
    lv_refr_now(NULL);

    MeterResult r;
    switch (t->type) {
        case M_201:   r = meter_201_program((uint32_t)value, progress_cb); break;
        case M_C101:  r = meter_c101_program(value, progress_cb); break;
        case M_1F:    r = meter_1F_program(value, progress_cb); break;
        case M_3F:    r = meter_3F_program(value, progress_cb); break;
        case M_6803:  r = meter_6803_program(value, progress_cb); break;
        case M_200MT: r = meter_200mt_program(value, progress_cb); break;
        default:      r.ok = false; strcpy(r.message, "Unknown meter."); break;
    }
    g_running = nullptr;

    set_status(t, r.message, r.ok ? 1 : 2);
    lv_bar_set_value(t->bar, r.ok ? 100 : 0, LV_ANIM_OFF);
    if (r.ok) {
        t->count++;
        char c[32];
        snprintf(c, sizeof(c), "Programmed: %d", t->count);
        lv_label_set_text(t->counter, c);
    }
}

static void btn_program_cb(lv_event_t *e) {
    run_meter((TabCtx *)lv_event_get_user_data(e));
}

// клавиатура главного экрана (поля программаторов + модалка смены PIN)
static void ta_main_cb(lv_event_t *e) {
    lv_event_code_t code = lv_event_get_code(e);
    lv_obj_t *ta = lv_event_get_target(e);
    if (code == LV_EVENT_FOCUSED || code == LV_EVENT_CLICKED) {
        lv_keyboard_set_textarea(kb_main, ta);
        lv_obj_clear_flag(kb_main, LV_OBJ_FLAG_HIDDEN);
        lv_obj_move_foreground(kb_main);
    } else if (code == LV_EVENT_DEFOCUSED || code == LV_EVENT_READY || code == LV_EVENT_CANCEL) {
        lv_keyboard_set_textarea(kb_main, NULL);
        lv_obj_add_flag(kb_main, LV_OBJ_FLAG_HIDDEN);
    }
}

static void build_tab(lv_obj_t *page, TabCtx *ctx, const char *title, const char *hint,
                      const char *def_val) {
    lv_obj_set_style_bg_color(page, COL_BG, 0);
    lv_obj_set_style_pad_all(page, 14, 0);
    lv_obj_set_flex_flow(page, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(page, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);

    lv_obj_t *card = lv_obj_create(page);
    lv_obj_remove_style_all(card);
    lv_obj_add_style(card, &st_card, 0);
    lv_obj_set_width(card, 620);
    lv_obj_set_height(card, LV_SIZE_CONTENT);
    lv_obj_set_flex_flow(card, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(card, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_START);
    lv_obj_set_style_pad_row(card, 12, 0);

    make_label(card, title, &ui_font_34, COL_TEXT);
    make_label(card, hint, &ui_font_18, COL_MUTED);

    ctx->ta = make_input(card, false, nullptr);
    lv_textarea_set_text(ctx->ta, def_val);
    lv_obj_set_width(ctx->ta, LV_PCT(100));
    lv_obj_add_event_cb(ctx->ta, ta_main_cb, LV_EVENT_ALL, NULL);

    lv_obj_t *btn = make_button(card, "PROGRAM  &  VERIFY", &st_btn);
    lv_obj_set_width(btn, LV_PCT(100));
    lv_obj_set_height(btn, 62);
    lv_obj_add_event_cb(btn, btn_program_cb, LV_EVENT_CLICKED, ctx);

    ctx->bar = lv_bar_create(card);
    lv_obj_remove_style_all(ctx->bar);
    lv_obj_add_style(ctx->bar, &st_bar_bg, LV_PART_MAIN);
    lv_obj_add_style(ctx->bar, &st_bar_ind, LV_PART_INDICATOR);
    lv_obj_set_size(ctx->bar, LV_PCT(100), 18);
    lv_bar_set_range(ctx->bar, 0, 100);
    lv_bar_set_value(ctx->bar, 0, LV_ANIM_OFF);

    ctx->status = make_label(card, "Ready.", &ui_font_18, COL_MUTED);
    lv_label_set_long_mode(ctx->status, LV_LABEL_LONG_WRAP);
    lv_obj_set_width(ctx->status, LV_PCT(100));

    ctx->counter = make_label(card, "Programmed: 0", &ui_font_18, COL_MUTED);
    ctx->count = 0;
}

// ============================================================
//  МОДАЛКА СМЕНЫ PIN
// ============================================================
static void modal_close_cb(lv_event_t *e) {
    (void)e;
    lv_obj_add_flag(modal, LV_OBJ_FLAG_HIDDEN);
    lv_obj_add_flag(kb_main, LV_OBJ_FLAG_HIDDEN);
}

static void modal_save_cb(lv_event_t *e) {
    (void)e;
    const char *o = lv_textarea_get_text(m_old);
    const char *n = lv_textarea_get_text(m_new);
    if (!n || n[0] == '\0') {
        lv_label_set_text(m_status, "Enter new PIN");
        lv_obj_set_style_text_color(m_status, COL_ERR, 0);
        return;
    }
    if (security_change_password(o, n)) {
        lv_label_set_text(m_status, "PIN changed");
        lv_obj_set_style_text_color(m_status, COL_OK, 0);
        lv_textarea_set_text(m_old, "");
        lv_textarea_set_text(m_new, "");
    } else {
        lv_label_set_text(m_status, "Wrong current PIN");
        lv_obj_set_style_text_color(m_status, COL_ERR, 0);
    }
}

static void open_modal_cb(lv_event_t *e) {
    (void)e;
    lv_textarea_set_text(m_old, "");
    lv_textarea_set_text(m_new, "");
    lv_label_set_text(m_status, "");
    lv_obj_clear_flag(modal, LV_OBJ_FLAG_HIDDEN);
    lv_obj_move_foreground(modal);
}

static void build_modal(lv_obj_t *parent) {
    modal = lv_obj_create(parent);
    lv_obj_remove_style_all(modal);
    lv_obj_set_size(modal, LV_PCT(100), LV_PCT(100));
    lv_obj_set_style_bg_color(modal, lv_color_hex(0x000000), 0);
    lv_obj_set_style_bg_opa(modal, LV_OPA_60, 0);
    lv_obj_add_flag(modal, LV_OBJ_FLAG_HIDDEN);
    lv_obj_clear_flag(modal, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *card = lv_obj_create(modal);
    lv_obj_remove_style_all(card);
    lv_obj_add_style(card, &st_card, 0);
    lv_obj_set_size(card, 520, 320);
    lv_obj_align(card, LV_ALIGN_TOP_MID, 0, 20);
    lv_obj_set_flex_flow(card, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(card, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_set_style_pad_row(card, 10, 0);
    lv_obj_clear_flag(card, LV_OBJ_FLAG_SCROLLABLE);

    make_label(card, "Change PIN", &ui_font_34, COL_TEXT);

    m_old = make_input(card, true, "current PIN");
    lv_obj_set_width(m_old, LV_PCT(100));
    lv_obj_add_event_cb(m_old, ta_main_cb, LV_EVENT_ALL, NULL);

    m_new = make_input(card, true, "new PIN");
    lv_obj_set_width(m_new, LV_PCT(100));
    lv_obj_add_event_cb(m_new, ta_main_cb, LV_EVENT_ALL, NULL);

    m_status = make_label(card, "", &ui_font_18, COL_MUTED);

    lv_obj_t *row = lv_obj_create(card);
    lv_obj_remove_style_all(row);
    lv_obj_set_size(row, LV_PCT(100), LV_SIZE_CONTENT);
    lv_obj_set_flex_flow(row, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(row, LV_FLEX_ALIGN_SPACE_BETWEEN, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_clear_flag(row, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *cancel = make_button(row, "Cancel", &st_btn2);
    lv_obj_set_width(cancel, 150); lv_obj_set_height(cancel, 52);
    lv_obj_add_event_cb(cancel, modal_close_cb, LV_EVENT_CLICKED, NULL);

    lv_obj_t *save = make_button(row, "Save", &st_btn);
    lv_obj_set_width(save, 150); lv_obj_set_height(save, 52);
    lv_obj_add_event_cb(save, modal_save_cb, LV_EVENT_CLICKED, NULL);
}

// ============================================================
//  ГЛАВНЫЙ ЭКРАН
// ============================================================
static void relock_cb(lv_event_t *e) {
    (void)e;
    lv_textarea_set_text(lock_pw, "");
    lv_obj_add_flag(lock_err, LV_OBJ_FLAG_HIDDEN);
    lv_scr_load_anim(scr_lock, LV_SCR_LOAD_ANIM_MOVE_RIGHT, 250, 0, false);
}

static void build_main_screen() {
    scr_main = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(scr_main, COL_BG, 0);
    lv_obj_clear_flag(scr_main, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_flex_flow(scr_main, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_all(scr_main, 0, 0);

    // Шапка
    lv_obj_t *bar = lv_obj_create(scr_main);
    lv_obj_remove_style_all(bar);
    lv_obj_set_size(bar, LV_PCT(100), 54);
    lv_obj_set_style_bg_color(bar, COL_CARD, 0);
    lv_obj_set_style_bg_opa(bar, LV_OPA_COVER, 0);
    lv_obj_set_style_pad_left(bar, 16, 0);
    lv_obj_set_style_pad_right(bar, 10, 0);
    lv_obj_set_flex_flow(bar, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(bar, LV_FLEX_ALIGN_SPACE_BETWEEN, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_clear_flag(bar, LV_OBJ_FLAG_SCROLLABLE);
    make_label(bar, APP_TITLE, &ui_font_24, COL_TEXT);

    lv_obj_t *right = lv_obj_create(bar);
    lv_obj_remove_style_all(right);
    lv_obj_set_size(right, LV_SIZE_CONTENT, LV_SIZE_CONTENT);
    lv_obj_set_flex_flow(right, LV_FLEX_FLOW_ROW);
    lv_obj_set_style_pad_column(right, 8, 0);
    lv_obj_clear_flag(right, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_t *pinb = make_button(right, "Change PIN", &st_btn2);
    lv_obj_add_event_cb(pinb, open_modal_cb, LV_EVENT_CLICKED, NULL);
    lv_obj_t *lockb = make_button(right, "Lock", &st_btn2);
    lv_obj_add_event_cb(lockb, relock_cb, LV_EVENT_CLICKED, NULL);

    // Вкладки
    lv_obj_t *tv = lv_tabview_create(scr_main, LV_DIR_TOP, 52);
    lv_obj_set_flex_grow(tv, 1);
    lv_obj_set_style_bg_color(tv, COL_BG, 0);

    lv_obj_t *tabbtns = lv_tabview_get_tab_btns(tv);
    lv_obj_set_style_bg_color(tabbtns, COL_CARD, 0);
    lv_obj_set_style_text_color(tabbtns, COL_MUTED, 0);
    lv_obj_set_style_text_font(tabbtns, &ui_font_18, 0);
    lv_obj_set_style_text_color(tabbtns, COL_TEXT, LV_PART_ITEMS | LV_STATE_CHECKED);
    lv_obj_set_style_border_color(tabbtns, COL_ACCENT, LV_PART_ITEMS | LV_STATE_CHECKED);
    lv_obj_set_style_bg_color(tabbtns, COL_CARD2, LV_PART_ITEMS | LV_STATE_CHECKED);
    lv_obj_set_style_bg_opa(tabbtns, LV_OPA_COVER, LV_PART_ITEMS | LV_STATE_CHECKED);

    struct { const char *name, *title, *hint, *def; MeterType type; } defs[6] = {
        { "201",    "201 random",   "24C16 - integer, random fraction",  "575",     M_201   },
        { "c101",   "c101",         "24C04 - reading, frames F8/FC",     "3558.00", M_C101  },
        { "1F",     "new 1F",       "AT24C1024 - round(value/2.56)",     "2941.44", M_1F    },
        { "3F",     "new 3F",       "AT24C1024 - floor(value/2.56)",     "2941.44", M_3F    },
        { "6803",   "ce6803b p32",  "24C04 - frames F8/FC + tail",       "3558.00", M_6803  },
        { "200_MT", "200 MT",       "24C16 - value at 0x0040",           "3456",    M_200MT },
    };
    for (int i = 0; i < 6; i++) {
        lv_obj_t *page = lv_tabview_add_tab(tv, defs[i].name);
        g_tabs[i].type = defs[i].type;
        build_tab(page, &g_tabs[i], defs[i].title, defs[i].hint, defs[i].def);
    }

    build_modal(scr_main);

    // Клавиатура главного экрана (появляется по фокусу поля)
    kb_main = lv_keyboard_create(scr_main);
    lv_keyboard_set_mode(kb_main, LV_KEYBOARD_MODE_NUMBER);
    lv_obj_set_size(kb_main, LV_PCT(100), 200);
    lv_obj_align(kb_main, LV_ALIGN_BOTTOM_MID, 0, 0);
    lv_obj_add_flag(kb_main, LV_OBJ_FLAG_HIDDEN);
    lv_obj_add_event_cb(kb_main, ta_main_cb, LV_EVENT_READY, NULL);
    lv_obj_add_event_cb(kb_main, ta_main_cb, LV_EVENT_CANCEL, NULL);
}

// ============================================================
//  ЭКРАН ВХОДА
// ============================================================
static void update_attempts() {
    char b[48];
    snprintf(b, sizeof(b), "Attempts left: %d", security_attempts_left());
    lv_label_set_text(lock_att, b);
}

static void unlock_try() {
    const char *pw = lv_textarea_get_text(lock_pw);
    if (security_check_password(pw)) {   // при превышении лимита не вернётся (стирание)
        lv_obj_add_flag(lock_err, LV_OBJ_FLAG_HIDDEN);
        lv_textarea_set_text(lock_pw, "");
        update_attempts();
        lv_scr_load_anim(scr_main, LV_SCR_LOAD_ANIM_MOVE_LEFT, 250, 0, false);
    } else {
        lv_obj_clear_flag(lock_err, LV_OBJ_FLAG_HIDDEN);
        lv_textarea_set_text(lock_pw, "");
        update_attempts();
    }
}

static void lock_ready_cb(lv_event_t *e) {
    if (lv_event_get_code(e) == LV_EVENT_READY) unlock_try();
}
static void unlock_btn_cb(lv_event_t *e) { (void)e; unlock_try(); }

static void build_lock_screen() {
    scr_lock = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(scr_lock, COL_BG, 0);
    lv_obj_clear_flag(scr_lock, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *card = lv_obj_create(scr_lock);
    lv_obj_remove_style_all(card);
    lv_obj_add_style(card, &st_card, 0);
    lv_obj_set_size(card, 560, 300);
    lv_obj_align(card, LV_ALIGN_TOP_MID, 0, 24);
    lv_obj_set_flex_flow(card, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(card, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_set_style_pad_row(card, 10, 0);
    lv_obj_clear_flag(card, LV_OBJ_FLAG_SCROLLABLE);

    make_label(card, APP_TITLE, &ui_font_34, COL_TEXT);
    make_label(card, "Enter PIN to unlock", &ui_font_18, COL_MUTED);

    lock_pw = make_input(card, true, "PIN");
    lv_obj_set_width(lock_pw, LV_PCT(90));
    lv_obj_add_event_cb(lock_pw, lock_ready_cb, LV_EVENT_READY, NULL);

    lock_err = make_label(card, "Wrong PIN", &ui_font_18, COL_ERR);
    lv_obj_add_flag(lock_err, LV_OBJ_FLAG_HIDDEN);

    lock_att = make_label(card, "", &ui_font_18, COL_MUTED);
    update_attempts();

    lv_obj_t *btn = make_button(card, "UNLOCK", &st_btn);
    lv_obj_set_width(btn, LV_PCT(60));
    lv_obj_set_height(btn, 56);
    lv_obj_add_event_cb(btn, unlock_btn_cb, LV_EVENT_CLICKED, NULL);

    kb_lock = lv_keyboard_create(scr_lock);
    lv_keyboard_set_mode(kb_lock, LV_KEYBOARD_MODE_NUMBER);
    lv_keyboard_set_textarea(kb_lock, lock_pw);
    lv_obj_set_size(kb_lock, LV_PCT(100), 150);
    lv_obj_align(kb_lock, LV_ALIGN_BOTTOM_MID, 0, 0);
}

// ============================================================
void ui_build() {
    init_styles();
    build_lock_screen();
    build_main_screen();
    lv_scr_load(scr_lock);
}
