import logging
from datetime import datetime, timedelta
from typing import Optional

import gspread
import httpx
from aiogram import Bot
from dateutil.relativedelta import relativedelta
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.texts import (
    ACTIVE_EVENT_INVITATION,
    ACTIVE_PAYMENT_SUCCESS,
    ACTIVE_PAYMENT_SUCCESS_NO_LINK,
    ACTIVE_RENEWAL_SUCCESS,
    EXPIRED_SUBSCRIPTION_CANCELLED,
    format_text,
)
from database.models import PaymentProvider, UserStatus
from database.requests import (
    add_payment,
    create_pending_invitation,
    get_scheduled_broadcast,
    get_user_analytics_profile,
    get_upcoming_events,
    get_user_rsvp,
    get_user_by_telegram_id,
    remove_unauthorized_member,
    update_user_status,
    update_user_subscription,
)
from services.analytics import track_event
from services.google_sheets import add_buyer_to_sheets
from utils.config import Config

logger = logging.getLogger(__name__)
GREGO_BOT_API_URL = "http://bot.hablacongrego.com"
EARLY_BIRD_DEADLINE = datetime(2026, 3, 4, 23, 0, 0)
EARLY_BIRD_BASE = datetime(2026, 3, 5, 0, 0, 0)
NAVIGATION_PHOTO_ID = "AgACAgIAAxkBAAIDRWl8z6pMIxUzOEpd_0Z_m_eNngXmAAJREWsbN07oSxbwbi8ZfXAQAQADAgADeQADOAQ"


async def _sync_subscription_reporting(
    session: AsyncSession,
    config: Optional[Config],
    gspread_client: Optional[gspread.Client],
    telegram_id: int,
    onboarding_version: Optional[str],
    event_name: str,
    *,
    source: Optional[str] = None,
    provider: Optional[PaymentProvider] = None,
    metadata: Optional[dict] = None,
    once_per_user: bool = False,
) -> None:
    profile = await get_user_analytics_profile(session, telegram_id)
    resolved_version = onboarding_version or (profile.onboarding_version if profile else None) or "core"
    await track_event(
        session,
        telegram_id=telegram_id,
        journey="subscription",
        onboarding_version=resolved_version,
        event_name=event_name,
        source=source,
        provider=provider,
        metadata=metadata,
        once_per_user=once_per_user,
        config=config,
        gspread_client=gspread_client,
    )


async def add_user_to_grego_bot(telegram_id: int) -> bool:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{GREGO_BOT_API_URL}/add_user", params={"telegram_id": telegram_id})
            return response.status_code == 200
    except Exception as e:
        logger.error(f"Не удалось связаться с Grego ботом для добавления {telegram_id}: {e}")
        return False


async def remove_user_from_grego_bot(telegram_id: int) -> bool:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{GREGO_BOT_API_URL}/remove_user", params={"telegram_id": telegram_id})
            return response.status_code == 200
    except Exception as e:
        logger.error(f"Не удалось связаться с Grego ботом для удаления {telegram_id}: {e}")
        return False


async def send_subscription_access_message(
    bot: Bot,
    config: Config,
    telegram_id: int,
    subscription_end: datetime,
) -> None:
    try:
        expire_date = datetime.utcnow() + timedelta(hours=24)
        invite_link = await bot.create_chat_invite_link(
            chat_id=config.channel_id,
            member_limit=1,
            expire_date=expire_date,
            name=f"User {telegram_id}",
        )
        from bot.keyboards import get_after_payment_keyboard

        end_date_str = subscription_end.strftime("%d.%m.%Y")
        await bot.send_photo(
            chat_id=telegram_id,
            photo=NAVIGATION_PHOTO_ID,
            caption=format_text(
                ACTIVE_PAYMENT_SUCCESS,
                end_date=end_date_str,
                invite_link=invite_link.invite_link,
            ),
            reply_markup=get_after_payment_keyboard(),
        )
    except Exception as e:
        logger.error(f"Ошибка при отправке ссылки пользователю {telegram_id}: {e}")
        end_date_str = subscription_end.strftime("%d.%m.%Y")
        await bot.send_message(
            chat_id=telegram_id,
            text=format_text(ACTIVE_PAYMENT_SUCCESS_NO_LINK, end_date=end_date_str),
            parse_mode="Markdown",
        )


async def send_upcoming_event_invitation(
    session: AsyncSession,
    bot: Bot,
    telegram_id: int,
) -> None:
    from bot.keyboards.inline import get_rsvp_buttons_keyboard
    from datetime import timedelta
    import pytz

    events = await get_upcoming_events(session, limit=100)
    if not events:
        return

    madrid_tz = pytz.timezone("Europe/Madrid")
    now = datetime.now(madrid_tz).replace(tzinfo=None)

    async def send_invitation(event) -> bool:
        event_dt = madrid_tz.localize(event.rsvp_event_datetime)
        day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        day_name = day_names[event_dt.weekday()]
        event_date = event_dt.strftime(f"{day_name}, %d.%m.%Y")
        event_time = event_dt.strftime("%H:%M Madrid")
        text = format_text(
            ACTIVE_EVENT_INVITATION,
            event_title=event.rsvp_event_title,
            event_date=event_date,
            event_time=event_time,
        )
        try:
            await bot.send_message(
                chat_id=telegram_id,
                text=text,
                reply_markup=get_rsvp_buttons_keyboard(event.id),
                parse_mode="Markdown",
            )
            return True
        except Exception as e:
            logger.warning(f"Не удалось отправить приглашение на встречу пользователю {telegram_id}: {e}")
            return False

    def calculate_send_time(event_datetime, current_time):
        time_until = event_datetime - current_time
        if time_until < timedelta(hours=3):
            return current_time, "urgent"
        if time_until < timedelta(days=1):
            return event_datetime - timedelta(hours=2), "high"
        if time_until < timedelta(days=3):
            return event_datetime - timedelta(days=1), "medium"
        return event_datetime - timedelta(days=3), "normal"

    event_schedule = []
    for event in events:
        send_at, priority = calculate_send_time(event.rsvp_event_datetime, now)
        if send_at < now:
            send_at = now
        broadcast = await get_scheduled_broadcast(session, event.id)
        if not broadcast:
            continue
        existing_rsvp = await get_user_rsvp(session, telegram_id, event.id)
        if existing_rsvp is not None:
            continue
        event_schedule.append({
            "event": event,
            "broadcast": broadcast,
            "send_at": send_at,
            "priority": priority,
        })

    event_schedule.sort(key=lambda x: x["send_at"])
    min_interval = timedelta(hours=2)
    last_send_time = None

    for item in event_schedule:
        if last_send_time is not None and item["send_at"] - last_send_time < min_interval:
            if item["send_at"] > now:
                new_send_time = last_send_time + min_interval
                event_dt = item["event"].rsvp_event_datetime
                if new_send_time >= event_dt - timedelta(minutes=30):
                    item["send_at"] = now
                else:
                    item["send_at"] = new_send_time
        if item["send_at"] <= now:
            last_send_time = now
        else:
            last_send_time = item["send_at"]

    for item in event_schedule:
        event = item["event"]
        send_at = item["send_at"]
        if send_at <= now + timedelta(minutes=1):
            await send_invitation(event)
        else:
            await create_pending_invitation(
                session=session,
                telegram_id=telegram_id,
                broadcast_id=event.id,
                send_at=send_at,
            )


def calculate_initial_subscription_end(tariff: str) -> datetime:
    base_date = EARLY_BIRD_BASE if datetime.utcnow() < EARLY_BIRD_DEADLINE else datetime.utcnow()
    if tariff == "1month":
        return base_date + relativedelta(months=1)
    if tariff == "3months":
        return base_date + relativedelta(months=3)
    return base_date + relativedelta(months=6)


def calculate_recurring_subscription_end(current_end: Optional[datetime], tariff: str) -> datetime:
    base_date = current_end or datetime.utcnow()
    if base_date < datetime.utcnow():
        base_date = datetime.utcnow()
    if tariff == "1month":
        return base_date + relativedelta(months=1)
    if tariff == "3months":
        return base_date + relativedelta(months=3)
    return base_date + relativedelta(months=6)


async def activate_initial_subscription(
    session: AsyncSession,
    bot: Bot,
    config: Config,
    telegram_id: int,
    subscription_end: datetime,
    amount: float,
    provider: PaymentProvider,
    external_payment_id: str,
    payment_customer_id: Optional[str] = None,
    stripe_customer_id: Optional[str] = None,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    existing_user = await get_user_by_telegram_id(session, telegram_id)
    previous_status = existing_user.status if existing_user else None

    await update_user_subscription(
        session=session,
        telegram_id=telegram_id,
        subscription_end_date=subscription_end,
        stripe_customer_id=stripe_customer_id,
        payment_provider=provider,
        payment_customer_id=payment_customer_id,
    )
    await remove_unauthorized_member(session, telegram_id)

    user = await get_user_by_telegram_id(session, telegram_id)
    payment_recorded = False
    if user:
        try:
            await add_payment(
                session=session,
                user_id=user.id,
                amount=amount,
                stripe_payment_id=external_payment_id,
                status="success",
                provider=provider,
                external_payment_id=external_payment_id,
            )
            payment_recorded = True
        except IntegrityError:
            await session.rollback()
            logger.info(f"Дубликат платежа ({external_payment_id}) — пропускаем запись")

        if gspread_client and payment_recorded:
            await add_buyer_to_sheets(
                client=gspread_client,
                config=config,
                user=user,
                amount=amount,
            )

    await add_user_to_grego_bot(telegram_id)

    if previous_status == UserStatus.active and not payment_recorded:
        logger.info(f"Повторная initial activation без нового платежа для {telegram_id} — уведомления не отправляем")
        return

    await _sync_subscription_reporting(
        session=session,
        config=config,
        gspread_client=gspread_client,
        telegram_id=telegram_id,
        onboarding_version=None,
        event_name="payment_succeeded",
        source="payment_activation:initial",
        provider=provider,
        metadata={
            "activation_type": "initial",
            "recurring": False,
            "amount": amount,
        },
    )
    logger.info(
        "user_stage_changed user=%s stage=active source=subscription provider=%s recurring=false previous_status=%s",
        telegram_id,
        provider.value,
        previous_status.value if previous_status else None,
    )

    await send_subscription_access_message(bot, config, telegram_id, subscription_end)
    await send_upcoming_event_invitation(session, bot, telegram_id)


async def grant_manual_subscription(
    session: AsyncSession,
    bot: Bot,
    config: Config,
    telegram_id: int,
    subscription_end: datetime,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    await update_user_subscription(
        session=session,
        telegram_id=telegram_id,
        subscription_end_date=subscription_end,
    )
    await remove_unauthorized_member(session, telegram_id)
    await add_user_to_grego_bot(telegram_id)
    await _sync_subscription_reporting(
        session=session,
        config=config,
        gspread_client=gspread_client,
        telegram_id=telegram_id,
        onboarding_version=None,
        event_name="subscription_activated",
        source="payment_activation:manual",
        provider=None,
        metadata={
            "activation_type": "manual",
        },
    )
    logger.info("user_stage_changed user=%s stage=active source=manual_grant", telegram_id)
    await send_subscription_access_message(bot, config, telegram_id, subscription_end)
    await send_upcoming_event_invitation(session, bot, telegram_id)


async def activate_recurring_subscription(
    session: AsyncSession,
    bot: Bot,
    telegram_id: int,
    subscription_end: datetime,
    amount: float,
    provider: PaymentProvider,
    external_payment_id: str,
    payment_customer_id: Optional[str] = None,
    stripe_customer_id: Optional[str] = None,
    config: Optional[Config] = None,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    existing_user = await get_user_by_telegram_id(session, telegram_id)
    previous_status = existing_user.status if existing_user else None

    await update_user_subscription(
        session=session,
        telegram_id=telegram_id,
        subscription_end_date=subscription_end,
        stripe_customer_id=stripe_customer_id,
        payment_provider=provider,
        payment_customer_id=payment_customer_id,
    )

    user = await get_user_by_telegram_id(session, telegram_id)
    if not user:
        return

    try:
        await add_payment(
            session=session,
            user_id=user.id,
            amount=amount,
            stripe_payment_id=external_payment_id,
            status="success",
            provider=provider,
            external_payment_id=external_payment_id,
        )
    except IntegrityError:
        await session.rollback()
        logger.info(f"Дубликат платежа ({external_payment_id}) — пропускаем запись")
        return

    await add_user_to_grego_bot(telegram_id)
    await _sync_subscription_reporting(
        session=session,
        config=config,
        gspread_client=gspread_client,
        telegram_id=telegram_id,
        onboarding_version=None,
        event_name="payment_succeeded",
        source="payment_activation:recurring" if previous_status == UserStatus.active else "payment_activation:recovered",
        provider=provider,
        metadata={
            "activation_type": "recurring" if previous_status == UserStatus.active else "recovered",
            "recurring": True,
            "amount": amount,
        },
    )
    logger.info(
        "user_stage_changed user=%s stage=active source=subscription provider=%s recurring=true previous_status=%s",
        telegram_id,
        provider.value,
        previous_status.value if previous_status else None,
    )

    if previous_status != UserStatus.active and config is not None:
        await remove_unauthorized_member(session, telegram_id)
        await send_subscription_access_message(bot, config, telegram_id, subscription_end)
        await send_upcoming_event_invitation(session, bot, telegram_id)
        return

    try:
        end_date_str = subscription_end.strftime("%d.%m.%Y")
        await bot.send_message(
            chat_id=telegram_id,
            text=format_text(ACTIVE_RENEWAL_SUCCESS, end_date=end_date_str),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.warning(f"Не удалось уведомить пользователя {telegram_id}: {e}")


async def expire_subscription(
    session: AsyncSession,
    bot: Bot,
    config: Config,
    telegram_id: int,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    await update_user_status(session, telegram_id, UserStatus.expired)
    await remove_user_from_grego_bot(telegram_id)
    await _sync_subscription_reporting(
        session=session,
        config=config,
        gspread_client=gspread_client,
        telegram_id=telegram_id,
        onboarding_version=None,
        event_name="subscription_expired",
        source="payment_activation:expire",
    )
    logger.info("user_stage_changed user=%s stage=expired source=subscription_end", telegram_id)

    try:
        await bot.ban_chat_member(chat_id=config.channel_id, user_id=telegram_id)
        await bot.unban_chat_member(chat_id=config.channel_id, user_id=telegram_id)
    except Exception as e:
        logger.warning(f"Не удалось исключить пользователя {telegram_id}: {e}")

    try:
        await bot.send_message(
            chat_id=telegram_id,
            text=EXPIRED_SUBSCRIPTION_CANCELLED,
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.warning(f"Не удалось уведомить пользователя {telegram_id}: {e}")
