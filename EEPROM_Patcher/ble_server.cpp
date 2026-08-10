#include "ble_server.h"
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include <Preferences.h>
#include <ArduinoJson.h>
#include "config.h"
#include "command_processor.h"

static Eeprom *g_ee = nullptr;
static BLEServer *pServer = nullptr;
static BLECharacteristic *pRespChar = nullptr;
static BLECharacteristic *pAuthChar = nullptr;
static BLECharacteristic *pCmdChar = nullptr;
static BLECharacteristic *pSetPinChar = nullptr;

static Preferences prefs;
static bool authenticated = false;
static int failCount = 0;
static uint32_t lockUntilMs = 0; // защита от подбора PIN: временная блокировка попыток
static volatile bool needRestartAdv = false;   // отложенный рестарт рекламы
static volatile uint32_t disconnectedAtMs = 0;  // когда произошёл дисконнект

static String getStoredPin() {
    prefs.begin("framauth", true); // read-only
    String pin = prefs.getString("pin", DEFAULT_PIN);
    prefs.end();
    return pin;
}

static void setStoredPin(const String &newPin) {
    prefs.begin("framauth", false);
    prefs.putString("pin", newPin);
    prefs.end();
}

static void sendResponse(JsonDocument &doc) {
    String out;
    serializeJson(doc, out);
    if (pRespChar) {
        pRespChar->setValue((uint8_t *)out.c_str(), out.length());
        pRespChar->notify();
    }
    Serial.println("[BLE] -> " + out);
}

static void sendSimple(bool ok, const char *event, const char *error = nullptr) {
    JsonDocument doc;
    doc["ok"] = ok;
    doc["event"] = event;
    if (error) doc["error"] = error;
    sendResponse(doc);
}

// ---------------- Server-level callbacks (подключение/отключение) ----------------
class ServerCallbacks : public BLEServerCallbacks {
    void onConnect(BLEServer *srv) override {
        authenticated = false;
        failCount = 0;
        needRestartAdv = false;   // клиент пришёл — отменяем отложенный рестарт
        Serial.println("[BLE] клиент подключился (не авторизован)");
    }
    void onDisconnect(BLEServer *srv) override {
        authenticated = false;
        // НЕ рестартим рекламу прямо здесь — стек ещё не освободил ресурсы.
        // Ставим флаг и время, реальный рестарт сделаем в loop с задержкой.
        needRestartAdv = true;
        disconnectedAtMs = millis();
        Serial.println("[BLE] клиент отключился, реклама будет перезапущена");
    }
};

// ---------------- AUTH: клиент присылает PIN ----------------
class AuthCallbacks : public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic *c) override {
        if (millis() < lockUntilMs) {
            sendSimple(false, "auth", "locked_try_later");
            return;
        }
        String pin = String(c->getValue().c_str());
        String stored = getStoredPin();

        if (pin.length() > 0 && pin == stored) {
            authenticated = true;
            failCount = 0;
            sendSimple(true, "auth");
            Serial.println("[BLE] PIN верный, доступ разрешён");
        } else {
            authenticated = false;
            failCount++;
            Serial.printf("[BLE] неверный PIN, попытка %d/%d\n", failCount, MAX_PIN_FAILS);
            if (failCount >= MAX_PIN_FAILS) {
                lockUntilMs = millis() + 30000UL; // блокируем попытки на 30 сек
                failCount = 0;
                sendSimple(false, "auth", "too_many_attempts_locked_30s");
            } else {
                sendSimple(false, "auth", "bad_pin");
            }
        }
    }
};

// ---------------- CMD: клиент шлёт JSON-команду (после авторизации) ----------------
class CmdCallbacks : public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic *c) override {
        if (!authenticated) {
            sendSimple(false, "cmd", "not_authenticated");
            return;
        }
        String raw = c->getValue();
        Serial.print("[CMD] получено: ");
        Serial.println(raw);
        JsonDocument in;
        DeserializationError err = deserializeJson(in, raw);
        JsonDocument out;
        if (err) {
            out["ok"] = false;
            out["error"] = "bad_json";
            Serial.println("[CMD] ошибка разбора JSON");
        } else {
            processCommand(*g_ee, in, out);
        }
        sendResponse(out);
    }
};

// ---------------- SETPIN: смена PIN (нужен текущий PIN + новый) ----------------
class SetPinCallbacks : public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic *c) override {
        if (!authenticated) {
            sendSimple(false, "setpin", "not_authenticated");
            return;
        }
        String raw = c->getValue();
        JsonDocument in;
        DeserializationError err = deserializeJson(in, raw);
        if (err) { sendSimple(false, "setpin", "bad_json"); return; }

        String oldPin = in["old"] | "";
        String newPin = in["new"] | "";
        String stored = getStoredPin();

        if (oldPin != stored) { sendSimple(false, "setpin", "bad_old_pin"); return; }
        if (newPin.length() < 4) { sendSimple(false, "setpin", "pin_too_short_min4"); return; }

        setStoredPin(newPin);
        sendSimple(true, "setpin");
        Serial.println("[BLE] PIN изменён");
    }
};

void bleServerBegin(Eeprom *eePtr) {
    g_ee = eePtr;

    // Уникальное имя платы в эфире BLE — берём кусок MAC, не зависит от PIN.
    char nameBuf[24];
    uint64_t mac = ESP.getEfuseMac();
    snprintf(nameBuf, sizeof(nameBuf), "EEPR-%04X", (uint16_t)(mac & 0xFFFF));

    BLEDevice::init(nameBuf);
    BLEDevice::setMTU(BLE_DESIRED_MTU);

    pServer = BLEDevice::createServer();
    pServer->setCallbacks(new ServerCallbacks());

    BLEService *pService = pServer->createService(BLE_SERVICE_UUID);

    pAuthChar = pService->createCharacteristic(
        BLE_AUTH_CHAR_UUID, BLECharacteristic::PROPERTY_WRITE);
    pAuthChar->setCallbacks(new AuthCallbacks());

    pCmdChar = pService->createCharacteristic(
        BLE_CMD_CHAR_UUID, BLECharacteristic::PROPERTY_WRITE);
    pCmdChar->setCallbacks(new CmdCallbacks());

    pRespChar = pService->createCharacteristic(
        BLE_RESP_CHAR_UUID, BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY);
    pRespChar->addDescriptor(new BLE2902());

    pSetPinChar = pService->createCharacteristic(
        BLE_SETPIN_CHAR_UUID, BLECharacteristic::PROPERTY_WRITE);
    pSetPinChar->setCallbacks(new SetPinCallbacks());

    pService->start();

    BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();
    pAdvertising->addServiceUUID(BLE_SERVICE_UUID);
    pAdvertising->setScanResponse(true);
    BLEDevice::startAdvertising();

    Serial.print("[BLE] сервер запущен, имя платы: ");
    Serial.println(nameBuf);
    Serial.println("[BLE] PIN по умолчанию: " DEFAULT_PIN " — смени через SETPIN после первого коннекта!");
}

// Вызывать из loop(). Перезапускает рекламу через 500мс после дисконнекта —
// даёт BLE-стеку время освободить ресурсы, иначе реклама не поднимается
// и плата пропадает из эфира ("то видит, то нет").
void bleServerLoop() {
    if (needRestartAdv && (millis() - disconnectedAtMs > 500)) {
        needRestartAdv = false;
        BLEDevice::startAdvertising();
        Serial.println("[BLE] реклама перезапущена, плата снова видна");
    }
}
