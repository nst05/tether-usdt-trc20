package com.eeprompatcher.ui.theme

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp

// Панель прибора — приподнятая поверхность с рамкой. modifier применяется
// снаружи (можно навесить clickable и т.п.).
@Composable
fun MeterPanel(
    modifier: Modifier = Modifier,
    content: @Composable ColumnScope.() -> Unit
) {
    Column(
        modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(14.dp))
            .background(MeterSurface)
            .border(1.dp, MeterBorder, RoundedCornerShape(14.dp))
            .padding(16.dp),
        content = content
    )
}

// Табло значения «только чтение» — как экран прибора: моноширинные зелёные цифры
// на тёмной подложке. Для текущих/вычисленных значений.
@Composable
fun DisplayField(label: String, value: String, modifier: Modifier = Modifier) {
    Column(modifier.fillMaxWidth()) {
        Text(
            label.uppercase(),
            style = MeterTypography.labelLarge,
            color = MeterTextDim
        )
        Spacer(Modifier.height(6.dp))
        Box(
            Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(10.dp))
                .background(MeterDisplay)
                .border(1.dp, MeterBorder, RoundedCornerShape(10.dp))
                .padding(horizontal = 14.dp, vertical = 12.dp)
        ) {
            Text(value.ifEmpty { "—" }, style = DisplayValueStyle)
        }
    }
}

// Поле ввода в приборном стиле — редактируемое значение.
@Composable
fun MeterInput(
    label: String,
    value: String,
    onValueChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    numeric: Boolean = true
) {
    Column(modifier.fillMaxWidth()) {
        Text(
            label.uppercase(),
            style = MeterTypography.labelLarge,
            color = MeterTextDim
        )
        Spacer(Modifier.height(6.dp))
        OutlinedTextField(
            value = value,
            onValueChange = onValueChange,
            singleLine = true,
            textStyle = DisplayValueStyle.copy(color = MeterText),
            keyboardOptions = if (numeric)
                KeyboardOptions(keyboardType = KeyboardType.Number) else KeyboardOptions.Default,
            colors = OutlinedTextFieldDefaults.colors(
                focusedBorderColor = MeterGreen,
                unfocusedBorderColor = MeterBorder,
                focusedContainerColor = MeterDisplay,
                unfocusedContainerColor = MeterDisplay,
            ),
            shape = RoundedCornerShape(10.dp),
            modifier = Modifier.fillMaxWidth()
        )
    }
}

// Кнопка основного действия — «зажигается» зелёным как индикатор.
@Composable
fun MeterPrimaryButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true
) {
    Button(
        onClick = onClick,
        enabled = enabled,
        shape = RoundedCornerShape(12.dp),
        colors = ButtonDefaults.buttonColors(
            containerColor = MeterGreen,
            contentColor = MeterBg,
            disabledContainerColor = MeterSurfaceHi,
            disabledContentColor = MeterTextDim
        ),
        modifier = modifier
            .fillMaxWidth()
            .height(52.dp)
    ) {
        Text(text, style = MeterTypography.labelLarge)
    }
}

// Статус-индикатор: маленький «светодиод» + подпись. Для CRC OK/BAD.
@Composable
fun StatusLed(label: String, ok: Boolean) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(
            Modifier
                .size(8.dp)
                .clip(RoundedCornerShape(4.dp))
                .background(if (ok) MeterGreen else MeterRed)
        )
        Spacer(Modifier.width(6.dp))
        Text(
            label,
            style = MeterTypography.bodySmall,
            color = if (ok) MeterGreen else MeterRed
        )
    }
}
