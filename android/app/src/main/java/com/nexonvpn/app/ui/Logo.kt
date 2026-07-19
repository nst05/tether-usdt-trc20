package com.nexonvpn.app.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.nexonvpn.app.ui.theme.NexonPrimary
import com.nexonvpn.app.ui.theme.NexonPrimaryDim

/**
 * Брендовая монограмма NexonVPN — зеркальные шевроны, образующие стилизованную «N»
 * (как в логотипе на заставке). Рисуется вектором, без растровых ассетов.
 */
@Composable
fun NexonLogo(size: Dp = 72.dp, modifier: Modifier = Modifier) {
    Canvas(modifier = modifier.size(size)) {
        val w = this.size.width
        val h = this.size.height
        val sw = w * 0.10f
        val stroke = Stroke(width = sw, cap = StrokeCap.Round)

        // Левый шеврон ">"
        val left = Path().apply {
            moveTo(w * 0.20f, h * 0.15f)
            lineTo(w * 0.44f, h * 0.50f)
            lineTo(w * 0.20f, h * 0.85f)
        }
        // Правый шеврон "<"
        val right = Path().apply {
            moveTo(w * 0.80f, h * 0.15f)
            lineTo(w * 0.56f, h * 0.50f)
            lineTo(w * 0.80f, h * 0.85f)
        }
        // Диагональ N
        val diag = Path().apply {
            moveTo(w * 0.30f, h * 0.82f)
            lineTo(w * 0.70f, h * 0.18f)
        }

        drawPath(diag, color = NexonPrimaryDim, style = Stroke(width = sw * 0.8f, cap = StrokeCap.Round))
        drawPath(left, color = NexonPrimary, style = stroke)
        drawPath(right, color = NexonPrimary, style = stroke)
    }
}

/** Иконка питания в центре кнопки подключения. */
@Composable
fun NexonPowerGlyph(color: androidx.compose.ui.graphics.Color, size: Dp = 34.dp) {
    Canvas(modifier = Modifier.size(size)) {
        val w = this.size.width
        val sw = w * 0.11f
        // Дуга
        drawArc(
            color = color,
            startAngle = -50f,
            sweepAngle = 280f,
            useCenter = false,
            style = Stroke(width = sw, cap = StrokeCap.Round),
        )
        // Вертикальная черта
        drawLine(
            color = color,
            start = Offset(w / 2f, 0f),
            end = Offset(w / 2f, w * 0.42f),
            strokeWidth = sw,
            cap = StrokeCap.Round,
        )
    }
}
