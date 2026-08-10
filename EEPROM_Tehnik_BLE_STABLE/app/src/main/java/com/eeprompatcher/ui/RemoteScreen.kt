package com.eeprompatcher.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.eeprompatcher.AppViewModel
import com.eeprompatcher.ui.theme.*

// Экран удалённого режима у ТЕХНИКА. Показывает код сессии, который техник
// называет оператору. Оператор по этому коду подключается и шлёт команды.
@Composable
fun RemoteScreen(vm: AppViewModel, onOpenAdmin: () -> Unit) {
    val code by vm.remote.sessionCode.collectAsState()
    val lastCmd by vm.remote.lastCommand.collectAsState()
    val active by vm.remote.active.collectAsState()

    // счётчик тапов по заголовку → 7 тапов открывают админку
    var tapCount by remember { mutableStateOf(0) }
    var lastTap by remember { mutableStateOf(0L) }

    // При входе на экран — запускаем сессию (если ещё не активна)
    LaunchedEffect(Unit) {
        if (!active) vm.startRemote()
    }

    Column(
        Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.Center
    ) {
        Text("УДАЛЁННЫЙ РЕЖИМ", style = MeterTypography.headlineSmall, color = MeterGreen,
            modifier = Modifier.clickable {
                val now = System.currentTimeMillis()
                tapCount = if (now - lastTap < 2000) tapCount + 1 else 1
                lastTap = now
                if (tapCount >= 7) { tapCount = 0; onOpenAdmin() }
            })
        Spacer(Modifier.height(8.dp))
        Text(
            "Назовите оператору код сессии. Держите телефон у платы — "
                + "оператор управляет удалённо.",
            style = MeterTypography.bodySmall, color = MeterTextDim
        )
        Spacer(Modifier.height(28.dp))

        // Большое табло с кодом сессии
        MeterPanel {
            Text("КОД СЕССИИ", style = MeterTypography.labelLarge, color = MeterTextDim,
                modifier = Modifier.fillMaxWidth(), textAlign = TextAlign.Center)
            Spacer(Modifier.height(10.dp))
            Box(Modifier.fillMaxWidth(), contentAlignment = androidx.compose.ui.Alignment.Center) {
                Text(
                    code ?: "······",
                    style = DisplayValueStyle.copy(fontSize = 40.sp, letterSpacing = 6.sp)
                )
            }
        }

        Spacer(Modifier.height(24.dp))

        // Индикатор связи + последняя команда
        MeterPanel {
            Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                StatusLed(if (active) "На связи с облаком" else "Не активно", active)
            }
            Spacer(Modifier.height(10.dp))
            Text(
                "Последняя команда: ${lastCmd ?: "—"}",
                style = MeterTypography.bodySmall, color = MeterTextDim
            )
        }
    }
}
