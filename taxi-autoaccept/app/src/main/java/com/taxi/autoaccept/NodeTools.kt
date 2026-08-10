package com.taxi.autoaccept

import android.graphics.Rect
import android.view.accessibility.AccessibilityNodeInfo

/**
 * Работа с деревом элементов чужого приложения: собрать текст экрана,
 * найти кнопку приёма и выгрузить дерево для настройки шаблонов.
 */
object NodeTools {

    private const val MAX_NODES = 3000

    /** Весь видимый текст экрана одной строкой — из него парсятся сумма и расстояния. */
    fun collectText(root: AccessibilityNodeInfo): String {
        val sb = StringBuilder()
        forEachNode(root) { node ->
            node.text?.toString()?.takeIf { it.isNotBlank() }?.let { sb.append(it).append(" | ") }
            node.contentDescription?.toString()?.takeIf { it.isNotBlank() }
                ?.let { sb.append(it).append(" | ") }
        }
        return sb.toString()
    }

    /**
     * Ищет кнопку приёма по тексту/описанию. Отсеивает похожие кнопки
     * («Принять условия»), а также невидимые и отключённые элементы.
     */
    fun findAcceptNode(
        root: AccessibilityNodeInfo,
        accept: Regex,
        deny: Regex,
    ): AccessibilityNodeInfo? {
        var found: AccessibilityNodeInfo? = null
        forEachNode(root) { node ->
            if (found != null) return@forEachNode
            if (!node.isVisibleToUser || !node.isEnabled) return@forEachNode
            val label = buildString {
                node.text?.let { append(it).append(' ') }
                node.contentDescription?.let { append(it) }
            }.trim()
            if (label.isEmpty() || label.length > 60) return@forEachNode
            if (!accept.containsMatchIn(label)) return@forEachNode
            if (deny.pattern.isNotEmpty() && deny.containsMatchIn(label)) return@forEachNode
            found = node
        }
        return found
    }

    /** Ближайший кликабельный предок (включая сам узел). */
    fun clickableSelfOrParent(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        var current: AccessibilityNodeInfo? = node
        var depth = 0
        while (current != null && depth < 8) {
            if (current.isClickable) return current
            current = current.parent
            depth++
        }
        return null
    }

    fun centerOf(node: AccessibilityNodeInfo): Pair<Float, Float> {
        val rect = Rect()
        node.getBoundsInScreen(rect)
        return rect.exactCenterX() to rect.exactCenterY()
    }

    /** Дамп дерева для режима обучения: по нему подбираются шаблоны кнопок. */
    fun dumpTree(root: AccessibilityNodeInfo): String {
        val sb = StringBuilder()
        dumpNode(root, 0, sb, intArrayOf(0))
        return sb.toString()
    }

    private fun dumpNode(
        node: AccessibilityNodeInfo?,
        depth: Int,
        sb: StringBuilder,
        counter: IntArray,
    ) {
        if (node == null || counter[0] >= MAX_NODES) return
        counter[0]++
        val text = node.text?.toString().orEmpty()
        val desc = node.contentDescription?.toString().orEmpty()
        val id = node.viewIdResourceName.orEmpty()
        if (text.isNotBlank() || desc.isNotBlank() || node.isClickable) {
            val rect = Rect().also { node.getBoundsInScreen(it) }
            sb.append(" ".repeat(depth.coerceAtMost(10)))
                .append(node.className ?: "?")
                .append(if (node.isClickable) " [clickable]" else "")
                .append(if (id.isNotEmpty()) " id=$id" else "")
                .append(if (text.isNotBlank()) " text=\"$text\"" else "")
                .append(if (desc.isNotBlank()) " desc=\"$desc\"" else "")
                .append(" @").append(rect.flattenToString())
                .append('\n')
        }
        for (i in 0 until node.childCount) {
            dumpNode(node.getChild(i), depth + 1, sb, counter)
        }
    }

    private fun forEachNode(root: AccessibilityNodeInfo, action: (AccessibilityNodeInfo) -> Unit) {
        val queue = ArrayDeque<AccessibilityNodeInfo>()
        queue.add(root)
        var visited = 0
        while (queue.isNotEmpty() && visited < MAX_NODES) {
            val node = queue.removeFirst()
            visited++
            action(node)
            for (i in 0 until node.childCount) {
                node.getChild(i)?.let { queue.add(it) }
            }
        }
    }
}
