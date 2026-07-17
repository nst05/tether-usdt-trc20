// -*- coding: utf-8 -*-
// Полный цикл прошивки. Тексты статусов — латиницей (на экране кириллица не рисуется).
#include "meters.h"
#include "meter_logic.h"
#include <Arduino.h>
#include <esp_random.h>
#include <string.h>
#include <stdio.h>

#define SIZE_24C16   2048
#define SIZE_24C04   512
#define SIZE_AT_1F   0x200
#define SIZE_AT_3F   0x200

static bool all_equal(const uint8_t *b, int n, uint8_t v) {
    for (int i = 0; i < n; i++) if (b[i] != v) return false;
    return true;
}

static MeterResult mk(bool ok, const char *msg) {
    MeterResult r;
    r.ok = ok;
    snprintf(r.message, sizeof(r.message), "%s", msg);
    return r;
}

// ===================== TAB 1: 201 (24C16) =====================
MeterResult meter_201_program(uint32_t int_part, eeprom_progress_fn cb) {
    static uint8_t orig[SIZE_24C16], back[SIZE_24C16];
    uint8_t frac = (uint8_t)(esp_random() % 100);

    if (!eeprom_read_24c16(orig, SIZE_24C16, cb)) return mk(false, "Read error 24C16 (no link?).");
    if (all_equal(orig, SIZE_24C16, 0xFF)) return mk(false, "All 0xFF - chip not connected.");
    if (all_equal(orig, SIZE_24C16, 0x00)) return mk(false, "All 0x00 - wiring problem.");

    static uint8_t patched[SIZE_24C16];
    memcpy(patched, orig, SIZE_24C16);
    patch_201(patched, SIZE_24C16, int_part, frac);

    if (!eeprom_write_24c16(patched, SIZE_24C16, cb)) return mk(false, "Write error 24C16.");
    if (!eeprom_read_24c16(back, SIZE_24C16, cb))      return mk(false, "Read-back error.");
    if (all_equal(back, SIZE_24C16, 0xFF)) return mk(false, "All 0xFF after write.");
    if (all_equal(back, SIZE_24C16, 0x00)) return mk(false, "All 0x00 after write.");

    if (blocks_match_201(patched, back, SIZE_24C16)) {
        char m[192];
        snprintf(m, sizeof(m), "OK: integer %lu, fraction %02u written.", (unsigned long)int_part, frac);
        return mk(true, m);
    }
    return mk(false, "Integer BCD/inv at 0x30/0x50 mismatch.");
}

// ===================== TAB 2: c101 (24C04) =====================
MeterResult meter_c101_program(double reading, eeprom_progress_fn cb) {
    static uint8_t orig[SIZE_24C04], back[SIZE_24C04], blob[SIZE_24C04];

    if (!eeprom_read_24c04(orig, SIZE_24C04, cb)) return mk(false, "Read error 24C04 (no link?).");
    if (all_equal(orig, SIZE_24C04, 0xFF)) return mk(false, "All 0xFF (no chip link).");
    if (all_equal(orig, SIZE_24C04, 0x00)) return mk(false, "All 0x00 (wiring problem).");

    memcpy(blob, orig, SIZE_24C04);
    uint8_t frame[4];
    if (patch_c101(blob, SIZE_24C04, reading, frame) != 0) return mk(false, "RAW out of range 0..0xFFFFFF.");

    if (!eeprom_write_24c04(blob, SIZE_24C04, cb)) return mk(false, "Write error 24C04.");
    if (!eeprom_read_24c04(back, SIZE_24C04, cb))  return mk(false, "Read-back error.");
    if (all_equal(back, SIZE_24C04, 0xFF)) return mk(false, "All 0xFF after write.");
    if (all_equal(back, SIZE_24C04, 0x00)) return mk(false, "All 0x00 after write.");

    if (memcmp(blob, back, SIZE_24C04) == 0) {
        char m[192];
        snprintf(m, sizeof(m), "Verified. Frame F8/FC: %02X %02X %02X %02X",
                 frame[0], frame[1], frame[2], frame[3]);
        return mk(true, m);
    }
    return mk(false, "Data differs from patched dump.");
}

// ===================== TAB 3: new_1F (AT24C1024) =====================
MeterResult meter_1F_program(double value, eeprom_progress_fn cb) {
    static uint8_t orig[SIZE_AT_1F], back[SIZE_AT_1F], image[SIZE_AT_1F];
    if (value < 0) return mk(false, "Value cannot be negative.");

    if (!eeprom_read_at1024(orig, SIZE_AT_1F, cb)) return mk(false, "Read error AT24C1024.");
    if (all_equal(orig, SIZE_AT_1F, 0xFF)) return mk(false, "All 0xFF - no response.");
    if (all_equal(orig, SIZE_AT_1F, 0x00)) return mk(false, "All 0x00 - wiring problem.");

    memcpy(image, orig, SIZE_AT_1F);
    uint8_t frame[4]; uint32_t N;
    if (patch_1F(image, SIZE_AT_1F, value, frame, &N) != 0) return mk(false, "N out of 24-bit range.");

    if (!eeprom_write_at1024(image, SIZE_AT_1F, cb)) return mk(false, "Write error AT24C1024.");
    if (!eeprom_read_at1024(back, SIZE_AT_1F, cb))   return mk(false, "Read-back error.");
    if (all_equal(back, SIZE_AT_1F, 0xFF)) return mk(false, "All 0xFF after write.");
    if (all_equal(back, SIZE_AT_1F, 0x00)) return mk(false, "All 0x00 after write.");

    if (memcmp(image, back, SIZE_AT_1F) == 0) {
        char m[192];
        snprintf(m, sizeof(m), "OK: N=%lu  D0 D1 D2 CRC = %02X %02X %02X %02X",
                 (unsigned long)N, frame[0], frame[1], frame[2], frame[3]);
        return mk(true, m);
    }
    return mk(false, "Bytes 0x0000..0x01FF mismatch.");
}

// ===================== TAB 4: new_3F (AT24C1024) =====================
MeterResult meter_3F_program(double value, eeprom_progress_fn cb) {
    static uint8_t orig[SIZE_AT_3F], back[SIZE_AT_3F], image[SIZE_AT_3F];
    if (value < 0) return mk(false, "Value cannot be negative.");

    if (!eeprom_read_at1024(orig, SIZE_AT_3F, cb)) return mk(false, "Read error AT24C1024.");
    if (all_equal(orig, SIZE_AT_3F, 0xFF)) return mk(false, "All 0xFF - no response.");
    if (all_equal(orig, SIZE_AT_3F, 0x00)) return mk(false, "All 0x00 - wiring problem.");

    memcpy(image, orig, SIZE_AT_3F);
    uint8_t frame[4]; uint32_t N;
    if (patch_3F(image, SIZE_AT_3F, value, frame, &N) != 0) return mk(false, "N out of 24-bit range.");

    if (!eeprom_write_at1024(image, SIZE_AT_3F, cb)) return mk(false, "Write error AT24C1024.");
    if (!eeprom_read_at1024(back, SIZE_AT_3F, cb))   return mk(false, "Read-back error.");
    if (all_equal(back, SIZE_AT_3F, 0xFF)) return mk(false, "All 0xFF after write.");
    if (all_equal(back, SIZE_AT_3F, 0x00)) return mk(false, "All 0x00 after write.");

    if (memcmp(image, back, SIZE_AT_3F) == 0) {
        char m[192];
        snprintf(m, sizeof(m), "OK: N=%lu  %02X %02X %02X %02X, 0x9C @1FB/1FF",
                 (unsigned long)N, frame[0], frame[1], frame[2], frame[3]);
        return mk(true, m);
    }
    return mk(false, "Bytes 0x0000..0x01FF mismatch.");
}

// ===================== TAB 5: ce6803b_p32 (24C04) =====================
MeterResult meter_6803_program(double reading, eeprom_progress_fn cb) {
    static uint8_t orig[SIZE_24C04], back[SIZE_24C04], blob[SIZE_24C04];

    if (!eeprom_read_24c04(orig, SIZE_24C04, cb)) return mk(false, "Read error 24C04 (no link?).");
    if (all_equal(orig, SIZE_24C04, 0xFF)) return mk(false, "All 0xFF (no chip).");
    if (all_equal(orig, SIZE_24C04, 0x00)) return mk(false, "All 0x00 (wiring problem).");

    memcpy(blob, orig, SIZE_24C04);
    uint8_t frame[4];
    if (patch_6803(blob, SIZE_24C04, reading, frame) != 0) return mk(false, "RAW out of range 0..0xFFFFFF.");

    if (!eeprom_write_24c04(blob, SIZE_24C04, cb)) return mk(false, "Write error 24C04.");
    if (!eeprom_read_24c04(back, SIZE_24C04, cb))  return mk(false, "Read-back error.");
    if (all_equal(back, SIZE_24C04, 0xFF)) return mk(false, "All 0xFF after write.");
    if (all_equal(back, SIZE_24C04, 0x00)) return mk(false, "All 0x00 after write.");

    if (memcmp(blob, back, SIZE_24C04) == 0) {
        char m[192];
        snprintf(m, sizeof(m), "Verified. F8/FC: %02X %02X %02X %02X, tail 00 00 00 69",
                 frame[0], frame[1], frame[2], frame[3]);
        return mk(true, m);
    }
    return mk(false, "Data differs from patched dump.");
}

// ===================== TAB 6: 200_MT (24C16, value at 0x0040) =====================
MeterResult meter_200mt_program(double base_value, eeprom_progress_fn cb) {
    if (base_value < 0) return mk(false, "Value cannot be negative.");
    if (cb) cb(10);

    long integer_part = (long)base_value;
    int fraction = (int)(esp_random() % 99) + 1;    // 1..99
    double value = (double)integer_part + fraction / 100.0;

    uint8_t expected[4];
    if (encode_value_200mt(value, expected) != 0) return mk(false, "Value too large.");

    if (cb) cb(40);
    if (!eeprom_write_bytes_24c16(0x0040, expected, 4)) return mk(false, "Write error at 0x0040.");
    if (cb) cb(65);
    delay(150);

    uint8_t actual[4] = {0, 0, 0, 0};
    bool matched = false;
    for (int i = 0; i < 10; i++) {
        if (eeprom_read_bytes_24c16(0x0040, actual, 4) && memcmp(actual, expected, 4) == 0) {
            matched = true;
            break;
        }
        delay(50);
    }
    if (cb) cb(100);

    if (!matched) return mk(false, "Verification failed.");

    double verified = decode_value_200mt(actual);
    char m[192];
    snprintf(m, sizeof(m), "OK: written %.2f", verified);
    return mk(true, m);
}
