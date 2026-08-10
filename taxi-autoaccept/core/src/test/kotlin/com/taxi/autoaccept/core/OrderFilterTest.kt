package com.taxi.autoaccept.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class OrderFilterTest {

    private val order = OrderInfo(
        price = 500.0,
        currency = "₽",
        pickupKm = 2.0,
        pickupMin = 6.0,
        tripKm = 10.0,
        surge = 1.2,
        rawText = "500 ₽ | подача 2 км 6 мин | маршрут 10 км",
    )

    @Test
    fun `подходящий заказ принимается`() {
        val cfg = FilterConfig(minPrice = 300.0, maxPickupKm = 5.0, minPricePerKm = 40.0)
        assertEquals(Decision.Accept, OrderFilter.decide(order, cfg))
    }

    @Test
    fun `сумма ниже минимума — отказ`() {
        val result = OrderFilter.decide(order, FilterConfig(minPrice = 800.0))
        assertTrue(result is Decision.Reject)
        assertTrue((result as Decision.Reject).reason.contains("сумма"))
    }

    @Test
    fun `сумма выше максимума — отказ`() {
        val result = OrderFilter.decide(order, FilterConfig(maxPrice = 400.0))
        assertTrue(result is Decision.Reject)
    }

    @Test
    fun `далёкая подача — отказ`() {
        val result = OrderFilter.decide(order, FilterConfig(maxPickupKm = 1.0))
        assertTrue(result is Decision.Reject)
    }

    @Test
    fun `долгая подача в минутах — отказ`() {
        val result = OrderFilter.decide(order, FilterConfig(maxPickupMin = 4.0))
        assertTrue(result is Decision.Reject)
    }

    @Test
    fun `слишком длинный маршрут — отказ`() {
        val result = OrderFilter.decide(order, FilterConfig(maxTripKm = 8.0))
        assertTrue(result is Decision.Reject)
    }

    @Test
    fun `слишком короткий маршрут — отказ`() {
        val result = OrderFilter.decide(order, FilterConfig(minTripKm = 12.0))
        assertTrue(result is Decision.Reject)
    }

    @Test
    fun `ставка с учётом подачи строже обычной`() {
        // 500 / 10 = 50 за км маршрута, но 500 / 12 ≈ 41,7 с подачей.
        assertEquals(Decision.Accept, OrderFilter.decide(order, FilterConfig(minPricePerKm = 45.0)))
        assertTrue(
            OrderFilter.decide(order, FilterConfig(minPricePerTotalKm = 45.0)) is Decision.Reject,
        )
    }

    @Test
    fun `низкий коэффициент — отказ`() {
        assertTrue(OrderFilter.decide(order, FilterConfig(minSurge = 1.5)) is Decision.Reject)
    }

    @Test
    fun `стоп-слово важнее всех остальных правил`() {
        val cfg = FilterConfig(blacklist = listOf("маршрут"))
        val result = OrderFilter.decide(order, cfg)
        assertTrue(result is Decision.Reject)
        assertTrue((result as Decision.Reject).reason.contains("стоп-слово"))
    }

    @Test
    fun `нет обязательного слова — отказ`() {
        val cfg = FilterConfig(requiredWords = listOf("аэропорт"))
        assertTrue(OrderFilter.decide(order, cfg) is Decision.Reject)
    }

    @Test
    fun `нераспознанная сумма не принимается по умолчанию`() {
        val unknown = order.copy(price = null)
        assertTrue(OrderFilter.decide(unknown, FilterConfig()) is Decision.Reject)
        assertEquals(
            Decision.Accept,
            OrderFilter.decide(unknown, FilterConfig(requireKnownPrice = false)),
        )
    }

    @Test
    fun `нераспознанное расстояние не проходит правило-ограничение`() {
        val unknown = order.copy(pickupKm = null)
        assertTrue(OrderFilter.decide(unknown, FilterConfig(maxPickupKm = 5.0)) is Decision.Reject)
    }

    @Test
    fun `правила переживают выгрузку и загрузку`() {
        val cfg = FilterConfig(
            minPrice = 350.0,
            maxPrice = 5000.0,
            minPricePerKm = 40.0,
            minPricePerTotalKm = 30.0,
            maxPickupKm = 4.0,
            maxPickupMin = 8.0,
            minTripKm = 1.0,
            maxTripKm = 60.0,
            minSurge = 1.2,
            blacklist = listOf("наличные", "домодедово"),
            requiredWords = listOf("такси"),
            requireKnownPrice = false,
        )
        assertEquals(cfg, RulesCodec.decode(RulesCodec.encode(cfg)))
    }
}
