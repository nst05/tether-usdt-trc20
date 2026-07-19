package com.nexonvpn.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.nexonvpn.app.data.remote.Tariff
import com.nexonvpn.app.ui.theme.*

private data class PayMethod(val id: String, val title: String)

private val PAY_METHODS = listOf(
    PayMethod("yookassa", "Банковская карта (ЮKassa)"),
    PayMethod("wata", "Карта (Wata)"),
    PayMethod("yoomoney", "ЮMoney"),
    PayMethod("platega", "Platega"),
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TariffsSheet(
    tariffs: List<Tariff>,
    onBuy: (tariffId: Int, method: String) -> Unit,
    onDismiss: () -> Unit,
) {
    var selected by remember { mutableStateOf<Tariff?>(null) }

    ModalBottomSheet(onDismissRequest = onDismiss, containerColor = NexonSurface) {
        Column(
            Modifier
                .fillMaxWidth()
                .heightIn(max = 560.dp)
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp)
                .padding(bottom = 28.dp),
        ) {
            Text(
                if (selected == null) "Тарифы" else "Способ оплаты",
                color = NexonOnBg, fontSize = 20.sp, fontWeight = FontWeight.SemiBold,
                modifier = Modifier.padding(vertical = 10.dp),
            )

            if (selected == null) {
                if (tariffs.isEmpty()) {
                    Text("Тарифы недоступны. Попробуйте позже.", color = NexonMuted, fontSize = 14.sp,
                        modifier = Modifier.padding(vertical = 24.dp))
                }
                tariffs.forEach { t ->
                    TariffRow(t) { selected = t }
                    Spacer(Modifier.height(10.dp))
                }
            } else {
                val t = selected!!
                Text(
                    "${t.name} · ${t.days} дн · ${priceLabel(t)}",
                    color = NexonMuted, fontSize = 14.sp, modifier = Modifier.padding(bottom = 12.dp),
                )
                PAY_METHODS.forEach { m ->
                    Row(
                        Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(14.dp))
                            .background(NexonSurfaceVariant)
                            .clickable { onBuy(t.id, m.id) }
                            .padding(16.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(m.title, color = NexonOnBg, fontSize = 15.sp, modifier = Modifier.weight(1f))
                        Text("→", color = NexonPrimary, fontSize = 18.sp)
                    }
                    Spacer(Modifier.height(8.dp))
                }
                Spacer(Modifier.height(8.dp))
                TextButton(onClick = { selected = null }) {
                    Text("← Назад к тарифам", color = NexonMuted)
                }
            }
        }
    }
}

@Composable
private fun TariffRow(t: Tariff, onClick: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .background(NexonSurfaceVariant)
            .clickable(onClick = onClick)
            .padding(16.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(t.name.ifBlank { "${t.days} дней" }, color = NexonOnBg, fontSize = 16.sp, fontWeight = FontWeight.Medium)
            val sub = buildString {
                append("${t.days} дней")
                if (t.trafficGb > 0) append(" · ${t.trafficGb} ГБ")
                if (t.limitIp > 0) append(" · до ${t.limitIp} устр.")
            }
            Text(sub, color = NexonMuted, fontSize = 13.sp)
        }
        Text(priceLabel(t), color = NexonPrimary, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
    }
}

private fun priceLabel(t: Tariff): String {
    val p = if (t.price % 1.0 == 0.0) t.price.toInt().toString() else t.price.toString()
    val cur = when (t.currency.uppercase()) {
        "RUB" -> "₽"; "USD" -> "$"; "EUR" -> "€"; else -> t.currency
    }
    return "$p $cur"
}
