"""
Безопасный сервисный слой поверх транспорта `stand.py`.

Назначение — правильная (безопасная) работа с сервисным уровнем прибора:
определение сервиса, снятие резервных копий, запись с обязательной обратной
проверкой, ведение журнала кадров и восстановление из бэкапа.

ГРАНИЦЫ. Модуль реализует только штатные операции прибора со страховкой:
диагностику, резервирование, верифицированную запись и восстановление.
В нём НЕТ и не должно быть подмены отображаемых показаний, регулировки
коэффициента скорости счёта энергии и обхода аппаратного входа P2.5 —
это фальсификация учёта, а не сервис.

Сервисный уровень включается ТОЛЬКО аппаратно (вход P2.5 на плате или флаг
0x04F2.12), см. docs/ACCESS.md. Программа его не «открывает» — она лишь
корректно пользуется командами, доступными, когда прибор уже в сервисе.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable

from stand import Stand, ResultError, ProtocolError, RESULT_TEXT


# ---------------------------------------------------------------------------
# Коды ошибок доступа (см. разбор: 0xB84E → 03 «недостаточный уровень»)
# ---------------------------------------------------------------------------
ERR_BAD_REQUEST = 0x01     # неверная команда/параметр (0xB842)
ERR_WRITE = 0x02           # ошибка записи/внешней памяти (0xB848)
ERR_ACCESS = 0x03          # недостаточный уровень доступа (0xB84E)
ERR_STATE = 0x04           # запрещено текущим состоянием (0xB856)
ERR_MODE = 0x05            # ошибка режима (0xB85C)


class ServiceError(Exception):
    """Ошибка на уровне сервисных операций (нарушены страховки)."""


class VerificationError(ServiceError):
    """Запись прошла, но обратное чтение не совпало с ожидаемым."""


# ---------------------------------------------------------------------------
# Контрольные суммы записей
# ---------------------------------------------------------------------------
def password_control(password: bytes) -> int:
    """Контрольный байт записи пароля: XOR всех 6 байт с начальным 0xF0.

    Это НЕ хэш и НЕ средство подбора — только формат контроля целостности
    записи, чтобы при штатной перезаписи известного пароля не испортить блок.
    """
    if len(password) != 6:
        raise ValueError("пароль ровно 6 байт")
    c = 0xF0
    for b in password:
        c ^= b
    return c & 0xFF


def password_record_valid(record7: bytes) -> bool:
    """Проверяет 7-байтную запись пароля: 6 байт значения + байт контроля."""
    if len(record7) != 7:
        raise ValueError("запись пароля — 7 байт")
    return password_control(record7[:6]) == record7[6]


def word_sum16(block: bytes) -> int:
    """Сумма 16-битных слов блока по модулю 2^16 (little-endian).

    Универсальная проверка целостности для читаемых блоков. Точный алгоритм
    контрольной суммы Info Flash — внутренний: прошивка пересчитывает его сама
    при записи (CMD 07, коды 0xEC/0xEE), поэтому опираться нужно на обратное
    чтение, а не на предвычисление.
    """
    s = 0
    for i in range(0, len(block) - 1, 2):
        s = (s + (block[i] | (block[i + 1] << 8))) & 0xFFFF
    return s


# ---------------------------------------------------------------------------
# Набор безопасных чтений для снимка состояния «до»
# ---------------------------------------------------------------------------
# Каждый элемент: имя -> (cmd, *args). Только чтение, без побочных эффектов.
DEFAULT_SNAPSHOT: dict[str, tuple[int, ...]] = {
    "identity_08_00":      (0x08, 0x00),   # серийный номер + дата (INFO 0x1080)
    "config_08_02":        (0x08, 0x02),   # базовая конфигурация 0x04E0..0x04E3
    "ext_config_08_07":    (0x08, 0x07),   # расширенная конфигурация 0x04E0..0x04E5
    "net_addr_08_05":      (0x08, 0x05),   # сетевой адрес 0x04FE
    "status_08_09":        (0x08, 0x09),   # слово состояния 0x04F4/0x04F5
    "flags_08_0A":         (0x08, 0x0A),   # 0x04FA/0x04FB + 0x04F0..0x04F3
    "byte_08_17":          (0x08, 0x17),   # байт 0x04FC
    "word_08_18":          (0x08, 0x18),   # слово 0x04F8
    "block_08_19":         (0x08, 0x19),   # 0x049D..0x049F
    "buf_08_1B":           (0x08, 0x1B),   # 0x04C8..0x04CF (8 байт)
    "buf_08_1C":           (0x08, 0x1C),   # 0x0420..0x0423 (4 байта)
    "phases_08_29":        (0x08, 0x29),   # мгновенные значения фаз A/B/C
}


@dataclass
class Snapshot:
    """Снимок состояния прибора с меткой времени (основа резервной копии)."""
    timestamp: float
    address: int
    data: dict[str, str] = field(default_factory=dict)   # имя -> hex

    def to_json(self, path: str) -> str:
        obj = {"timestamp": self.timestamp,
               "time_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(self.timestamp)),
               "address": self.address, "data": self.data}
        json.dump(obj, open(path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        return path

    @classmethod
    def from_json(cls, path: str) -> "Snapshot":
        obj = json.load(open(path, encoding="utf-8"))
        return cls(obj["timestamp"], obj["address"], obj["data"])


# ---------------------------------------------------------------------------
# Сессия сервисных операций
# ---------------------------------------------------------------------------
class ServiceSession:
    """Обёртка над `Stand` с обязательными страховками для записи.

    Правила, которые модуль соблюдает автоматически:
      1. Любая запись запрещена без предварительного backup() в этой сессии.
      2. Каждая запись сопровождается обратным чтением и сравнением (verify).
      3. Все кадры пишутся в журнал (файл).
      4. Есть режим dry_run: запись только логируется, но не отправляется.
    """

    def __init__(self, dev: Stand, journal: str = "service.log", dry_run: bool = False):
        self.dev = dev
        self.dry_run = dry_run
        self._journal = open(journal, "a", encoding="utf-8")
        self._have_backup = False
        self._backup_path: str | None = None
        dev.on_frame = self._on_frame
        self._note(f"=== сессия открыта {time.strftime('%Y-%m-%d %H:%M:%S')} "
                   f"(dry_run={dry_run}) ===")

    # ---- журнал ----
    def _on_frame(self, direction: str, frame: bytes):
        self._journal.write(f"{time.time():.3f}  {direction}  {frame.hex(' ')}\n")
        self._journal.flush()

    def _note(self, text: str):
        self._journal.write(f"# {text}\n")
        self._journal.flush()

    def close(self):
        self._note("=== сессия закрыта ===")
        self._journal.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ---- авторизация (уровни 1/2, штатный пароль) ----
    def login(self, password: bytes, level: int = 1):
        self._note(f"login уровень {level}")
        self.dev.open_channel(password, level)

    def logout(self):
        self._note("logout")
        self.dev.close_channel()

    # ---- определение сервисного уровня ----
    def service_state(self, aggressive: bool = False) -> str:
        """Определение состояния сервисного уровня — честно, по возможностям прибора.

        В прошивке НЕТ сервисной команды чтения: сервисный бит 0x08B8.8 гейтит
        только записи и в ответ не попадает. Поэтому:

          * 'off'      — сервисная команда отклонена по доступу (код 03/01),
                         прибор точно НЕ в сервисе; запись не производилась;
          * 'unknown'  — безопасно подтвердить «включён» нельзя;
          * 'on'       — только при aggressive=True и ценой побочного эффекта.

        Безопасный режим (aggressive=False) никогда не вызывает запись: он
        возвращает 'off' лишь если удаётся получить отказ по доступу без риска,
        иначе 'unknown'. Достоверное «включён» подтверждается результатом первой
        верифицированной операции (backup → safe_write → сверка), а не пробой.

        aggressive=True шлёт сервисную команду CMD 03/0A: при выключенном сервисе
        она безвредно вернёт код 03, но при ВКЛЮЧЁННОМ — выполнит операцию
        (побочный эффект, флаг 0x04F6.8). Использовать только осознанно.
        """
        if not aggressive:
            self._note("service_state: безопасный режим — 'on' подтверждается "
                       "только верифицированной операцией")
            return 'unknown'
        try:
            self.dev.raw(0x03, 0x0A)          # длина 5; сервисно-зависимая
            self._note("service_state(aggressive) -> on (ВНИМАНИЕ: побочный эффект)")
            return 'on'
        except ResultError as e:
            state = 'off' if (e.code & 0x7F) in (ERR_ACCESS, ERR_BAD_REQUEST) else 'unknown'
            self._note(f"service_state(aggressive) -> {state} (код {e.code:#04x})")
            return state
        except ProtocolError as e:
            self._note(f"service_state -> нет ответа ({e})")
            return 'unknown'

    def confirm_service_by_operation(self, operation: Callable[[Stand], None],
                                     verify_read: tuple[int, ...],
                                     expected: bytes) -> bool:
        """Достоверное подтверждение сервиса: выполнить операцию и сверить.

        Если операция прошла и обратное чтение совпало — сервис был включён
        (возвращает True). Если прибор отклонил по доступу — сервис выключен,
        запись не выполнялась (возвращает False). Требует backup() в сессии.
        Операцию задавайте идемпотентной (запись того же значения), чтобы
        подтверждение не меняло состояние прибора.
        """
        if not self._have_backup:
            raise ServiceError("подтверждение записью запрещено без backup()")
        try:
            self.safe_write(operation, verify_read, expected,
                            description="подтверждение сервиса идемпотентной операцией")
            return True
        except ResultError as e:
            if (e.code & 0x7F) in (ERR_ACCESS, ERR_BAD_REQUEST):
                self._note("confirm_service -> сервис выключен (запись отклонена)")
                return False
            raise

    # ---- снятие резервной копии ----
    def backup(self, reads: dict[str, tuple[int, ...]] | None = None,
               path: str | None = None) -> Snapshot:
        """Читает набор диагностических команд и сохраняет снимок «до» на диск.

        Backup обязателен перед любой записью — без него safe_* поднимут ошибку.
        Резервируйте и основную, и зеркальную копии, если пишете в зеркалируемые
        области (пароли/коэффициенты, сдвиг 0x0100).
        """
        reads = reads or DEFAULT_SNAPSHOT
        snap = Snapshot(time.time(), self.dev.address)
        for name, req in reads.items():
            try:
                snap.data[name] = self.dev.raw(*req).hex(" ")
            except ResultError as e:
                snap.data[name] = f"ERR:{e.code:#04x}"
            except ProtocolError:
                snap.data[name] = "ERR:no-reply"
        path = path or f"backup_{self.dev.address:02x}_{int(snap.timestamp)}.json"
        snap.to_json(path)
        self._have_backup = True
        self._backup_path = path
        self._note(f"backup сохранён: {path} ({len(snap.data)} записей)")
        return snap

    # ---- верифицированная запись ----
    def safe_write(self,
                   write_fn: Callable[[Stand], None],
                   verify_read: tuple[int, ...],
                   expected: bytes,
                   description: str = "") -> None:
        """Выполнить ОДНУ штатную запись и обязательно сверить результат.

        write_fn(dev)   — функция, посылающая штатную команду записи (CMD 03/07);
        verify_read     — парная команда чтения для проверки;
        expected        — какие данные должны читаться после записи.

        Требует ранее выполненного backup() в этой сессии. Не совпало → откат
        решается оператором (restore из бэкапа).
        """
        if not self._have_backup:
            raise ServiceError("запись запрещена без backup() в этой сессии")
        self._note(f"safe_write: {description or '(без описания)'}")
        if self.dry_run:
            self._note("  dry_run: запись пропущена")
            return
        write_fn(self.dev)
        back = self.dev.raw(*verify_read)
        if back != expected:
            self._note(f"  ВЕРИФИКАЦИЯ НЕ ПРОШЛА: ждали {expected.hex(' ')}, "
                       f"прочитали {back.hex(' ')}")
            raise VerificationError(
                f"ждали {expected.hex(' ')}, прочитали {back.hex(' ')}")
        self._note("  верификация OK")

    # ---- восстановление из бэкапа ----
    def restore_plan(self, snapshot: Snapshot) -> list[str]:
        """Готовит человекочитаемый план восстановления из снимка.

        НЕ выполняет запись сам: восстановление зависит от того, какими парными
        командами записи возвращаются конкретные поля. План показывает, что и на
        какое значение нужно вернуть; оператор подтверждает и выполняет через
        safe_write с корректной командой записи для каждого поля.
        """
        plan = [f"Восстановление к снимку от "
                f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(snapshot.timestamp))}:"]
        for name, hexval in snapshot.data.items():
            plan.append(f"  {name}: вернуть -> {hexval}")
        return plan


# ---------------------------------------------------------------------------
# Пример сценария (запускать только на приборе, физически в сервисе)
# ---------------------------------------------------------------------------
def demo(dev: Stand):
    """Демонстрация безопасного порядка работы (без реальных записей)."""
    with ServiceSession(dev, dry_run=True) as s:
        print("связь:", "ok" if dev.test_link() else "нет")
        print("состояние сервиса (безопасно):", s.service_state())
        snap = s.backup()
        print("снимок:", json.dumps(snap.data, ensure_ascii=False, indent=1))
        # Пример штатной верифицированной записи в dry_run (ничего не пишется):
        s.safe_write(
            write_fn=lambda d: None,           # здесь была бы штатная CMD 03/07
            verify_read=(0x08, 0x02),
            expected=bytes.fromhex(snap.data["config_08_02"].replace(" ", "")),
            description="пример: перезапись конфигурации с проверкой")
        print("готово (dry_run)")


if __name__ == "__main__":
    import sys
    if "--sim" in sys.argv:
        from sim import make_sim_stand
        demo(make_sim_stand(0x00))
    else:
        print("Запуск на приборе: импортируйте ServiceSession и работайте по "
              "порядку probe → backup → safe_write. Для демо: python3 service.py --sim")
