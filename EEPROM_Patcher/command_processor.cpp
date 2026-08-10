#include "command_processor.h"
#include "image_builder.h"
#include "config.h"
#include "mcu_reset.h"
#include <string.h>
#include <math.h>

// Извлечь показание (value) из образа при чтении — обратное преобразование.
// Читаем 3 байта данных с 0x00F8 и восстанавливаем значение.
static float decodeValue(const uint8_t *buf) {
#if defined(MODE_3F)
    // 3F: 3 байта LE, N, value = N * 2.56
    uint32_t N = buf[0x00F8] | (buf[0x00F9] << 8) | (buf[0x00FA] << 16);
    return N * 2.56f;
#elif defined(MODE_CE6803)
    // ce6803: 3 байта BE, raw, value = raw * 2.56
    uint32_t raw = ((uint32_t)buf[0x00F8] << 16) | (buf[0x00F9] << 8) | buf[0x00FA];
    return raw * 2.56f;
#endif
}

static void doWrite(Eeprom &ee, const JsonDocument &in, JsonDocument &out) {
    float value = in["value"] | 0.0f;

    uint8_t img[512];
    uint32_t intVal = buildImage(value, img);  // формируем образ, получаем N/raw

    // пишем образ
    mcuHoldReset();
    bool wOk = ee.writeImage(img);
    if (!wOk) { mcuRelease(); out["ok"] = false; out["error"] = "write_failed"; return; }

    // верификация обратным чтением (ещё под reset)
    uint8_t rb[512];
    bool rOk = ee.readImage(rb);
    mcuRelease();
    if (!rOk) { out["ok"] = false; out["error"] = "readback_failed"; return; }

    // проверка на нули/FF (чип не подключён)
    bool allFF = true, all00 = true;
    for (int i = 0; i < 512; i++) { if (rb[i] != 0xFF) allFF = false; if (rb[i] != 0x00) all00 = false; }
    if (allFF) { out["ok"] = false; out["error"] = "chip_all_FF"; return; }

    // сравнение ключевых адресов данных (0xF8, 0xFC по 4 байта)
    bool match = true;
    const uint16_t chk[2] = {0x00F8, 0x00FC};
    for (int a = 0; a < 2; a++)
        for (int i = 0; i < 4; i++)
            if (rb[chk[a] + i] != img[chk[a] + i]) match = false;

    if (match) {
        mcuResetAfterWrite();   // повторный сброс на 2 сек — счётчик перечитает EEPROM
        out["ok"] = true;
        out["value"] = value;
        out["intVal"] = intVal;
    } else {
        out["ok"] = false;
        out["error"] = "verify_mismatch";
    }
}

static void doRead(Eeprom &ee, JsonDocument &out) {
    uint8_t rb[512];
    mcuHoldReset();
    bool rdOk = ee.readImage(rb);
    mcuRelease();
    if (!rdOk) { out["ok"] = false; out["error"] = "read_failed"; return; }
    bool allFF = true, all00 = true;
    for (int i = 0; i < 512; i++) { if (rb[i] != 0xFF) allFF = false; if (rb[i] != 0x00) all00 = false; }
    if (allFF) { out["ok"] = false; out["error"] = "chip_all_FF"; return; }
    out["ok"] = true;
    out["value"] = decodeValue(rb);
}

static void doStatus(JsonDocument &out) {
#if defined(MODE_3F)
    out["mode"] = "3F";
    out["chip"] = "AT24C1024";
#elif defined(MODE_CE6803)
    out["mode"] = "CE6803";
    out["chip"] = "24C04";
#endif
    out["ok"] = true;
}

void processCommand(Eeprom &ee, const JsonDocument &in, JsonDocument &out) {
    const char *cmd = in["cmd"] | "";
    if (strcmp(cmd, "write") == 0)              doWrite(ee, in, out);
    else if (strcmp(cmd, "read") == 0)          doRead(ee, out);
    else if (strcmp(cmd, "status") == 0)        doStatus(out);
    else if (strcmp(cmd, "ping") == 0)          out["ok"] = true;
    else { out["ok"] = false; out["error"] = "unknown_cmd"; }
}
