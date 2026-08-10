package com.taxi.autoaccept

import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager

data class AppEntry(val label: String, val packageName: String) {
    override fun toString(): String = "$label  ·  $packageName"
}

/**
 * Список установленных приложений для выбора цели.
 *
 * Пакеты не зашиты в код намеренно: у региональных служб (Анжи Такси, местные
 * диспетчерские на базе «Такси Мастер») имена пакетов разные и меняются от сборки
 * к сборке. Вместо угадывания приложение показывает то, что реально стоит на
 * телефоне, а похожие на такси поднимает наверх списка.
 */
object AppPicker {

    private val TAXI_HINT = Regex(
        "(?i)(такси|taxi|driver|водител|про\\b|drive|яндекс|indriv|indrive|bolt|uber|maxim|" +
            "максим|ситимобил|анжи|anji|didi|gett|везёт|вези)",
    )

    fun installedApps(context: Context): List<AppEntry> {
        val pm = context.packageManager
        val intent = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
        val resolved = pm.queryIntentActivities(intent, PackageManager.MATCH_ALL)

        val apps = resolved
            .asSequence()
            .map { info ->
                AppEntry(
                    label = info.loadLabel(pm).toString(),
                    packageName = info.activityInfo.packageName,
                )
            }
            .filter { it.packageName != context.packageName }
            .distinctBy { it.packageName }
            .toList()

        val (likely, others) = apps.partition {
            TAXI_HINT.containsMatchIn(it.label) || TAXI_HINT.containsMatchIn(it.packageName)
        }
        val byLabel = compareBy<AppEntry> { it.label.lowercase() }
        return likely.sortedWith(byLabel) + others.sortedWith(byLabel)
    }
}
