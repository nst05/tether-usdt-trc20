package com.eeprompatcher

import android.app.Application
import android.content.Context
import androidx.lifecycle.AndroidViewModel
import com.eeprompatcher.ble.BleManager
import com.eeprompatcher.remote.RemoteTechnician
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import org.json.JSONObject

class AppViewModel(app: Application) : AndroidViewModel(app) {
    val ble = BleManager(app.applicationContext)
    val remote = RemoteTechnician()

    private val prefs = app.getSharedPreferences("fram_prefs", Context.MODE_PRIVATE)

    // Выбранный режим (1/2/3). 0 = ещё не выбран (покажем экран выбора).
    private val _selectedMode = MutableStateFlow(prefs.getInt("selected_mode", 0))
    val selectedMode: StateFlow<Int> = _selectedMode

    fun setSelectedMode(mode: Int) {
        prefs.edit().putInt("selected_mode", mode).apply()
        _selectedMode.value = mode
    }

    fun isModeChosen(): Boolean = _selectedMode.value in 1..2

    // ---- Рабочий режим приложения: MANUAL (ручной) / REMOTE (удалённый) ----
    // Задаётся администратором в скрытой админ-панели. По умолчанию ручной.
    private val _workMode = MutableStateFlow(prefs.getString("work_mode", "MANUAL") ?: "MANUAL")
    val workMode: StateFlow<String> = _workMode

    fun setWorkMode(mode: String) {
        prefs.edit().putString("work_mode", mode).apply()
        _workMode.value = mode
    }

    // Код доступа к скрытой админ-панели (переключение режимов).
    // ВНИМАНИЕ: замени на свой. Знать должен только администратор.
    private val adminAccessCode = "324727"

    fun checkAdminCode(code: String): Boolean = code == adminAccessCode

    // ---- Удалённый режим: команда из облака → выполнение на плате по BLE ----
    fun startRemote() {
        // колбэк: получили команду из Firebase → шлём на плату по BLE → ответ
        remote.onCommand = { json ->
            ble.sendCommand(json)   // та же BLE-логика, что для кнопок
        }
        remote.start(_selectedMode.value.let { if (it in 1..2) it else 1 })
    }

    fun stopRemote() {
        remote.stop()
    }

    private val _bluetoothEnabled = MutableStateFlow(ble.isBluetoothEnabled())
    val bluetoothEnabled: StateFlow<Boolean> = _bluetoothEnabled

    // true — если нужна геолокация для скана, но она выключена (Android ≤11)
    private val _locationNeeded = MutableStateFlow(ble.isLocationRequiredAndOff())
    val locationNeeded: StateFlow<Boolean> = _locationNeeded

    // Открытие системного экрана настроек геолокации задаётся из MainActivity.
    private var openLocationSettings: (() -> Unit)? = null

    fun setOpenLocationSettings(fn: () -> Unit) { openLocationSettings = fn }
    fun requestOpenLocationSettings() { openLocationSettings?.invoke() }

    private var enableBluetoothRequester: (() -> Unit)? = null

    fun setEnableBluetoothRequester(requester: () -> Unit) {
        enableBluetoothRequester = requester
    }

    fun requestEnableBluetooth() {
        enableBluetoothRequester?.invoke()
    }

    fun refreshBluetoothState() {
        _bluetoothEnabled.value = ble.isBluetoothEnabled()
        _locationNeeded.value = ble.isLocationRequiredAndOff()
    }
}
