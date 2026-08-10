package com.eeprompatcher.ui

import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import com.eeprompatcher.AppViewModel
import com.eeprompatcher.ble.ConnectionState
import com.eeprompatcher.ui.theme.MeterColorScheme
import com.eeprompatcher.ui.theme.MeterTypography

private enum class AppScreen { SCAN, PIN, MODE_SELECT, MAIN, SETTINGS, ADMIN, REMOTE }

@Composable
fun App(vm: AppViewModel) {
    var screen by remember { mutableStateOf(AppScreen.SCAN) }
    val connState by vm.ble.connectionState.collectAsState()

    LaunchedEffect(connState) {
        when (connState) {
            ConnectionState.DISCONNECTED -> if (screen != AppScreen.SCAN) screen = AppScreen.SCAN
            ConnectionState.CONNECTED -> if (screen == AppScreen.SCAN) screen = AppScreen.PIN
            else -> Unit
        }
    }

    // После авторизации: маршрут зависит от рабочего режима.
    // REMOTE → экран удалённого доступа. MANUAL → выбор/работа с режимами.
    fun afterAuth() {
        screen = when {
            vm.workMode.value == "REMOTE" -> AppScreen.REMOTE
            vm.isModeChosen() -> AppScreen.MAIN
            else -> AppScreen.MODE_SELECT
        }
    }

    MaterialTheme(colorScheme = MeterColorScheme, typography = MeterTypography) {
        Surface(modifier = Modifier.fillMaxSize()) {
            when (screen) {
                AppScreen.SCAN -> ScanScreen(vm)
                AppScreen.PIN -> PinScreen(vm, onAuthenticated = { afterAuth() })
                AppScreen.MODE_SELECT -> ModeSelectScreen(vm, onChosen = { screen = AppScreen.MAIN })
                AppScreen.MAIN -> MainScreen(
                    vm,
                    onOpenSettings = { screen = AppScreen.SETTINGS },
                    onDisconnect = {
                        vm.ble.disconnect()
                        screen = AppScreen.SCAN
                    },
                    onOpenAdmin = { screen = AppScreen.ADMIN }
                )
                AppScreen.SETTINGS -> SettingsScreen(vm, onBack = { screen = AppScreen.MAIN })
                AppScreen.ADMIN -> AdminScreen(vm, onBack = {
                    // после админки — туда, куда ведёт текущий рабочий режим
                    screen = if (vm.workMode.value == "REMOTE") AppScreen.REMOTE else AppScreen.MAIN
                })
                AppScreen.REMOTE -> RemoteScreen(vm, onOpenAdmin = { screen = AppScreen.ADMIN })
            }
        }
    }
}
