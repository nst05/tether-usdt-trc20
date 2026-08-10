package com.taxi.autoaccept.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class OrderParserTest {

    @Test
    fun `карточка Яндекс Про — цена, подача, маршрут`() {
        val text = "Новый заказ | 450 ₽ | Подача 2,4 км · 5 мин | Маршрут 8,6 км | Принять"
        val order = OrderParser.parse(text)

        assertEquals(450.0, order.price!!, 0.01)
        assertEquals("₽", order.currency)
        assertEquals(2.4, order.pickupKm!!, 0.01)
        assertEquals(5.0, order.pickupMin!!, 0.01)
        assertEquals(8.6, order.tripKm!!, 0.01)
    }

    @Test
    fun `цена с разделителем тысяч`() {
        val order = OrderParser.parse("1 250 руб. | Подача 1,2 км")
        assertEquals(1250.0, order.price!!, 0.01)
    }

    @Test
    fun `метры переводятся в километры`() {
        val order = OrderParser.parse("300 ₽ | подача 800 м | маршрут 3,5 км")
        assertEquals(0.8, order.pickupKm!!, 0.001)
        assertEquals(3.5, order.tripKm!!, 0.001)
    }

    @Test
    fun `без меток первое расстояние это подача, второе маршрут`() {
        val order = OrderParser.parse("520 сум | 1,5 км | 12 км | Принять")
        assertEquals(1.5, order.pickupKm!!, 0.01)
        assertEquals(12.0, order.tripKm!!, 0.01)
    }

    @Test
    fun `подача с меткой не считается маршрутом`() {
        val order = OrderParser.parse("700 ₽ | подача 3 км | 14 км до точки")
        assertEquals(3.0, order.pickupKm!!, 0.01)
        assertEquals(14.0, order.tripKm!!, 0.01)
    }

    @Test
    fun `коэффициент спроса`() {
        val order = OrderParser.parse("890 ₽ ×1,7 | подача 2 км | маршрут 9 км")
        assertEquals(1.7, order.surge!!, 0.01)
    }

    @Test
    fun `нет цены — поле пустое, а не ноль`() {
        val order = OrderParser.parse("Ожидание заказов")
        assertNull(order.price)
        assertNull(order.tripKm)
    }

    @Test
    fun `ставка за км считается с подачей и без`() {
        val order = OrderParser.parse("600 ₽ | подача 2 км | маршрут 10 км")
        assertEquals(60.0, order.pricePerKm!!, 0.01)
        assertEquals(50.0, order.pricePerTotalKm!!, 0.01)
    }

    @Test
    fun `карточка регионального диспетчера — Анжи Такси`() {
        val text = "Заказ №1523 | Стоимость 250 руб | Подача 1,2 км | " +
            "ул. Ленина, 5 — пр. Шамиля, 40 | 6,3 км | Взять заказ"
        val order = OrderParser.parse(text)

        assertEquals(250.0, order.price!!, 0.01)
        assertEquals(1.2, order.pickupKm!!, 0.01)
        assertEquals(6.3, order.tripKm!!, 0.01)
    }

    @Test
    fun `номер заказа и дом не путаются с суммой`() {
        val order = OrderParser.parse("Заказ 1523 | ул. Ленина 5 | Стоимость 250 руб")
        assertEquals(250.0, order.price!!, 0.01)
    }
}
