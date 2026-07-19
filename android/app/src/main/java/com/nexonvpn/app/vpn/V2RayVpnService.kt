package com.nexonvpn.app.vpn

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.VpnService
import android.os.Build
import android.os.ParcelFileDescriptor
import android.util.Log
import androidx.core.app.NotificationCompat
import com.nexonvpn.app.MainActivity
import com.nexonvpn.app.R
import libv2ray.CoreCallbackHandler
import libv2ray.CoreController
import libv2ray.Libv2ray
import java.io.File

/**
 * VPN-сервис NexonVPN на актуальном API AndroidLibXrayLite.
 *
 * Пайплайн: VpnService (TUN) → CoreController.startLoop(config, tunFd) → Xray-core.
 * Ядро принимает файловый дескриптор TUN напрямую и само мостит трафик
 * (внешний tun2socks не нужен). Чтобы исходящие соединения самого ядра не
 * заворачивались обратно в туннель, приложение исключается из VPN
 * (addDisallowedApplication) — отдельный protect() в новом API отсутствует.
 */
class V2RayVpnService : VpnService() {

    companion object {
        private const val TAG = "NexonVpn"
        private const val NOTIF_CHANNEL = "nexon_vpn"
        private const val NOTIF_ID = 1

        private const val PRIVATE_VLAN4_CLIENT = "26.26.26.1"
        private const val VPN_MTU = 1500
    }

    private var tunFd: ParcelFileDescriptor? = null
    private lateinit var coreController: CoreController

    private val callback = object : CoreCallbackHandler {
        override fun startup(): Long = 0L
        // Уведомление от ядра об остановке — саму очистку делает stopVpn().
        override fun shutdown(): Long = 0L
        override fun onEmitStatus(l: Long, s: String?): Long = 0L
    }

    override fun onCreate() {
        super.onCreate()
        Libv2ray.initCoreEnv(userAssetPath(), "")
        coreController = Libv2ray.newCoreController(callback)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            VpnController.ACTION_STOP -> { stopVpn(); return START_NOT_STICKY }
            VpnController.ACTION_START -> {
                val config = intent.getStringExtra(VpnController.EXTRA_CONFIG)
                val name = intent.getStringExtra(VpnController.EXTRA_NAME).orEmpty()
                if (config.isNullOrBlank()) { stopVpn(); return START_NOT_STICKY }
                startForegroundNotif(name)
                startCore(config)
            }
        }
        return START_STICKY
    }

    private fun startCore(config: String) {
        try {
            val fd = establishTun()
            coreController.startLoop(config, fd)
            VpnController.updateStatus(VpnStatus.CONNECTED)
        } catch (e: Exception) {
            Log.e(TAG, "startLoop failed", e)
            VpnController.updateStatus(VpnStatus.ERROR)
            stopVpn()
        }
    }

    /** Поднимает TUN и возвращает его файловый дескриптор для ядра. */
    private fun establishTun(): Int {
        val builder = Builder()
            .setSession("NexonVPN")
            .setMtu(VPN_MTU)
            .addAddress(PRIVATE_VLAN4_CLIENT, 30)
            .addDnsServer("1.1.1.1")
            .addDnsServer("8.8.8.8")
            .addRoute("0.0.0.0", 0)

        // Не заворачиваем трафик самого приложения (и ядра внутри него) в туннель.
        runCatching { builder.addDisallowedApplication(packageName) }

        val pfd = builder.establish() ?: throw IllegalStateException("establish() returned null")
        tunFd = pfd
        return pfd.fd
    }

    private fun stopVpn() {
        VpnController.updateStatus(VpnStatus.DISCONNECTED)
        VpnController.updateActiveServer(null)
        runCatching { if (coreController.isRunning) coreController.stopLoop() }
        runCatching { tunFd?.close() }
        tunFd = null
        stopForegroundCompat()
        stopSelf()
    }

    override fun onDestroy() {
        runCatching { if (coreController.isRunning) coreController.stopLoop() }
        runCatching { tunFd?.close() }
        tunFd = null
        super.onDestroy()
    }

    override fun onRevoke() {
        stopVpn()
    }

    // ── Foreground-уведомление ───────────────────────────────────────────────
    private fun startForegroundNotif(serverName: String) {
        val nm = getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            nm.createNotificationChannel(
                NotificationChannel(NOTIF_CHANNEL, getString(R.string.notif_channel_name), NotificationManager.IMPORTANCE_LOW)
            )
        }
        val pi = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        val notif = NotificationCompat.Builder(this, NOTIF_CHANNEL)
            .setContentTitle(getString(R.string.notif_connected_title))
            .setContentText(serverName.ifBlank { getString(R.string.app_name) })
            .setSmallIcon(R.drawable.ic_notification)
            .setOngoing(true)
            .setContentIntent(pi)
            .build()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(NOTIF_ID, notif, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        } else {
            startForeground(NOTIF_ID, notif)
        }
    }

    private fun stopForegroundCompat() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            stopForeground(STOP_FOREGROUND_REMOVE)
        } else {
            @Suppress("DEPRECATION") stopForeground(true)
        }
    }

    private fun userAssetPath(): String {
        val dir = File(filesDir, "assets")
        if (!dir.exists()) dir.mkdirs()
        return dir.absolutePath
    }
}
