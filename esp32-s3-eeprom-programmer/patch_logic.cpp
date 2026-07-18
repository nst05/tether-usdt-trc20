#include "patch_logic.h"
#include <math.h>

uint16_t crc16Ibm(const uint8_t* data, size_t len) {
    uint16_t crc = 0xFFFF;
    for (size_t n = 0; n < len; ++n) {
        crc ^= data[n];
        for (uint8_t i = 0; i < 8; ++i)
            crc = (crc & 1) ? ((crc >> 1) ^ 0xA001) : (crc >> 1);
    }
    return crc;
}

uint8_t crc8B5(const uint8_t* data, size_t len) {
    uint8_t crc = 0xFF;
    for (size_t n = 0; n < len; ++n) {
        crc ^= data[n];
        for (uint8_t i = 0; i < 8; ++i)
            crc = (crc & 0x80) ? uint8_t((crc << 1) ^ 0xB5) : uint8_t(crc << 1);
    }
    return crc;
}

uint8_t crcLowCcittFalse3(const uint8_t data[3]) {
    uint16_t crc = 0xFFFF;
    for (uint8_t n = 0; n < 3; ++n) {
        crc ^= uint16_t(data[n]) << 8;
        for (uint8_t i = 0; i < 8; ++i)
            crc = (crc & 0x8000) ? uint16_t((crc << 1) ^ 0x1021) : uint16_t(crc << 1);
    }
    return uint8_t(crc & 0xFF);
}

static void encodeBcd6(uint32_t value, uint8_t out[3]) {
    value %= 1000000UL;
    char s[7];
    snprintf(s, sizeof(s), "%06lu", (unsigned long)value);
    for (uint8_t i = 0; i < 3; ++i)
        out[i] = uint8_t((s[i * 2] - '0') << 4) | uint8_t(s[i * 2 + 1] - '0');
}

bool patch201(uint8_t* image, size_t size, uint32_t integerPart, uint8_t fraction) {
    if (!image || size < 0x58 || fraction > 99) return false;

    uint8_t bcd[3], first6[6], frame[8];
    encodeBcd6(integerPart, bcd);
    first6[0] = bcd[0]; first6[1] = bcd[1]; first6[2] = bcd[2];
    first6[3] = 0xFF - bcd[0]; first6[4] = 0xFF - bcd[1]; first6[5] = 0xFF - bcd[2];
    memcpy(frame, first6, 6);
    uint16_t crc = crc16Ibm(first6, 6);
    frame[6] = crc & 0xFF; frame[7] = crc >> 8;
    memcpy(image + 0x30, frame, 8);
    memcpy(image + 0x50, frame, 8);

    const uint8_t fracBcd = uint8_t((fraction / 10) << 4) | (fraction % 10);
    uint8_t frac6[6] = {0x03, 0x00, fracBcd, 0xFC, 0xFF, uint8_t(0xFF - fracBcd)};
    memcpy(image + 0x20, frac6, 6);
    crc = crc16Ibm(frac6, 6);
    image[0x26] = crc & 0xFF; image[0x27] = crc >> 8;
    return true;
}

static bool makeBeFrame(double reading, uint8_t frame[4]) {
    const long long raw = llround(reading / 2.56);
    if (raw < 0 || raw > 0xFFFFFF) return false;
    frame[0] = (raw >> 16) & 0xFF;
    frame[1] = (raw >> 8) & 0xFF;
    frame[2] = raw & 0xFF;
    frame[3] = crc8B5(frame, 3);
    return true;
}

bool patchC101(uint8_t* image, size_t size, double reading) {
    if (!image || size < 0x200) return false;
    uint8_t f[4];
    if (!makeBeFrame(reading, f)) return false;
    memcpy(image + 0xF8, f, 4);
    memcpy(image + 0xFC, f, 4);
    return true;
}

static bool makeLeCcittFrame(double reading, bool useFloor, uint8_t frame[4]) {
    const double scaled = reading / 2.56;
    const long long raw = useFloor ? (long long)floor(scaled) : llround(scaled);
    if (raw < 0 || raw > 0xFFFFFF) return false;
    frame[0] = raw & 0xFF;
    frame[1] = (raw >> 8) & 0xFF;
    frame[2] = (raw >> 16) & 0xFF;
    frame[3] = crcLowCcittFalse3(frame);
    return true;
}

bool patch1F(uint8_t* image, size_t size, double reading) {
    if (!image || size < 0x200) return false;
    uint8_t f[4];
    if (!makeLeCcittFrame(reading, false, f)) return false;
    memcpy(image + 0xF8, f, 4);
    memcpy(image + 0xFC, f, 4);
    memset(image + 0x1F0, 0, 5);
    return true;
}

bool patch3F(uint8_t* image, size_t size, double reading) {
    if (!image || size < 0x200) return false;
    uint8_t f[4];
    if (!makeLeCcittFrame(reading, true, f)) return false;
    memcpy(image + 0xF8, f, 4);
    memcpy(image + 0xFC, f, 4);
    image[0x1FB] = 0x9C;
    image[0x1FF] = 0x9C;
    return true;
}

bool patchCE6803(uint8_t* image, size_t size, double reading) {
    if (!image || size < 0x200) return false;
    uint8_t f[4];
    if (!makeBeFrame(reading, f)) return false;
    memcpy(image + 0xF8, f, 4);
    memcpy(image + 0xFC, f, 4);
    const uint8_t tail[4] = {0, 0, 0, 0x69};
    memcpy(image + 0x1F8, tail, 4);
    memcpy(image + 0x1FC, tail, 4);
    return true;
}

bool make200MT(double integerInput, uint8_t fraction, uint8_t out[4], double& actualValue) {
    if (!out || integerInput < 0 || fraction < 1 || fraction > 99) return false;
    const uint32_t integerPart = uint32_t(integerInput);
    actualValue = double(integerPart) + double(fraction) / 100.0;
    const double scaled = actualValue * 100.0;
    if (scaled < 0 || scaled > 4294967295.0) return false;
    const uint32_t raw = uint32_t(llround(scaled));
    out[0] = raw & 0xFF;
    out[1] = (raw >> 8) & 0xFF;
    out[2] = (raw >> 16) & 0xFF;
    out[3] = (raw >> 24) & 0xFF;
    return true;
}
