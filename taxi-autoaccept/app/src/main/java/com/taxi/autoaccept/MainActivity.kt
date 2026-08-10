package com.taxi.autoaccept

import android.Manifest
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.text.TextUtils
import android.view.View
import android.widget.ArrayAdapter
import android.widget.EditText
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.taxi.autoaccept.core.RulesCodec
import com.taxi.autoaccept.databinding.ActivityMainBinding

/**
 * Единственный экран: сверху большой переключатель и статус, ниже — карточки
 * с настройками. Всё в одном вертикальном скролле, чтобы вёрстка одинаково
 * держалась и на маленьком экране, и на планшете, и при крупном системном шрифте.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var prefs: Prefs
    private var apps: List<AppEntry> = emptyList()

    private val notificationPermission =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        prefs = Prefs(this)
        askNotificationPermission()
        setupAppSpinner()
        loadIntoUi()
        wireActions()
    }

    override fun onResume() {
        super.onResume()
        refreshStatus()
        refreshLog()
    }

    private fun wireActions() = with(binding) {
        masterSwitch.setOnCheckedChangeListener { _, checked ->
            prefs.enabled = checked
            Notifications.show(this@MainActivity, checked, statusSubtitle())
            EventLog.add(this@MainActivity, if (checked) "включено" else "выключено")
            refreshStatus()
        }

        accessibilityButton.setOnClickListener {
            runCatching {
                startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
            }.onFailure { toast(getString(R.string.open_accessibility)) }
        }

        saveButton.setOnClickListener {
            saveFromUi()
            toast(getString(R.string.saved))
            refreshStatus()
        }

        exportRulesButton.setOnClickListener {
            saveFromUi()
            val text = RulesCodec.encode(prefs.toFilterConfig())
            startActivity(
                Intent.createChooser(
                    Intent(Intent.ACTION_SEND).apply {
                        type = "text/plain"
                        putExtra(Intent.EXTRA_TEXT, text)
                    },
                    getString(R.string.export_rules),
                ),
            )
        }

        importRulesButton.setOnClickListener { importRulesFromClipboard() }

        refreshLogButton.setOnClickListener { refreshLog() }
        clearLogButton.setOnClickListener {
            EventLog.clear(this@MainActivity)
            refreshLog()
        }
        shareLogButton.setOnClickListener {
            val log = EventLog.read(this@MainActivity, maxLines = 500)
            startActivity(
                Intent.createChooser(
                    Intent(Intent.ACTION_SEND).apply {
                        type = "text/plain"
                        putExtra(Intent.EXTRA_TEXT, log)
                    },
                    getString(R.string.share_log),
                ),
            )
        }
    }

    private fun setupAppSpinner() {
        apps = AppPicker.installedApps(this)
        val adapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, apps)
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        binding.appSpinner.adapter = adapter

        val index = apps.indexOfFirst { it.packageName == prefs.targetPackage }
        if (index >= 0) binding.appSpinner.setSelection(index)
    }

    private fun loadIntoUi() = with(binding) {
        masterSwitch.isChecked = prefs.enabled
        if (prefs.autoMode) modeAuto.isChecked = true else modeConfirm.isChecked = true

        confirmWindowEdit.setInt(prefs.confirmWindowSec)
        minPriceEdit.setNum(prefs.minPrice)
        maxPriceEdit.setNum(prefs.maxPrice)
        minPricePerKmEdit.setNum(prefs.minPricePerKm)
        minPricePerTotalKmEdit.setNum(prefs.minPricePerTotalKm)
        maxPickupKmEdit.setNum(prefs.maxPickupKm)
        maxPickupMinEdit.setNum(prefs.maxPickupMin)
        minTripKmEdit.setNum(prefs.minTripKm)
        maxTripKmEdit.setNum(prefs.maxTripKm)
        minSurgeEdit.setNum(prefs.minSurge)
        acceptDelayMinEdit.setNum(prefs.acceptDelayMinSec)
        acceptDelayMaxEdit.setNum(prefs.acceptDelayMaxSec)
        scanIntervalEdit.setInt(prefs.scanIntervalMs)
        blacklistEdit.setText(prefs.blacklist)
        requiredEdit.setText(prefs.requiredWords)
        cooldownEdit.setInt(prefs.cooldownSec)
        maxPerHourEdit.setInt(prefs.maxPerHour)
        workFromEdit.setInt(prefs.workFromHour)
        workToEdit.setInt(prefs.workToHour)
        requirePriceSwitch.isChecked = prefs.requireKnownPrice
        speakSwitch.isChecked = prefs.speak
        acceptRegexEdit.setText(prefs.acceptRegex)
        denyRegexEdit.setText(prefs.denyRegex)
        learnSwitch.isChecked = prefs.learnMode
    }

    private fun saveFromUi() = with(binding) {
        apps.getOrNull(appSpinner.selectedItemPosition)?.let { prefs.targetPackage = it.packageName }
        prefs.autoMode = modeAuto.isChecked

        prefs.confirmWindowSec = confirmWindowEdit.int(8).coerceIn(3, 60)
        prefs.minPrice = minPriceEdit.num()
        prefs.maxPrice = maxPriceEdit.num()
        prefs.minPricePerKm = minPricePerKmEdit.num()
        prefs.minPricePerTotalKm = minPricePerTotalKmEdit.num()
        prefs.maxPickupKm = maxPickupKmEdit.num()
        prefs.maxPickupMin = maxPickupMinEdit.num()
        prefs.minTripKm = minTripKmEdit.num()
        prefs.maxTripKm = maxTripKmEdit.num()
        prefs.minSurge = minSurgeEdit.num()

        // «до» не может быть меньше «от», иначе диапазон задержки бессмысленный.
        val delayMin = acceptDelayMinEdit.num().coerceIn(0.0, 60.0)
        prefs.acceptDelayMinSec = delayMin
        prefs.acceptDelayMaxSec = acceptDelayMaxEdit.num().coerceIn(delayMin, 60.0)
        prefs.scanIntervalMs = scanIntervalEdit.int(250).coerceIn(50, 5000)
        // Показываем то, что реально сохранилось после подгонки границ.
        acceptDelayMaxEdit.setNum(prefs.acceptDelayMaxSec)
        scanIntervalEdit.setInt(prefs.scanIntervalMs)

        prefs.blacklist = blacklistEdit.text.toString()
        prefs.requiredWords = requiredEdit.text.toString()
        prefs.cooldownSec = cooldownEdit.int(20).coerceIn(0, 600)
        prefs.maxPerHour = maxPerHourEdit.int(12).coerceIn(0, 100)
        prefs.workFromHour = workFromEdit.int(0).coerceIn(0, 23)
        prefs.workToHour = workToEdit.int(0).coerceIn(0, 23)
        prefs.requireKnownPrice = requirePriceSwitch.isChecked
        prefs.speak = speakSwitch.isChecked
        prefs.acceptRegex = acceptRegexEdit.text.toString().ifBlank { Prefs.DEFAULT_ACCEPT_REGEX }
        prefs.denyRegex = denyRegexEdit.text.toString()
        prefs.learnMode = learnSwitch.isChecked

        Notifications.show(this@MainActivity, prefs.enabled, statusSubtitle())
    }

    private fun importRulesFromClipboard() {
        val clip = getSystemService(ClipboardManager::class.java)
            ?.primaryClip
            ?.takeIf { it.itemCount > 0 }
            ?.getItemAt(0)
            ?.coerceToText(this)
            ?.toString()
            .orEmpty()

        if (!clip.contains("min_price")) {
            toast(getString(R.string.rules_import_failed))
            return
        }

        val cfg = RulesCodec.decode(clip)
        prefs.minPrice = cfg.minPrice
        prefs.maxPrice = cfg.maxPrice
        prefs.minPricePerKm = cfg.minPricePerKm
        prefs.minPricePerTotalKm = cfg.minPricePerTotalKm
        prefs.maxPickupKm = cfg.maxPickupKm
        prefs.maxPickupMin = cfg.maxPickupMin
        prefs.minTripKm = cfg.minTripKm
        prefs.maxTripKm = cfg.maxTripKm
        prefs.minSurge = cfg.minSurge
        prefs.blacklist = cfg.blacklist.joinToString(", ")
        prefs.requiredWords = cfg.requiredWords.joinToString(", ")
        prefs.requireKnownPrice = cfg.requireKnownPrice

        loadIntoUi()
        toast(getString(R.string.rules_imported))
    }

    private fun refreshStatus() {
        val serviceOn = isAccessibilityServiceEnabled()
        val state = when {
            !serviceOn -> getString(R.string.service_needed)
            prefs.enabled -> "${getString(R.string.status_on)} · ${statusSubtitle()}"
            else -> "${getString(R.string.status_off)} · ${getString(R.string.service_ready)}"
        }
        binding.statusText.text = state
        binding.accessibilityButton.setVisible(!serviceOn)
    }

    private fun refreshLog() {
        val log = EventLog.read(this)
        binding.logText.text = log.ifBlank { getString(R.string.log_empty) }
    }

    private fun statusSubtitle(): String {
        val app = apps.firstOrNull { it.packageName == prefs.targetPackage }?.label
            ?: prefs.targetPackage.ifEmpty { getString(R.string.no_app_selected) }
        return "$app · ${if (prefs.autoMode) "авто" else "по кнопке"}"
    }

    /** Включена ли наша служба в системных настройках спец. возможностей. */
    private fun isAccessibilityServiceEnabled(): Boolean {
        val expected = "$packageName/${AutoAcceptService::class.java.name}"
        val enabled = Settings.Secure.getString(
            contentResolver,
            Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES,
        ).orEmpty()

        val splitter = TextUtils.SimpleStringSplitter(':')
        splitter.setString(enabled)
        return splitter.any { it.equals(expected, ignoreCase = true) }
    }

    private fun askNotificationPermission() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return
        val granted = ContextCompat.checkSelfPermission(
            this,
            Manifest.permission.POST_NOTIFICATIONS,
        ) == PackageManager.PERMISSION_GRANTED
        if (!granted) notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
    }

    private fun toast(text: String) =
        Toast.makeText(this, text, Toast.LENGTH_SHORT).show()

    private fun View.setVisible(visible: Boolean) {
        visibility = if (visible) View.VISIBLE else View.GONE
    }

    /** Пустое поле значит «правило выключено», поэтому ноль не показываем. */
    private fun EditText.setNum(value: Double) {
        setText(
            when {
                value <= 0.0 -> ""
                value == value.toLong().toDouble() -> value.toLong().toString()
                else -> value.toString()
            },
        )
    }

    private fun EditText.setInt(value: Int) = setText(value.toString())

    private fun EditText.num(): Double =
        text.toString().trim().replace(',', '.').toDoubleOrNull()?.coerceAtLeast(0.0) ?: 0.0

    private fun EditText.int(default: Int): Int =
        text.toString().trim().toIntOrNull() ?: default
}
