package com.eeprompatcher.ui.theme

import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

// --- Палитра «измерительный прибор» ---
// Корпус: графит. Акцент: зелёный семисегментного индикатора. Янтарь: предупреждения.
val MeterBg          = Color(0xFF0E1116)   // корпус прибора, фон
val MeterSurface     = Color(0xFF171B22)   // панель
val MeterSurfaceHi   = Color(0xFF1F2530)   // приподнятая панель
val MeterDisplay     = Color(0xFF0A0D11)   // «экран» табло (темнее фона)
val MeterGreen       = Color(0xFF4ADE80)   // акцент — индикатор
val MeterGreenDim    = Color(0xFF2A8C4A)   // приглушённый зелёный
val MeterAmber       = Color(0xFFFFB020)   // предупреждение
val MeterRed         = Color(0xFFFF5A52)   // ошибка/BAD
val MeterText        = Color(0xFFE6EAF0)   // основной текст
val MeterTextDim     = Color(0xFF8A93A3)   // вторичный текст
val MeterBorder      = Color(0xFF2A303B)   // границы панелей

val MeterColorScheme = darkColorScheme(
    primary = MeterGreen,
    onPrimary = Color(0xFF07120B),
    secondary = MeterGreenDim,
    background = MeterBg,
    onBackground = MeterText,
    surface = MeterSurface,
    onSurface = MeterText,
    surfaceVariant = MeterSurfaceHi,
    onSurfaceVariant = MeterTextDim,
    error = MeterRed,
    outline = MeterBorder,
)

// Моноширинный — для числовых значений (как табло прибора).
val MonoFamily = FontFamily.Monospace

val MeterTypography = Typography(
    headlineSmall = TextStyle(
        fontWeight = FontWeight.SemiBold,
        fontSize = 20.sp,
        letterSpacing = 0.5.sp,
        color = MeterText
    ),
    titleMedium = TextStyle(
        fontWeight = FontWeight.Medium,
        fontSize = 16.sp,
        letterSpacing = 0.3.sp,
        color = MeterText
    ),
    bodyMedium = TextStyle(
        fontWeight = FontWeight.Normal,
        fontSize = 14.sp,
        color = MeterText
    ),
    bodySmall = TextStyle(
        fontWeight = FontWeight.Normal,
        fontSize = 12.sp,
        color = MeterTextDim
    ),
    labelLarge = TextStyle(
        fontWeight = FontWeight.Medium,
        fontSize = 13.sp,
        letterSpacing = 0.8.sp,
    ),
)

// Стиль для числового «табло» — моноширинные крупные цифры.
val DisplayValueStyle = TextStyle(
    fontFamily = MonoFamily,
    fontWeight = FontWeight.Medium,
    fontSize = 22.sp,
    letterSpacing = 1.sp,
    color = MeterGreen
)
