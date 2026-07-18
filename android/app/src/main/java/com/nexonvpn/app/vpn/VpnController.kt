package com.nexonvpn.app.vpn

import android.content.Context
import android.content.Intent
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

enum class VpnStatus { DISCONNECTED, CONNECTING, CONNECTED, ERROR }

/**
 * Единая точка управления туннелем. UI подписывается на [status], сервис его
 * обновляет. Конфиг Xray и адрес прокси передаются в сервис через Intent.
 */
object VpnController {

    private val _status = MutableStateFlow(VpnStatus.DISCONNECTED)
    val status: StateFlow<VpnStatus> = _status.asStateFlow()

    private val _activeServer = MutableStateFlow<String?>(null)
    val activeServer: StateFlow<String?> = _activeServer.asStateFlow()

    internal fun updateStatus(s: VpnStatus) { _status.value = s }
    internal fun updateActiveServer(name: String?) { _activeServer.value = name }

    const val ACTION_START = "com.nexonvpn.app.START"
    const val ACTION_STOP = "com.nexonvpn.app.STOP"
    const val EXTRA_CONFIG = "config"
    const val EXTRA_DOMAIN = "domain"     // host:port выбранного сервера
    const val EXTRA_NAME = "name"

    fun start(context: Context, configJson: String, domain: String, name: String) {
        _status.value = VpnStatus.CONNECTING
        _activeServer.value = name
        val intent = Intent(context, V2RayVpnService::class.java).apply {
            action = ACTION_START
            putExtra(EXTRA_CONFIG, configJson)
            putExtra(EXTRA_DOMAIN, domain)
            putExtra(EXTRA_NAME, name)
        }
        androidx.core.content.ContextCompat.startForegroundService(context, intent)
    }

    fun stop(context: Context) {
        val intent = Intent(context, V2RayVpnService::class.java).apply { action = ACTION_STOP }
        context.startService(intent)
    }
}
