package com.taxi.autoaccept

import com.taxi.autoaccept.core.FilterConfig

import android.content.Context
import android.content.SharedPreferences
import kotlin.reflect.KProperty

/**
 * Все настройки приложения. Хранятся в SharedPreferences, читаются службой на каждом заказе,
 * поэтому менять их можно на ходу — перезапуск службы не нужен.
 */
class Prefs(context: Context) {

    private val sp: SharedPreferences =
        context.applicationContext.getSharedPreferences(NAME, Context.MODE_PRIVATE)

    var enabled: Boolean
        get() = sp.getBoolean(KEY_ENABLED, false)
        set(value) = sp.edit().putBoolean(KEY_ENABLED, value).apply()

    var targetPackage: String
        get() = sp.getString(KEY_TARGET, "") ?: ""
        set(value) = sp.edit().putString(KEY_TARGET, value).apply()

    /** true — нажимать сразу, false — ждать подтверждения кнопкой громкости. */
    var autoMode: Boolean
        get() = sp.getBoolean(KEY_AUTO_MODE, true)
        set(value) = sp.edit().putBoolean(KEY_AUTO_MODE, value).apply()

    var minPrice: Double by DoublePref(KEY_MIN_PRICE, 0f)
    var maxPrice: Double by DoublePref(KEY_MAX_PRICE, 0f)
    var minPricePerKm: Double by DoublePref(KEY_MIN_PRICE_PER_KM, 0f)
    var minPricePerTotalKm: Double by DoublePref(KEY_MIN_PRICE_TOTAL_KM, 0f)
    var maxPickupKm: Double by DoublePref(KEY_MAX_PICKUP_KM, 0f)
    var maxPickupMin: Double by DoublePref(KEY_MAX_PICKUP_MIN, 0f)
    var minTripKm: Double by DoublePref(KEY_MIN_TRIP_KM, 0f)
    var maxTripKm: Double by DoublePref(KEY_MAX_TRIP_KM, 0f)
    var minSurge: Double by DoublePref(KEY_MIN_SURGE, 0f)

    /**
     * Задержка перед нажатием. Хранится диапазоном: каждый раз берётся случайное
     * значение между «от» и «до», чтобы темп приёма не был машинно-ровным.
     * Оба нуля — нажимать сразу.
     */
    var acceptDelayMinSec: Double by DoublePref(KEY_DELAY_MIN, 0f)
    var acceptDelayMaxSec: Double by DoublePref(KEY_DELAY_MAX, 0f)

    /** Как часто перечитывать экран, мс. Меньше — быстрее реакция и выше расход батареи. */
    var scanIntervalMs: Int
        get() = sp.getInt(KEY_SCAN_INTERVAL, 250)
        set(value) = sp.edit().putInt(KEY_SCAN_INTERVAL, value).apply()

    var cooldownSec: Int
        get() = sp.getInt(KEY_COOLDOWN, 20)
        set(value) = sp.edit().putInt(KEY_COOLDOWN, value).apply()

    var maxPerHour: Int
        get() = sp.getInt(KEY_MAX_PER_HOUR, 12)
        set(value) = sp.edit().putInt(KEY_MAX_PER_HOUR, value).apply()

    var confirmWindowSec: Int
        get() = sp.getInt(KEY_CONFIRM_WINDOW, 8)
        set(value) = sp.edit().putInt(KEY_CONFIRM_WINDOW, value).apply()

    /** Рабочие часы. Если оба значения равны — ограничение выключено. */
    var workFromHour: Int
        get() = sp.getInt(KEY_WORK_FROM, 0)
        set(value) = sp.edit().putInt(KEY_WORK_FROM, value).apply()

    var workToHour: Int
        get() = sp.getInt(KEY_WORK_TO, 0)
        set(value) = sp.edit().putInt(KEY_WORK_TO, value).apply()

    var acceptRegex: String
        get() = sp.getString(KEY_ACCEPT_REGEX, DEFAULT_ACCEPT_REGEX) ?: DEFAULT_ACCEPT_REGEX
        set(value) = sp.edit().putString(KEY_ACCEPT_REGEX, value).apply()

    var denyRegex: String
        get() = sp.getString(KEY_DENY_REGEX, DEFAULT_DENY_REGEX) ?: DEFAULT_DENY_REGEX
        set(value) = sp.edit().putString(KEY_DENY_REGEX, value).apply()

    var blacklist: String
        get() = sp.getString(KEY_BLACKLIST, "") ?: ""
        set(value) = sp.edit().putString(KEY_BLACKLIST, value).apply()

    var requiredWords: String
        get() = sp.getString(KEY_REQUIRED, "") ?: ""
        set(value) = sp.edit().putString(KEY_REQUIRED, value).apply()

    var speak: Boolean
        get() = sp.getBoolean(KEY_SPEAK, true)
        set(value) = sp.edit().putBoolean(KEY_SPEAK, value).apply()

    var requireKnownPrice: Boolean
        get() = sp.getBoolean(KEY_REQUIRE_PRICE, true)
        set(value) = sp.edit().putBoolean(KEY_REQUIRE_PRICE, value).apply()

    var learnMode: Boolean
        get() = sp.getBoolean(KEY_LEARN, false)
        set(value) = sp.edit().putBoolean(KEY_LEARN, value).apply()

    fun registerListener(l: SharedPreferences.OnSharedPreferenceChangeListener) =
        sp.registerOnSharedPreferenceChangeListener(l)

    fun unregisterListener(l: SharedPreferences.OnSharedPreferenceChangeListener) =
        sp.unregisterOnSharedPreferenceChangeListener(l)

    fun toFilterConfig(): FilterConfig = FilterConfig(
        minPrice = minPrice,
        maxPrice = maxPrice,
        minPricePerKm = minPricePerKm,
        minPricePerTotalKm = minPricePerTotalKm,
        maxPickupKm = maxPickupKm,
        maxPickupMin = maxPickupMin,
        minTripKm = minTripKm,
        maxTripKm = maxTripKm,
        minSurge = minSurge,
        blacklist = splitWords(blacklist),
        requiredWords = splitWords(requiredWords),
        requireKnownPrice = requireKnownPrice,
    )

    /** Внутри рабочих часов? Окно может переходить через полночь: 20 → 6. */
    fun isWithinWorkHours(hour: Int): Boolean {
        val from = workFromHour
        val to = workToHour
        if (from == to) return true
        return if (from < to) hour in from until to else hour >= from || hour < to
    }

    private inner class DoublePref(private val key: String, private val def: Float) {
        operator fun getValue(thisRef: Any?, property: KProperty<*>): Double =
            sp.getFloat(key, def).toDouble()

        operator fun setValue(thisRef: Any?, property: KProperty<*>, value: Double) {
            sp.edit().putFloat(key, value.toFloat()).apply()
        }
    }

    companion object {
        private const val NAME = "auto_accept_prefs"

        private const val KEY_ENABLED = "enabled"
        private const val KEY_TARGET = "target_package"
        private const val KEY_AUTO_MODE = "auto_mode"
        private const val KEY_MIN_PRICE = "min_price"
        private const val KEY_MAX_PRICE = "max_price"
        private const val KEY_MIN_PRICE_PER_KM = "min_price_per_km"
        private const val KEY_MIN_PRICE_TOTAL_KM = "min_price_total_km"
        private const val KEY_MAX_PICKUP_KM = "max_pickup_km"
        private const val KEY_MAX_PICKUP_MIN = "max_pickup_min"
        private const val KEY_MIN_TRIP_KM = "min_trip_km"
        private const val KEY_MAX_TRIP_KM = "max_trip_km"
        private const val KEY_MIN_SURGE = "min_surge"
        private const val KEY_DELAY_MIN = "accept_delay_min_sec"
        private const val KEY_DELAY_MAX = "accept_delay_max_sec"
        private const val KEY_SCAN_INTERVAL = "scan_interval_ms"
        private const val KEY_COOLDOWN = "cooldown_sec"
        private const val KEY_MAX_PER_HOUR = "max_per_hour"
        private const val KEY_CONFIRM_WINDOW = "confirm_window_sec"
        private const val KEY_WORK_FROM = "work_from_hour"
        private const val KEY_WORK_TO = "work_to_hour"
        private const val KEY_ACCEPT_REGEX = "accept_regex"
        private const val KEY_DENY_REGEX = "deny_regex"
        private const val KEY_BLACKLIST = "blacklist"
        private const val KEY_REQUIRED = "required_words"
        private const val KEY_SPEAK = "speak"
        private const val KEY_REQUIRE_PRICE = "require_price"
        private const val KEY_LEARN = "learn_mode"

        /**
         * Текст кнопки приёма в популярных приложениях (ru/en/kk/uz/uk).
         * «взять» покрывает региональные диспетчерские вроде Анжи Такси,
         * где кнопка подписана «Взять заказ».
         */
        const val DEFAULT_ACCEPT_REGEX =
            "(?i)(принять|принимаю|беру|взять|accept|қабылдау|qabul|прийняти)"

        /** Кнопки, которые похожи на «принять», но заказом не являются. */
        const val DEFAULT_DENY_REGEX =
            "(?i)(услови|соглаш|правил|политик|terms|policy|обновл|update|разреш|permission)"

        fun splitWords(raw: String): List<String> =
            raw.split(',', '\n')
                .map { it.trim().lowercase() }
                .filter { it.isNotEmpty() }
    }
}
