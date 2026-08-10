package com.eeprompatcher.ui

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.eeprompatcher.AppViewModel
import com.eeprompatcher.ui.theme.*
import kotlinx.coroutines.launch

@Composable
fun PinScreen(vm: AppViewModel, onAuthenticated: () -> Unit) {
    var pin by remember { mutableStateOf("") }
    var status by remember { mutableStateOf<String?>(null) }
    var loading by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    Column(
        Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.Center
    ) {
        Text("ДОСТУП К ПЛАТЕ", style = MeterTypography.headlineSmall, color = MeterGreen)
        Spacer(Modifier.height(8.dp))
        Text(
            "Введите PIN. По умолчанию на новой плате — 123456.",
            style = MeterTypography.bodySmall, color = MeterTextDim
        )
        Spacer(Modifier.height(24.dp))

        MeterPanel {
            Text("PIN-КОД", style = MeterTypography.labelLarge, color = MeterTextDim)
            Spacer(Modifier.height(8.dp))
            OutlinedTextField(
                value = pin,
                onValueChange = { pin = it.filter { c -> c.isDigit() }.take(12) },
                singleLine = true,
                textStyle = DisplayValueStyle.copy(color = MeterText),
                visualTransformation = PasswordVisualTransformation(),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = MeterGreen,
                    unfocusedBorderColor = MeterBorder,
                    focusedContainerColor = MeterDisplay,
                    unfocusedContainerColor = MeterDisplay,
                ),
                shape = androidx.compose.foundation.shape.RoundedCornerShape(10.dp),
                modifier = Modifier.fillMaxWidth()
            )
            Spacer(Modifier.height(16.dp))
            MeterPrimaryButton(
                if (loading) "Проверка…" else "Войти",
                enabled = !loading && pin.isNotEmpty(),
                onClick = {
                    loading = true; status = null
                    scope.launch {
                        try {
                            val resp = vm.ble.authenticate(pin)
                            if (resp.optBoolean("ok", false)) onAuthenticated()
                            else status = "Неверный PIN"
                        } catch (e: Exception) { status = "Ошибка: ${e.message}" }
                        loading = false
                    }
                }
            )
            status?.let {
                Spacer(Modifier.height(12.dp))
                Text(it, style = MeterTypography.bodySmall, color = MeterRed)
            }
        }
    }
}
