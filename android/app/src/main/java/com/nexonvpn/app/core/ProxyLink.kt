package com.nexonvpn.app.core

import android.net.Uri
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.add
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.net.URLDecoder

/**
 * Разобранная ссылка сервера: человекочитаемое имя + готовый Xray-outbound.
 */
data class ProxyLink(
    val tag: String,
    val name: String,
    val host: String,
    val port: Int,
    val outbound: JsonObject,
) {
    companion object {
        /** Парсит одну ссылку подписки. null — если протокол не поддержан/битая. */
        fun parse(raw: String, index: Int): ProxyLink? {
            val s = raw.trim()
            return when {
                s.startsWith("vless://") -> parseVless(s, index)
                s.startsWith("trojan://") -> parseTrojan(s, index)
                s.startsWith("ss://") -> parseShadowsocks(s, index)
                else -> null // vmess/hysteria2 и пр. можно добавить отдельно
            }
        }

        private fun frag(uri: Uri, fallback: String): String {
            val f = uri.fragment
            return if (f.isNullOrBlank()) fallback else runCatching {
                URLDecoder.decode(f, "UTF-8")
            }.getOrDefault(f)
        }

        // ── VLESS (в т.ч. Reality / XTLS-Vision) ─────────────────────────────
        private fun parseVless(s: String, index: Int): ProxyLink? {
            val uri = Uri.parse(s)
            val uuid = uri.userInfo ?: return null
            val host = uri.host ?: return null
            val port = uri.port.takeIf { it > 0 } ?: 443
            val q = { k: String -> uri.getQueryParameter(k) }

            val network = q("type") ?: "tcp"
            val security = q("security") ?: "none"
            val flow = q("flow").orEmpty()
            val name = frag(uri, "VLESS-$index")

            val outbound = buildJsonObject {
                put("tag", "proxy")
                put("protocol", "vless")
                put("settings", buildJsonObject {
                    put("vnext", buildJsonArray {
                        add(buildJsonObject {
                            put("address", host)
                            put("port", port)
                            put("users", buildJsonArray {
                                add(buildJsonObject {
                                    put("id", uuid)
                                    put("encryption", q("encryption") ?: "none")
                                    if (flow.isNotEmpty()) put("flow", flow)
                                    put("level", 0)
                                })
                            })
                        })
                    })
                })
                put("streamSettings", buildStreamSettings(network, security, uri, host))
            }
            return ProxyLink("proxy", name, host, port, outbound)
        }

        // ── Trojan ───────────────────────────────────────────────────────────
        private fun parseTrojan(s: String, index: Int): ProxyLink? {
            val uri = Uri.parse(s)
            val password = uri.userInfo ?: return null
            val host = uri.host ?: return null
            val port = uri.port.takeIf { it > 0 } ?: 443
            val network = uri.getQueryParameter("type") ?: "tcp"
            val security = uri.getQueryParameter("security") ?: "tls"
            val name = frag(uri, "Trojan-$index")

            val outbound = buildJsonObject {
                put("tag", "proxy")
                put("protocol", "trojan")
                put("settings", buildJsonObject {
                    put("servers", buildJsonArray {
                        add(buildJsonObject {
                            put("address", host)
                            put("port", port)
                            put("password", password)
                            put("level", 0)
                        })
                    })
                })
                put("streamSettings", buildStreamSettings(network, security, uri, host))
            }
            return ProxyLink("proxy", name, host, port, outbound)
        }

        // ── Shadowsocks (SIP002: ss://base64(method:pass)@host:port#name) ─────
        private fun parseShadowsocks(s: String, index: Int): ProxyLink? {
            val hashIdx = s.indexOf('#')
            val name = if (hashIdx >= 0) runCatching {
                URLDecoder.decode(s.substring(hashIdx + 1), "UTF-8")
            }.getOrDefault("SS-$index") else "SS-$index"
            val body = (if (hashIdx >= 0) s.substring(5, hashIdx) else s.substring(5))

            val atIdx = body.lastIndexOf('@')
            if (atIdx < 0) return null
            val userPart = body.substring(0, atIdx)
            val hostPart = body.substring(atIdx + 1)

            val decodedUser = runCatching {
                String(android.util.Base64.decode(userPart, android.util.Base64.URL_SAFE or android.util.Base64.NO_PADDING))
            }.getOrElse { userPart }
            val colon = decodedUser.indexOf(':')
            if (colon < 0) return null
            val method = decodedUser.substring(0, colon)
            val password = decodedUser.substring(colon + 1)

            val hp = hostPart.substringBefore('?')
            val host = hp.substringBeforeLast(':')
            val port = hp.substringAfterLast(':').toIntOrNull() ?: return null

            val outbound = buildJsonObject {
                put("tag", "proxy")
                put("protocol", "shadowsocks")
                put("settings", buildJsonObject {
                    put("servers", buildJsonArray {
                        add(buildJsonObject {
                            put("address", host)
                            put("port", port)
                            put("method", method)
                            put("password", password)
                            put("level", 0)
                        })
                    })
                })
                put("streamSettings", buildJsonObject { put("network", "tcp") })
            }
            return ProxyLink("proxy", name, host, port, outbound)
        }

        // ── streamSettings (транспорт + защита) ──────────────────────────────
        private fun buildStreamSettings(
            network: String,
            security: String,
            uri: Uri,
            host: String,
        ): JsonObject = buildJsonObject {
            put("network", network)
            put("security", security)
            val q = { k: String -> uri.getQueryParameter(k) }
            val sni = q("sni") ?: q("host") ?: host
            val fp = q("fp").orEmpty()
            val alpn = q("alpn").orEmpty()

            when (security) {
                "reality" -> put("realitySettings", buildJsonObject {
                    put("serverName", sni)
                    put("fingerprint", fp.ifEmpty { "chrome" })
                    put("publicKey", q("pbk").orEmpty())
                    put("shortId", q("sid").orEmpty())
                    put("spiderX", q("spx").orEmpty())
                    put("show", false)
                })
                "tls", "xtls" -> put("tlsSettings", buildJsonObject {
                    put("serverName", sni)
                    if (fp.isNotEmpty()) put("fingerprint", fp)
                    if (alpn.isNotEmpty()) put("alpn", buildJsonArray { alpn.split(',').forEach { add(it.trim()) } })
                    put("allowInsecure", q("allowInsecure") == "1")
                })
            }

            when (network) {
                "ws" -> put("wsSettings", buildJsonObject {
                    put("path", q("path") ?: "/")
                    val h = q("host") ?: sni
                    put("headers", buildJsonObject { put("Host", h) })
                })
                "grpc" -> put("grpcSettings", buildJsonObject {
                    put("serviceName", q("serviceName") ?: q("path").orEmpty())
                    put("multiMode", q("mode") == "multi")
                })
                "http", "h2" -> put("httpSettings", buildJsonObject {
                    put("path", q("path") ?: "/")
                    put("host", buildJsonArray { add(q("host") ?: sni) })
                })
                "tcp" -> {
                    val headerType = q("headerType")
                    if (headerType == "http") put("tcpSettings", buildJsonObject {
                        put("header", buildJsonObject {
                            put("type", "http")
                            put("request", buildJsonObject {
                                put("path", buildJsonArray { add(q("path") ?: "/") })
                                put("headers", buildJsonObject { put("Host", buildJsonArray { add(q("host") ?: sni) }) })
                            })
                        })
                    })
                }
            }
        }
    }
}
