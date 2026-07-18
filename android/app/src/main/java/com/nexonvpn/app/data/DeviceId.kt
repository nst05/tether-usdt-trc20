package com.nexonvpn.app.data

import android.content.Context
import android.os.Build
import java.security.MessageDigest
import java.util.UUID

/**
 * Стабильный идентификатор устройства (HWID) для автономной регистрации и
 * лимита устройств на сервере (заголовок X-HWID).
 *
 * Основа — случайный UUID, сгенерированный при первом запуске и сохранённый в
 * DataStore (переживает обновления приложения, сбрасывается при переустановке).
 * Возвращаем SHA-256 хэш в hex — сервер хранит именно строку HWID.
 */
object DeviceId {

    /** Человекочитаемое имя устройства для метаданных (X-Forwarded-Device-Model). */
    val model: String get() = "${Build.MANUFACTURER} ${Build.MODEL}".trim()

    val osVersion: String get() = Build.VERSION.RELEASE ?: ""

    /** Хэшируем сырой seed в стабильный HWID. */
    fun hwidFromSeed(seed: String): String {
        val digest = MessageDigest.getInstance("SHA-256").digest(seed.toByteArray())
        return digest.joinToString("") { "%02x".format(it) }
    }

    fun newSeed(context: Context): String {
        // Комбинируем случайный UUID с ANDROID_ID для устойчивости.
        val androidId = try {
            android.provider.Settings.Secure.getString(
                context.contentResolver,
                android.provider.Settings.Secure.ANDROID_ID,
            ) ?: ""
        } catch (_: Throwable) { "" }
        return UUID.randomUUID().toString() + ":" + androidId
    }
}
