#pragma once
#include <Arduino.h>
#include "config.h"

// ---------------------------------------------------------------------
// I2C EEPROM драйвер для двух чипов:
//   MODE_3F    -> AT24C1024 (16-битный адрес, страница 32, dev 0x50)
//   MODE_CE6803-> 24C04 (8-битный адрес + выбор блока, страница 16)
// Образ 512 байт (0x200) в обоих случаях.
// ---------------------------------------------------------------------

#if defined(MODE_3F)
  static const uint16_t EE_SIZE = 0x200;   // работаем с первыми 512 байт
  static const uint8_t  EE_PAGE = 32;
  static const bool     EE_ADDR16 = true;  // 16-битный адрес
#elif defined(MODE_CE6803)
  static const uint16_t EE_SIZE = 0x200;
  static const uint8_t  EE_PAGE = 16;
  static const bool     EE_ADDR16 = false; // 8-битный адрес + блок в dev-адресе
#else
  #error "Выбери MODE_3F или MODE_CE6803 в config.h"
#endif

class Eeprom {
public:
    bool begin();
    // Чтение/запись всего образа 512 байт
    bool readImage(uint8_t *buf);
    bool writeImage(const uint8_t *buf);
    // Проверка отклика чипа
    bool probe();
};
