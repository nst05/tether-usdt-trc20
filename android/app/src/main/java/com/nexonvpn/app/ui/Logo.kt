package com.nexonvpn.app.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

/** Иконка питания в центре кнопки подключения. */
@Composable
fun NexonPowerGlyph(color: Color, size: Dp = 34.dp) {
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
