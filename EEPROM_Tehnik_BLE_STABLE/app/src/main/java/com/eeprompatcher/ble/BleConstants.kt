package com.eeprompatcher.ble

// Должны 1:1 совпадать с include/config.h в прошивке ESP32
object BleConstants {
    const val SERVICE_UUID = "b2f9a7d0-3c4e-5f6a-8b1c-9d2e4f6a8c10"
    const val AUTH_CHAR_UUID = "b2f9a7d1-3c4e-5f6a-8b1c-9d2e4f6a8c10"
    const val CMD_CHAR_UUID = "b2f9a7d2-3c4e-5f6a-8b1c-9d2e4f6a8c10"
    const val RESP_CHAR_UUID = "b2f9a7d3-3c4e-5f6a-8b1c-9d2e4f6a8c10"
    const val SETPIN_CHAR_UUID = "b2f9a7d4-3c4e-5f6a-8b1c-9d2e4f6a8c10"

    // Стандартный дескриптор Client Characteristic Configuration (включение notify)
    const val CCCD_UUID = "00002902-0000-1000-8000-00805f9b34fb"

    const val DESIRED_MTU = 247
    const val REQUEST_TIMEOUT_MS = 5000L
}

enum class ConnectionState {
    DISCONNECTED, CONNECTING, DISCOVERING, CONNECTED, AUTHENTICATED
}
