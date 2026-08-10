package com.eeprompatcher.ui

import android.annotation.SuppressLint
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.eeprompatcher.AppViewModel
import com.eeprompatcher.ui.theme.*
import kotlinx.coroutines.launch

@SuppressLint("MissingPermission")
@Composable
fun ScanScreen(vm: AppViewModel) {
    val devices by vm.ble.devices.collectAsState()
    val error by vm.ble.lastError.collectAsState()
    val btEnabled by vm.bluetoothEnabled.collectAsState()
    val locationNeeded by vm.locationNeeded.collectAsState()
    val scanning by vm.ble.isScanning.collectAsState()
    val scope = rememberCoroutineScope()
    var connecting by remember { mutableStateOf(false) }

    // A scan is started automatically whenever this screen is opened. The BLE
    // manager replaces an existing scan safely and stops it after 12 seconds.
    LaunchedEffect(btEnabled, locationNeeded) {
        if (btEnabled && !locationNeeded) vm.ble.startScan()
    }
    DisposableEffect(Unit) {
        onDispose { vm.ble.stopScan() }
    }

    Column(Modifier.fillMaxSize().padding(20.dp)) {
        Spacer(Modifier.height(8.dp))
        // Заголовок — «шильдик прибора»
        Text("EEPROM PATCHER EN", style = MeterTypography.headlineSmall, color = MeterGreen)
        Text(
            "Калибровочный терминал · BLE",
            style = MeterTypography.bodySmall,
            color = MeterTextDim
        )
        Spacer(Modifier.height(20.dp))

        if (!btEnabled) {
            MeterPanel {
                Text("BLUETOOTH ВЫКЛЮЧЕН", style = MeterTypography.labelLarge, color = MeterAmber)
                Spacer(Modifier.height(6.dp))
                Text(
                    "Включите Bluetooth, чтобы найти платы.",
                    style = MeterTypography.bodySmall, color = MeterTextDim
                )
                Spacer(Modifier.height(12.dp))
                MeterPrimaryButton("Включить Bluetooth", onClick = { vm.requestEnableBluetooth() })
            }
            Spacer(Modifier.height(14.dp))
        }

        if (locationNeeded) {
            MeterPanel {
                Text("НУЖНА ГЕОЛОКАЦИЯ", style = MeterTypography.labelLarge, color = MeterAmber)
                Spacer(Modifier.height(6.dp))
                Text(
                    "На этой версии Android поиск BLE-устройств не работает без включённой службы геолокации. Приложение её не использует — это требование системы.",
                    style = MeterTypography.bodySmall, color = MeterTextDim
                )
                Spacer(Modifier.height(12.dp))
                MeterPrimaryButton("Открыть настройки геолокации", onClick = { vm.requestOpenLocationSettings() })
            }
            Spacer(Modifier.height(14.dp))
        }

        MeterPrimaryButton(
            if (scanning) "Обновить поиск" else "Искать платы",
            onClick = { vm.ble.startScan() },
            enabled = btEnabled && !locationNeeded
        )
        Spacer(Modifier.height(16.dp))

        if (scanning) {
            Text(
                "Идёт поиск платы…",
                style = MeterTypography.bodySmall,
                color = MeterTextDim
            )
            Spacer(Modifier.height(8.dp))
        }

        error?.let {
            Text(it, style = MeterTypography.bodySmall, color = MeterRed)
            Spacer(Modifier.height(8.dp))
        }

        if (devices.isEmpty()) {
            Spacer(Modifier.height(40.dp))
            Text(
                "Платы не найдены.\nНажмите «Искать платы» и подождите.",
                style = MeterTypography.bodyMedium,
                color = MeterTextDim,
                modifier = Modifier.align(Alignment.CenterHorizontally)
            )
        }

        LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            items(devices) { device ->
                MeterPanel {
                    Row(
                        Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column {
                            Text(
                                device.name ?: "Без имени",
                                style = MeterTypography.titleMedium.copy(fontFamily = MonoFamily),
                                color = MeterGreen
                            )
                            Text(device.address, style = MeterTypography.bodySmall, color = MeterTextDim)
                        }
                        Button(
                            enabled = !connecting,
                            onClick = {
                                connecting = true
                                scope.launch {
                                    val connected = vm.ble.connect(device)
                                    connecting = false
                                    if (!connected) vm.ble.startScan()
                                }
                            },
                            shape = androidx.compose.foundation.shape.RoundedCornerShape(10.dp),
                            colors = ButtonDefaults.buttonColors(
                                containerColor = MeterGreen, contentColor = MeterBg
                            )
                        ) { Text(if (connecting) "…" else "Связать") }
                    }
                }
            }
        }
    }
}
