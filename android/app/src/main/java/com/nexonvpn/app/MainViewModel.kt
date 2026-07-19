package com.nexonvpn.app

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.nexonvpn.app.core.XrayConfig
import com.nexonvpn.app.data.ServerInfo
import com.nexonvpn.app.data.SubscriptionRepository
import com.nexonvpn.app.data.SubscriptionState
import com.nexonvpn.app.vpn.VpnController
import com.nexonvpn.app.vpn.VpnStatus
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class UiState(
    val loading: Boolean = true,
    val sub: SubscriptionState? = null,
    val selected: Int = 0,
    val error: String? = null,
)

/** Данные для запуска туннеля выбранного сервера. */
data class ConnectRequest(val config: String, val domain: String, val name: String)

class MainViewModel(app: Application) : AndroidViewModel(app) {

    private val repo = SubscriptionRepository(app)

    private val _ui = MutableStateFlow(UiState())
    val ui: StateFlow<UiState> = _ui.asStateFlow()

    private val _tariffs = MutableStateFlow<List<com.nexonvpn.app.data.remote.Tariff>>(emptyList())
    val tariffs: StateFlow<List<com.nexonvpn.app.data.remote.Tariff>> = _tariffs.asStateFlow()

    val vpnStatus: StateFlow<VpnStatus> = VpnController.status
    val activeServer: StateFlow<String?> = VpnController.activeServer

    init { refresh() }

    fun refresh() {
        _ui.value = _ui.value.copy(loading = true, error = null)
        viewModelScope.launch {
            repo.loadSubscription()
                .onSuccess { state ->
                    _ui.value = UiState(loading = false, sub = state, selected = 0, error = null)
                }
                .onFailure { e ->
                    _ui.value = _ui.value.copy(
                        loading = false,
                        error = e.message ?: "unknown",
                    )
                }
        }
    }

    fun selectServer(index: Int) {
        val servers = _ui.value.sub?.servers ?: return
        if (index !in servers.indices) return
        _ui.value = _ui.value.copy(selected = index)
        viewModelScope.launch { repo.setSelectedServer(servers[index].name) }
    }

    /** Готовит запрос на подключение для текущего выбранного сервера. */
    fun prepareConnect(): ConnectRequest? {
        val state = _ui.value.sub ?: return null
        val server: ServerInfo = state.servers.getOrNull(_ui.value.selected) ?: return null
        val config = XrayConfig.build(server.proxy)
        return ConnectRequest(config = config, domain = server.domain, name = server.name)
    }

    fun onConnectionRefused() {
        VpnController.updateStatus(VpnStatus.DISCONNECTED)
    }

    fun loadTariffs() {
        viewModelScope.launch {
            _tariffs.value = repo.loadTariffs()
        }
    }

    /** Создаёт платёж и отдаёт URL для открытия в браузере (или ошибку). */
    fun purchase(tariffId: Int, method: String, onUrl: (String) -> Unit, onError: (String) -> Unit) {
        viewModelScope.launch {
            repo.purchase(tariffId, method)
                .onSuccess { onUrl(it) }
                .onFailure { onError(it.message ?: "error") }
        }
    }
}
