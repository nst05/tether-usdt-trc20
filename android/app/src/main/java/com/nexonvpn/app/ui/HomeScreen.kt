package com.nexonvpn.app.ui

import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
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
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.nexonvpn.app.MainViewModel
import com.nexonvpn.app.R
import com.nexonvpn.app.ui.theme.*
import com.nexonvpn.app.vpn.VpnStatus

@Composable
fun HomeScreen(
    vm: MainViewModel,
    onConnect: () -> Unit,
    onDisconnect: () -> Unit,
) {
    val ui by vm.ui.collectAsStateWithLifecycle()
    val status by vm.vpnStatus.collectAsStateWithLifecycle()
    var showServers by remember { mutableStateOf(false) }

    Box(
        Modifier
            .fillMaxSize()
            .background(
                Brush.verticalGradient(listOf(Color(0xFF071018), NexonBg, Color(0xFF04070C)))
            )
    ) {
        Column(
            Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 24.dp)
                .padding(top = 56.dp, bottom = 32.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            NexonLogo(size = 76.dp)
            Spacer(Modifier.height(14.dp))
            Text("NEXONVPN", color = NexonOnBg, fontSize = 22.sp, fontWeight = FontWeight.Bold, letterSpacing = 4.sp)
            Text(stringResource(R.string.tagline), color = NexonMuted, fontSize = 13.sp)

            Spacer(Modifier.height(48.dp))

            ConnectOrb(status = status, onClick = { if (status == VpnStatus.CONNECTED) onDisconnect() else onConnect() })

            Spacer(Modifier.height(20.dp))
            Text(
                statusLabel(status),
                color = when (status) {
                    VpnStatus.CONNECTED -> NexonPrimary
                    VpnStatus.ERROR -> NexonDanger
                    else -> NexonMuted
                },
                fontSize = 15.sp,
                fontWeight = FontWeight.Medium,
            )

            Spacer(Modifier.height(40.dp))

            when {
                ui.loading -> LoadingCard()
                ui.error != null -> ErrorCard(ui.error!!) { vm.refresh() }
                ui.sub != null -> {
                    SubscriptionCard(ui.sub!!)
                    Spacer(Modifier.height(14.dp))
                    ServerSelector(
                        current = ui.sub!!.servers.getOrNull(ui.selected)?.name ?: stringResource(R.string.auto_fastest),
                        enabled = ui.sub!!.servers.isNotEmpty() && status != VpnStatus.CONNECTED,
                        onClick = { showServers = true },
                    )
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
}

@Composable
private fun ConnectOrb(status: VpnStatus, onClick: () -> Unit) {
    val transition = rememberInfiniteTransition(label = "orb")
    val pulse by transition.animateFloat(
        initialValue = 0.85f, targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(1400), RepeatMode.Reverse), label = "pulse",
    )
    val active = status == VpnStatus.CONNECTED
    val connecting = status == VpnStatus.CONNECTING
    val ring = if (active) NexonPrimary else if (status == VpnStatus.ERROR) NexonDanger else NexonSurfaceVariant

    Box(contentAlignment = Alignment.Center) {
        // Свечение
        Box(
            Modifier
                .size(220.dp)
                .clip(CircleShape)
                .background(
                    Brush.radialGradient(
                        listOf(
                            (if (active) NexonPrimary else Color(0xFF16324A)).copy(alpha = if (active) 0.30f * pulse else 0.12f),
                            Color.Transparent,
                        )
                    )
                )
        )
        Box(
            Modifier
                .size(168.dp)
                .clip(CircleShape)
                .background(Brush.verticalGradient(listOf(NexonSurface, Color(0xFF0A1420))))
                .clickable(enabled = !connecting, onClick = onClick),
            contentAlignment = Alignment.Center,
        ) {
            Box(
                Modifier
                    .size(if (active) 150.dp * pulse else 150.dp)
                    .clip(CircleShape)
                    .background(Color.Transparent),
                contentAlignment = Alignment.Center,
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    NexonPowerGlyph(color = ring)
                    Spacer(Modifier.height(8.dp))
                    Text(
                        when (status) {
                            VpnStatus.CONNECTED -> stringResource(R.string.disconnect)
                            VpnStatus.CONNECTING -> stringResource(R.string.connecting)
                            else -> stringResource(R.string.connect)
                        },
                        color = ring, fontSize = 13.sp, fontWeight = FontWeight.SemiBold,
                    )
                }
            }
        }
    }
}

@Composable
private fun SubscriptionCard(sub: com.nexonvpn.app.data.SubscriptionState) {
    Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = NexonSurface), shape = RoundedCornerShape(18.dp)) {
        Row(Modifier.padding(18.dp), verticalAlignment = Alignment.CenterVertically) {
            StatColumn(
                title = stringResource(R.string.days_left),
                value = if (sub.status == "ACTIVE") sub.daysLeft.toString() else "—",
                accent = sub.status == "ACTIVE",
                modifier = Modifier.weight(1f),
            )
            VerticalDivider(Modifier.height(40.dp), color = NexonSurfaceVariant)
            StatColumn(
                title = stringResource(R.string.traffic),
                value = when {
                    sub.trafficLimit.equals("Unlimited", true) || sub.trafficLimit.isBlank() -> stringResource(R.string.unlimited)
                    else -> "${sub.trafficUsed} / ${sub.trafficLimit}"
                },
                accent = false,
                modifier = Modifier.weight(1f),
            )
        }
        if (sub.status != "ACTIVE") {
            Text(
                statusMessage(sub.status),
                color = NexonWarn,
                fontSize = 13.sp,
                textAlign = TextAlign.Center,
                modifier = Modifier.fillMaxWidth().padding(bottom = 14.dp, start = 16.dp, end = 16.dp),
            )
        }
    }
}

@Composable
private fun StatColumn(title: String, value: String, accent: Boolean, modifier: Modifier = Modifier) {
    Column(modifier, horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value, color = if (accent) NexonPrimary else NexonOnBg, fontSize = 20.sp, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(2.dp))
        Text(title, color = NexonMuted, fontSize = 12.sp)
    }
}

@Composable
private fun ServerSelector(current: String, enabled: Boolean, onClick: () -> Unit) {
    Card(
        Modifier.fillMaxWidth().then(if (enabled) Modifier.clickable(onClick = onClick) else Modifier),
        colors = CardDefaults.cardColors(containerColor = NexonSurface),
        shape = RoundedCornerShape(18.dp),
    ) {
        Row(Modifier.padding(18.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(10.dp).clip(CircleShape).background(NexonPrimary))
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(stringResource(R.string.servers), color = NexonMuted, fontSize = 12.sp)
                Text(current, color = NexonOnBg, fontSize = 16.sp, fontWeight = FontWeight.Medium)
            }
            Text("▾", color = NexonMuted, fontSize = 18.sp)
        }
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
    Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = NexonSurface), shape = RoundedCornerShape(18.dp)) {
        Row(Modifier.fillMaxWidth().padding(22.dp), horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically) {
            CircularProgressIndicator(color = NexonPrimary, strokeWidth = 2.dp, modifier = Modifier.size(20.dp))
            Spacer(Modifier.width(14.dp))
            Text(stringResource(R.string.preparing), color = NexonMuted, fontSize = 14.sp)
        }
    }
}

@Composable
private fun ErrorCard(error: String, onRetry: () -> Unit) {
    Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = NexonSurface), shape = RoundedCornerShape(18.dp)) {
        Column(Modifier.fillMaxWidth().padding(22.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Text(stringResource(R.string.error_register), color = NexonDanger, fontSize = 14.sp, textAlign = TextAlign.Center)
            Spacer(Modifier.height(12.dp))
            Button(onClick = onRetry, colors = ButtonDefaults.buttonColors(containerColor = NexonPrimary, contentColor = Color(0xFF00201B))) {
                Text(stringResource(R.string.retry), fontWeight = FontWeight.SemiBold)
            }
        }
    }
}

@Composable
private fun statusLabel(status: VpnStatus): String = when (status) {
    VpnStatus.CONNECTED -> stringResource(R.string.connected)
    VpnStatus.CONNECTING -> stringResource(R.string.connecting)
    VpnStatus.ERROR -> stringResource(R.string.disconnected)
    VpnStatus.DISCONNECTED -> stringResource(R.string.disconnected)
}

@Composable
private fun statusMessage(status: String): String = when (status) {
    "BLOCKED" -> stringResource(R.string.status_blocked)
    "EXPIRED" -> stringResource(R.string.status_expired)
    "DEVICE_LIMIT" -> stringResource(R.string.status_device_limit)
    else -> ""
}
