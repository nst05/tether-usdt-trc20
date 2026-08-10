package com.eeprompatcher.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.eeprompatcher.AppViewModel
import com.eeprompatcher.ui.theme.*
import kotlinx.coroutines.launch
import org.json.JSONObject

// Рабочий экран EEPROM: ввод показания счётчика, запись/чтение.
// Запись выполняется сразу, без кода подтверждения.
@Composable
fun EepromScreen(vm: AppViewModel) {
    val scope = rememberCoroutineScope()

    var reading by remember { mutableStateOf("") }        // показание счётчика
    var current by remember { mutableStateOf<Double?>(null) }
    var status by remember { mutableStateOf("Готов к работе") }
    var loading by remember { mutableStateOf(false) }

    fun parse(s: String) = s.replace(',', '.').toDoubleOrNull() ?: 0.0

    fun readFromChip() {
        loading = true
        scope.launch {
            try {
                val resp = vm.ble.sendCommand(JSONObject().put("cmd", "read"))
                if (resp.optBoolean("ok")) {
                    current = resp.optDouble("value")
                    status = "Прочитано с EEPROM"
                } else status = "Ошибка: ${resp.optString("error")}"
            } catch (e: Exception) { status = "Нет связи: ${e.message}" }
            loading = false
        }
    }

    fun writeToChip() {
        loading = true
        scope.launch {
            try {
                val cmd = JSONObject().put("cmd", "write").put("value", parse(reading))
                val resp = vm.ble.sendCommand(cmd)
                status = when {
                    resp.optBoolean("ok") -> "Записано и проверено"
                    resp.optString("error") == "verify_mismatch" -> "Запись не подтвердилась"
                    resp.optString("error") == "chip_all_FF" -> "Чип не отвечает (проверь подключение)"
                    else -> "Ошибка: ${resp.optString("error")}"
                }
                if (resp.optBoolean("ok")) readFromChip()
            } catch (e: Exception) { status = "Нет связи: ${e.message}" }
            loading = false
        }
    }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp)) {
        // Текущее показание
        MeterPanel {
            Text("ТЕКУЩЕЕ ПОКАЗАНИЕ", style = MeterTypography.labelLarge, color = MeterTextDim)
            Spacer(Modifier.height(10.dp))
            DisplayField("Показание", current?.let { "%.2f".format(it) } ?: "—")
            Spacer(Modifier.height(12.dp))
            MeterPrimaryButton(
                if (loading) "Чтение…" else "Прочитать с EEPROM",
                onClick = { readFromChip() }, enabled = !loading
            )
        }

        Spacer(Modifier.height(14.dp))

        // Запись нового показания
        MeterPanel {
            Text("НОВОЕ ПОКАЗАНИЕ", style = MeterTypography.labelLarge, color = MeterTextDim)
            Spacer(Modifier.height(12.dp))
            MeterInput("Показание счётчика", reading, { reading = it }, numeric = false)
            Spacer(Modifier.height(16.dp))
            MeterPrimaryButton(
                if (loading) "Запись…" else "Записать в EEPROM",
                onClick = { writeToChip() },
                enabled = !loading && reading.isNotEmpty()
            )
        }

        Spacer(Modifier.height(14.dp))
        MeterPanel { Text(status, style = MeterTypography.bodyMedium, color = MeterText) }
        Spacer(Modifier.height(24.dp))
    }
}
