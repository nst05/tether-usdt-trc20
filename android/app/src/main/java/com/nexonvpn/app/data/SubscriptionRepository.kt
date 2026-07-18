package com.nexonvpn.app.data

import android.content.Context
import com.nexonvpn.app.core.ProxyLink
import com.nexonvpn.app.data.remote.ApiService
import com.nexonvpn.app.data.remote.SubscriptionUser

/** Один сервер из подписки, готовый к подключению. */
data class ServerInfo(
    val name: String,
    val host: String,
    val port: Int,
    val proxy: ProxyLink,
) {
    val domain: String get() = "$host:$port"
}

/** Итог загрузки подписки. */
data class SubscriptionState(
    val status: String,          // ACTIVE | EXPIRED | BLOCKED | DEVICE_LIMIT | ERROR | EMPTY
    val daysLeft: Int = 0,
    val trafficUsed: String = "",
    val trafficLimit: String = "",
    val expiresAt: String = "",
    val servers: List<ServerInfo> = emptyList(),
) {
    val isUsable: Boolean get() = status == "ACTIVE" && servers.isNotEmpty()
}

class SubscriptionRepository(context: Context) {

    private val appContext = context.applicationContext
    private val prefs = PrefsStore(appContext)

    private suspend fun api(): ApiService {
        val hwid = DeviceId.hwidFromSeed(prefs.deviceSeed())
        return ApiService(hwid = hwid, deviceModel = DeviceId.model, osVersion = DeviceId.osVersion)
    }

    /** Возвращает UUID подписки, регистрируя устройство при первом запуске. */
    suspend fun ensureRegistered(): Result<String> {
        prefs.subUuidOnce()?.let { return Result.success(it) }
        val resp = runCatching { api().register() }.getOrElse {
            return Result.failure(it)
        }
        val uuid = resp.uuid
        return if (resp.ok && !uuid.isNullOrBlank()) {
            prefs.setSubUuid(uuid)
            Result.success(uuid)
        } else {
            Result.failure(IllegalStateException(resp.error ?: "register_failed"))
        }
    }

    /** Загружает актуальный список серверов и статус подписки. */
    suspend fun loadSubscription(): Result<SubscriptionState> {
        val uuid = ensureRegistered().getOrElse { return Result.failure(it) }
        val service = api()

        val resp = runCatching { service.subscription(uuid) }.getOrElse {
            return Result.failure(it)
        }

        if (!resp.isFound || resp.user == null) {
            // Фолбэк на классическую base64-подписку
            val links = runCatching { service.subscriptionLinksBase64(uuid) }.getOrDefault(emptyList())
            val servers = parseServers(links)
            return Result.success(
                SubscriptionState(
                    status = if (servers.isNotEmpty()) "ACTIVE" else "EMPTY",
                    servers = servers,
                )
            )
        }

        val u: SubscriptionUser = resp.user
        val servers = parseServers(resp.links)
        return Result.success(
            SubscriptionState(
                status = u.userStatus,
                daysLeft = u.daysLeft,
                trafficUsed = u.trafficUsed,
                trafficLimit = u.trafficLimit,
                expiresAt = u.expiresAt,
                servers = servers,
            )
        )
    }

    private fun parseServers(links: List<String>): List<ServerInfo> =
        links.mapIndexedNotNull { i, link ->
            // Пропускаем заглушки-ссылки (0000@127.0.0.1)
            if (link.contains("0000@127.0.0.1")) return@mapIndexedNotNull null
            ProxyLink.parse(link, i)?.let { p ->
                ServerInfo(name = p.name, host = p.host, port = p.port, proxy = p)
            }
        }

    suspend fun setSelectedServer(name: String) = prefs.setSelectedServer(name)
}
