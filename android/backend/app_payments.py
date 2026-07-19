"""
NexonVPN — публичные эндпоинты тарифов и оплаты для мобильного приложения.

Повторяют платёжный флоу сайта (website/run.py → POST /pay/{tariff_id}), но
идентифицируют пользователя по устройству (заголовок X-HWID → app_devices →
синтетический user_id, заведённый в app_register). Зачисление после оплаты
выполняет ШТАТНЫЙ вебхук провайдера (process_successful_payment по user_id из
metadata) — здесь ничего дублировать не нужно.

Поддерживаемые методы (как на сайте): yookassa, platega, yoomoney, wata.

Интеграция (в xuiweb/run.py):
    from app_payments import router as app_payments_router
    app.include_router(app_payments_router)

Требует, чтобы модули бота (db_helpers, src.pay) были импортируемы, а провайдеры
настроены в админке (ключи в таблице settings) — те же, что использует сайт.
"""

from __future__ import annotations

import logging
import os
import time

import aiosqlite
from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("app_payments")
router = APIRouter()

import db_helpers  # noqa: E402
from app_config import app_conf  # noqa: E402

try:
    from config import DB_PATH as _DB_PATH  # type: ignore
except Exception:  # pragma: no cover
    _DB_PATH = os.getenv("DB_PATH", "users.db")


# ── Настройки/креды (env → settings, как на сайте) ───────────────────────────
async def _get_setting(key: str, default: str = "") -> str:
    async with aiosqlite.connect(_DB_PATH) as db:
        async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
            return (row[0] if row and row[0] else default) or default


async def _uid_for_hwid(hwid: str) -> int | None:
    async with aiosqlite.connect(_DB_PATH) as db:
        async with db.execute(
            "SELECT telegram_id FROM app_devices WHERE hwid = ?", (hwid,)
        ) as cur:
            row = await cur.fetchone()
            return int(row[0]) if row else None


def _base_url() -> str:
    return str(app_conf.get("sub_page_url", "https://vpn.example.com")).rstrip("/")


# ── Тарифы ───────────────────────────────────────────────────────────────────
@router.get("/api/app/tariffs")
async def app_tariffs():
    tariffs = await db_helpers.get_active_tariffs()
    out = [
        {
            "id": t["id"],
            "name": t.get("name", ""),
            "days": int(t.get("days") or 0),
            "price": float(t.get("price") or 0),
            "currency": t.get("currency", "RUB"),
            "traffic_gb": int(t.get("traffic_gb") or 0),
            "limit_ip": int(t.get("limit_ip") or 0),
            "description": t.get("description") or "",
        }
        for t in tariffs
    ]
    return JSONResponse({"tariffs": out})


# ── Создание платежа ─────────────────────────────────────────────────────────
@router.post("/api/app/purchase")
async def app_purchase(
    request: Request,
    x_hwid: str | None = Header(default=None, alias="X-HWID"),
    x_forwarded_hwid: str | None = Header(default=None, alias="X-Forwarded-HWID"),
):
    hwid = (x_hwid or x_forwarded_hwid or "").strip()
    body = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not hwid:
        hwid = str(body.get("hwid", "")).strip()
    if not hwid:
        return JSONResponse({"ok": False, "error": "no_hwid"}, status_code=400)

    uid = await _uid_for_hwid(hwid)
    if uid is None:
        return JSONResponse({"ok": False, "error": "not_registered"}, status_code=404)

    try:
        tariff_id = int(body.get("tariff_id"))
    except (TypeError, ValueError):
        return JSONResponse({"ok": False, "error": "bad_tariff"}, status_code=400)
    method = str(body.get("method", "yookassa")).strip().lower()

    tariff = await db_helpers.get_tariff_by_id(tariff_id)
    if not tariff or not tariff.get("is_active", 1):
        return JSONResponse({"ok": False, "error": "tariff_not_found"}, status_code=404)

    amount = float(tariff["price"])
    currency = tariff.get("currency", "RUB")
    return_url = f"{_base_url()}/app/paid"  # приложение опрашивает статус само

    result = None
    try:
        if method == "yookassa":
            shop_id = os.getenv("WEBSITE_YOOKASSA_SHOP_ID", "").strip() or await _get_setting("yookassa_shop_id")
            secret = os.getenv("WEBSITE_YOOKASSA_SECRET_KEY", "").strip() or await _get_setting("yookassa_secret_key")
            if not shop_id or not secret:
                return JSONResponse({"ok": False, "error": "method_unavailable"}, status_code=503)
            from src.pay import create_yookassa_payment_shared
            result = await create_yookassa_payment_shared(
                shop_id=shop_id, secret_key=secret, amount=amount, currency=currency,
                tariff=tariff, user_id=uid, return_url=return_url,
                registration_type="app", email="",
            )

        elif method == "platega":
            merchant_id = os.getenv("WEBSITE_PLATEGA_MERCHANT_ID", "").strip() or await _get_setting("platega_merchant_id")
            api_secret = os.getenv("WEBSITE_PLATEGA_API_SECRET", "").strip() or await _get_setting("platega_api_secret")
            if not merchant_id or not api_secret:
                return JSONResponse({"ok": False, "error": "method_unavailable"}, status_code=503)
            from src.pay import create_platega_payment_shared
            result = await create_platega_payment_shared(
                merchant_id=merchant_id, api_secret=api_secret, amount=amount,
                tariff=tariff, user_id=uid, return_url=return_url,
                registration_type="app", email="",
            )

        elif method == "wata":
            wata_token = (
                os.getenv("WEBSITE_WATA_ACCESS_TOKEN", "").strip()
                or os.getenv("WATA_ACCESS_TOKEN", "").strip()
                or await _get_setting("wata_access_token")
            )
            wata_pid = (
                os.getenv("WEBSITE_WATA_TERMINAL_PUBLIC_ID", "").strip()
                or os.getenv("WATA_TERMINAL_PUBLIC_ID", "").strip()
                or await _get_setting("wata_terminal_public_id")
            )
            if not wata_token:
                return JSONResponse({"ok": False, "error": "method_unavailable"}, status_code=503)
            from src.pay import create_wata_payment_shared
            result = await create_wata_payment_shared(
                wata_token, amount=amount, tariff=tariff, user_id=uid,
                return_url=return_url, registration_type="app", email="",
                currency=currency, terminal_public_id=wata_pid,
            )

        elif method == "yoomoney":
            account = os.getenv("WEBSITE_YOOMONEY_ACCOUNT", "").strip() or await _get_setting("yoomoney_account")
            token = os.getenv("WEBSITE_YOOMONEY_TOKEN", "").strip() or await _get_setting("yoomoney_token")
            notif = os.getenv("WEBSITE_YOOMONEY_NOTIFICATION_SECRET", "").strip() or await _get_setting("yoomoney_notification_secret")
            if not account or not token or not notif:
                return JSONResponse({"ok": False, "error": "method_unavailable"}, status_code=503)
            from src.pay import create_yoomoney_quickpay
            ym_payment_id = f"YOOMONEY_{int(time.time())}_{uid}_{tariff_id}"
            ym_meta = {
                "telegram_user_id": uid, "user_id": uid,
                "subscription_days": int(tariff.get("days") or 0),
                "days": int(tariff.get("days") or 0),
                "limit_ip": int(tariff.get("limit_ip") or 0),
                "price": amount, "amount": amount, "currency": currency,
                "tariff_id": tariff_id, "registration_type": "app",
                "payment_method": "YooMoney",
            }
            url = await create_yoomoney_quickpay(
                account=account, telegram_id=uid, payment_id=ym_payment_id,
                amount=amount, currency=currency,
                target_text=f"Подписка {tariff.get('name', '')}".strip(),
                metadata=ym_meta,
            )
            result = (ym_payment_id, url) if url else None
        else:
            return JSONResponse({"ok": False, "error": "unknown_method"}, status_code=400)
    except Exception as e:  # pragma: no cover
        logger.error("[app/purchase] provider error uid=%s method=%s: %s", uid, method, e, exc_info=True)
        return JSONResponse({"ok": False, "error": "provider_error"}, status_code=500)

    url = result[1] if result else None
    if not url:
        return JSONResponse({"ok": False, "error": "payment_failed"}, status_code=500)

    return JSONResponse({"ok": True, "payment_url": url})
