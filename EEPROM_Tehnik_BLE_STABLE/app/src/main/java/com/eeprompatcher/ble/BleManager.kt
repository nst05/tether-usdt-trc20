package com.eeprompatcher.ble

import android.Manifest
import android.annotation.SuppressLint
import android.bluetooth.*
import android.bluetooth.le.*
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withTimeoutOrNull
import org.json.JSONObject
import java.util.UUID

/** BLE discovery and connection manager for EEPROM Patcher boards. */
class BleManager(private val context: Context) {

    companion object {
        private const val DEVICE_NAME_PREFIX = "EEPR-"
        private const val SCAN_DURATION_MS = 12_000L
        private const val SCAN_RESTART_DELAY_MS = 350L
        private const val SCAN_RETRY_DELAY_MS = 800L
        private const val MTU_DISCOVERY_FALLBACK_MS = 1_200L
        private const val CONNECT_TIMEOUT_MS = 12_000L
        private const val CONNECT_RETRY_DELAY_MS = 700L
        private const val CONNECT_ATTEMPTS = 2
    }

    private val bluetoothManager by lazy {
        context.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
    }
    private val adapter: BluetoothAdapter? get() = bluetoothManager.adapter
    private val mainHandler = Handler(Looper.getMainLooper())

    private val serviceUuid = UUID.fromString(BleConstants.SERVICE_UUID)
    private val authUuid = UUID.fromString(BleConstants.AUTH_CHAR_UUID)
    private val cmdUuid = UUID.fromString(BleConstants.CMD_CHAR_UUID)
    private val respUuid = UUID.fromString(BleConstants.RESP_CHAR_UUID)
    private val setPinUuid = UUID.fromString(BleConstants.SETPIN_CHAR_UUID)
    private val cccdUuid = UUID.fromString(BleConstants.CCCD_UUID)

    /** true, if the phone has an enabled Bluetooth adapter. */
    fun isBluetoothEnabled(): Boolean = adapter?.isEnabled == true

    /** true, if the phone has a Bluetooth adapter at all. */
    fun hasBluetooth(): Boolean = adapter != null

    /** Android 11 and below require an enabled location provider for BLE scans. */
    fun isLocationRequiredAndOff(): Boolean {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) return false
        val lm = context.getSystemService(Context.LOCATION_SERVICE) as android.location.LocationManager
        val gps = lm.isProviderEnabled(android.location.LocationManager.GPS_PROVIDER)
        val network = lm.isProviderEnabled(android.location.LocationManager.NETWORK_PROVIDER)
        return !(gps || network)
    }

    private var gatt: BluetoothGatt? = null
    private var authChar: BluetoothGattCharacteristic? = null
    private var cmdChar: BluetoothGattCharacteristic? = null
    private var respChar: BluetoothGattCharacteristic? = null
    private var setPinChar: BluetoothGattCharacteristic? = null
    private var servicesDiscoveryStarted = false

    private var scanner: BluetoothLeScanner? = null
    private var scanRegistered = false
    private var scanRetryCount = 0
    private var scanStartTask: Runnable? = null
    private var scanStopTask: Runnable? = null

    private val _connectionState = MutableStateFlow(ConnectionState.DISCONNECTED)
    val connectionState: StateFlow<ConnectionState> = _connectionState

    private val _devices = MutableStateFlow<List<BluetoothDevice>>(emptyList())
    val devices: StateFlow<List<BluetoothDevice>> = _devices

    private val _lastError = MutableStateFlow<String?>(null)
    val lastError: StateFlow<String?> = _lastError

    private val _isScanning = MutableStateFlow(false)
    val isScanning: StateFlow<Boolean> = _isScanning

    // Commands are serialized: the next notification belongs to the latest command.
    private val responseChannel = Channel<String>(Channel.UNLIMITED)
    private val requestMutex = Mutex()
    private var connectDeferred: CompletableDeferred<Boolean>? = null
    private var writeDeferred: CompletableDeferred<Boolean>? = null

    private val scanCallback = object : ScanCallback() {
        override fun onScanResult(callbackType: Int, result: ScanResult) {
            // Do filtering in the app. Some ESP32/Android combinations expose the
            // service UUID in a scan response late, while the board name is stable.
            if (!isPatcher(result)) return

            val device = result.device
            if (_devices.value.none { it.address == device.address }) {
                _devices.value = _devices.value + device
            }
        }

        override fun onScanFailed(errorCode: Int) {
            scanRegistered = false
            scanStopTask?.let(mainHandler::removeCallbacks)
            scanStopTask = null

            if (scanRetryCount == 0 && errorCode != SCAN_FAILED_FEATURE_UNSUPPORTED) {
                scanRetryCount++
                _lastError.value = "Поиск BLE перезапускается (код $errorCode)…"
                scheduleScanStart(SCAN_RETRY_DELAY_MS)
            } else {
                _isScanning.value = false
                _lastError.value = "Ошибка поиска BLE: код $errorCode"
            }
        }
    }

    /**
     * Starts one controlled 12-second scan. Repeated taps safely replace the
     * previous scan instead of registering the same callback twice.
     */
    @SuppressLint("MissingPermission")
    fun startScan() {
        if (!isBluetoothEnabled()) {
            _lastError.value = "Bluetooth выключен"
            return
        }
        if (!hasScanPermission()) {
            _lastError.value = "Не выдано разрешение на поиск Bluetooth-устройств"
            return
        }

        val replaceActiveScan = scanRegistered || scanStartTask != null
        stopScanInternal()
        _devices.value = emptyList()
        _lastError.value = null
        scanRetryCount = 0
        scheduleScanStart(if (replaceActiveScan) SCAN_RESTART_DELAY_MS else 0L)
    }

    @SuppressLint("MissingPermission")
    fun stopScan() {
        stopScanInternal()
    }

    @SuppressLint("MissingPermission")
    private fun stopScanInternal() {
        scanStartTask?.let(mainHandler::removeCallbacks)
        scanStartTask = null
        scanStopTask?.let(mainHandler::removeCallbacks)
        scanStopTask = null

        if (scanRegistered) {
            runCatching { scanner?.stopScan(scanCallback) }
        }
        scanRegistered = false
        _isScanning.value = false
    }

    @SuppressLint("MissingPermission")
    private fun scheduleScanStart(delayMs: Long) {
        _isScanning.value = true
        val task = Runnable {
            scanStartTask = null
            val activeScanner = adapter?.bluetoothLeScanner
            if (activeScanner == null) {
                _isScanning.value = false
                _lastError.value = "BLE-сканер недоступен"
                return@Runnable
            }

            scanner = activeScanner
            val settings = ScanSettings.Builder()
                .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
                .setReportDelay(0L)
                .build()

            try {
                // No hardware UUID filter here: it is the source of intermittent
                // discovery on some ESP32 and Android BLE stacks.
                activeScanner.startScan(null, settings, scanCallback)
                scanRegistered = true
                scheduleScanStop()
            } catch (e: SecurityException) {
                scanRegistered = false
                _isScanning.value = false
                _lastError.value = "Нет разрешения на BLE-поиск"
            } catch (e: IllegalStateException) {
                scanRegistered = false
                _isScanning.value = false
                _lastError.value = "Не удалось начать BLE-поиск: ${e.message}"
            }
        }
        scanStartTask = task
        mainHandler.postDelayed(task, delayMs)
    }

    private fun scheduleScanStop() {
        val task = Runnable {
            scanStopTask = null
            stopScanInternal()
        }
        scanStopTask = task
        mainHandler.postDelayed(task, SCAN_DURATION_MS)
    }

    private fun isPatcher(result: ScanResult): Boolean {
        val record = result.scanRecord
        val advertisesService = record?.serviceUuids?.any { it.uuid == serviceUuid } == true
        val name = record?.deviceName
            ?: runCatching { result.device.name }.getOrNull()
            ?: ""
        return advertisesService || name.startsWith(DEVICE_NAME_PREFIX, ignoreCase = true)
    }

    @SuppressLint("MissingPermission")
    suspend fun connect(device: BluetoothDevice): Boolean {
        stopScan()
        if (!hasConnectPermission()) {
            _lastError.value = "Не выдано разрешение на подключение Bluetooth"
            return false
        }

        _lastError.value = null
        closeActiveGatt(disconnect = true)

        repeat(CONNECT_ATTEMPTS) { index ->
            _connectionState.value = ConnectionState.CONNECTING
            servicesDiscoveryStarted = false
            val deferred = CompletableDeferred<Boolean>()
            connectDeferred = deferred

            gatt = try {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                    device.connectGatt(context, false, gattCallback, BluetoothDevice.TRANSPORT_LE)
                } else {
                    device.connectGatt(context, false, gattCallback)
                }
            } catch (e: SecurityException) {
                _lastError.value = "Нет разрешения на подключение BLE"
                null
            }

            if (gatt == null) {
                _lastError.value = "Android не начал подключение к плате"
            } else {
                val connected = withTimeoutOrNull(CONNECT_TIMEOUT_MS) { deferred.await() } ?: false
                if (connected) return true
            }

            closeActiveGatt(disconnect = true)
            if (index < CONNECT_ATTEMPTS - 1) delay(CONNECT_RETRY_DELAY_MS)
        }

        _connectionState.value = ConnectionState.DISCONNECTED
        if (_lastError.value == null) _lastError.value = "Не удалось подключиться к плате"
        return false
    }

    @SuppressLint("MissingPermission")
    private val gattCallback = object : BluetoothGattCallback() {
        override fun onConnectionStateChange(g: BluetoothGatt, status: Int, newState: Int) {
            if (g !== gatt) {
                runCatching { g.close() }
                return
            }

            if (status != BluetoothGatt.GATT_SUCCESS || newState != BluetoothProfile.STATE_CONNECTED) {
                val message = if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                    "Соединение с платой разорвано (код $status)"
                } else {
                    "Ошибка подключения GATT: код $status"
                }
                failConnection(message)
                return
            }

            _connectionState.value = ConnectionState.DISCOVERING
            // MTU is needed for JSON commands larger than the default ATT payload,
            // but service discovery must not depend on the MTU callback arriving.
            val mtuStarted = runCatching { g.requestMtu(BleConstants.DESIRED_MTU) }.getOrDefault(false)
            if (!mtuStarted) beginServiceDiscovery(g)
            mainHandler.postDelayed({ beginServiceDiscovery(g) }, MTU_DISCOVERY_FALLBACK_MS)
        }

        override fun onMtuChanged(g: BluetoothGatt, mtu: Int, status: Int) {
            if (g === gatt) beginServiceDiscovery(g)
        }

        override fun onServicesDiscovered(g: BluetoothGatt, status: Int) {
            if (g !== gatt) return
            if (status != BluetoothGatt.GATT_SUCCESS) {
                failConnection("Не удалось получить BLE-сервисы: код $status")
                return
            }

            val service = g.getService(serviceUuid)
            if (service == null) {
                failConnection("На устройстве не найден сервис EEPROM Patcher")
                return
            }

            val auth = service.getCharacteristic(authUuid)
            val cmd = service.getCharacteristic(cmdUuid)
            val resp = service.getCharacteristic(respUuid)
            val setPin = service.getCharacteristic(setPinUuid)
            if (auth == null || cmd == null || resp == null || setPin == null) {
                failConnection("В плате отсутствуют необходимые BLE-характеристики")
                return
            }

            authChar = auth
            cmdChar = cmd
            respChar = resp
            setPinChar = setPin

            if (!g.setCharacteristicNotification(resp, true)) {
                failConnection("Не удалось включить ответы от платы")
                return
            }
            val cccd = resp.getDescriptor(cccdUuid)
            if (cccd == null) {
                failConnection("В плате отсутствует дескриптор уведомлений")
                return
            }

            @Suppress("DEPRECATION")
            cccd.value = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
            @Suppress("DEPRECATION")
            val started = g.writeDescriptor(cccd)
            if (!started) failConnection("Не удалось запросить уведомления от платы")
        }

        @Suppress("DEPRECATION")
        override fun onDescriptorWrite(g: BluetoothGatt, descriptor: BluetoothGattDescriptor, status: Int) {
            if (g !== gatt || descriptor.uuid != cccdUuid || descriptor.characteristic.uuid != respUuid) return
            if (status != BluetoothGatt.GATT_SUCCESS) {
                failConnection("Плата не включила уведомления: код $status")
                return
            }
            _connectionState.value = ConnectionState.CONNECTED
            connectDeferred?.let { if (!it.isCompleted) it.complete(true) }
        }

        @Suppress("DEPRECATION")
        override fun onCharacteristicChanged(g: BluetoothGatt, characteristic: BluetoothGattCharacteristic) {
            if (g !== gatt || characteristic.uuid != respUuid) return
            val json = String(characteristic.value ?: return, Charsets.UTF_8)
            responseChannel.trySend(json)
        }

        override fun onCharacteristicWrite(g: BluetoothGatt, characteristic: BluetoothGattCharacteristic, status: Int) {
            if (g !== gatt) return
            val pending = writeDeferred ?: return
            if (status != BluetoothGatt.GATT_SUCCESS) {
                _lastError.value = "Плата не приняла команду: код $status"
                pending.complete(false)
            } else {
                pending.complete(true)
            }
        }
    }

    @SuppressLint("MissingPermission")
    private fun beginServiceDiscovery(g: BluetoothGatt) {
        if (g !== gatt || servicesDiscoveryStarted) return
        servicesDiscoveryStarted = true
        if (!g.discoverServices()) failConnection("Не удалось начать поиск BLE-сервисов")
    }

    private fun failConnection(message: String) {
        _lastError.value = message
        _connectionState.value = ConnectionState.DISCONNECTED
        connectDeferred?.let { if (!it.isCompleted) it.complete(false) }
        writeDeferred?.let { if (!it.isCompleted) it.complete(false) }
    }

    @SuppressLint("MissingPermission")
    @Suppress("DEPRECATION")
    private suspend fun writeAndAwait(
        char: BluetoothGattCharacteristic?,
        payload: String
    ): JSONObject {
        val characteristic = char ?: throw IllegalStateException("Характеристика недоступна — нет подключения")
        return requestMutex.withLock {
            val activeGatt = gatt ?: throw IllegalStateException("Плата не подключена")
            if (_connectionState.value != ConnectionState.CONNECTED &&
                _connectionState.value != ConnectionState.AUTHENTICATED
            ) {
                throw IllegalStateException("Подключение к плате ещё не готово")
            }

            // A previous timed-out response must not be mistaken for this command.
            while (responseChannel.tryReceive().getOrNull() != null) Unit

            val writeResult = CompletableDeferred<Boolean>()
            writeDeferred = writeResult
            try {
                characteristic.value = payload.toByteArray(Charsets.UTF_8)
                characteristic.writeType = BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
                if (activeGatt !== gatt || !activeGatt.writeCharacteristic(characteristic)) {
                    throw IllegalStateException("Не удалось отправить данные по BLE")
                }
                val writeOk = withTimeoutOrNull(BleConstants.REQUEST_TIMEOUT_MS) { writeResult.await() } ?: false
                if (!writeOk) throw IllegalStateException("Плата не подтвердила приём команды")

                val raw = withTimeoutOrNull(BleConstants.REQUEST_TIMEOUT_MS) { responseChannel.receive() }
                    ?: throw IllegalStateException("Плата не ответила на команду")
                JSONObject(raw)
            } finally {
                if (writeDeferred === writeResult) writeDeferred = null
            }
        }
    }

    suspend fun authenticate(pin: String): JSONObject {
        val response = writeAndAwait(authChar, pin)
        if (response.optBoolean("ok", false)) {
            _connectionState.value = ConnectionState.AUTHENTICATED
        }
        return response
    }

    suspend fun sendCommand(cmd: JSONObject): JSONObject = writeAndAwait(cmdChar, cmd.toString())

    suspend fun setPin(oldPin: String, newPin: String): JSONObject {
        val payload = JSONObject().put("old", oldPin).put("new", newPin)
        return writeAndAwait(setPinChar, payload.toString())
    }

    @SuppressLint("MissingPermission")
    fun disconnect() {
        stopScan()
        closeActiveGatt(disconnect = true)
        _connectionState.value = ConnectionState.DISCONNECTED
    }

    @SuppressLint("MissingPermission")
    private fun closeActiveGatt(disconnect: Boolean) {
        val activeGatt = gatt
        gatt = null
        authChar = null
        cmdChar = null
        respChar = null
        setPinChar = null
        servicesDiscoveryStarted = false
        connectDeferred?.let { if (!it.isCompleted) it.complete(false) }
        writeDeferred?.let { if (!it.isCompleted) it.complete(false) }
        if (activeGatt != null) {
            if (disconnect) runCatching { activeGatt.disconnect() }
            runCatching { activeGatt.close() }
        }
    }

    private fun hasScanPermission(): Boolean {
        val permission = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            Manifest.permission.BLUETOOTH_SCAN
        } else {
            Manifest.permission.ACCESS_FINE_LOCATION
        }
        return context.checkSelfPermission(permission) == PackageManager.PERMISSION_GRANTED
    }

    private fun hasConnectPermission(): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) return true
        return context.checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED
    }
}
