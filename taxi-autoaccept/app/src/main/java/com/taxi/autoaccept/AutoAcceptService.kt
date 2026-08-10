package com.taxi.autoaccept

import com.taxi.autoaccept.core.Decision
import com.taxi.autoaccept.core.OrderFilter
import com.taxi.autoaccept.core.OrderInfo
import com.taxi.autoaccept.core.OrderParser

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.graphics.Path
import android.os.Build
import android.os.SystemClock
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.view.KeyEvent
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import java.util.Calendar

/**
 * Ядро автоприёма.
 *
 * Служба слушает изменения экрана выбранного приложения такси, собирает текст карточки,
 * прогоняет его через фильтры и либо сама нажимает «Принять», либо озвучивает заказ
 * и ждёт подтверждения кнопкой громкости — чтобы не отвлекаться на экран за рулём.
 */
class AutoAcceptService : AccessibilityService() {

    private lateinit var prefs: Prefs
    private var speaker: Speaker? = null

    private var lastScanAt = 0L
    private var lastAcceptAt = 0L
    private var lastDumpAt = 0L
    private var lastScreenHash = 0
    private val acceptTimestamps = ArrayDeque<Long>()

    private var pendingSince = 0L
    private var pendingSummary = ""

    override fun onServiceConnected() {
        super.onServiceConnected()
        prefs = Prefs(this)
        speaker = Speaker(this)
        EventLog.add(this, "служба подключена")
        Notifications.show(this, prefs.enabled, statusLine())
    }

    override fun onDestroy() {
        speaker?.shutdown()
        speaker = null
        Notifications.hide(this)
        super.onDestroy()
    }

    override fun onInterrupt() = Unit

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (!::prefs.isInitialized || !prefs.enabled) return

        val target = prefs.targetPackage
        if (target.isEmpty() || event?.packageName?.toString() != target) return

        val now = SystemClock.elapsedRealtime()
        if (now - lastScanAt < SCAN_THROTTLE_MS) return
        lastScanAt = now

        val root = rootInActiveWindow ?: return

        if (prefs.learnMode && now - lastDumpAt > DUMP_INTERVAL_MS) {
            lastDumpAt = now
            EventLog.add(this, "--- дерево экрана ---\n" + NodeTools.dumpTree(root))
        }

        expirePendingConfirm(now)
        if (pendingSince != 0L) return
        if (now - lastAcceptAt < prefs.cooldownSec * 1000L) return
        if (!prefs.isWithinWorkHours(currentHour())) return
        if (hourlyLimitReached()) return

        val acceptNode = NodeTools.findAcceptNode(root, acceptRegex(), denyRegex()) ?: return

        val screenText = NodeTools.collectText(root)
        val hash = screenText.hashCode()
        if (hash == lastScreenHash) return
        lastScreenHash = hash

        val order = OrderParser.parse(screenText)
        when (val decision = OrderFilter.decide(order, prefs.toFilterConfig())) {
            is Decision.Reject -> {
                EventLog.add(this, "пропуск: ${decision.reason} · ${summary(order)}")
            }

            Decision.Accept -> {
                if (prefs.autoMode) {
                    acceptNow(acceptNode, order)
                } else {
                    armConfirm(order)
                }
            }
        }
    }

    /**
     * В режиме подтверждения кнопки громкости перехватываются только пока
     * висит объявленный заказ — в остальное время громкость работает как обычно.
     */
    override fun onKeyEvent(event: KeyEvent?): Boolean {
        if (event == null || pendingSince == 0L) return false
        if (event.action != KeyEvent.ACTION_DOWN) {
            // Гасим и ACTION_UP пойманных клавиш, иначе система покажет ползунок громкости.
            return event.keyCode == KeyEvent.KEYCODE_VOLUME_UP ||
                event.keyCode == KeyEvent.KEYCODE_VOLUME_DOWN
        }
        return when (event.keyCode) {
            KeyEvent.KEYCODE_VOLUME_UP -> {
                val root = rootInActiveWindow
                val node = root?.let { NodeTools.findAcceptNode(it, acceptRegex(), denyRegex()) }
                if (node != null) {
                    acceptNow(node, null, pendingSummary)
                } else {
                    EventLog.add(this, "подтверждение: кнопка приёма уже исчезла")
                    speaker?.say("Заказ уже недоступен")
                }
                clearPending()
                true
            }

            KeyEvent.KEYCODE_VOLUME_DOWN -> {
                EventLog.add(this, "отказ водителя · $pendingSummary")
                speaker?.say("Пропускаю")
                clearPending()
                true
            }

            else -> false
        }
    }

    private fun armConfirm(order: OrderInfo) {
        pendingSince = SystemClock.elapsedRealtime()
        pendingSummary = summary(order)
        vibrate(120)
        speaker?.say("Заказ. $pendingSummary. Громкость вверх — принять")
        EventLog.add(this, "жду подтверждения · $pendingSummary")
    }

    private fun expirePendingConfirm(now: Long) {
        if (pendingSince == 0L) return
        if (now - pendingSince > prefs.confirmWindowSec * 1000L) {
            EventLog.add(this, "подтверждение не получено · $pendingSummary")
            clearPending()
        }
    }

    private fun clearPending() {
        pendingSince = 0L
        pendingSummary = ""
    }

    private fun acceptNow(
        node: AccessibilityNodeInfo,
        order: OrderInfo?,
        fallbackSummary: String = "",
    ) {
        val clicked = click(node)
        val now = SystemClock.elapsedRealtime()
        lastAcceptAt = now
        acceptTimestamps.addLast(now)

        val text = order?.let { summary(it) } ?: fallbackSummary
        if (clicked) {
            vibrate(60)
            if (prefs.speak) speaker?.say("Принял. $text")
            EventLog.add(this, "ПРИНЯТ · $text")
        } else {
            EventLog.add(this, "не удалось нажать кнопку · $text")
        }
    }

    /**
     * Сначала обычный клик по ближайшему кликабельному предку, а если разметка
     * нарисована кастомно (Flutter, игровые движки) — жест-тап по центру кнопки.
     */
    private fun click(node: AccessibilityNodeInfo): Boolean {
        NodeTools.clickableSelfOrParent(node)?.let {
            if (it.performAction(AccessibilityNodeInfo.ACTION_CLICK)) return true
        }
        val (x, y) = NodeTools.centerOf(node)
        if (x <= 0f || y <= 0f) return false
        val path = Path().apply { moveTo(x, y) }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0L, 60L))
            .build()
        return dispatchGesture(gesture, null, null)
    }

    private fun hourlyLimitReached(): Boolean {
        val limit = prefs.maxPerHour
        if (limit <= 0) return false
        val hourAgo = SystemClock.elapsedRealtime() - 3_600_000L
        while (acceptTimestamps.isNotEmpty() && acceptTimestamps.first() < hourAgo) {
            acceptTimestamps.removeFirst()
        }
        if (acceptTimestamps.size < limit) return false
        EventLog.add(this, "лимит $limit заказов в час исчерпан")
        return true
    }

    private fun summary(order: OrderInfo): String = buildList {
        order.price?.let { add("${trim(it)} ${order.currency ?: ""}".trim()) }
        order.pickupKm?.let { add("подача ${trim(it)} км") }
        order.pickupMin?.let { add("${trim(it)} мин") }
        order.tripKm?.let { add("маршрут ${trim(it)} км") }
        order.surge?.let { add("коэф. ${trim(it)}") }
    }.joinToString(", ").ifEmpty { "без данных" }

    private fun trim(v: Double): String =
        if (v == v.toLong().toDouble()) v.toLong().toString() else String.format("%.1f", v)

    private fun statusLine(): String {
        val target = prefs.targetPackage.ifEmpty { getString(R.string.no_app_selected) }
        return "$target · ${if (prefs.autoMode) "авто" else "по кнопке"}"
    }

    private fun currentHour(): Int = Calendar.getInstance().get(Calendar.HOUR_OF_DAY)

    private fun acceptRegex(): Regex =
        runCatching { Regex(prefs.acceptRegex) }.getOrElse { Regex(Prefs.DEFAULT_ACCEPT_REGEX) }

    private fun denyRegex(): Regex =
        runCatching { Regex(prefs.denyRegex) }.getOrElse { Regex(Prefs.DEFAULT_DENY_REGEX) }

    private fun vibrate(ms: Long) {
        val vibrator = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            getSystemService(VibratorManager::class.java)?.defaultVibrator
        } else {
            @Suppress("DEPRECATION")
            getSystemService(Vibrator::class.java)
        }
        runCatching {
            vibrator?.vibrate(VibrationEffect.createOneShot(ms, VibrationEffect.DEFAULT_AMPLITUDE))
        }
    }

    companion object {
        private const val SCAN_THROTTLE_MS = 250L
        private const val DUMP_INTERVAL_MS = 3000L
    }
}
