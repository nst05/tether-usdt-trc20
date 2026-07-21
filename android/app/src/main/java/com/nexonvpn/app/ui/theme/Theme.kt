package com.nexonvpn.app.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

// ── Палитра NexonVPN · Aurora ─────────────────────────────────────
val NexonBg = Color(0xFF080B18)            // низ фонового градиента
val AuroraBgTop = Color(0xFF141A34)        // верх фонового градиента
val AuroraViolet = Color(0xFF3A2170)       // фиолетовое свечение сверху
val NexonSurface = Color(0xFF121A2E)       // тёмная панель (шторки/боттом-шит)
val NexonSurfaceVariant = Color(0xFF1B2540)

val NexonPrimary = Color(0xFF2EE7CF)       // бирюзовый акцент
val AuroraCyan = Color(0xFF37C2FF)         // голубой (в градиенте кнопки/CTA)
val AuroraPurple = Color(0xFF7A5CFF)       // фиолетовый (в кольце кнопки)
val NexonPrimaryDim = Color(0xFF1BB49B)

val NexonOnBg = Color(0xFFEAF2FF)
val NexonMuted = Color(0xFF8FA3BE)
val NexonTealSoft = Color(0xFF8FE9D8)      // подпись под кнопкой
val NexonDanger = Color(0xFFFF6B7D)
val NexonWarn = Color(0xFFFFC24B)

// Стекло
val GlassFill = Color(0x14FFFFFF)          // белый ~8%
val GlassBorder = Color(0x24FFFFFF)        // белый ~14%

private val NexonColorScheme = darkColorScheme(
    primary = NexonPrimary,
    onPrimary = Color(0xFF04231F),
    secondary = AuroraCyan,
    background = NexonBg,
    onBackground = NexonOnBg,
    surface = NexonSurface,
    onSurface = NexonOnBg,
    surfaceVariant = NexonSurfaceVariant,
    onSurfaceVariant = NexonMuted,
    error = NexonDanger,
    outline = GlassBorder,
)

private val NexonTypography = Typography(
    titleLarge = TextStyle(fontWeight = FontWeight.Bold, fontSize = 22.sp),
    titleMedium = TextStyle(fontWeight = FontWeight.SemiBold, fontSize = 17.sp),
    bodyLarge = TextStyle(fontSize = 16.sp),
    bodyMedium = TextStyle(fontSize = 14.sp),
    labelSmall = TextStyle(fontWeight = FontWeight.Medium, fontSize = 12.sp, letterSpacing = 0.6.sp),
)

@Composable
fun NexonTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = NexonColorScheme,
        typography = NexonTypography,
        content = content,
    )
}
