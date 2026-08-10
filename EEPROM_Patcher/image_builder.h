#pragma once
#include <Arduino.h>

// Формирование образа 512 байт по показанию (порт из Python 1:1).
// Заполняет buf[512]. Возвращает целое N/raw (для кода подтверждения).

// MODE_3F: N=floor(value/2.56), 3 байта LE + CRC-CCITT, адреса 0xF8/0xFC,
//          метки 0x9C @0x1FB/0x1FF.
// MODE_CE6803: raw=round(value/2.56), 3 байта BE + CRC8(0xB5),
//          адреса 0xF8/0xFC, хвост 00 00 00 69 @0x1F8/0x1FC.

uint32_t buildImage(float value, uint8_t *buf);   // buf[512]
