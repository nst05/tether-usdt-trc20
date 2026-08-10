package com.taxi.autoaccept

import android.content.Context
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Простой файловый журнал: что видели на экране, что приняли, что отсеяли и почему.
 * Нужен, чтобы после смены разобрать, почему бот не сработал, и подкрутить фильтры.
 */
object EventLog {

    private const val FILE_NAME = "events.log"
    private const val MAX_BYTES = 512 * 1024

    private val stamp = SimpleDateFormat("dd.MM HH:mm:ss", Locale.getDefault())

    @Synchronized
    fun add(context: Context, line: String) {
        val file = file(context)
        runCatching {
            if (file.length() > MAX_BYTES) trim(file)
            file.appendText("${stamp.format(Date())}  $line\n")
        }
    }

    fun read(context: Context, maxLines: Int = 200): String {
        val file = file(context)
        if (!file.exists()) return ""
        return runCatching {
            file.readLines().takeLast(maxLines).reversed().joinToString("\n")
        }.getOrDefault("")
    }

    fun clear(context: Context) {
        runCatching { file(context).writeText("") }
    }

    fun file(context: Context): File = File(context.filesDir, FILE_NAME)

    /** Оставляем последнюю половину файла, чтобы журнал не рос бесконечно. */
    private fun trim(file: File) {
        val lines = file.readLines()
        file.writeText(lines.takeLast(lines.size / 2).joinToString("\n", postfix = "\n"))
    }
}
