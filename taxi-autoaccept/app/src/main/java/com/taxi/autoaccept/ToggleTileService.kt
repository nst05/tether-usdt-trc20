package com.taxi.autoaccept

import android.service.quicksettings.Tile
import android.service.quicksettings.TileService

/**
 * Плитка в быстрых настройках: свайп сверху и одно нажатие, не глядя на экран.
 */
class ToggleTileService : TileService() {

    override fun onStartListening() {
        super.onStartListening()
        refresh()
    }

    override fun onClick() {
        super.onClick()
        val prefs = Prefs(this)
        prefs.enabled = !prefs.enabled
        EventLog.add(this, if (prefs.enabled) "включено с плитки" else "выключено с плитки")
        Notifications.show(this, prefs.enabled, prefs.targetPackage)
        refresh()
    }

    private fun refresh() {
        val tile = qsTile ?: return
        val enabled = Prefs(this).enabled
        tile.state = if (enabled) Tile.STATE_ACTIVE else Tile.STATE_INACTIVE
        tile.label = getString(R.string.tile_label)
        tile.updateTile()
    }
}
