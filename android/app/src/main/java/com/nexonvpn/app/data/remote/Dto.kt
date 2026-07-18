package com.nexonvpn.app.data.remote

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Ответ бэкенда NexonVPN на GET /api/sub/{uuid} (формат Remnawave-совместимый).
 * Поля объявлены опциональными — сервер может опустить часть при ошибках/заглушках.
 */
@Serializable
data class SubscriptionResponse(
    val isFound: Boolean = false,
    val user: SubscriptionUser? = null,
    val links: List<String> = emptyList(),
    val subscriptionUrl: String? = null,
)

@Serializable
data class SubscriptionUser(
    val shortUuid: String = "",
    val daysLeft: Int = 0,
    val trafficUsed: String = "0",
    val trafficLimit: String = "Unlimited",
    val trafficUsedBytes: String = "0",
    val trafficLimitBytes: String = "0",
    val username: String = "",
    val expiresAt: String = "",
    val isActive: Boolean = false,
    /** ACTIVE | EXPIRED | BLOCKED | DEVICE_LIMIT */
    val userStatus: String = "EXPIRED",
    val limitIp: Int = 0,
    val limitIpDisplay: String = "",
)

/**
 * Ответ нового публичного эндпоинта автономной регистрации
 * POST /api/app/register  (добавляется на сервер, см. backend/app_register.py).
 */
@Serializable
data class RegisterResponse(
    val ok: Boolean = false,
    /** UUID клиента для формирования ссылки подписки {base}/sub/{uuid} */
    val uuid: String? = null,
    @SerialName("sub_url") val subUrl: String? = null,
    @SerialName("expires_at") val expiresAt: String? = null,
    val error: String? = null,
)
