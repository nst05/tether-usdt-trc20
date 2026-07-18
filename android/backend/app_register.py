"""
NexonVPN — публичный эндпоинт автономной регистрации из мобильного приложения.

Назначение
----------
Приложение при первом запуске вызывает POST /api/app/register с заголовком
X-HWID (идентификатор устройства). Сервер заводит «устройственного» пользователя
(без Telegram), выдаёт ему пробную подписку и возвращает UUID для формирования
ссылки подписки {sub_page_url}/sub/{uuid}. Дальше приложение работает через уже
существующий /api/sub/{uuid}.

Идемпотентность
---------------
Соответствие hwid → синтетический telegram_id хранится в таблице app_devices.
Повторный вызов с тем же X-HWID вернёт тот же UUID (без выдачи второго триала).

Интеграция (в xuiweb/run.py)
----------------------------
    from app_register import router as app_register_router
    app.include_router(app_register_router)

Модуль переиспользует функции бота: db_helpers.add_user,
subscription_manager.grant_subscription, db_helpers.get_last_subscription.
Он должен запускаться в окружении, где эти модули импортируемы (тот же репозиторий
бота). Если xuiweb вынесен отдельно — импортируйте эти функции из общего пакета.

Защита от абьюза (опционально)
------------------------------
Если задан env APP_REGISTER_TOKEN, запрос обязан содержать заголовок
X-App-Token с этим значением.
"""

from __future__ import annotations

import hashlib
import logging
import os

import aiosqlite
from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("app_register")

router = APIRouter()

# Функции бота (тот же репозиторий). Если структура иная — поправьте импорты.
import db_helpers  # noqa: E402
import subscription_manager  # noqa: E402
from app_config import app_conf  # noqa: E402

# Путь к БД — тот же, что использует xuiweb.
try:
    from config import DB_PATH as _DB_PATH  # type: ignore
except Exception:  # pragma: no cover
    _DB_PATH = os.getenv("DB_PATH", "users.db")


def _synthetic_telegram_id(hwid: str) -> int:
    """Стабильный отрицательный id из hwid (не пересекается с реальными TG id > 0)."""
    h = hashlib.sha256(hwid.encode()).hexdigest()
    n = int(h[:15], 16) % 2_000_000_000
    return -(n + 100_000_000)


async def _ensure_device_table() -> None:
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS app_devices (
                hwid        TEXT PRIMARY KEY,
                telegram_id INTEGER NOT NULL,
                created_at  TEXT DEFAULT (datetime('now'))
            )
            """
        )
        await db.commit()


async def _get_device_user(hwid: str) -> int | None:
    async with aiosqlite.connect(_DB_PATH) as db:
        async with db.execute(
            "SELECT telegram_id FROM app_devices WHERE hwid = ?", (hwid,)
        ) as cur:
            row = await cur.fetchone()
            return int(row[0]) if row else None


async def _bind_device(hwid: str, telegram_id: int) -> None:
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO app_devices (hwid, telegram_id) VALUES (?, ?)",
            (hwid, telegram_id),
        )
        await db.commit()


async def _sub_uuid_for(user_id: int) -> str | None:
    sub = await db_helpers.get_last_subscription(user_id)
    if sub and sub.get("xui_client_uuid"):
        return sub["xui_client_uuid"]
    return None


def _sub_url(uuid: str) -> str:
    base = str(app_conf.get("sub_page_url", "https://vpn.example.com")).rstrip("/")
    return f"{base}/sub/{uuid}"


@router.post("/api/app/register")
async def app_register(
    request: Request,
    x_hwid: str | None = Header(default=None, alias="X-HWID"),
    x_forwarded_hwid: str | None = Header(default=None, alias="X-Forwarded-HWID"),
    x_app_token: str | None = Header(default=None, alias="X-App-Token"),
):
    # Опциональная защита токеном
    required_token = os.getenv("APP_REGISTER_TOKEN")
    if required_token and x_app_token != required_token:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

    # HWID из заголовка или тела
    hwid = (x_hwid or x_forwarded_hwid or "").strip()
    if not hwid:
        try:
            body = await request.json()
            hwid = str(body.get("hwid", "")).strip()
        except Exception:
            hwid = ""
    if not hwid or len(hwid) < 8 or len(hwid) > 128:
        return JSONResponse({"ok": False, "error": "invalid_hwid"}, status_code=400)

    await _ensure_device_table()

    # Уже зарегистрированное устройство → отдаём существующую подписку (идемпотентно)
    existing_uid = await _get_device_user(hwid)
    if existing_uid is not None:
        uuid = await _sub_uuid_for(existing_uid)
        if uuid:
            return JSONResponse({"ok": True, "uuid": uuid, "sub_url": _sub_url(uuid)})
        # маппинг есть, но подписки нет (например, была удалена) — выдадим заново ниже
        user_id = existing_uid
    else:
        user_id = _synthetic_telegram_id(hwid)

    # Параметры триала из настроек
    try:
        trial_days = int(app_conf.get("trial_days", 3) or 3)
    except (TypeError, ValueError):
        trial_days = 3
    try:
        trial_limit_ip = int(app_conf.get("trial_limit_ip", 0) or 0)
    except (TypeError, ValueError):
        trial_limit_ip = 0

    if trial_days <= 0:
        return JSONResponse({"ok": False, "error": "trial_disabled"}, status_code=403)

    # Заводим пользователя и выдаём пробную подписку
    try:
        await db_helpers.add_user(user_id, username=f"app_{hwid[:8]}")
        result = await subscription_manager.grant_subscription(
            user_id, trial_days, is_trial=True, limit_ip=trial_limit_ip
        )
    except Exception as e:  # pragma: no cover
        logger.error("[app/register] provision failed for %s: %s", user_id, e, exc_info=True)
        return JSONResponse({"ok": False, "error": "provision_failed"}, status_code=500)

    if not result or result.get("error"):
        return JSONResponse({"ok": False, "error": "provision_failed"}, status_code=500)

    uuid = await _sub_uuid_for(user_id) or result.get("xui_client_uuid")
    if not uuid:
        return JSONResponse({"ok": False, "error": "no_uuid"}, status_code=500)

    await _bind_device(hwid, user_id)

    expires_at = ""
    exp = result.get("expiry_date")
    if exp is not None and hasattr(exp, "isoformat"):
        expires_at = exp.isoformat()

    return JSONResponse({
        "ok": True,
        "uuid": uuid,
        "sub_url": _sub_url(uuid),
        "expires_at": expires_at,
    })
