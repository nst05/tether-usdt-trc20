#include "image_builder.h"
#include "config.h"
#include <math.h>

#if defined(MODE_3F)
// --- new_3F: AT24C1024 ---
static uint8_t crc_ccitt_3F(uint8_t d0, uint8_t d1, uint8_t d2) {
    uint16_t crc = 0xFFFF;
    uint8_t bytes[3] = {d0, d1, d2};
    for (int k = 0; k < 3; k++) {
        crc ^= (uint16_t)bytes[k] << 8;
        for (int i = 0; i < 8; i++) {
            if (crc & 0x8000) crc = (crc << 1) ^ 0x1021;
            else crc <<= 1;
        }
    }
    return (uint8_t)(crc & 0xFF);
}

uint32_t buildImage(float value, uint8_t *buf) {
    uint32_t N = (uint32_t)floor(value / 2.56);
    uint8_t d0 = N & 0xFF, d1 = (N >> 8) & 0xFF, d2 = (N >> 16) & 0xFF;
    uint8_t crc = crc_ccitt_3F(d0, d1, d2);

    for (int i = 0; i < 512; i++) buf[i] = 0x00;

    // адреса данных 0x00F8 и 0x00FC
    const uint16_t addrs[2] = {0x00F8, 0x00FC};
    for (int a = 0; a < 2; a++) {
        buf[addrs[a] + 0] = d0;
        buf[addrs[a] + 1] = d1;
        buf[addrs[a] + 2] = d2;
        buf[addrs[a] + 3] = crc;
    }
    // метки 0x9C
    buf[0x01FB] = 0x9C;
    buf[0x01FF] = 0x9C;
    return N;
}

#elif defined(MODE_CE6803)
// --- ce6803b: 24C04 ---
static uint8_t crc8_b5(const uint8_t *data, int len) {
    uint8_t crc = 0xFF;
    for (int j = 0; j < len; j++) {
        crc ^= data[j];
        for (int i = 0; i < 8; i++) {
            if (crc & 0x80) crc = (crc << 1) ^ 0xB5;
            else crc <<= 1;
        }
    }
    return crc;
}

uint32_t buildImage(float value, uint8_t *buf) {
    uint32_t raw = (uint32_t)lround(value / 2.56);
    uint8_t data3[3] = {
        (uint8_t)((raw >> 16) & 0xFF),
        (uint8_t)((raw >> 8) & 0xFF),
        (uint8_t)(raw & 0xFF)
    };
    uint8_t crc = crc8_b5(data3, 3);

    for (int i = 0; i < 512; i++) buf[i] = 0x00;

    // хвост 00 00 00 69 @0x1F8/0x1FC
    const uint16_t tail[2] = {0x01F8, 0x01FC};
    for (int a = 0; a < 2; a++) {
        buf[tail[a] + 0] = 0x00;
        buf[tail[a] + 1] = 0x00;
        buf[tail[a] + 2] = 0x00;
        buf[tail[a] + 3] = 0x69;
    }
    // данные 0x00F8 и 0x00FC
    const uint16_t addrs[2] = {0x00F8, 0x00FC};
    for (int a = 0; a < 2; a++) {
        buf[addrs[a] + 0] = data3[0];
        buf[addrs[a] + 1] = data3[1];
        buf[addrs[a] + 2] = data3[2];
        buf[addrs[a] + 3] = crc;
    }
    return raw;
}
#endif
