import logging
from typing import Any, Optional

import gspread
from aiogram import Bot
from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.texts import INVOICE_PAYMENT_FAILED
from database.models import PaymentOrder, PaymentOrderStatus, PaymentProvider
from database.requests import (
    get_payment_order_by_external_invoice_id,
    get_payment_order_by_parent_invoice_id,
    get_user_analytics_profile,
    get_user_by_telegram_id,
    update_payment_order_status,
)
from services.analytics import track_event
from services.payment_activation import (
    activate_initial_subscription,
    activate_recurring_subscription,
    calculate_initial_subscription_end,
    calculate_recurring_subscription_end,
    expire_subscription,
)
from utils.config import Config

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhook", tags=["webhooks"])


def _mask_secret(value: str) -> str:
    if not value:
        return "<empty>"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}***{value[-4:]}"


def _payload_keys(data: Any) -> list[str]:
    if not isinstance(data, dict):
        return []
    return sorted(str(key) for key in data.keys())


def _extract_value(data: dict[str, Any], *keys: str) -> Optional[Any]:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return None


def _extract_invoice_id(data: dict[str, Any]) -> Optional[str]:
    value = _extract_value(data, "invoiceId", "id", "contractId")
    return str(value) if value is not None else None


def _extract_contract_id(data: dict[str, Any]) -> Optional[str]:
    value = _extract_value(data, "contractId")
    return str(value) if value is not None else None


def _extract_parent_invoice_id(data: dict[str, Any]) -> Optional[str]:
    value = _extract_value(data, "parentContractId", "parentInvoiceId", "subscriptionId")
    return str(value) if value is not None else None


def _extract_amount(data: dict[str, Any]) -> float:
    total_amount = data.get("totalAmount")
    if isinstance(total_amount, dict):
        amount = total_amount.get("amount")
        return float(amount or 0)
    if total_amount is not None:
        return float(total_amount)
    amount = data.get("amount")
    return float(amount or 0)


def _extract_currency(data: dict[str, Any], fallback: str) -> str:
    total_amount = data.get("totalAmount")
    if isinstance(total_amount, dict) and total_amount.get("currency"):
        return str(total_amount["currency"])
    if data.get("currency"):
        return str(data["currency"])
    return fallback


def _extract_buyer_email(data: dict[str, Any]) -> Optional[str]:
    buyer = data.get("buyer")
    if isinstance(buyer, dict):
        value = buyer.get("email")
        if value not in (None, ""):
            return str(value).strip().lower()
    value = data.get("email")
    if value not in (None, ""):
        return str(value).strip().lower()
    return None


async def _find_lavatop_order(
    session: AsyncSession,
    data: dict[str, Any],
) -> tuple[Optional[PaymentOrder], Optional[str]]:
    invoice_id = _extract_invoice_id(data)
    contract_id = _extract_contract_id(data)
    parent_invoice_id = _extract_parent_invoice_id(data)

    if invoice_id:
        order = await get_payment_order_by_external_invoice_id(session, invoice_id)
        if order is not None:
            return order, "external_invoice_id"

    for external_ref, source in (
        (parent_invoice_id, "external_parent_invoice_id"),
        (contract_id, "contract_id"),
    ):
        if not external_ref:
            continue
        order = await get_payment_order_by_parent_invoice_id(session, external_ref)
        if order is not None:
            return order, source

        stmt = (
            select(PaymentOrder)
            .where(
                PaymentOrder.provider == PaymentProvider.lavatop,
                PaymentOrder.external_customer_id == external_ref,
            )
            .order_by(PaymentOrder.id.desc())
        )
        result = await session.execute(stmt)
        order = result.scalars().first()
        if order is not None:
            return order, f"{source}:external_customer_id"

    buyer_email = _extract_buyer_email(data)
    amount = _extract_amount(data)
    currency = _extract_currency(data, "")
    if buyer_email:
        stmt = select(PaymentOrder).where(
            PaymentOrder.provider == PaymentProvider.lavatop,
            PaymentOrder.email == buyer_email,
            PaymentOrder.status == PaymentOrderStatus.created,
        )
        if amount > 0:
            stmt = stmt.where(PaymentOrder.amount == amount)
        if currency:
            stmt = stmt.where(PaymentOrder.currency == currency)
        stmt = stmt.order_by(PaymentOrder.created_at.desc(), PaymentOrder.id.desc())
        result = await session.execute(stmt)
        order = result.scalars().first()
        if order is not None:
            return order, "buyer_email+amount+currency"

        stmt = (
            select(PaymentOrder)
            .where(
                PaymentOrder.provider == PaymentProvider.lavatop,
                PaymentOrder.email == buyer_email,
                or_(
                    PaymentOrder.status == PaymentOrderStatus.created,
                    PaymentOrder.status == PaymentOrderStatus.failed,
                ),
            )
            .order_by(PaymentOrder.created_at.desc(), PaymentOrder.id.desc())
        )
        result = await session.execute(stmt)
        order = result.scalars().first()
        if order is not None:
            return order, "buyer_email"

    return None, None


async def handle_payment_success(
    data: dict[str, Any],
    session: AsyncSession,
    bot: Bot,
    config: Config,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    invoice_id = _extract_invoice_id(data)
    if not invoice_id:
        logger.warning("LavaTop payment.success без invoice id")
        return

    order, match_source = await _find_lavatop_order(session, data)
    if order is None:
        logger.warning(
            "LavaTop order не найден: invoice=%s contract=%s buyer_email=%s amount=%s currency=%s",
            invoice_id,
            _extract_contract_id(data),
            _extract_buyer_email(data),
            _extract_amount(data),
            _extract_currency(data, ""),
        )
        return

    logger.info(
        "LavaTop payment.success matched order: order_id=%s telegram_id=%s invoice=%s incoming_invoice=%s contract=%s match_source=%s status=%s",
        order.id,
        order.telegram_id,
        order.external_invoice_id,
        invoice_id,
        _extract_contract_id(data),
        match_source,
        order.status.value,
    )

    if order.status == PaymentOrderStatus.paid:
        logger.info(f"LavaTop payment.success duplicate ignored for invoice={order.external_invoice_id}")
        return

    parent_invoice_id = _extract_parent_invoice_id(data)
    contract_id = _extract_contract_id(data)
    amount = _extract_amount(data) or float(order.amount or 0)
    currency = _extract_currency(data, order.currency)
    subscription_end = calculate_initial_subscription_end(order.tariff)

    await update_payment_order_status(
        session=session,
        external_invoice_id=order.external_invoice_id,
        status=PaymentOrderStatus.paid,
        external_parent_invoice_id=parent_invoice_id,
        external_customer_id=parent_invoice_id or contract_id,
    )

    await activate_initial_subscription(
        session=session,
        bot=bot,
        config=config,
        telegram_id=order.telegram_id,
        subscription_end=subscription_end,
        amount=amount,
        provider=PaymentProvider.lavatop,
        external_payment_id=order.external_invoice_id,
        payment_customer_id=parent_invoice_id or contract_id or order.external_invoice_id,
        gspread_client=gspread_client,
    )

    logger.info(f"LavaTop initial payment processed: telegram_id={order.telegram_id}, invoice={invoice_id}, currency={currency}")


async def handle_payment_failed(
    data: dict[str, Any],
    session: AsyncSession,
    bot: Bot,
    config: Config,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    invoice_id = _extract_invoice_id(data)
    if not invoice_id:
        logger.warning("LavaTop payment.failed без invoice id")
        return
    order, match_source = await _find_lavatop_order(session, data)
    if order is None:
        logger.warning(
            "LavaTop failed order не найден: invoice=%s contract=%s buyer_email=%s amount=%s currency=%s",
            invoice_id,
            _extract_contract_id(data),
            _extract_buyer_email(data),
            _extract_amount(data),
            _extract_currency(data, ""),
        )
        return
    logger.info(
        "LavaTop payment.failed matched order: order_id=%s telegram_id=%s invoice=%s incoming_invoice=%s contract=%s match_source=%s status=%s",
        order.id,
        order.telegram_id,
        order.external_invoice_id,
        invoice_id,
        _extract_contract_id(data),
        match_source,
        order.status.value,
    )

    if order.status == PaymentOrderStatus.failed:
        logger.info(f"LavaTop payment.failed duplicate ignored for invoice={order.external_invoice_id}")
        return

    await update_payment_order_status(
        session=session,
        external_invoice_id=order.external_invoice_id,
        status=PaymentOrderStatus.failed,
    )

    try:
        await bot.send_message(chat_id=order.telegram_id, text=INVOICE_PAYMENT_FAILED, parse_mode="Markdown")
        profile = await get_user_analytics_profile(session, order.telegram_id)
        await track_event(
            session,
            telegram_id=order.telegram_id,
            journey="payment",
            onboarding_version=profile.onboarding_version if profile and profile.onboarding_version else "core",
            event_name="payment_failed",
            source="lavatop:payment.failed",
            provider=PaymentProvider.lavatop,
            metadata={"invoice_id": invoice_id or order.external_invoice_id},
            config=config,
            gspread_client=gspread_client,
        )
    except Exception as e:
        logger.warning(f"Не удалось уведомить пользователя {order.telegram_id}: {e}")


async def handle_recurring_payment_success(
    data: dict[str, Any],
    session: AsyncSession,
    bot: Bot,
    config: Config,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    invoice_id = _extract_invoice_id(data)
    parent_invoice_id = _extract_parent_invoice_id(data)
    if not invoice_id and not parent_invoice_id:
        logger.warning("LavaTop recurring success без invoice id")
        return

    order = None
    if parent_invoice_id:
        order = await get_payment_order_by_parent_invoice_id(session, parent_invoice_id)
    if order is None and invoice_id:
        order = await get_payment_order_by_external_invoice_id(session, invoice_id)
    if order is None:
        logger.warning(f"LavaTop recurring order не найден для invoice={invoice_id}, parent={parent_invoice_id}")
        return

    logger.info(
        "LavaTop recurring success matched order: order_id=%s telegram_id=%s invoice=%s parent=%s status=%s",
        order.id,
        order.telegram_id,
        order.external_invoice_id,
        parent_invoice_id,
        order.status.value,
    )

    user = await get_user_by_telegram_id(session, order.telegram_id)
    if user is None:
        logger.warning(f"LavaTop recurring success: пользователь {order.telegram_id} не найден")
        return

    subscription_end = calculate_recurring_subscription_end(user.subscription_end_date, order.tariff)
    amount = _extract_amount(data) or float(order.amount or 0)

    await update_payment_order_status(
        session=session,
        external_invoice_id=order.external_invoice_id,
        status=PaymentOrderStatus.paid,
        external_parent_invoice_id=parent_invoice_id or order.external_parent_invoice_id,
        external_customer_id=parent_invoice_id or order.external_customer_id,
    )

    await activate_recurring_subscription(
        session=session,
        bot=bot,
        telegram_id=order.telegram_id,
        subscription_end=subscription_end,
        amount=amount,
        provider=PaymentProvider.lavatop,
        external_payment_id=invoice_id or parent_invoice_id or order.external_invoice_id,
        payment_customer_id=parent_invoice_id or order.external_customer_id or order.external_invoice_id,
        config=config,
        gspread_client=gspread_client,
    )


async def handle_recurring_payment_failed(
    data: dict[str, Any],
    session: AsyncSession,
    bot: Bot,
    config: Config,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    parent_invoice_id = _extract_parent_invoice_id(data)
    invoice_id = _extract_invoice_id(data)
    order = None
    if parent_invoice_id:
        order = await get_payment_order_by_parent_invoice_id(session, parent_invoice_id)
    if order is None and invoice_id:
        order = await get_payment_order_by_external_invoice_id(session, invoice_id)
    if order is None:
        logger.warning(f"LavaTop recurring failed order не найден для invoice={invoice_id}, parent={parent_invoice_id}")
        return

    logger.info(
        "LavaTop recurring failed matched order: order_id=%s telegram_id=%s invoice=%s parent=%s status=%s",
        order.id,
        order.telegram_id,
        order.external_invoice_id,
        parent_invoice_id,
        order.status.value,
    )

    await update_payment_order_status(
        session=session,
        external_invoice_id=order.external_invoice_id,
        status=PaymentOrderStatus.failed,
    )

    try:
        await bot.send_message(chat_id=order.telegram_id, text=INVOICE_PAYMENT_FAILED, parse_mode="Markdown")
        profile = await get_user_analytics_profile(session, order.telegram_id)
        await track_event(
            session,
            telegram_id=order.telegram_id,
            journey="payment",
            onboarding_version=profile.onboarding_version if profile and profile.onboarding_version else "core",
            event_name="payment_failed",
            source="lavatop:subscription.payment_failed",
            provider=PaymentProvider.lavatop,
            metadata={"invoice_id": invoice_id or order.external_invoice_id},
            config=config,
            gspread_client=gspread_client,
        )
    except Exception as e:
        logger.warning(f"Не удалось уведомить пользователя {order.telegram_id}: {e}")


async def handle_subscription_cancelled(
    data: dict[str, Any],
    session: AsyncSession,
    bot: Bot,
    config: Config,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    parent_invoice_id = _extract_parent_invoice_id(data)
    invoice_id = _extract_invoice_id(data)
    order = None
    if parent_invoice_id:
        order = await get_payment_order_by_parent_invoice_id(session, parent_invoice_id)
    if order is None and invoice_id:
        order = await get_payment_order_by_external_invoice_id(session, invoice_id)
    if order is None:
        logger.warning(f"LavaTop cancelled order не найден для invoice={invoice_id}, parent={parent_invoice_id}")
        return

    logger.info(
        "LavaTop subscription.cancelled matched order: order_id=%s telegram_id=%s invoice=%s parent=%s status=%s",
        order.id,
        order.telegram_id,
        order.external_invoice_id,
        parent_invoice_id,
        order.status.value,
    )

    await update_payment_order_status(
        session=session,
        external_invoice_id=order.external_invoice_id,
        status=PaymentOrderStatus.cancelled,
    )
    await expire_subscription(session, bot, config, order.telegram_id, gspread_client)


def create_lavatop_webhook_endpoint(
    session_factory: async_sessionmaker[AsyncSession],
    bot: Bot,
    config: Config,
    gspread_client: Optional[gspread.Client] = None,
) -> APIRouter:
    @router.post("/lavatop")
    async def lavatop_webhook(
        request: Request,
        x_api_key: str = Header(default="", alias="X-Api-Key"),
    ) -> dict[str, str]:
        raw_body = await request.body()
        logger.info(
            "LavaTop webhook request received: method=%s path=%s host=%s content_type=%s body_len=%s has_x_api_key=%s received_key=%s",
            request.method,
            request.url.path,
            request.headers.get("host", ""),
            request.headers.get("content-type", ""),
            len(raw_body),
            bool(x_api_key),
            _mask_secret(x_api_key),
        )

        if not config.lavatop_webhook_incoming_key:
            logger.error("LavaTop webhook rejected: incoming key is not configured")
            raise HTTPException(status_code=503, detail="LavaTop webhook is not configured")
        if x_api_key != config.lavatop_webhook_incoming_key:
            logger.warning(
                "LavaTop webhook rejected: invalid X-Api-Key received=%s expected=%s",
                _mask_secret(x_api_key),
                _mask_secret(config.lavatop_webhook_incoming_key),
            )
            raise HTTPException(status_code=401, detail="Invalid X-Api-Key")

        try:
            payload = await request.json()
        except Exception:
            logger.exception(
                "LavaTop webhook payload parse failed: raw_body=%s",
                raw_body[:1000].decode("utf-8", errors="replace"),
            )
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

        event_type = payload.get("eventType")
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        if not isinstance(data, dict):
            logger.warning(
                "LavaTop webhook rejected: invalid payload structure event_type=%s payload_keys=%s",
                event_type,
                _payload_keys(payload),
            )
            raise HTTPException(status_code=400, detail="Invalid payload")

        invoice_id = _extract_invoice_id(data)
        parent_invoice_id = _extract_parent_invoice_id(data)
        logger.info(
            "LavaTop webhook parsed: event_type=%s payload_keys=%s data_keys=%s invoice_id=%s parent_invoice_id=%s",
            event_type,
            _payload_keys(payload),
            _payload_keys(data),
            invoice_id,
            parent_invoice_id,
        )

        handled = True
        try:
            async with session_factory() as session:
                if event_type == "payment.success":
                    await handle_payment_success(data, session, bot, config, gspread_client)
                elif event_type == "payment.failed":
                    await handle_payment_failed(data, session, bot, config, gspread_client)
                elif event_type == "subscription.recurring.payment.success":
                    await handle_recurring_payment_success(data, session, bot, config, gspread_client)
                elif event_type == "subscription.recurring.payment.failed":
                    await handle_recurring_payment_failed(data, session, bot, config, gspread_client)
                elif event_type == "subscription.cancelled":
                    await handle_subscription_cancelled(data, session, bot, config, gspread_client)
                else:
                    handled = False
                    logger.warning(f"Необработанное LavaTop событие: {event_type}")
        except Exception:
            logger.exception(
                "LavaTop webhook processing failed: event_type=%s invoice_id=%s parent_invoice_id=%s",
                event_type,
                invoice_id,
                parent_invoice_id,
            )
            raise

        logger.info(
            "LavaTop webhook completed: event_type=%s handled=%s invoice_id=%s parent_invoice_id=%s",
            event_type,
            handled,
            invoice_id,
            parent_invoice_id,
        )

        return {"status": "ok"}

    return router
