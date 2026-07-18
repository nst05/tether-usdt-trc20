package com.nexonvpn.app.core

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.add
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * Собирает полный конфиг Xray-core: локальный socks-inbound (в него направляется
 * трафик из TUN через tun2socks), выбранный прокси-outbound, direct/block и DNS.
 */
object XrayConfig {

    const val SOCKS_PORT = 10808
    private val json = Json { prettyPrint = false }

    fun build(proxy: ProxyLink, socksPort: Int = SOCKS_PORT): String {
        val config = buildJsonObject {
            put("log", buildJsonObject { put("loglevel", "warning") })

            put("inbounds", buildJsonArray {
                add(buildJsonObject {
                    put("tag", "socks-in")
                    put("port", socksPort)
                    put("listen", "127.0.0.1")
                    put("protocol", "socks")
                    put("settings", buildJsonObject {
                        put("auth", "noauth")
                        put("udp", true)
                        put("userLevel", 8)
                    })
                    put("sniffing", buildJsonObject {
                        put("enabled", true)
                        put("destOverride", buildJsonArray { add("http"); add("tls"); add("quic") })
                        put("routeOnly", false)
                    })
                })
            })

            put("outbounds", buildJsonArray {
                add(proxy.outbound)                               // tag = proxy
                add(buildJsonObject {
                    put("tag", "direct")
                    put("protocol", "freedom")
                    put("settings", buildJsonObject { put("domainStrategy", "UseIP") })
                })
                add(buildJsonObject {
                    put("tag", "block")
                    put("protocol", "blackhole")
                    put("settings", buildJsonObject { put("response", buildJsonObject { put("type", "http") }) })
                })
            })

            put("dns", buildDns())
            put("routing", buildRouting())
        }
        return json.encodeToString(JsonObject.serializer(), config)
    }

    private fun buildDns(): JsonObject = buildJsonObject {
        put("servers", buildJsonArray {
            add("1.1.1.1")
            add("8.8.8.8")
            add(buildJsonObject {
                put("address", "223.5.5.5")
                put("domains", buildJsonArray { add("geosite:cn") })
            })
        })
        put("queryStrategy", "UseIP")
    }

    private fun buildRouting(): JsonObject = buildJsonObject {
        put("domainStrategy", "IPIfNonMatch")
        put("rules", buildJsonArray {
            // Приватные сети — напрямую
            add(buildJsonObject {
                put("type", "field")
                put("ip", buildJsonArray { add("geoip:private") })
                put("outboundTag", "direct")
            })
            // Блокируем рекламу/трекеры (если есть geosite)
            add(buildJsonObject {
                put("type", "field")
                put("domain", buildJsonArray { add("geosite:category-ads-all") })
                put("outboundTag", "block")
            })
            // Всё остальное — через прокси (по умолчанию, default outbound)
        })
    }
}
