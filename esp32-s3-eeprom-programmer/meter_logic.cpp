// -*- coding: utf-8 -*-
// Реализация чистой логики. Портировано 1:1 из Python-версии.
#include "meter_logic.h"
#include <math.h>
#include <string.h>

// ===================== CRC =====================

uint16_t crc16_ibm(const uint8_t *data, size_t len) {
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (int b = 0; b < 8; b++) {
            if (crc & 1) crc = (uint16_t)((crc >> 1) ^ 0xA001);
            else         crc = (uint16_t)(crc >> 1);
        }
    }
    return crc & 0xFFFF;
}

uint8_t crc8_b5(const uint8_t *data, size_t len) {
    uint8_t crc = 0xFF;                 // INIT
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (int b = 0; b < 8; b++) {
            if (crc & 0x80) crc = (uint8_t)((crc << 1) ^ 0xB5);
            else            crc = (uint8_t)(crc << 1);
        }
    }
    return crc;
}

uint8_t crc_low_ccitt_false(uint8_t d0, uint8_t d1, uint8_t d2) {
    uint16_t crc = 0xFFFF;
    uint8_t bytes[3] = { d0, d1, d2 };
    for (int i = 0; i < 3; i++) {
        crc ^= (uint16_t)(bytes[i] << 8);
        for (int b = 0; b < 8; b++) {
            if (crc & 0x8000) crc = (uint16_t)((crc << 1) ^ 0x1021);
            else              crc = (uint16_t)(crc << 1);
        }
    }
    return (uint8_t)(crc & 0xFF);
}

// ===================== helpers =====================

void to_bcd_bytes_201(uint32_t value, uint8_t out[3]) {
    // 6 цифр с ведущими нулями
    char digits[7];
    // %06u усечёт при value > 999999, как и str().rjust(6) не усекает,
    // но исходник ожидает <= 999999. Ограничим по модулю 1e6 для безопасности.
    uint32_t v = value % 1000000u;
    for (int i = 5; i >= 0; i--) { digits[i] = (char)('0' + (v % 10)); v /= 10; }
    digits[6] = 0;
    out[0] = (uint8_t)((digits[0] - '0') * 16 + (digits[1] - '0'));
    out[1] = (uint8_t)((digits[2] - '0') * 16 + (digits[3] - '0'));
    out[2] = (uint8_t)((digits[4] - '0') * 16 + (digits[5] - '0'));
}

uint8_t hund_to_bcd(uint8_t hund) {
    uint8_t tens = (uint8_t)(hund / 10);
    uint8_t ones = (uint8_t)(hund % 10);
    return (uint8_t)((tens << 4) | ones);
}

// ===================== TAB 1: 201 =====================

void patch_201(uint8_t *eeprom, size_t len, uint32_t int_value, uint8_t frac_hund) {
    if (len < 0x58) return;

    // целая часть
    uint8_t bcd[3];
    to_bcd_bytes_201(int_value, bcd);
    uint8_t inv[3] = { (uint8_t)(0xFF - bcd[0]), (uint8_t)(0xFF - bcd[1]), (uint8_t)(0xFF - bcd[2]) };
    uint8_t bcdinv[6] = { bcd[0], bcd[1], bcd[2], inv[0], inv[1], inv[2] };
    uint16_t crc6 = crc16_ibm(bcdinv, 6);
    uint8_t frame_int[8] = { bcd[0], bcd[1], bcd[2], inv[0], inv[1], inv[2],
                             (uint8_t)(crc6 & 0xFF), (uint8_t)((crc6 >> 8) & 0xFF) };

    // дробная часть
    uint8_t C = hund_to_bcd(frac_hund);
    uint8_t first6[6] = { 0x03, 0x00, C, 0xFC, 0xFF, (uint8_t)((0xFF - C) & 0xFF) };
    uint16_t crc_frac = crc16_ibm(first6, 6);
    uint8_t frame_frac[8] = { first6[0], first6[1], first6[2], first6[3], first6[4], first6[5],
                              (uint8_t)(crc_frac & 0xFF), (uint8_t)((crc_frac >> 8) & 0xFF) };

    // патчим (порядок как в оригинале)
    memcpy(&eeprom[0x20], frame_frac, 8);   // дробная часть
    memcpy(&eeprom[0x33], inv, 3);          // инверсии (перекрывается ниже)
    memcpy(&eeprom[0x30], frame_int, 8);    // целая часть
    memcpy(&eeprom[0x50], frame_int, 8);    // копия
}

int blocks_match_201(const uint8_t *golden, const uint8_t *actual, size_t len) {
    if (len < 0x56) return 0;
    for (int a = 0x30; a < 0x36; a++) if (golden[a] != actual[a]) return 0;
    for (int a = 0x50; a < 0x56; a++) if (golden[a] != actual[a]) return 0;
    return 1;
}

// ===================== TAB 2: c101 =====================

int patch_c101(uint8_t *blob, size_t len, double reading, uint8_t frame_out[4]) {
    long raw = (long)lround(reading / 2.56);
    if (raw < 0 || raw > 0xFFFFFF) return -1;
    uint8_t data3[3] = { (uint8_t)((raw >> 16) & 0xFF), (uint8_t)((raw >> 8) & 0xFF), (uint8_t)(raw & 0xFF) };
    uint8_t crc = crc8_b5(data3, 3);
    uint8_t frame[4] = { data3[0], data3[1], data3[2], crc };
    if (len >= 0x0100) {
        memcpy(&blob[0x00F8], frame, 4);
        memcpy(&blob[0x00FC], frame, 4);
    }
    memcpy(frame_out, frame, 4);
    return 0;
}

// ===================== TAB 3: new_1F =====================

int patch_1F(uint8_t *image, size_t len, double value, uint8_t frame_out[4], uint32_t *N_out) {
    if (len < 0x0200) return -1;
    long N = (long)lround(value / 2.56);
    if (N < 0 || N > 0xFFFFFF) return -1;
    uint8_t d0 = (uint8_t)(N & 0xFF);
    uint8_t d1 = (uint8_t)((N >> 8) & 0xFF);
    uint8_t d2 = (uint8_t)((N >> 16) & 0xFF);
    uint8_t crc = crc_low_ccitt_false(d0, d1, d2);
    uint8_t frame[4] = { d0, d1, d2, crc };
    const int addrs[2] = { 0x00F8, 0x00FC };
    for (int k = 0; k < 2; k++) memcpy(&image[addrs[k]], frame, 4);
    // статический шаблон 5 x 0x00 по 0x01F0
    for (int i = 0; i < 5; i++) image[0x01F0 + i] = 0x00;
    memcpy(frame_out, frame, 4);
    if (N_out) *N_out = (uint32_t)N;
    return 0;
}

// ===================== TAB 4: new_3F =====================

int patch_3F(uint8_t *image, size_t len, double value, uint8_t frame_out[4], uint32_t *N_out) {
    if (len < 0x0200) return -1;
    long N = (long)floor(value / 2.56);
    if (N < 0 || N > 0xFFFFFF) return -1;
    uint8_t d0 = (uint8_t)(N & 0xFF);
    uint8_t d1 = (uint8_t)((N >> 8) & 0xFF);
    uint8_t d2 = (uint8_t)((N >> 16) & 0xFF);
    uint8_t crc = crc_low_ccitt_false(d0, d1, d2);
    uint8_t frame[4] = { d0, d1, d2, crc };
    const int addrs[2] = { 0x00F8, 0x00FC };
    for (int k = 0; k < 2; k++) memcpy(&image[addrs[k]], frame, 4);
    image[0x01FB] = 0x9C;
    image[0x01FF] = 0x9C;
    memcpy(frame_out, frame, 4);
    if (N_out) *N_out = (uint32_t)N;
    return 0;
}

// ===================== TAB 5: ce6803b_p32 =====================

int patch_6803(uint8_t *blob, size_t len, double reading, uint8_t frame_out[4]) {
    long raw = (long)lround(reading / 2.56);
    if (raw < 0 || raw > 0xFFFFFF) return -1;
    uint8_t data3[3] = { (uint8_t)((raw >> 16) & 0xFF), (uint8_t)((raw >> 8) & 0xFF), (uint8_t)(raw & 0xFF) };
    uint8_t crc = crc8_b5(data3, 3);
    uint8_t frame[4] = { data3[0], data3[1], data3[2], crc };
    static const uint8_t tail[4] = { 0x00, 0x00, 0x00, 0x69 };
    if (len >= 0x0200) {
        memcpy(&blob[0x00F8], frame, 4);
        memcpy(&blob[0x00FC], frame, 4);
        memcpy(&blob[0x01F8], tail, 4);
        memcpy(&blob[0x01FC], tail, 4);
    }
    memcpy(frame_out, frame, 4);
    return 0;
}

// ===================== TAB 6: 200_MT =====================

int encode_value_200mt(double value, uint8_t out[4]) {
    long long raw = (long long)llround(value * 100.0);
    if (raw < 0 || raw > 0xFFFFFFFFLL) return -1;
    out[0] = (uint8_t)(raw & 0xFF);
    out[1] = (uint8_t)((raw >> 8) & 0xFF);
    out[2] = (uint8_t)((raw >> 16) & 0xFF);
    out[3] = (uint8_t)((raw >> 24) & 0xFF);
    return 0;
}

double decode_value_200mt(const uint8_t data[4]) {
    uint32_t raw = (uint32_t)data[0] | ((uint32_t)data[1] << 8) |
                   ((uint32_t)data[2] << 16) | ((uint32_t)data[3] << 24);
    return (double)raw / 100.0;
}
