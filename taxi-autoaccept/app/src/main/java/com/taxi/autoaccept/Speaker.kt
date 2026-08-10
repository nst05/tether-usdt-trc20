package com.taxi.autoaccept

import android.content.Context
import android.media.AudioAttributes
import android.speech.tts.TextToSpeech
import java.util.Locale

/**
 * Озвучка заказов. Голос идёт в канал навигационных подсказок — музыка и звонок
 * приглушаются, а не обрываются, и объявление слышно даже на громкой музыке.
 */
class Speaker(context: Context) {

    @Volatile
    private var ready = false

    private val tts: TextToSpeech = TextToSpeech(
        context.applicationContext,
        TextToSpeech.OnInitListener { status -> onInit(status) },
    )

    private fun onInit(status: Int) {
        if (status != TextToSpeech.SUCCESS) return
        runCatching {
            tts.language = Locale("ru", "RU")
            tts.setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ASSISTANCE_NAVIGATION_GUIDANCE)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build(),
            )
        }
        ready = true
    }

    fun say(text: String, interrupt: Boolean = true) {
        if (!ready) return
        val mode = if (interrupt) TextToSpeech.QUEUE_FLUSH else TextToSpeech.QUEUE_ADD
        runCatching { tts.speak(text, mode, null, "auto_accept") }
    }

    fun shutdown() {
        ready = false
        runCatching { tts.stop() }
        runCatching { tts.shutdown() }
    }
}
