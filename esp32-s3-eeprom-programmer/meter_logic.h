// -*- coding: utf-8 -*-
// Чистая логика формирования кадров/патчей для 6 программаторов.
// Портировано 1:1 из all_tabs_ch341_merged_6tabs.py.
// Здесь НЕТ зависимостей от Arduino / I2C — только вычисления над буферами,
// чтобы этот файл можно было компилировать и тестировать на ПК (gcc).
#ifndef METER_LOGIC_H
#define METER_LOGIC_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

// ---- CRC ----
uint16_t crc16_ibm(const uint8_t *data, size_t len);   // reflected, poly 0xA001, init 0xFFFF
uint8_t  crc8_b5(const uint8_t *data, size_t len);      // poly 0xB5, init 0xFF (сдвиг влево)
uint8_t  crc_low_ccitt_false(uint8_t d0, uint8_t d1, uint8_t d2); // CCITT-FALSE, младший байт

// ---- Вспомогательное ----
void to_bcd_bytes_201(uint32_t value, uint8_t out[3]);  // целое -> 6 цифр -> 3 BCD-байта
uint8_t hund_to_bcd(uint8_t hund);                      // 00..99 -> BCD

// ---- TAB 1: 201_drob_random (24C16, буфер 2048) ----
// int_value — целая часть, frac_hund — сотые (0..99). Патчит eeprom на месте.
void patch_201(uint8_t *eeprom, size_t len, uint32_t int_value, uint8_t frac_hund);
// Сравнение блоков целой части: 0x30..0x35 и 0x50..0x55
int  blocks_match_201(const uint8_t *golden, const uint8_t *actual, size_t len);

// ---- TAB 2: c101 (24C04, буфер 512) ----
// Возвращает 0 при успехе, -1 если raw вне 24 бит. frame[4] заполняется.
int  patch_c101(uint8_t *blob, size_t len, double reading, uint8_t frame_out[4]);

// ---- TAB 3: new_1F (AT24C1024, патч первых 0x200) ----
// round(value/2.56). Возвращает 0/-1. Заполняет frame[4] и N.
int  patch_1F(uint8_t *image, size_t len, double value, uint8_t frame_out[4], uint32_t *N_out);

// ---- TAB 4: new_3F (AT24C1024, патч первых 0x200) ----
// floor(value/2.56). 0x9C по 0x1FB и 0x1FF.
int  patch_3F(uint8_t *image, size_t len, double value, uint8_t frame_out[4], uint32_t *N_out);

// ---- TAB 5: ce6803b_p32 (24C04, буфер 512) ----
int  patch_6803(uint8_t *blob, size_t len, double reading, uint8_t frame_out[4]);

// ---- TAB 6: 200_MT (24C16) ----
// value*100 -> 4 байта little-endian. Возвращает 0/-1 (переполнение).
int  encode_value_200mt(double value, uint8_t out[4]);
double decode_value_200mt(const uint8_t data[4]);

#ifdef __cplusplus
}
#endif

#endif // METER_LOGIC_H
