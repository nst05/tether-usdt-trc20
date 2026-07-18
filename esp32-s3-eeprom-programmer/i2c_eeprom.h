#pragma once
#include <Arduino.h>
#include <Wire.h>

enum class EepromType : uint8_t {
    C24C16,
    C24C04,
    AT24C1024
};

struct EepromProfile {
    const char* name;
    uint32_t capacity;
    uint16_t pageSize;
};

const EepromProfile& eepromProfile(EepromType type);

class I2cEeprom {
public:
    explicit I2cEeprom(TwoWire& wire);

    bool begin(int sda, int scl, uint32_t frequency);
    bool probe(EepromType type);
    bool read(EepromType type, uint32_t address, uint8_t* data, size_t length);
    bool write(EepromType type, uint32_t address, const uint8_t* data, size_t length);
    bool verify(EepromType type, uint32_t address, const uint8_t* data, size_t length);
    const String& lastError() const { return lastError_; }

private:
    TwoWire& wire_;
    String lastError_;

    bool mapAddress(EepromType type, uint32_t address,
                    uint8_t& device, uint16_t& memory, uint8_t& addrBytes,
                    uint32_t& blockRemaining) const;
    bool waitReady(uint8_t device, uint32_t timeoutMs = 30);
    void fail(const String& text) { lastError_ = text; }
};
