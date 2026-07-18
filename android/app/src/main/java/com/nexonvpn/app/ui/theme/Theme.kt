package com.nexonvpn.app.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

// ── Палитра NexonVPN ──────────────────────────────────────────────
val NexonBg = Color(0xFF060B12)
val NexonSurface = Color(0xFF0D1826)
val NexonSurfaceVariant = Color(0xFF12233A)
val NexonPrimary = Color(0xFF24E5C6)      // неоновый бирюзовый акцент
val NexonPrimaryDim = Color(0xFF1BB49B)
val NexonAccent = Color(0xFF3FA9FF)
val NexonOnBg = Color(0xFFE7F0F7)
val NexonMuted = Color(0xFF8199B0)
val NexonDanger = Color(0xFFFF5C6C)
val NexonWarn = Color(0xFFFFC24B)

private val NexonColorScheme = darkColorScheme(
    primary = NexonPrimary,
    onPrimary = Color(0xFF00201B),
    secondary = NexonAccent,
    background = NexonBg,
    onBackground = NexonOnBg,
    surface = NexonSurface,
    onSurface = NexonOnBg,
    surfaceVariant = NexonSurfaceVariant,
    onSurfaceVariant = NexonMuted,
    error = NexonDanger,
    outline = Color(0xFF24384F),
)

private val NexonTypography = Typography(
    titleLarge = TextStyle(fontWeight = FontWeight.SemiBold, fontSize = 22.sp),
    titleMedium = TextStyle(fontWeight = FontWeight.Medium, fontSize = 17.sp),
    bodyLarge = TextStyle(fontSize = 16.sp),
    bodyMedium = TextStyle(fontSize = 14.sp),
    labelSmall = TextStyle(fontWeight = FontWeight.Medium, fontSize = 12.sp, letterSpacing = 0.6.sp),
)

@Composable
fun NexonTheme(content: @Composable () -> Unit) {
    // Приложение всегда в тёмной теме (брендовый стиль), системный флаг игнорируем.
    @Suppress("UNUSED_EXPRESSION") isSystemInDarkTheme()
    MaterialTheme(
        colorScheme = NexonColorScheme,
        typography = NexonTypography,
        content = content,
    )
}
