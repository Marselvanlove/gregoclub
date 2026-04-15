# FastAPI роутер для обработки вебхуков Stripe
# Эндпоинт: POST /webhook/stripe

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from dateutil.relativedelta import relativedelta

import httpx
from aiogram import Bot
from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from database.models import PaymentOrderStatus, PaymentProvider, UserStatus
from database.requests import (
    add_payment,
    get_user_analytics_profile,
    get_user_by_stripe_customer_id,
    get_user_by_telegram_id,
    update_payment_order_status,
    update_user_status,
    update_user_subscription,
)
from bot.texts import (
    ACTIVE_PAYMENT_SUCCESS,
    ACTIVE_PAYMENT_SUCCESS_NO_LINK,
    ACTIVE_RENEWAL_SUCCESS,
    EXPIRED_SUBSCRIPTION_CANCELLED,
    INVOICE_PAYMENT_FAILED,
    format_text,
)
from services.google_sheets import add_buyer_to_sheets
from services.analytics import track_event
from services.payment_activation import (
    activate_initial_subscription,
    activate_recurring_subscription,
    calculate_initial_subscription_end,
    expire_subscription,
)
from services.stripe_api import get_subscription_by_id, init_stripe, verify_webhook_signature
from utils.config import Config
import gspread

logger = logging.getLogger(__name__)

# Early-bird акция: оплата строго ДО 5 марта 2026 00:00 Madrid CET (= 4 марта 23:00 UTC)
_EARLY_BIRD_DEADLINE = datetime(2026, 3, 4, 23, 0, 0)
_EARLY_BIRD_BASE     = datetime(2026, 3, 5, 0, 0, 0)  # base_date = старт занятий

router = APIRouter(prefix="/webhook", tags=["webhooks"])

# URL внешнего AI бота Grego
GREGO_BOT_API_URL = "http://bot.hablacongrego.com"


async def add_user_to_grego_bot(telegram_id: int) -> bool:
    """
    Добавляет пользователя в AI бот Grego.
    Возвращает True при успехе, False при ошибке.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{GREGO_BOT_API_URL}/add_user", params={"telegram_id": telegram_id})
            if response.status_code == 200:
                logger.info(f"Пользователь {telegram_id} добавлен в Grego бот")
                return True
            else:
                logger.warning(f"Ошибка добавления в Grego бот: {response.status_code} - {response.text}")
                return False
    except Exception as e:
        logger.error(f"Не удалось связаться с Grego ботом для добавления {telegram_id}: {e}")
        return False


async def remove_user_from_grego_bot(telegram_id: int) -> bool:
    """
    Удаляет пользователя из AI бота Grego.
    Возвращает True при успехе, False при ошибке.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{GREGO_BOT_API_URL}/remove_user", params={"telegram_id": telegram_id})
            if response.status_code == 200:
                logger.info(f"Пользователь {telegram_id} удалён из Grego бот")
                return True
            else:
                logger.warning(f"Ошибка удаления из Grego бот: {response.status_code} - {response.text}")
                return False
    except Exception as e:
        logger.error(f"Не удалось связаться с Grego ботом для удаления {telegram_id}: {e}")
        return False


async def send_upcoming_event_invitation(
    session: AsyncSession,
    bot: Bot,
    telegram_id: int,
) -> None:
    """
    Отправляет персональные приглашения на ВСЕ предстоящие встречи с RSVP-кнопками.
    Вызывается после успешной оплаты подписки.
    
    Алгоритм расчета времени отправки для каждого события:
    - < 24 часов до события → отправить немедленно
    - 1-3 дня до события → отправить за 1 день до события
    - 3+ дней до события → отправить за 3 дня до события
    
    С коррекцией: минимум 2 часа между отправками для избежания спама.
    Если после коррекции отправка опаздывает (< 30 минут до события), отправляется сразу.
    """
    import logging
    from database.requests import get_upcoming_events, create_pending_invitation, get_scheduled_broadcast
    from database.models import BroadcastStatus
    from bot.keyboards.inline import get_rsvp_buttons_keyboard
    from bot.texts import ACTIVE_EVENT_INVITATION, format_text
    from datetime import timedelta
    import pytz
    
    logger = logging.getLogger(__name__)
    
    # Получаем ВСЕ предстоящие встречи
    events = await get_upcoming_events(session, limit=100)
    if not events:
        logger.info(f"Нет предстоящих встреч для приглашения пользователя {telegram_id}")
        return
    
    madrid_tz = pytz.timezone("Europe/Madrid")
    now = datetime.now(madrid_tz).replace(tzinfo=None)
    
    # Вспомогательная функция для отправки приглашения
    async def send_invitation(event):
        event_dt = madrid_tz.localize(event.rsvp_event_datetime)
        
        # Форматируем дату и время
        day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        day_name = day_names[event_dt.weekday()]
        event_date = event_dt.strftime(f"{day_name}, %d.%m.%Y")
        event_time = event_dt.strftime("%H:%M Madrid")
        
        # Формируем текст приглашения
        text = format_text(
            ACTIVE_EVENT_INVITATION,
            event_title=event.rsvp_event_title,
            event_date=event_date,
            event_time=event_time,
        )
        
        # Отправляем приглашение с RSVP-кнопками
        try:
            await bot.send_message(
                chat_id=telegram_id,
                text=text,
                reply_markup=get_rsvp_buttons_keyboard(event.id),
                parse_mode="Markdown",
            )
            logger.info(f"Персональное приглашение на встречу #{event.id} отправлено пользователю {telegram_id}")
            return True
        except Exception as e:
            logger.warning(f"Не удалось отправить приглашение на встречу пользователю {telegram_id}: {e}")
            return False
    
    # Функция для расчета оптимального времени отправки
    def calculate_send_time(event_datetime, current_time):
        """
        Рассчитывает оптимальное время отправки приглашения.
        Возвращает (send_at, priority).
        """
        time_until = event_datetime - current_time
        
        if time_until < timedelta(days=1):
            # Событие через < 24 часов → отправить НЕМЕДЛЕННО
            # (коррекция интервалов расставит события с промежутком 2ч)
            return current_time, "urgent"
        elif time_until < timedelta(days=3):
            # Событие через 1-3 дня → отправить за 1 день до события
            return event_datetime - timedelta(days=1), "medium"
        else:
            # Событие через 3+ дней → отправить за 3 дня до события
            return event_datetime - timedelta(days=3), "normal"
    
    # Подготовка расписания отправки для всех событий
    event_schedule = []
    
    for event in events:
        send_at, priority = calculate_send_time(event.rsvp_event_datetime, now)
        
        # Если расчетное время уже прошло, отправить немедленно
        if send_at < now:
            send_at = now
        
        # Получаем broadcast для проверки статуса
        broadcast = await get_scheduled_broadcast(session, event.id)
        
        if not broadcast:
            logger.warning(f"Не найден broadcast #{event.id}, пропускаем")
            continue
        
        event_schedule.append({
            'event': event,
            'broadcast': broadcast,
            'send_at': send_at,
            'priority': priority
        })
    
    if not event_schedule:
        logger.info(f"Нет валидных событий для пользователя {telegram_id}")
        return
    
    # Сортируем по времени отправки (раньше → позже)
    event_schedule.sort(key=lambda x: x['send_at'])
    
    logger.info(f"Обработка {len(event_schedule)} событий для пользователя {telegram_id}")
    
    # КОРРЕКЦИЯ: Минимальный интервал между отправками (2 часа)
    MIN_INTERVAL = timedelta(hours=2)
    last_send_time = None  # Начинаем с None, чтобы первое событие не сдвигалось
    
    for item in event_schedule:
        original_send_at = item['send_at']
        
        # Если это НЕ первое событие и отправка слишком близко к предыдущей
        if last_send_time is not None and item['send_at'] - last_send_time < MIN_INTERVAL:
            # НЕ сдвигаем события, которые должны быть отправлены немедленно
            if item['send_at'] > now:
                # Только сдвигаем если это не приведет к опозданию
                new_send_time = last_send_time + MIN_INTERVAL
                event_dt = item['event'].rsvp_event_datetime
                
                # Проверка: не опоздали ли? (минимум за 30 минут до события)
                if new_send_time >= event_dt - timedelta(minutes=30):
                    # Слишком поздно — отправить сразу
                    item['send_at'] = now
                    logger.info(f"Событие #{item['event'].id}: сдвиг приведет к опозданию, отправка немедленно")
                else:
                    item['send_at'] = new_send_time
                    logger.info(f"Событие #{item['event'].id}: сдвиг с {original_send_at} на {new_send_time}")
        
        # Обновляем last_send_time для следующей итерации
        if item['send_at'] <= now:
            # Для немедленных отправок используем now как базу для следующего интервала
            last_send_time = now
            logger.info(f"Событие #{item['event'].id}: отправка НЕМЕДЛЕННО (send_at={item['send_at']})")
        else:
            last_send_time = item['send_at']
            logger.info(f"Событие #{item['event'].id}: отложенная отправка на {item['send_at']}")
    
    # Отправка или создание отложенных приглашений
    for item in event_schedule:
        event = item['event']
        send_at = item['send_at']
        
        # Если время отправки уже наступило (или через 1 минуту)
        if send_at <= now + timedelta(minutes=1):
            # Отправляем приглашение немедленно
            logger.info(f"→ Отправка приглашения на событие #{event.id} пользователю {telegram_id} СЕЙЧАС")
            await send_invitation(event)
        else:
            # Создаём отложенное приглашение
            await create_pending_invitation(
                session=session,
                telegram_id=telegram_id,
                broadcast_id=event.id,
                send_at=send_at,
            )
            logger.info(
                f"→ Создано отложенное приглашение на событие #{event.id} "
                f"для пользователя {telegram_id}, отправка: {send_at}"
            )


async def handle_checkout_completed(
    event_data: dict,
    session: AsyncSession,
    bot: Bot,
    config: Config,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    """
    Обработка события checkout.session.completed.
    Первичная оплата успешна — активируем подписку.
    """
    checkout_session = event_data

    # Получаем telegram_id из client_reference_id
    telegram_id_str = checkout_session.get("client_reference_id")
    if not telegram_id_str:
        logger.warning("checkout.session.completed без client_reference_id")
        return

    telegram_id = int(telegram_id_str)
    stripe_customer_id = checkout_session.get("customer")
    subscription_id = checkout_session.get("subscription")
    amount_total = checkout_session.get("amount_total", 0) / 100  # Stripe хранит в центах
    tariff = checkout_session.get("metadata", {}).get("tariff", "1month")

    subscription_end = calculate_initial_subscription_end(tariff)
    stripe_payment_id = subscription_id or checkout_session.get("id")
    checkout_session_id = checkout_session.get("id")

    if checkout_session_id:
        try:
            await update_payment_order_status(
                session=session,
                external_invoice_id=checkout_session_id,
                status=PaymentOrderStatus.paid,
                external_customer_id=stripe_customer_id,
            )
        except Exception as exc:
            logger.warning("Не удалось обновить Stripe payment_order %s: %s", checkout_session_id, exc)

    await activate_initial_subscription(
        session=session,
        bot=bot,
        config=config,
        telegram_id=telegram_id,
        subscription_end=subscription_end,
        amount=amount_total,
        provider=PaymentProvider.stripe,
        external_payment_id=stripe_payment_id,
        payment_customer_id=stripe_customer_id,
        stripe_customer_id=stripe_customer_id,
        gspread_client=gspread_client,
    )


def _get_invoice_period_end(invoice: dict) -> Optional[int]:
    lines = (invoice.get("lines") or {}).get("data") or []
    period_ends: List[int] = []
    for line in lines:
        period = line.get("period") or {}
        end_ts = period.get("end")
        if isinstance(end_ts, int):
            period_ends.append(end_ts)

    if period_ends:
        return max(period_ends)

    invoice_period_end = invoice.get("period_end")
    if isinstance(invoice_period_end, int):
        return invoice_period_end

    return None


async def handle_invoice_payment_succeeded(
    event_data: dict,
    session: AsyncSession,
    bot: Bot,
    config: Config,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    """
    Обработка события invoice.payment_succeeded.
    Рекуррентный платёж (продление подписки).
    """
    invoice = event_data
    stripe_customer_id = invoice.get("customer")
    subscription_id = invoice.get("subscription")
    billing_reason = invoice.get("billing_reason")

    if not stripe_customer_id:
        return

    # Находим пользователя по Stripe Customer ID
    user = await get_user_by_stripe_customer_id(session, stripe_customer_id)
    period_end_ts = _get_invoice_period_end(invoice)

    if billing_reason in {"subscription_create", "subscription_update"}:
        if not subscription_id:
            logger.warning(
                "Первичный invoice Stripe без subscription id: customer=%s billing_reason=%s",
                stripe_customer_id,
                billing_reason,
            )
            return

        stripe_client = init_stripe(config)
        subscription = await get_subscription_by_id(stripe_client, subscription_id)
        if not subscription:
            logger.warning(
                f"Не удалось восстановить subscription={subscription_id} для customer={stripe_customer_id}"
            )
            return

        metadata = subscription.get("metadata") or {}
        telegram_id_str = metadata.get("telegram_id")
        if not telegram_id_str:
            logger.warning(
                f"Stripe subscription {subscription_id} не содержит telegram_id metadata"
            )
            return

        try:
            telegram_id = int(telegram_id_str)
        except ValueError:
            logger.warning(
                f"Некорректный telegram_id в metadata subscription={subscription_id}: {telegram_id_str}"
            )
            return

        tariff = metadata.get("tariff", "1month")
        subscription_end = calculate_initial_subscription_end(tariff)

        await activate_initial_subscription(
            session=session,
            bot=bot,
            config=config,
            telegram_id=telegram_id,
            subscription_end=subscription_end,
            amount=invoice.get("amount_paid", 0) / 100,
            provider=PaymentProvider.stripe,
            external_payment_id=subscription_id,
            payment_customer_id=stripe_customer_id,
            stripe_customer_id=stripe_customer_id,
            gspread_client=gspread_client,
        )
        logger.info(
            "Первичная Stripe активация обработана через invoice event: telegram_id=%s, subscription=%s, billing_reason=%s",
            telegram_id,
            subscription_id,
            billing_reason,
        )
        return

    if not user:
        logger.warning(f"Пользователь не найден для customer={stripe_customer_id}")
        return

    # Дата окончания подписки должна быть взята из Stripe (period.end).
    # Это важно для корректной работы тарифов (например, 3 месяца), а также для идемпотентности.
    if period_end_ts is not None:
        new_end = datetime.utcfromtimestamp(period_end_ts)
    else:
        # Крайний фолбэк (на случай нестандартного события): не падаем.
        # Но логируем, чтобы можно было отловить кейс и допилить.
        logger.warning(
            "invoice.payment_succeeded без period.end — продлеваем на 30 дней как fallback"
        )
        current_end = user.subscription_end_date or datetime.utcnow()
        if current_end < datetime.utcnow():
            current_end = datetime.utcnow()
        new_end = current_end + timedelta(days=30)

    await activate_recurring_subscription(
        session=session,
        bot=bot,
        telegram_id=user.telegram_id,
        subscription_end=new_end,
        amount=invoice.get("amount_paid", 0) / 100,
        provider=PaymentProvider.stripe,
        external_payment_id=invoice.get("id"),
        payment_customer_id=stripe_customer_id,
        stripe_customer_id=stripe_customer_id,
        config=config,
        gspread_client=gspread_client,
    )

    logger.info(f"Подписка продлена: telegram_id={user.telegram_id}, new_end={new_end}")


async def handle_invoice_payment_failed(
    event_data: dict,
    session: AsyncSession,
    bot: Bot,
    config: Config,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    """
    Обработка события invoice.payment_failed.
    Не удалось списать деньги — уведомляем пользователя.
    """
    invoice = event_data
    stripe_customer_id = invoice.get("customer")

    if not stripe_customer_id:
        return

    user = await get_user_by_stripe_customer_id(session, stripe_customer_id)
    if not user:
        logger.warning(f"Пользователь не найден для customer={stripe_customer_id}")
        return

    # Уведомляем пользователя
    try:
        await bot.send_message(
            chat_id=user.telegram_id,
            text=INVOICE_PAYMENT_FAILED,
            parse_mode="Markdown",
        )
        logger.info(f"Уведомление о неудачном платеже отправлено: telegram_id={user.telegram_id}")
        profile = await get_user_analytics_profile(session, user.telegram_id)
        await track_event(
            session,
            telegram_id=user.telegram_id,
            journey="payment",
            onboarding_version=profile.onboarding_version if profile and profile.onboarding_version else "core",
            event_name="payment_failed",
            source="stripe:invoice.payment_failed",
            provider=PaymentProvider.stripe,
            metadata={"invoice_id": invoice.get("id")},
            config=config,
            gspread_client=gspread_client,
        )
    except Exception as e:
        logger.warning(f"Не удалось уведомить пользователя {user.telegram_id}: {e}")


async def handle_subscription_deleted(
    event_data: dict,
    session: AsyncSession,
    bot: Bot,
    config: Config,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    """
    Обработка события customer.subscription.deleted.
    Подписка отменена или не оплачена — исключаем из канала.
    """
    subscription = event_data
    stripe_customer_id = subscription.get("customer")

    if not stripe_customer_id:
        return

    user = await get_user_by_stripe_customer_id(session, stripe_customer_id)
    if not user:
        logger.warning(f"Пользователь не найден для customer={stripe_customer_id}")
        return

    await expire_subscription(session, bot, config, user.telegram_id, gspread_client)


def create_stripe_webhook_endpoint(
    session_factory: async_sessionmaker[AsyncSession],
    bot: Bot,
    config: Config,
    gspread_client: Optional[gspread.Client] = None,
) -> APIRouter:
    """
    Создаёт FastAPI роутер с эндпоинтом /webhook/stripe.
    Принимает зависимости: session_factory, bot, config, gspread_client.
    """

    @router.post("/stripe")
    async def stripe_webhook(
        request: Request,
        stripe_signature: str = Header(None, alias="Stripe-Signature"),
    ):
        """
        Эндпоинт для приёма вебхуков от Stripe.
        Проверяет подпись и обрабатывает события.
        """
        # Получаем сырое тело запроса
        payload = await request.body()

        logger.info(
            "Stripe webhook request received: method=%s path=%s host=%s content_type=%s body_len=%s has_signature=%s",
            request.method,
            request.url.path,
            request.headers.get("host", ""),
            request.headers.get("content-type", ""),
            len(payload),
            bool(stripe_signature),
        )

        if not stripe_signature:
            raise HTTPException(status_code=400, detail="Missing Stripe-Signature header")

        # Проверяем подпись
        event = verify_webhook_signature(
            payload=payload,
            sig_header=stripe_signature,
            webhook_secret=config.stripe_webhook_secret,
        )

        if event is None:
            raise HTTPException(status_code=400, detail="Invalid signature")

        event_type = event.type
        event_data = event.data.object

        logger.info(f"Получен Stripe webhook: id={event.id}, type={event_type}")

        # Обрабатываем события в зависимости от типа
        async with session_factory() as session:
            if event_type == "checkout.session.completed":
                await handle_checkout_completed(event_data, session, bot, config, gspread_client)

            elif event_type in {"invoice.payment_succeeded", "invoice.paid"}:
                await handle_invoice_payment_succeeded(event_data, session, bot, config, gspread_client)

            elif event_type == "invoice.payment_failed":
                await handle_invoice_payment_failed(event_data, session, bot, config, gspread_client)

            elif event_type == "customer.subscription.deleted":
                await handle_subscription_deleted(event_data, session, bot, config, gspread_client)

            else:
                logger.debug(f"Необработанное событие: {event_type}")

        return {"status": "ok"}

    return router
