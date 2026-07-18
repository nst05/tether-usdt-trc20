package com.nexonvpn.app.data

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

private val Context.dataStore by preferencesDataStore(name = "nexon_prefs")

/**
 * Персистентное хранилище состояния клиента: seed устройства, UUID подписки,
 * последний выбранный сервер.
 */
class PrefsStore(private val context: Context) {

    private object Keys {
        val DEVICE_SEED = stringPreferencesKey("device_seed")
        val SUB_UUID = stringPreferencesKey("sub_uuid")
        val SELECTED_SERVER = stringPreferencesKey("selected_server")
    }

    /** Возвращает существующий seed устройства или создаёт и сохраняет новый. */
    suspend fun deviceSeed(): String {
        val existing = context.dataStore.data.map { it[Keys.DEVICE_SEED] }.first()
        if (!existing.isNullOrBlank()) return existing
        val seed = DeviceId.newSeed(context)
        context.dataStore.edit { it[Keys.DEVICE_SEED] = seed }
        return seed
    }

    val subUuid: Flow<String?> = context.dataStore.data.map { it[Keys.SUB_UUID] }

    suspend fun subUuidOnce(): String? = context.dataStore.data.map { it[Keys.SUB_UUID] }.first()

    suspend fun setSubUuid(uuid: String) {
        context.dataStore.edit { it[Keys.SUB_UUID] = uuid }
    }

    val selectedServer: Flow<String?> = context.dataStore.data.map { it[Keys.SELECTED_SERVER] }

    suspend fun setSelectedServer(tag: String) {
        context.dataStore.edit { it[Keys.SELECTED_SERVER] = tag }
    }
}
