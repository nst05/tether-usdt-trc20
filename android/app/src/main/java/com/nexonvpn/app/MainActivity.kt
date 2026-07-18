package com.nexonvpn.app

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.VpnService
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.core.view.WindowCompat
import com.nexonvpn.app.ui.HomeScreen
import com.nexonvpn.app.ui.theme.NexonTheme
import com.nexonvpn.app.vpn.VpnController
import com.nexonvpn.app.vpn.VpnStatus

class MainActivity : ComponentActivity() {

    private val vm: MainViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, false)

        setContent {
            NexonTheme {
                val pendingConnect = remember { arrayOfNulls<ConnectRequest>(1) }

                // Разрешение на VPN (VpnService.prepare)
                val vpnPermLauncher = rememberLauncherForActivityResult(
                    ActivityResultContracts.StartActivityForResult()
                ) { result ->
                    if (result.resultCode == RESULT_OK) {
                        pendingConnect[0]?.let { req ->
                            VpnController.start(this, req.config, req.domain, req.name)
                        }
                    } else {
                        vm.onConnectionRefused()
                    }
                    pendingConnect[0] = null
                }

                // Разрешение на уведомления (Android 13+)
                val notifLauncher = rememberLauncherForActivityResult(
                    ActivityResultContracts.RequestPermission()
                ) { /* игнорируем результат — сервис работает и без уведомлений */ }

                HomeScreen(
                    vm = vm,
                    onConnect = {
                        maybeRequestNotifications(notifLauncher)
                        val req = vm.prepareConnect() ?: return@HomeScreen
                        val prepare = VpnService.prepare(this)
                        if (prepare == null) {
                            VpnController.start(this, req.config, req.domain, req.name)
                        } else {
                            pendingConnect[0] = req
                            vpnPermLauncher.launch(prepare)
                        }
                    },
                    onDisconnect = { VpnController.stop(this) },
                )
            }
        }
    }

    private fun maybeRequestNotifications(
        launcher: androidx.activity.result.ActivityResultLauncher<String>
    ) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            launcher.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
    }
}
