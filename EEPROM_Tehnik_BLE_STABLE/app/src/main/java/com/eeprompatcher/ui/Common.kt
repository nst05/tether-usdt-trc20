package com.eeprompatcher.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.width
import androidx.compose.material3.FilterChip
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

// Выбор коэффициента чипами 1000 / 2000.
@Composable
fun CoefSelector(value: Int, onChange: (Int) -> Unit) {
    Row {
        FilterChip(selected = value == 1000, onClick = { onChange(1000) }, label = { Text("1000") })
        Spacer(Modifier.width(6.dp))
        FilterChip(selected = value == 2000, onClick = { onChange(2000) }, label = { Text("2000") })
    }
}

@Composable
fun <T> RadioGroup(options: List<Pair<T, String>>, selected: T, onSelect: (T) -> Unit) {
    Column {
        options.forEach { (value, label) ->
            Row(verticalAlignment = Alignment.CenterVertically) {
                RadioButton(selected = selected == value, onClick = { onSelect(value) })
                Text(label)
            }
        }
    }
}
