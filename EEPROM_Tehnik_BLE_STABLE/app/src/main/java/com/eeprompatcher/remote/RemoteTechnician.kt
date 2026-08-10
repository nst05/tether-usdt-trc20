package com.eeprompatcher.remote

import com.google.firebase.database.*
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import org.json.JSONObject

// Менеджер удалённого режима на стороне ТЕХНИКА.
// Техник создаёт сессию (код), слушает команды оператора из Firebase,
// выполняет их (через колбэк по BLE) и пишет ответ обратно.
//
// Схема в Realtime Database:
//   /sessions/{code}/command  — оператор пишет команду (с полем id)
//   /sessions/{code}/response — техник пишет ответ (с полем forId)
//   /sessions/{code}/meta     — статус сессии (техник онлайн, время)
class RemoteTechnician {

    private val db = FirebaseDatabase.getInstance(
        "https://eeprom-patcher-default-rtdb.europe-west1.firebasedatabase.app"
    )
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var sessionRef: DatabaseReference? = null
    private var commandListener: ValueEventListener? = null
    private var lastHandledId: String? = null

    private val _sessionCode = MutableStateFlow<String?>(null)
    val sessionCode: StateFlow<String?> = _sessionCode

    private val _active = MutableStateFlow(false)
    val active: StateFlow<Boolean> = _active

    private val _lastCommand = MutableStateFlow<String?>(null)
    val lastCommand: StateFlow<String?> = _lastCommand

    // Колбэк выполнения команды: получает JSON-команду, возвращает JSON-ответ.
    // Задаётся снаружи — внутри он вызывает BLE (ту же логику, что кнопки).
    var onCommand: (suspend (JSONObject) -> JSONObject)? = null

    // Запуск удалённого доступа: генерирует код сессии, начинает слушать.
    // mode — выбранный режим техника (1/2/3), передаётся оператору.
    fun start(mode: Int = 2): String {
        val code = generateCode()
        _sessionCode.value = code
        sessionRef = db.getReference("sessions").child(code)

        // отметка, что техник онлайн + его режим
        sessionRef!!.child("meta").setValue(
            mapOf("online" to true, "mode" to mode, "ts" to ServerValue.TIMESTAMP)
        )

        listenCommands()
        _active.value = true
        return code
    }

    private fun listenCommands() {
        val cmdRef = sessionRef?.child("command") ?: return
        commandListener = object : ValueEventListener {
            override fun onDataChange(snapshot: DataSnapshot) {
                if (!snapshot.exists()) return
                val id = snapshot.child("id").getValue(String::class.java) ?: return
                if (id == lastHandledId) return   // уже обработали
                lastHandledId = id

                // собираем JSON-команду
                val json = JSONObject()
                snapshot.children.forEach { child ->
                    if (child.key != "id") {
                        json.put(child.key!!, child.value)
                    }
                }
                _lastCommand.value = json.optString("cmd", "?")

                // выполняем через колбэк (BLE) в корутине
                val handler = onCommand
                if (handler != null) {
                    scope.launch {
                        val resp = try { handler(json) }
                        catch (e: Exception) { JSONObject().put("ok", false).put("error", e.message) }
                        writeResponse(id, resp)
                    }
                }
            }
            override fun onCancelled(error: DatabaseError) {}
        }
        cmdRef.addValueEventListener(commandListener!!)
    }

    private fun writeResponse(forId: String, resp: JSONObject) {
        val respRef = sessionRef?.child("response") ?: return
        val map = HashMap<String, Any?>()
        map["forId"] = forId
        // разворачиваем JSON в map
        resp.keys().forEach { k -> map[k] = resp.get(k) }
        respRef.setValue(map)
    }

    // Остановка удалённого доступа.
    fun stop() {
        commandListener?.let { sessionRef?.child("command")?.removeEventListener(it) }
        sessionRef?.child("meta")?.child("online")?.setValue(false)
        sessionRef = null
        _active.value = false
        _sessionCode.value = null
        _lastCommand.value = null
    }

    // Генерация 6-значного кода сессии (цифры).
    private fun generateCode(): String {
        return (100000..999999).random().toString()
    }
}
