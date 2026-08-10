package com.taxi.autoaccept.core

/**
 * Разобранная карточка заказа. Любое поле может быть null — приложения такси
 * показывают разный набор данных, а вёрстка меняется от версии к версии.
 */
data class OrderInfo(
    /** Сумма заказа. */
    val price: Double? = null,
    val currency: String? = null,
    /** Расстояние подачи (до клиента), км. */
    val pickupKm: Double? = null,
    /** Время подачи, мин. */
    val pickupMin: Double? = null,
    /** Длина маршрута, км. */
    val tripKm: Double? = null,
    /** Коэффициент спроса, например ×1,5. */
    val surge: Double? = null,
    val rawText: String = "",
) {
    /** Ставка за километр маршрута. */
    val pricePerKm: Double?
        get() {
            val p = price ?: return null
            val d = tripKm ?: return null
            return if (d > 0.0) p / d else null
        }

    /**
     * Ставка за километр с учётом подачи — то, что реально зарабатывается:
     * пустой пробег до клиента оплачивается редко.
     */
    val pricePerTotalKm: Double?
        get() {
            val p = price ?: return null
            val trip = tripKm ?: return null
            val total = trip + (pickupKm ?: 0.0)
            return if (total > 0.0) p / total else null
        }
}

/**
 * Достаёт сумму, расстояния, время подачи и коэффициент из текста, собранного с экрана.
 *
 * Работает по меткам («подача», «до клиента», «маршрут»), а если меток нет —
 * по порядку: первое расстояние считается подачей, второе маршрутом.
 * Именно так карточку рисуют Яндекс Про, inDrive, Maxim и Bolt.
 */
object OrderParser {

    /**
     * Граница слова вместо \b: в Java-регексах \b опирается на ASCII-класс \w,
     * поэтому после кириллического «км» границы не возникает и правило не срабатывает.
     */
    private const val BOUND = "(?![\\p{L}\\p{N}])"

    private const val NUM = "\\d+(?:[\\s\\u00A0]?\\d{3})*(?:[.,]\\d+)?"

    private val PRICE_REGEX = Regex(
        "($NUM)\\s*(₽|руб\\.?|р\\.|сум|so'm|soʻm|₸|тг|тнг|₴|грн|сом|лей|KZT|UZS|RUB)",
        RegexOption.IGNORE_CASE,
    )

    /** Сумма может стоять и после валюты: «₽ 350». */
    private val PRICE_PREFIX_REGEX = Regex(
        "(₽|₸|₴)\\s*($NUM)",
        RegexOption.IGNORE_CASE,
    )

    private val PICKUP_LABELED = Regex(
        "(?:подач[аиуе]|до\\s+клиент[аи]|к\\s+клиенту|подъезд|pickup)[^\\d]{0,24}($NUM)\\s*(км|km|м|m)$BOUND",
        RegexOption.IGNORE_CASE,
    )

    private val TRIP_LABELED = Regex(
        "(?:маршрут|поездк[аи]|в\\s+пути|до\\s+точки|trip|route)[^\\d]{0,24}($NUM)\\s*(км|km|м|m)$BOUND",
        RegexOption.IGNORE_CASE,
    )

    private val ANY_DISTANCE = Regex(
        "($NUM)\\s*(км|km|м|m)$BOUND",
        RegexOption.IGNORE_CASE,
    )

    private val PICKUP_MIN_LABELED = Regex(
        "(?:подач[аиуе]|до\\s+клиент[аи]|к\\s+клиенту|pickup)[^\\d]{0,24}($NUM)\\s*(?:мин|min|мн)$BOUND",
        RegexOption.IGNORE_CASE,
    )

    private val ANY_MIN = Regex(
        "($NUM)\\s*(?:мин|min)$BOUND",
        RegexOption.IGNORE_CASE,
    )

    /** «×1,5», «x2», «1.5x», «коэффициент 1,7». */
    private val SURGE_REGEX = Regex(
        "(?:[x×хX]\\s*($NUM)|($NUM)\\s*[x×]|коэф\\w*\\s*($NUM))",
    )

    fun parse(text: String): OrderInfo {
        val priceMatch = PRICE_REGEX.find(text)
        val prefixMatch = if (priceMatch == null) PRICE_PREFIX_REGEX.find(text) else null

        val price = when {
            priceMatch != null -> parseNumber(priceMatch.groupValues[1])
            prefixMatch != null -> parseNumber(prefixMatch.groupValues[2])
            else -> null
        }
        val currency = when {
            priceMatch != null -> priceMatch.groupValues[2]
            prefixMatch != null -> prefixMatch.groupValues[1]
            else -> null
        }

        var pickup = PICKUP_LABELED.find(text)?.let { toKm(it.groupValues[1], it.groupValues[2]) }
        var trip = TRIP_LABELED.find(text)?.let { toKm(it.groupValues[1], it.groupValues[2]) }

        if (pickup == null || trip == null) {
            val all = ANY_DISTANCE.findAll(text)
                .mapNotNull { toKm(it.groupValues[1], it.groupValues[2]) }
                .toMutableList()
            if (pickup == null) pickup = all.firstOrNull()
            // Убираем подачу из списка, иначе её же можно принять за маршрут.
            pickup?.let { all.remove(it) }
            if (trip == null) trip = all.firstOrNull()
        }

        val pickupMin = PICKUP_MIN_LABELED.find(text)?.let { parseNumber(it.groupValues[1]) }
            ?: ANY_MIN.find(text)?.let { parseNumber(it.groupValues[1]) }

        val surge = SURGE_REGEX.find(text)?.let { m ->
            m.groupValues.drop(1).firstOrNull { it.isNotEmpty() }?.let { parseNumber(it) }
        }?.takeIf { it in 1.0..9.9 }

        return OrderInfo(
            price = price,
            currency = currency,
            pickupKm = pickup,
            pickupMin = pickupMin,
            tripKm = trip,
            surge = surge,
            rawText = text,
        )
    }

    internal fun parseNumber(raw: String): Double? =
        raw.replace(' ', ' ')
            .replace(" ", "")
            .replace(',', '.')
            .toDoubleOrNull()

    private fun toKm(raw: String, unit: String): Double? {
        val value = parseNumber(raw) ?: return null
        return if (unit.lowercase() in setOf("м", "m")) value / 1000.0 else value
    }
}
