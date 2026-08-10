package com.taxi.autoaccept.core

/**
 * Правила отбора заказов. Ноль в любом числовом поле = правило выключено.
 */
data class FilterConfig(
    /** Минимальная сумма заказа. */
    val minPrice: Double = 0.0,
    /** Максимальная сумма — отсекает «слишком хорошие» карточки с опечаткой в разборе. */
    val maxPrice: Double = 0.0,
    /** Минимум за километр маршрута. */
    val minPricePerKm: Double = 0.0,
    /** Минимум за километр с учётом подачи (реальная ставка). */
    val minPricePerTotalKm: Double = 0.0,
    val maxPickupKm: Double = 0.0,
    val maxPickupMin: Double = 0.0,
    val minTripKm: Double = 0.0,
    val maxTripKm: Double = 0.0,
    /** Минимальный коэффициент спроса (×1.5 и выше). */
    val minSurge: Double = 0.0,
    val blacklist: List<String> = emptyList(),
    val requiredWords: List<String> = emptyList(),
    /** Не принимать заказ, если сумму распознать не удалось. */
    val requireKnownPrice: Boolean = true,
)

sealed class Decision {
    object Accept : Decision()
    data class Reject(val reason: String) : Decision()
}

/**
 * Решает, брать ли заказ. Любое непонятное значение трактуется в сторону отказа:
 * пропущенный заказ стоит дешевле, чем принятый вслепую.
 */
object OrderFilter {

    fun decide(order: OrderInfo, cfg: FilterConfig): Decision {
        val lower = order.rawText.lowercase()

        cfg.blacklist.firstOrNull { it in lower }?.let {
            return Decision.Reject("стоп-слово «$it»")
        }

        cfg.requiredWords.firstOrNull { it !in lower }?.let {
            return Decision.Reject("нет обязательного слова «$it»")
        }

        val price = order.price
        if (price == null) {
            if (cfg.requireKnownPrice) return Decision.Reject("сумма не распознана")
        } else {
            if (cfg.minPrice > 0.0 && price < cfg.minPrice) {
                return Decision.Reject("сумма ${fmt(price)} < ${fmt(cfg.minPrice)}")
            }
            if (cfg.maxPrice > 0.0 && price > cfg.maxPrice) {
                return Decision.Reject("сумма ${fmt(price)} > ${fmt(cfg.maxPrice)}")
            }
        }

        cfg.maxPickupKm.checkMax(order.pickupKm, "подача", "км")?.let { return it }
        cfg.maxPickupMin.checkMax(order.pickupMin, "подача", "мин")?.let { return it }
        cfg.maxTripKm.checkMax(order.tripKm, "маршрут", "км")?.let { return it }
        cfg.minTripKm.checkMin(order.tripKm, "маршрут", "км")?.let { return it }
        cfg.minPricePerKm.checkMin(order.pricePerKm, "ставка за км", "")?.let { return it }
        cfg.minPricePerTotalKm.checkMin(order.pricePerTotalKm, "ставка с подачей", "")
            ?.let { return it }
        cfg.minSurge.checkMin(order.surge, "коэффициент", "")?.let { return it }

        return Decision.Accept
    }

    /** Правило-максимум: значение обязано быть распознано, иначе отказ. */
    private fun Double.checkMax(value: Double?, name: String, unit: String): Decision.Reject? {
        if (this <= 0.0) return null
        if (value == null) return Decision.Reject("$name не распознан(а)")
        val u = if (unit.isEmpty()) "" else " $unit"
        return if (value > this) {
            Decision.Reject("$name ${fmt(value)}$u > ${fmt(this)}$u")
        } else {
            null
        }
    }

    private fun Double.checkMin(value: Double?, name: String, unit: String): Decision.Reject? {
        if (this <= 0.0) return null
        if (value == null) return Decision.Reject("$name не распознан(а)")
        val u = if (unit.isEmpty()) "" else " $unit"
        return if (value < this) {
            Decision.Reject("$name ${fmt(value)}$u < ${fmt(this)}$u")
        } else {
            null
        }
    }

    /** Своё форматирование вместо String.format — ядро не должно зависеть от JVM. */
    private fun fmt(v: Double): String {
        val rounded = kotlin.math.round(v * 10.0) / 10.0
        return if (rounded == rounded.toLong().toDouble()) {
            rounded.toLong().toString()
        } else {
            rounded.toString()
        }
    }
}
