package com.taxi.autoaccept.core

/**
 * Перенос правил между устройствами и платформами в виде простого текста
 * «ключ=значение»: его можно отправить в мессенджере, положить в облако
 * и прочитать любой другой обёрткой над этим ядром.
 */
object RulesCodec {

    fun encode(cfg: FilterConfig): String = buildList {
        add("min_price=${cfg.minPrice}")
        add("max_price=${cfg.maxPrice}")
        add("min_price_per_km=${cfg.minPricePerKm}")
        add("min_price_per_total_km=${cfg.minPricePerTotalKm}")
        add("max_pickup_km=${cfg.maxPickupKm}")
        add("max_pickup_min=${cfg.maxPickupMin}")
        add("min_trip_km=${cfg.minTripKm}")
        add("max_trip_km=${cfg.maxTripKm}")
        add("min_surge=${cfg.minSurge}")
        add("blacklist=${cfg.blacklist.joinToString(",")}")
        add("required=${cfg.requiredWords.joinToString(",")}")
        add("require_known_price=${cfg.requireKnownPrice}")
    }.joinToString("\n")

    fun decode(text: String): FilterConfig {
        val map = text.lineSequence()
            .mapNotNull { line ->
                val trimmed = line.trim()
                if (trimmed.isEmpty() || trimmed.startsWith("#")) return@mapNotNull null
                val idx = trimmed.indexOf('=')
                if (idx <= 0) return@mapNotNull null
                trimmed.substring(0, idx).trim() to trimmed.substring(idx + 1).trim()
            }
            .toMap()

        fun num(key: String) = map[key]?.replace(',', '.')?.toDoubleOrNull() ?: 0.0
        fun words(key: String) = map[key].orEmpty()
            .split(',')
            .map { it.trim().lowercase() }
            .filter { it.isNotEmpty() }

        return FilterConfig(
            minPrice = num("min_price"),
            maxPrice = num("max_price"),
            minPricePerKm = num("min_price_per_km"),
            minPricePerTotalKm = num("min_price_per_total_km"),
            maxPickupKm = num("max_pickup_km"),
            maxPickupMin = num("max_pickup_min"),
            minTripKm = num("min_trip_km"),
            maxTripKm = num("max_trip_km"),
            minSurge = num("min_surge"),
            blacklist = words("blacklist"),
            requiredWords = words("required"),
            requireKnownPrice = map["require_known_price"]?.toBooleanStrictOrNull() ?: true,
        )
    }
}
