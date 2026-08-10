package com.eeprompatcher.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.eeprompatcher.AppViewModel
import com.eeprompatcher.ui.theme.*

// Выбор режима EEPROM: 3F (AT24C1024) или ce6803 (24C04).
@Composable
fun ModeSelectScreen(vm: AppViewModel, onChosen: () -> Unit) {
    Column(
        Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.Center
    ) {
        Text("ВЫБОР РЕЖИМА", style = MeterTypography.headlineSmall, color = MeterGreen)
        Spacer(Modifier.height(8.dp))
        Text(
            "Показывается только выбранный режим. Сменить можно в настройках.",
            style = MeterTypography.bodySmall, color = MeterTextDim
        )
        Spacer(Modifier.height(24.dp))

        ModeCard("3F", "Режим 3F", "AT24C1024 · формат 3F") { vm.setSelectedMode(1); onChosen() }
        Spacer(Modifier.height(12.dp))
        ModeCard("CE", "Режим ce6803", "24C04 · формат ce6803b/p32") { vm.setSelectedMode(2); onChosen() }
    }
}

@Composable
private fun ModeCard(num: String, title: String, subtitle: String, onClick: () -> Unit) {
    MeterPanel(Modifier.clickable(onClick = onClick)) {
        Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
            Text(num, style = DisplayValueStyle.copy(color = MeterGreenDim))
            Spacer(Modifier.width(16.dp))
            Column {
                Text(title, style = MeterTypography.titleMedium, color = MeterText)
                Text(subtitle, style = MeterTypography.bodySmall, color = MeterTextDim)
            }
        }
    }
}
