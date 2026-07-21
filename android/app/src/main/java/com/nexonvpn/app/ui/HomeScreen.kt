package com.nexonvpn.app.ui

import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.nexonvpn.app.MainViewModel
import com.nexonvpn.app.R
import com.nexonvpn.app.data.SubscriptionState
import com.nexonvpn.app.ui.theme.*
import com.nexonvpn.app.vpn.VpnStatus

/** Стеклянная поверхность (Aurora): полупрозрачная заливка + светлая рамка. */
private fun Modifier.glass(radius: Int = 20) = this
    .clip(RoundedCornerShape(radius.dp))
    .background(GlassFill)
    .border(1.dp, GlassBorder, RoundedCornerShape(radius.dp))

@Composable
fun HomeScreen(
    vm: MainViewModel,
    onConnect: () -> Unit,
    onDisconnect: () -> Unit,
) {
    val ui by vm.ui.collectAsStateWithLifecycle()
    val status by vm.vpnStatus.collectAsStateWithLifecycle()
    val tariffs by vm.tariffs.collectAsStateWithLifecycle()
    var showServers by remember { mutableStateOf(false) }
    var showTariffs by remember { mutableStateOf(false) }
    val context = LocalContext.current

    Box(
        Modifier
            .fillMaxSize()
            .background(Brush.verticalGradient(listOf(AuroraBgTop, NexonBg, Color(0xFF04060E))))
    ) {
        // Фиолетовое свечение сверху-справа
        Box(
            Modifier
                .align(Alignment.TopEnd)
                .offset(x = 60.dp, y = (-80).dp)
                .size(360.dp)
                .background(Brush.radialGradient(listOf(AuroraViolet.copy(alpha = 0.55f), Color.Transparent)))
        )

        Column(
            Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 22.dp)
                .padding(top = 52.dp, bottom = 30.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            // Шапка
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Image(
                    painter = painterResource(R.drawable.nexon_logo),
                    contentDescription = null,
                    modifier = Modifier.size(30.dp),
                )
                Spacer(Modifier.width(10.dp))
                Text("NEXONVPN", color = NexonOnBg, fontSize = 15.sp, fontWeight = FontWeight.Bold, letterSpacing = 3.sp)
                Spacer(Modifier.weight(1f))
                Text("⋯", color = NexonMuted, fontSize = 20.sp)
            }

            Spacer(Modifier.height(44.dp))

            ConnectOrb(status = status, onClick = { if (status == VpnStatus.CONNECTED) onDisconnect() else onConnect() })

            Spacer(Modifier.height(16.dp))
            Text(
                statusSubtitle(status),
                color = when (status) {
                    VpnStatus.CONNECTED -> NexonTealSoft
                    VpnStatus.ERROR -> NexonDanger
                    else -> NexonMuted
                },
                fontSize = 13.sp,
            )

            Spacer(Modifier.height(44.dp))

            when {
                ui.loading -> LoadingCard()
                ui.error != null -> ErrorCard { vm.refresh() }
                ui.sub != null -> {
                    SubscriptionCard(ui.sub!!)
                    Spacer(Modifier.height(12.dp))
                    ServerSelector(
                        current = ui.sub!!.servers.getOrNull(ui.selected)?.name ?: stringResource(R.string.auto_fastest),
                        enabled = ui.sub!!.servers.isNotEmpty() && status != VpnStatus.CONNECTED,
                        onClick = { showServers = true },
                    )
                    Spacer(Modifier.height(12.dp))
                    TariffsButton { vm.loadTariffs(); showTariffs = true }
                }
            }
        }
    }

    if (showServers && ui.sub != null) {
        ServerSheet(
            servers = ui.sub!!.servers.map { it.name },
            selected = ui.selected,
            onSelect = { vm.selectServer(it); showServers = false },
            onDismiss = { showServers = false },
        )
    }

    if (showTariffs) {
        TariffsSheet(
            tariffs = tariffs,
            onBuy = { id, method ->
                vm.purchase(
                    id, method,
                    onUrl = { url ->
                        runCatching {
                            context.startActivity(
                                android.content.Intent(android.content.Intent.ACTION_VIEW, android.net.Uri.parse(url))
                                    .addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
                            )
                        }
                        showTariffs = false
                    },
                    onError = { android.widget.Toast.makeText(context, "Оплата недоступна: $it", android.widget.Toast.LENGTH_LONG).show() },
                )
            },
            onDismiss = { showTariffs = false },
        )
    }
}

@Composable
private fun ConnectOrb(status: VpnStatus, onClick: () -> Unit) {
    val transition = rememberInfiniteTransition(label = "orb")
    val pulse by transition.animateFloat(
        initialValue = 0.82f, targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(1500), RepeatMode.Reverse), label = "pulse",
    )
    val active = status == VpnStatus.CONNECTED
    val connecting = status == VpnStatus.CONNECTING
    val error = status == VpnStatus.ERROR

    val ringBrush = when {
        active -> Brush.sweepGradient(listOf(NexonPrimary, AuroraCyan, AuroraPurple, NexonPrimary))
        error -> SolidColor(NexonDanger)
        else -> SolidColor(NexonSurfaceVariant)
    }
    val iconColor = if (active) Color(0xFF5CF0D8) else if (error) NexonDanger else NexonMuted

    Box(contentAlignment = Alignment.Center) {
        // Свечение под кнопкой
        Box(
            Modifier
                .size(230.dp)
                .clip(CircleShape)
                .background(
                    Brush.radialGradient(
                        listOf(
                            (if (active) NexonPrimary else Color(0xFF16324A)).copy(alpha = if (active) 0.30f * pulse else 0.10f),
                            Color.Transparent,
                        )
                    )
                )
        )
        // Кольцо + внутренний круг
        Box(
            Modifier
                .size(if (active) 158.dp * (0.98f + 0.02f * pulse) else 158.dp)
                .clip(CircleShape)
                .background(ringBrush)
                .padding(3.dp)
                .clip(CircleShape)
                .background(Brush.verticalGradient(listOf(Color(0xFF16223F), Color(0xFF0A1020))))
                .clickable(enabled = !connecting, onClick = onClick),
            contentAlignment = Alignment.Center,
        ) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                NexonPowerGlyph(color = iconColor, size = 30.dp)
                Spacer(Modifier.height(8.dp))
                Text(
                    when (status) {
                        VpnStatus.CONNECTED -> stringResource(R.string.connected)
                        VpnStatus.CONNECTING -> stringResource(R.string.connecting)
                        else -> stringResource(R.string.connect)
                    },
                    color = if (active) Color(0xFFEAFFF9) else NexonOnBg,
                    fontSize = 13.sp, fontWeight = FontWeight.SemiBold,
                )
            }
        }
    }
}

@Composable
private fun SubscriptionCard(sub: SubscriptionState) {
    Column(Modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            StatTile(
                value = if (sub.status == "ACTIVE") sub.daysLeft.toString() else "—",
                title = stringResource(R.string.days_left),
                accent = sub.status == "ACTIVE",
                modifier = Modifier.weight(1f),
            )
            StatTile(
                value = when {
                    sub.trafficLimit.equals("Unlimited", true) || sub.trafficLimit.isBlank() -> stringResource(R.string.unlimited)
                    else -> sub.trafficUsed
                },
                title = stringResource(R.string.traffic),
                accent = false,
                modifier = Modifier.weight(1f),
            )
        }
        if (sub.status != "ACTIVE") {
            Spacer(Modifier.height(10.dp))
            Text(
                statusMessage(sub.status),
                color = NexonWarn, fontSize = 13.sp, textAlign = TextAlign.Center,
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}

@Composable
private fun StatTile(value: String, title: String, accent: Boolean, modifier: Modifier = Modifier) {
    Column(
        modifier.glass().padding(vertical = 14.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(value, color = if (accent) NexonPrimary else NexonOnBg, fontSize = 18.sp, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(2.dp))
        Text(title, color = NexonMuted, fontSize = 11.sp)
    }
}

@Composable
private fun ServerSelector(current: String, enabled: Boolean, onClick: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .glass()
            .then(if (enabled) Modifier.clickable(onClick = onClick) else Modifier)
            .padding(16.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(10.dp).clip(CircleShape).background(NexonPrimary))
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(stringResource(R.string.servers), color = NexonMuted, fontSize = 11.sp)
            Text(current, color = NexonOnBg, fontSize = 15.sp, fontWeight = FontWeight.Medium)
        }
        Text("›", color = NexonMuted, fontSize = 20.sp)
    }
}

@Composable
private fun TariffsButton(onClick: () -> Unit) {
    Box(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(18.dp))
            .background(Brush.horizontalGradient(listOf(NexonPrimary, AuroraCyan)))
            .clickable(onClick = onClick)
            .padding(vertical = 16.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text("Продлить · Тарифы и оплата", color = Color(0xFF04231F), fontSize = 15.sp, fontWeight = FontWeight.Bold)
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ServerSheet(servers: List<String>, selected: Int, onSelect: (Int) -> Unit, onDismiss: () -> Unit) {
    ModalBottomSheet(onDismissRequest = onDismiss, containerColor = NexonSurface) {
        Text(
            stringResource(R.string.servers),
            color = NexonOnBg, fontSize = 18.sp, fontWeight = FontWeight.SemiBold,
            modifier = Modifier.padding(horizontal = 24.dp, vertical = 8.dp),
        )
        servers.forEachIndexed { i, name ->
            Row(
                Modifier.fillMaxWidth().clickable { onSelect(i) }.padding(horizontal = 24.dp, vertical = 14.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Box(Modifier.size(8.dp).clip(CircleShape).background(if (i == selected) NexonPrimary else NexonSurfaceVariant))
                Spacer(Modifier.width(14.dp))
                Text(name, color = if (i == selected) NexonPrimary else NexonOnBg, fontSize = 15.sp)
            }
        }
        Spacer(Modifier.height(24.dp))
    }
}

@Composable
private fun LoadingCard() {
    Row(
        Modifier.fillMaxWidth().glass().padding(22.dp),
        horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically,
    ) {
        CircularProgressIndicator(color = NexonPrimary, strokeWidth = 2.dp, modifier = Modifier.size(20.dp))
        Spacer(Modifier.width(14.dp))
        Text(stringResource(R.string.preparing), color = NexonMuted, fontSize = 14.sp)
    }
}

@Composable
private fun ErrorCard(onRetry: () -> Unit) {
    Column(
        Modifier.fillMaxWidth().glass().padding(22.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(stringResource(R.string.error_register), color = NexonDanger, fontSize = 14.sp, textAlign = TextAlign.Center)
        Spacer(Modifier.height(12.dp))
        Box(
            Modifier
                .clip(RoundedCornerShape(14.dp))
                .background(Brush.horizontalGradient(listOf(NexonPrimary, AuroraCyan)))
                .clickable(onClick = onRetry)
                .padding(horizontal = 24.dp, vertical = 11.dp),
        ) {
            Text(stringResource(R.string.retry), color = Color(0xFF04231F), fontWeight = FontWeight.SemiBold)
        }
    }
}

@Composable
private fun statusSubtitle(status: VpnStatus): String = when (status) {
    VpnStatus.CONNECTED -> "Защищённое соединение активно"
    VpnStatus.CONNECTING -> stringResource(R.string.connecting)
    else -> "Соединение не защищено"
}

@Composable
private fun statusMessage(status: String): String = when (status) {
    "BLOCKED" -> stringResource(R.string.status_blocked)
    "EXPIRED" -> stringResource(R.string.status_expired)
    "DEVICE_LIMIT" -> stringResource(R.string.status_device_limit)
    else -> ""
}
