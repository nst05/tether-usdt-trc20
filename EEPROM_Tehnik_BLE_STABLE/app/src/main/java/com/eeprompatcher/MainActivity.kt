package com.eeprompatcher

import android.Manifest
import android.bluetooth.BluetoothAdapter
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.core.content.ContextCompat
import com.eeprompatcher.ui.App

class MainActivity : ComponentActivity() {

    private val vm: AppViewModel by viewModels()

    private val permissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) {
            // После выдачи разрешений сразу запускаем поиск: до этого UI мог
            // успеть открыть экран сканирования, но Android ещё блокировал BLE.
            vm.refreshBluetoothState()
            if (vm.ble.isBluetoothEnabled()) vm.ble.startScan()
        }

    // Системный диалог включения Bluetooth (ACTION_REQUEST_ENABLE).
    // Android сам показывает запрос «Разрешить включить Bluetooth?» — приложение
    // не может включить адаптер молча (запрещено с Android 13).
    private val enableBtLauncher =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) {
            vm.refreshBluetoothState()
        }

    // Слушаем системные изменения состояния адаптера (вкл/выкл из шторки и т.п.),
    // чтобы баннер в UI обновлялся сам.
    private val btStateReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if (intent?.action == BluetoothAdapter.ACTION_STATE_CHANGED) {
                vm.refreshBluetoothState()
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        requestBlePermissionsIfNeeded()

        vm.setEnableBluetoothRequester {
            enableBtLauncher.launch(Intent(BluetoothAdapter.ACTION_REQUEST_ENABLE))
        }

        // Открытие системного экрана настроек геолокации (включить нельзя
        // программно, но можно открыть нужный экран одним нажатием).
        vm.setOpenLocationSettings {
            startActivity(Intent(android.provider.Settings.ACTION_LOCATION_SOURCE_SETTINGS))
        }

        setContent {
            App(vm)
        }
    }

    override fun onStart() {
        super.onStart()
        registerReceiver(btStateReceiver, IntentFilter(BluetoothAdapter.ACTION_STATE_CHANGED))
        vm.refreshBluetoothState()
    }

    override fun onStop() {
        super.onStop()
        runCatching { unregisterReceiver(btStateReceiver) }
    }

    private fun requestBlePermissionsIfNeeded() {
        val needed = requiredPermissions().filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (needed.isNotEmpty()) {
            permissionLauncher.launch(needed.toTypedArray())
        }
    }

    private fun requiredPermissions(): List<String> {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            listOf(Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.BLUETOOTH_CONNECT)
        } else {
            listOf(Manifest.permission.ACCESS_FINE_LOCATION)
        }
    }
}
