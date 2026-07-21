# Подключение эндпоинтов приложения к серверу (5 минут)

Нужно один раз добавить на сервер 2 файла и 4 строки. Nginx менять **не нужно**
(он уже проксирует `/api/` → порт 8282, где работает `xuiweb`).

Файлы: `app_register.py`, `app_payments.py` (лежат рядом с этим README).

---

## Шаг 1. Скопировать 2 файла на сервер

Положить их в папку `xuiweb`, рядом с `run.py`:

```
/root/bot/xuiweb/app_register.py
/root/bot/xuiweb/app_payments.py
```

Способы:
- через SFTP/панель хостинга просто перетащить файлы в `/root/bot/xuiweb/`, **или**
- на сервере командой (пример через scp с локального ПК):
  ```bash
  scp app_register.py app_payments.py root@СЕРВЕР:/root/bot/xuiweb/
  ```

## Шаг 2. Дописать 4 строки в `run.py`

Открыть `/root/bot/xuiweb/run.py` и добавить **в самый конец файла**:

```python
# --- NexonVPN app endpoints ---
from app_register import router as app_register_router
from app_payments import router as app_payments_router
app.include_router(app_register_router)
app.include_router(app_payments_router)
```

(через nano: `nano /root/bot/xuiweb/run.py`, прокрутить в конец, вставить, `Ctrl+O`, `Enter`, `Ctrl+X`.)

## Шаг 3. Перезапустить сервер подписки

```bash
systemctl restart xuiweb
```

## Шаг 4. Проверить, что заработало

```bash
curl -i -X POST https://auth.nexonv.com/api/app/register -H "X-HWID: test12345678"
```

- **Хорошо:** приходит JSON (`{"ok": true, "uuid": ...}` или `{"ok": false, "error": "trial_disabled"}`) — эндпоинт работает.
- **Плохо:** `404 Not Found` — файлы не там или строки не добавлены; проверь Шаги 1–2.

Проверить логи, если что-то не так:
```bash
journalctl -u xuiweb -n 50 --no-pager
```

---

## Возможная проблема: ModuleNotFoundError

Если в логах `ModuleNotFoundError: No module named 'XXX'` — в venv у `xuiweb`
не хватает зависимости. Доставить:
```bash
/root/bot/xuiweb/venv/bin/pip install XXX
systemctl restart xuiweb
```
(эндпоинты используют уже существующие модули бота — `db_helpers`,
`subscription_manager`, `src.pay` — которые лежат в `/root/bot` и подхватываются
автоматически.)

---

## Что дальше

После этого приложение при первом запуске сможет:
- зарегистрировать устройство и получить пробную подписку (`/api/app/register`);
- показать тарифы и создать оплату (`/api/app/tariffs`, `/api/app/purchase`).

Пробный период и лимит устройств берутся из настроек в админке
(`trial_days`, `trial_limit_ip`). Если триал = 0 дней — регистрация вернёт
`trial_disabled` (тогда доступ только после оплаты).
