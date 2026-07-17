// -*- coding: utf-8 -*-
#include "eeprom_i2c.h"
#include <Arduino.h>

#define EEPROM_WRITE_CYCLE_MS  6   // пауза на внутренний цикл записи страницы

// Используемый экземпляр I2C (задаётся из скетча; по умолчанию — Wire).
static TwoWire *s_wire = &Wire;

void eeprom_i2c_set_wire(TwoWire *wire) {
    if (wire) s_wire = wire;
}

// ---- низкоуровневые операции ----

// addrsize: 8 или 16 бит внутреннего адреса
static bool mem_write(uint8_t dev, uint16_t mem, uint8_t addrsize, const uint8_t *data, int len) {
    s_wire->beginTransmission(dev);
    if (addrsize == 16) s_wire->write((uint8_t)(mem >> 8));
    s_wire->write((uint8_t)(mem & 0xFF));
    for (int i = 0; i < len; i++) s_wire->write(data[i]);
    bool ok = (s_wire->endTransmission() == 0);
    delay(EEPROM_WRITE_CYCLE_MS);
    return ok;
}

static bool mem_read(uint8_t dev, uint16_t mem, uint8_t addrsize, uint8_t *data, int len) {
    s_wire->beginTransmission(dev);
    if (addrsize == 16) s_wire->write((uint8_t)(mem >> 8));
    s_wire->write((uint8_t)(mem & 0xFF));
    if (s_wire->endTransmission(false) != 0) return false;   // repeated start
    int got = s_wire->requestFrom((int)dev, len);
    if (got != len) return false;
    for (int i = 0; i < len; i++) data[i] = s_wire->read();
    return true;
}

// ================= 24C16 =================

bool eeprom_read_24c16(uint8_t *out, int total, eeprom_progress_fn cb) {
    const int page = 16;
    for (int addr = 0; addr < total; addr += page) {
        uint8_t dev = 0x50 | ((addr >> 8) & 0x07);
        uint8_t mem = addr & 0xFF;
        if (!mem_read(dev, mem, 8, &out[addr], page)) return false;
        if (cb) cb((int)((addr + page) * 100L / total));
    }
    return true;
}

bool eeprom_write_24c16(const uint8_t *in, int total, eeprom_progress_fn cb) {
    const int page = 16;
    for (int addr = 0; addr < total; addr += page) {
        uint8_t dev = 0x50 | ((addr >> 8) & 0x07);
        uint8_t mem = addr & 0xFF;
        if (!mem_write(dev, mem, 8, &in[addr], page)) return false;
        if (cb) cb((int)((addr + page) * 100L / total));
    }
    return true;
}

bool eeprom_read_bytes_24c16(uint16_t addr, uint8_t *out, int len) {
    uint8_t dev = 0x50 | ((addr >> 8) & 0x07);
    uint8_t mem = addr & 0xFF;
    return mem_read(dev, mem, 8, out, len);   // блок 4 байта не пересекает границу страницы
}

bool eeprom_write_bytes_24c16(uint16_t addr, const uint8_t *in, int len) {
    uint8_t dev = 0x50 | ((addr >> 8) & 0x07);
    uint8_t mem = addr & 0xFF;
    return mem_write(dev, mem, 8, in, len);
}

// ================= 24C04 =================

bool eeprom_read_24c04(uint8_t *out, int total, eeprom_progress_fn cb) {
    const int page = 16;
    for (int addr = 0; addr < total; addr += page) {
        uint8_t dev = 0x50 | ((addr >> 8) & 0x01);
        uint8_t mem = addr & 0xFF;
        if (!mem_read(dev, mem, 8, &out[addr], page)) return false;
        if (cb) cb((int)((addr + page) * 100L / total));
    }
    return true;
}

bool eeprom_write_24c04(const uint8_t *in, int total, eeprom_progress_fn cb) {
    const int page = 16;
    for (int addr = 0; addr < total; addr += page) {
        uint8_t dev = 0x50 | ((addr >> 8) & 0x01);
        uint8_t mem = addr & 0xFF;
        if (!mem_write(dev, mem, 8, &in[addr], page)) return false;
        if (cb) cb((int)((addr + page) * 100L / total));
    }
    return true;
}

// ================= AT24C1024 (16-битный адрес) =================

bool eeprom_read_at1024(uint8_t *out, int size, eeprom_progress_fn cb) {
    const int page = 32;
    for (int addr = 0; addr < size; addr += page) {
        int rd = (page < size - addr) ? page : (size - addr);
        if (!mem_read(0x50, (uint16_t)addr, 16, &out[addr], rd)) return false;
        if (cb) cb((int)((addr + rd) * 100L / size));
    }
    return true;
}

bool eeprom_write_at1024(const uint8_t *in, int size, eeprom_progress_fn cb) {
    const int page = 32;
    for (int addr = 0; addr < size; addr += page) {
        int wr = (page < size - addr) ? page : (size - addr);
        if (!mem_write(0x50, (uint16_t)addr, 16, &in[addr], wr)) return false;
        if (cb) cb((int)((addr + wr) * 100L / size));
    }
    return true;
}
