// -*- coding: utf-8 -*-
// Чтение/запись EEPROM по I2C для трёх схем адресации (перенос логики CH341-версии).
//  * 24C16   — 2048 байт, 8-битный адрес, блок (A10..A8) в адресе устройства 0x50..0x57
//  * 24C04   — 512 байт,  8-битный адрес, блок (A8) в адресе устройства 0x50..0x51
//  * AT24C1024 — 16-битный адрес, устройство 0x50 (используется первый блок)
#ifndef EEPROM_I2C_H
#define EEPROM_I2C_H

#include <stdint.h>
#include <stdbool.h>
#include <Wire.h>

typedef void (*eeprom_progress_fn)(int percent);

// Указать экземпляр I2C (по умолчанию — глобальный Wire). Вызывать до операций.
void eeprom_i2c_set_wire(TwoWire *wire);

// --- 24C16 (2048 байт) ---
bool eeprom_read_24c16(uint8_t *out, int total, eeprom_progress_fn cb);
bool eeprom_write_24c16(const uint8_t *in, int total, eeprom_progress_fn cb);
// произвольный небольшой блок (для вкладки 200_MT, адрес 0x0040)
bool eeprom_read_bytes_24c16(uint16_t addr, uint8_t *out, int len);
bool eeprom_write_bytes_24c16(uint16_t addr, const uint8_t *in, int len);

// --- 24C04 (512 байт) ---
bool eeprom_read_24c04(uint8_t *out, int total, eeprom_progress_fn cb);
bool eeprom_write_24c04(const uint8_t *in, int total, eeprom_progress_fn cb);

// --- AT24C1024 (16-битный адрес, первые size байт) ---
bool eeprom_read_at1024(uint8_t *out, int size, eeprom_progress_fn cb);
bool eeprom_write_at1024(const uint8_t *in, int size, eeprom_progress_fn cb);

#endif // EEPROM_I2C_H
