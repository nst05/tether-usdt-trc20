package com.eeprompatcher.ui

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.eeprompatcher.AppViewModel
import com.eeprompatcher.ui.theme.*

// Скрытая админ-панель. Открывается 7 тапами по заголовку + кодом доступа.
// Здесь администратор выбирает рабочий режим (ручной/удалённый).
@Composable
fun AdminScreen(vm: AppViewModel, onBack: () -> Unit) {
    var unlocked by remember { mutableStateOf(false) }
    var code by remember { mutableStateOf("") }
    var err by remember { mutableStateOf<String?>(null) }
    val workMode by vm.workMode.collectAsState()

    Column(
        Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.Center
    ) {
        if (!unlocked) {
            // --- Ввод кода доступа ---
            Text("КОД ДОСТУПА", style = MeterTypography.headlineSmall, color = MeterGreen)
            Spacer(Modifier.height(16.dp))
            MeterPanel {
                OutlinedTextField(
                    value = code,
                    onValueChange = { code = it.filter { c -> c.isDigit() }.take(8) },
                    singleLine = true,
                    textStyle = DisplayValueStyle.copy(color = MeterText),
                    visualTransformation = PasswordVisualTransformation(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = MeterGreen,
                        unfocusedBorderColor = MeterBorder,
                        focusedContainerColor = MeterDisplay,
                        unfocusedContainerColor = MeterDisplay,
                    ),
                    shape = androidx.compose.foundation.shape.RoundedCornerShape(10.dp),
                    modifier = Modifier.fillMaxWidth()
                )
                Spacer(Modifier.height(14.dp))
                MeterPrimaryButton("Войти", onClick = {
                    if (vm.checkAdminCode(code)) { unlocked = true; err = null }
                    else err = "Неверный код"
                })
                err?.let {
                    Spacer(Modifier.height(10.dp))
                    Text(it, style = MeterTypography.bodySmall, color = MeterRed)
                }
            }
            Spacer(Modifier.height(16.dp))
            TextButton(onClick = onBack) { Text("Отмена", color = MeterTextDim) }
        } else {
            // --- Админ-панель ---
            Text("АДМИНИСТРИРОВАНИЕ", style = MeterTypography.headlineSmall, color = MeterGreen)
            Spacer(Modifier.height(8.dp))
            Text("Режим работы, который увидит техник:",
                style = MeterTypography.bodySmall, color = MeterTextDim)
            Spacer(Modifier.height(16.dp))

            MeterPanel {
                ModeRow("Ручной режим",
                    "Техник пишет показания сам",
                    selected = workMode == "MANUAL",
                    onClick = { vm.setWorkMode("MANUAL") })
                Spacer(Modifier.height(10.dp))
                ModeRow("Удалённый режим",
                    "Команды приходят от оператора",
                    selected = workMode == "REMOTE",
                    onClick = { vm.setWorkMode("REMOTE") })
            }

            Spacer(Modifier.height(24.dp))
            MeterPrimaryButton("Готово", onClick = onBack)
        }
    }
}

@Composable
private fun ModeRow(title: String, subtitle: String, selected: Boolean, onClick: () -> Unit) {
    Row(
        Modifier.fillMaxWidth(),
        verticalAlignment = androidx.compose.ui.Alignment.CenterVertically
    ) {
        RadioButton(
            selected = selected,
            onClick = onClick,
            colors = RadioButtonDefaults.colors(selectedColor = MeterGreen, unselectedColor = MeterTextDim)
        )
        Spacer(Modifier.width(8.dp))
        Column {
            Text(title, style = MeterTypography.titleMedium, color = MeterText)
            Text(subtitle, style = MeterTypography.bodySmall, color = MeterTextDim)
        }
    }
}
