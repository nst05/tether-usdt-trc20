#pragma once

// =====================================================================
//  ВЫБОР РЕЖИМА (микросхема + формат данных счётчика)
//  Раскомментируй ОДИН режим под свою задачу.
// =====================================================================
#define MODE_3F         // new_3F — AT24C1024, формат 3F
//#define MODE_CE6803   // ce6803b — 24C04, формат ce6803b/p32
// =====================================================================

// ---------- I2C пины (ESP32) ----------
// Стандартные пины I2C ESP32. Если EEPROM подключена к другим — поменяй.
#define PIN_SDA 21
#define PIN_SCL 22
#define I2C_FREQ 100000   // 100 кГц — надёжно для EEPROM

// --- RESET процессора счётчика (in-circuit) ---
// Процессор счётчика сидит на той же I2C-шине. На время чтения/записи
// держим его в сбросе, чтобы не мешал обмену. В покое — Hi-Z (не трогаем).
// Пин идёт на вывод RESET процессора счётчика (не на память!).
#define PIN_MCU_RESET 25
#define RESET_ASSERT_SETTLE_MS 300   // держим сброс перед операцией (мс)
#define RESET_AFTER_WRITE_MS 2000    // RST -> GND после успешной записи EEPROM (мс)
#define RESET_IDLE_MS 200            // пауза после отпускания (процессор стартует)
// RESET_RELEASE_HIZ: 1 = отпускать в Hi-Z (если вход RESET подтянут в приборе),
//   0 = активно держать HIGH. Если прибор не оживает — поменяй значение.
#define RESET_RELEASE_HIZ 1

// ---------- BLE ----------
#define BLE_SERVICE_UUID     "b2f9a7d0-3c4e-5f6a-8b1c-9d2e4f6a8c10"
#define BLE_AUTH_CHAR_UUID   "b2f9a7d1-3c4e-5f6a-8b1c-9d2e4f6a8c10"
#define BLE_CMD_CHAR_UUID    "b2f9a7d2-3c4e-5f6a-8b1c-9d2e4f6a8c10"
#define BLE_RESP_CHAR_UUID   "b2f9a7d3-3c4e-5f6a-8b1c-9d2e4f6a8c10"
#define BLE_SETPIN_CHAR_UUID "b2f9a7d4-3c4e-5f6a-8b1c-9d2e4f6a8c10"

#define DEFAULT_PIN "123456"
#define MAX_PIN_FAILS 5
#define BLE_DESIRED_MTU 247
