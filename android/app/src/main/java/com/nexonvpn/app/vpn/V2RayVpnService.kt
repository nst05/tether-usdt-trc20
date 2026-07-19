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
import com.nexonvpn.app.BuildConfig
import com.nexonvpn.app.MainActivity
import com.nexonvpn.app.R
import com.nexonvpn.app.core.XrayConfig
import libv2ray.Libv2ray
import libv2ray.V2RayPoint
import libv2ray.V2RayVPNServiceSupportsSet
import java.io.File

/**
 * VPN-сервис NexonVPN.
 *
 * Пайплайн (как в v2rayNG):
 *   TUN (VpnService) ──► tun2socks (libtun2socks.so) ──► socks 127.0.0.1:10808 ──► Xray-core ──► сервер
 *
 * Xray-core запускается через libv2ray (gomobile AAR из AndroidLibXrayLite).
 * Нативные библиотеки (libv2ray.aar, libtun2socks.so) поставляются при сборке —
 * см. .github/workflows/android.yml.
 */
class V2RayVpnService : VpnService() {

    companion object {
        private const val TAG = "NexonVpn"
        private const val NOTIF_CHANNEL = "nexon_vpn"
        private const val NOTIF_ID = 1

        private const val PRIVATE_VLAN4_CLIENT = "26.26.26.1"
        private const val PRIVATE_VLAN4_ROUTER = "26.26.26.2"
        private const val VPN_MTU = 1500
        private const val TUN2SOCKS = "libtun2socks.so"
    }

    private var tunFd: ParcelFileDescriptor? = null
    private var process: Process? = null
    private lateinit var v2rayPoint: V2RayPoint
    private var domain: String = ""

    // Сигнатуры соответствуют реальному интерфейсу AndroidLibXrayLite
    // (методы возвращают Long/Boolean, как в v2rayNG).
    private val supportSet = object : V2RayVPNServiceSupportsSet {
        override fun setup(s: String): Long =
            try { startTunnel(); 0L } catch (e: Exception) { Log.e(TAG, "setup failed", e); -1L }
        override fun shutdown(): Long { stopAll(); return 0L }
        override fun protect(l: Long): Boolean = this@V2RayVpnService.protect(l.toInt())
        override fun onEmitStatus(l: Long, s: String?): Long = 0L
        override fun prepare(): Long = 0L
        override fun sendFd(): Long = sendTunFd()
    }

    override fun onCreate() {
        super.onCreate()
        Libv2ray.initV2Env(userAssetPath(), "")
        v2rayPoint = Libv2ray.newV2RayPoint(supportSet, false)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            VpnController.ACTION_STOP -> { stopService(); return START_NOT_STICKY }
            VpnController.ACTION_START -> {
                val config = intent.getStringExtra(VpnController.EXTRA_CONFIG)
                domain = intent.getStringExtra(VpnController.EXTRA_DOMAIN).orEmpty()
                val name = intent.getStringExtra(VpnController.EXTRA_NAME).orEmpty()
                if (config.isNullOrBlank()) { stopService(); return START_NOT_STICKY }
                startForegroundNotif(name)
                startV2Ray(config)
            }
        }
        return START_STICKY
    }

    private fun startV2Ray(config: String) {
        try {
            v2rayPoint.configureFileContent = config
            v2rayPoint.domainName = domain
            v2rayPoint.runLoop(false)   // false → предпочитать IPv4; вызовет supportSet.setup()
            VpnController.updateStatus(VpnStatus.CONNECTED)
        } catch (e: Exception) {
            Log.e(TAG, "runLoop failed", e)
            VpnController.updateStatus(VpnStatus.ERROR)
            stopService()
        }
    }

    /** Устанавливает TUN и запускает tun2socks. Вызывается ядром из supportSet.setup(). */
    private fun startTunnel() {
        val builder = Builder()
            .setSession("NexonVPN")
            .setMtu(VPN_MTU)
            .addAddress(PRIVATE_VLAN4_CLIENT, 30)
            .addDnsServer("1.1.1.1")
            .addDnsServer("8.8.8.8")
            .addRoute("0.0.0.0", 0)

        // Не заворачиваем сам себя в туннель
        runCatching { builder.addDisallowedApplication(packageName) }

        tunFd = builder.establish() ?: throw IllegalStateException("establish() returned null")
        runTun2socks()
    }

    private fun runTun2socks() {
        val socksPort = XrayConfig.SOCKS_PORT
        val cmd = arrayListOf(
            File(applicationInfo.nativeLibraryDir, TUN2SOCKS).absolutePath,
            "--netif-ipaddr", PRIVATE_VLAN4_ROUTER,
            "--netif-netmask", "255.255.255.252",
            "--socks-server-addr", "127.0.0.1:$socksPort",
            "--tunmtu", VPN_MTU.toString(),
            "--sock-path", File(filesDir, "sock_path").absolutePath,
            "--enable-udprelay",
            "--loglevel", "notice",
        )
        process = ProcessBuilder(cmd).redirectErrorStream(true).start()
        // Мониторим процесс: если упал — переподнимаем, пока туннель активен
        Thread {
            try {
                process?.waitFor()
                if (v2rayPoint.isRunning) runTun2socks()
            } catch (_: InterruptedException) {}
        }.apply { isDaemon = true }.start()
    }

    /** Передаёт TUN fd процессу tun2socks по доменному сокету. */
    private fun sendTunFd(): Long {
        val fd = tunFd?.fileDescriptor ?: return -1L
        val path = File(filesDir, "sock_path").absolutePath
        var tries = 0
        while (tries < 6) {
            try {
                Thread.sleep(50L * (tries + 1))
                android.net.LocalSocket().use { ls ->
                    ls.connect(android.net.LocalSocketAddress(path, android.net.LocalSocketAddress.Namespace.FILESYSTEM))
                    ls.setFileDescriptorsForSend(arrayOf(fd))
                    ls.outputStream.write(42)
                }
                return 0L
            } catch (e: Exception) {
                Log.w(TAG, "sendFd retry ${tries + 1}: ${e.message}")
                tries++
            }
        }
        Log.e(TAG, "sendFd failed after retries")
        return -1L
    }

    private fun stopService() {
        VpnController.updateStatus(VpnStatus.DISCONNECTED)
        VpnController.updateActiveServer(null)
        stopAll()
        stopForegroundCompat()
        stopSelf()
    }

    private fun stopAll() {
        runCatching { if (v2rayPoint.isRunning) v2rayPoint.stopLoop() }
        runCatching { process?.destroy() }
        process = null
        runCatching { tunFd?.close() }
        tunFd = null
    }

    override fun onDestroy() {
        stopAll()
        super.onDestroy()
    }

    override fun onRevoke() {
        stopService()
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
