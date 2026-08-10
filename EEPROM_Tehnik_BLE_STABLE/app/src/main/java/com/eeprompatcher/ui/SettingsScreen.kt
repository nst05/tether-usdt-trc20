package com.eeprompatcher.ui

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.eeprompatcher.AppViewModel
import kotlinx.coroutines.launch

@Composable
fun SettingsScreen(vm: AppViewModel, onBack: () -> Unit) {
    var oldPin by remember { mutableStateOf("") }
    var newPin by remember { mutableStateOf("") }
    var newPin2 by remember { mutableStateOf("") }
    var status by remember { mutableStateOf<String?>(null) }
    var loading by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    Column(
        Modifier
            .fillMaxSize()
            .padding(16.dp)
    ) {
        // --- Выбор режима (фильтр) ---
        Text("Режим работы", style = MaterialTheme.typography.headlineSmall)
        Spacer(Modifier.height(8.dp))
        Text(
            "Показывается только выбранный режим.",
            style = MaterialTheme.typography.bodySmall
        )
        Spacer(Modifier.height(12.dp))

        val currentMode by vm.selectedMode.collectAsState()
        Row {
            listOf(1, 2, 3).forEach { m ->
                FilterChip(
                    selected = currentMode == m,
                    onClick = { vm.setSelectedMode(m) },
                    label = { Text("Режим $m") }
                )
                Spacer(Modifier.width(8.dp))
            }
        }

        Spacer(Modifier.height(24.dp))
        Divider()
        Spacer(Modifier.height(24.dp))

        // --- Смена PIN ---
        Text("Смена PIN этой платы", style = MaterialTheme.typography.headlineSmall)
        Spacer(Modifier.height(8.dp))
        Text(
            "PIN хранится в NVS-памяти конкретного ESP32 — задай уникальный для каждой платы.",
            style = MaterialTheme.typography.bodySmall
        )
        Spacer(Modifier.height(16.dp))

        OutlinedTextField(
            value = oldPin,
            onValueChange = { oldPin = it.filter { c -> c.isDigit() }.take(12) },
            label = { Text("Текущий PIN") },
            visualTransformation = PasswordVisualTransformation(),
            modifier = Modifier.fillMaxWidth()
        )
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(
            value = newPin,
            onValueChange = { newPin = it.filter { c -> c.isDigit() }.take(12) },
            label = { Text("Новый PIN (минимум 4 цифры)") },
            visualTransformation = PasswordVisualTransformation(),
            modifier = Modifier.fillMaxWidth()
        )
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(
            value = newPin2,
            onValueChange = { newPin2 = it.filter { c -> c.isDigit() }.take(12) },
            label = { Text("Повтори новый PIN") },
            visualTransformation = PasswordVisualTransformation(),
            modifier = Modifier.fillMaxWidth()
        )
        Spacer(Modifier.height(16.dp))

        Button(
            enabled = !loading && oldPin.isNotEmpty() && newPin.length >= 4,
            onClick = {
                if (newPin != newPin2) {
                    status = "Новые PIN не совпадают"
                    return@Button
                }
                loading = true
                status = null
                scope.launch {
                    try {
                        val resp = vm.ble.setPin(oldPin, newPin)
                        status = if (resp.optBoolean("ok", false)) {
                            "PIN успешно изменён"
                        } else {
                            "Ошибка: ${resp.optString("error", "неизвестно")}"
                        }
                    } catch (e: Exception) {
                        status = "Ошибка связи: ${e.message}"
                    }
                    loading = false
                }
            },
            modifier = Modifier.fillMaxWidth()
        ) { Text(if (loading) "Меняю..." else "Сменить PIN") }

        status?.let {
            Spacer(Modifier.height(12.dp))
            Text(it)
        }

        Spacer(Modifier.height(24.dp))
        TextButton(onClick = onBack) { Text("Назад") }
    }
}
