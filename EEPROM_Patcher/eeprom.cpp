#include "eeprom.h"
#include <Wire.h>

bool Eeprom::begin() {
    Wire.begin(PIN_SDA, PIN_SCL, I2C_FREQ);
    Wire.setTimeOut(50);  // таймаут 50мс — чтобы I2C не подвешивал плату
    return true;
}

bool Eeprom::probe() {
    // Пробуем достучаться до dev 0x50
    Wire.beginTransmission(0x50);
    return (Wire.endTransmission() == 0);
}

#if defined(MODE_3F)
// --- AT24C1024: 16-битный адрес, dev 0x50 ---
bool Eeprom::writeImage(const uint8_t *buf) {
    for (uint16_t addr = 0; addr < EE_SIZE; addr += EE_PAGE) {
        Wire.beginTransmission(0x50);
        Wire.write((uint8_t)(addr >> 8));    // старший байт адреса
        Wire.write((uint8_t)(addr & 0xFF));  // младший байт адреса
        for (uint8_t i = 0; i < EE_PAGE && (addr + i) < EE_SIZE; i++)
            Wire.write(buf[addr + i]);
        if (Wire.endTransmission() != 0) return false;
        delay(6);  // пауза на запись страницы EEPROM
    }
    return true;
}

bool Eeprom::readImage(uint8_t *buf) {
    for (uint16_t addr = 0; addr < EE_SIZE; addr += EE_PAGE) {
        Wire.beginTransmission(0x50);
        Wire.write((uint8_t)(addr >> 8));
        Wire.write((uint8_t)(addr & 0xFF));
        if (Wire.endTransmission(false) != 0) return false; // repeated start
        uint8_t n = EE_PAGE;
        if (addr + n > EE_SIZE) n = EE_SIZE - addr;
        Wire.requestFrom((uint8_t)0x50, n);
        for (uint8_t i = 0; i < n; i++) {
            if (!Wire.available()) return false;
            buf[addr + i] = Wire.read();
        }
    }
    return true;
}

#elif defined(MODE_CE6803)
// --- 24C04: 8-битный адрес, старший бит адреса (A8) -> в dev-адрес (блок) ---
bool Eeprom::writeImage(const uint8_t *buf) {
    for (uint16_t addr = 0; addr < EE_SIZE; addr += EE_PAGE) {
        uint8_t block = (addr >> 8) & 0x01;      // A8 -> блок
        uint8_t dev = 0x50 | block;
        Wire.beginTransmission(dev);
        Wire.write((uint8_t)(addr & 0xFF));      // 8-битный адрес внутри блока
        for (uint8_t i = 0; i < EE_PAGE && (addr + i) < EE_SIZE; i++)
            Wire.write(buf[addr + i]);
        if (Wire.endTransmission() != 0) return false;
        delay(6);
    }
    return true;
}

bool Eeprom::readImage(uint8_t *buf) {
    for (uint16_t addr = 0; addr < EE_SIZE; addr += EE_PAGE) {
        uint8_t block = (addr >> 8) & 0x01;
        uint8_t dev = 0x50 | block;
        Wire.beginTransmission(dev);
        Wire.write((uint8_t)(addr & 0xFF));
        if (Wire.endTransmission(false) != 0) return false;
        uint8_t n = EE_PAGE;
        if (addr + n > EE_SIZE) n = EE_SIZE - addr;
        Wire.requestFrom(dev, n);
        for (uint8_t i = 0; i < n; i++) {
            if (!Wire.available()) return false;
            buf[addr + i] = Wire.read();
        }
    }
    return true;
}
#endif
