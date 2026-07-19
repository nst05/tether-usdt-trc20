package com.nexonvpn.app.data.remote

import android.util.Base64
import com.nexonvpn.app.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.concurrent.TimeUnit

/**
 * Клиент к бэкенду NexonVPN.
 *
 * Заголовки устройства проставляются на каждый запрос — по ним сервер:
 *  • отличает VPN-клиент от браузера (User-Agent),
 *  • ведёт лимит устройств (X-HWID / X-Forwarded-HWID),
 *  • логирует устройство (X-Forwarded-Device-OS / Ver-OS / Device-Model).
 */
class ApiService(
    private val baseUrl: String = BuildConfig.BASE_URL,
    private val hwid: String,
    private val deviceModel: String,
    private val osVersion: String,
) {
    private val json = Json { ignoreUnknownKeys = true; coerceInputValues = true }

    private val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(12, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .addInterceptor { chain ->
            val req = chain.request().newBuilder()
                .header("User-Agent", BuildConfig.CLIENT_UA)
                .header("X-HWID", hwid)
                .header("X-Forwarded-HWID", hwid)
                .header("X-Forwarded-User-Agent", BuildConfig.CLIENT_UA)
                .header("X-Forwarded-Device-OS", "android")
                .header("X-Forwarded-Ver-OS", osVersion)
                .header("X-Forwarded-Device-Model", deviceModel)
                .header("Accept", "application/json")
                .build()
            chain.proceed(req)
        }
        .build()

    private fun base(): String = baseUrl.trimEnd('/')

    /** Автономная регистрация устройства → возвращает UUID подписки. */
    suspend fun register(): RegisterResponse = withContext(Dispatchers.IO) {
        val body = json.encodeToString(
            RegisterRequest.serializer(),
            RegisterRequest(hwid = hwid, model = deviceModel, os = "android", osVersion = osVersion),
        ).toRequestBody("application/json".toMediaType())

        val req = Request.Builder()
            .url("${base()}/api/app/register")
            .post(body)
            .build()

        client.newCall(req).execute().use { resp ->
            val text = resp.body?.string().orEmpty()
            if (!resp.isSuccessful) return@withContext RegisterResponse(ok = false, error = "http_${resp.code}")
            runCatching { json.decodeFromString(RegisterResponse.serializer(), text) }
                .getOrElse { RegisterResponse(ok = false, error = "parse") }
        }
    }

    /** Данные подписки (серверы + статус) в JSON. */
    suspend fun subscription(uuid: String): SubscriptionResponse = withContext(Dispatchers.IO) {
        val req = Request.Builder().url("${base()}/api/sub/$uuid").get().build()
        client.newCall(req).execute().use { resp ->
            val text = resp.body?.string().orEmpty()
            if (!resp.isSuccessful) return@withContext SubscriptionResponse(isFound = false)
            runCatching { json.decodeFromString(SubscriptionResponse.serializer(), text) }
                .getOrElse { SubscriptionResponse(isFound = false) }
        }
    }

    /** Список активных тарифов. */
    suspend fun tariffs(): List<Tariff> = withContext(Dispatchers.IO) {
        val req = Request.Builder().url("${base()}/api/app/tariffs").get().build()
        client.newCall(req).execute().use { resp ->
            val text = resp.body?.string().orEmpty()
            if (!resp.isSuccessful) return@withContext emptyList()
            runCatching { json.decodeFromString(TariffsResponse.serializer(), text).tariffs }
                .getOrDefault(emptyList())
        }
    }

    /** Создать платёж за тариф. method: yookassa | platega | yoomoney | wata. */
    suspend fun purchase(tariffId: Int, method: String): PurchaseResponse = withContext(Dispatchers.IO) {
        val payload = buildString {
            append("{\"tariff_id\":").append(tariffId)
            append(",\"method\":\"").append(method).append("\"}")
        }.toRequestBody("application/json".toMediaType())
        val req = Request.Builder().url("${base()}/api/app/purchase").post(payload).build()
        client.newCall(req).execute().use { resp ->
            val text = resp.body?.string().orEmpty()
            runCatching { json.decodeFromString(PurchaseResponse.serializer(), text) }
                .getOrElse { PurchaseResponse(ok = false, error = "parse") }
        }
    }

    /**
     * Фолбэк: классическая base64-подписка /sub/{uuid} → список ссылок.
     * Используется, если /api/sub недоступен на конкретной инсталляции.
     */
    suspend fun subscriptionLinksBase64(uuid: String): List<String> = withContext(Dispatchers.IO) {
        val req = Request.Builder().url("${base()}/sub/$uuid").get().build()
        client.newCall(req).execute().use { resp ->
            val text = resp.body?.string().orEmpty().trim()
            if (!resp.isSuccessful || text.isEmpty()) return@withContext emptyList()
            val decoded = runCatching {
                String(Base64.decode(text, Base64.DEFAULT))
            }.getOrElse { text }
            decoded.split('\n').map { it.trim() }.filter { it.isNotEmpty() }
        }
    }
}

@kotlinx.serialization.Serializable
private data class RegisterRequest(
    val hwid: String,
    val model: String,
    val os: String,
    val osVersion: String,
)
