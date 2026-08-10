package com.eeprompatcher.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import com.eeprompatcher.AppViewModel
import com.eeprompatcher.ui.theme.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MainScreen(
    vm: AppViewModel,
    onOpenSettings: () -> Unit,
    onDisconnect: () -> Unit,
    onOpenAdmin: () -> Unit
) {
    val mode by vm.selectedMode.collectAsState()
    val title = when (mode) {
        1 -> "РЕЖИМ 3F"; 2 -> "РЕЖИМ CE6803"; else -> "EEPROM"
    }

    var tapCount by remember { mutableStateOf(0) }
    var lastTap by remember { mutableStateOf(0L) }

    Column(Modifier.fillMaxSize()) {
        TopAppBar(
            title = {
                Text(title, style = MeterTypography.titleMedium, color = MeterGreen,
                    modifier = Modifier.clickable {
                        val now = System.currentTimeMillis()
                        tapCount = if (now - lastTap < 2000) tapCount + 1 else 1
                        lastTap = now
                        if (tapCount >= 7) { tapCount = 0; onOpenAdmin() }
                    })
            },
            colors = TopAppBarDefaults.topAppBarColors(
                containerColor = MeterSurface,
                titleContentColor = MeterGreen
            ),
            actions = {
                IconButton(onClick = onOpenSettings) {
                    Icon(Icons.Filled.Settings, contentDescription = "Настройки", tint = MeterTextDim)
                }
                TextButton(onClick = onDisconnect) {
                    Text("Отключить", color = MeterTextDim)
                }
            }
        )
        Box(Modifier.weight(1f)) {
            // оба режима используют один экран EepromScreen — команда одна (write/read),
            // а конкретный формат (3F/ce6803) определяется прошивкой на плате
            EepromScreen(vm)
        }
    }
}
