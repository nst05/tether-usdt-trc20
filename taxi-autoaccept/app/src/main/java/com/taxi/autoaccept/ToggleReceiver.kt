package com.taxi.autoaccept

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** Кнопка «Переключить» в уведомлении. */
class ToggleReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        val prefs = Prefs(context)
        prefs.enabled = !prefs.enabled
        EventLog.add(context, if (prefs.enabled) "включено из шторки" else "выключено из шторки")
        Notifications.show(context, prefs.enabled, statusLine(context, prefs))
    }

    private fun statusLine(context: Context, prefs: Prefs): String {
        val target = prefs.targetPackage.ifEmpty { context.getString(R.string.no_app_selected) }
        return "$target · ${if (prefs.autoMode) "авто" else "по кнопке"}"
    }
}
