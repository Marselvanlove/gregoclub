# Тестовые команды для разработки и отладки
import logging
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline import get_feedback_start_keyboard
from bot.texts import FEEDBACK_INTRO
from database.models import BroadcastStatus, ScheduledBroadcast, UserStatus
from database.requests import (
    get_user_by_telegram_id,
    update_user_subscription,
    update_user_status,
)
from utils.config import Config

router = Router(name="test_commands")
logger = logging.getLogger(__name__)


@router.message(Command("test_sh"))
async def cmd_test_subscription_handler(
    message: Message,
    session: AsyncSession,
    config: Config,
) -> None:
    """
    Тестовая команда для имитации успешной оплаты подписки.
    Активирует подписку и вызывает функцию отправки приглашения на встречу.
    
    Использование: /test_sh
    """
    if message.from_user.id not in config.admin_ids:
        await message.answer("⛔ Доступ запрещён")
        return
    
    telegram_id = message.from_user.id
    
    # Проверяем, существует ли пользователь
    user = await get_user_by_telegram_id(session, telegram_id)
    if not user:
        await message.answer("❌ Пользователь не найден в базе. Сначала выполните /start")
        return
    
    # Имитируем успешную оплату на 1 месяц
    subscription_end = datetime.utcnow() + relativedelta(months=1)
    
    # Обновляем подписку
    await update_user_subscription(
        session=session,
        telegram_id=telegram_id,
        subscription_end_date=subscription_end,
        stripe_customer_id=f"test_customer_{telegram_id}",
    )
    
    await message.answer(
        "✅ **Тест: имитация оплаты**\n\n"
        f"Подписка активирована до: {subscription_end.strftime('%d.%m.%Y')}\n"
        "Статус: ACTIVE\n\n"
        "Сейчас будет отправлено приглашение на ближайшую встречу...",
        parse_mode="Markdown",
    )
    
    # Вызываем функцию отправки приглашения на встречу
    from services.payment_activation import send_upcoming_event_invitation
    
    try:
        await send_upcoming_event_invitation(
            session=session,
            bot=message.bot,
            telegram_id=telegram_id,
        )
        await message.answer(
            "✅ Функция `send_upcoming_event_invitation` выполнена.\n\n"
            "Проверьте, получили ли вы приглашение на встречу с RSVP-кнопками.",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Ошибка при тестировании приглашения: {e}")
        await message.answer(
            f"❌ Ошибка при отправке приглашения:\n\n"
            f"<code>{str(e)}</code>",
            parse_mode="HTML",
        )


@router.message(Command("test_posle"))
async def cmd_test_post_event_feedback(
    message: Message,
    session: AsyncSession,
    config: Config,
) -> None:
    if message.from_user.id not in config.admin_ids:
        await message.answer("⛔ Доступ запрещён")
        return

    user = await get_user_by_telegram_id(session, message.from_user.id)
    if not user:
        await message.answer("❌ Пользователь не найден в базе. Сначала выполните /start")
        return

    parts = (message.text or "").split(maxsplit=1)
    level_arg = parts[1].strip().upper() if len(parts) > 1 else "B"

    if level_arg not in {"A", "B"}:
        await message.answer(
            "❌ Использование: `/test_posle` или `/test_posle A` / `/test_posle B`",
            parse_mode="Markdown",
        )
        return

    level_segment = "level:B1-B2" if level_arg == "B" else "level:A1-A2"
    level_label = "B1-B2" if level_arg == "B" else "A1-A2"
    now = datetime.utcnow()

    broadcast = ScheduledBroadcast(
        segment=level_segment,
        content_type="text",
        content_text=f"TEST post-event feedback ({level_label})",
        scheduled_at=now,
        status=BroadcastStatus.sent,
        has_rsvp=True,
        rsvp_event_title=f"TEST: feedback after meeting ({level_label})",
        rsvp_event_datetime=now,
        reminder_15min_sent=True,
        reminder_5min_sent=True,
        feedback_sent=True,
        sent_count=1,
    )
    session.add(broadcast)
    await session.commit()
    await session.refresh(broadcast)

    await message.answer(
        "✅ **Тест post-meeting feedback**\n\n"
        f"Создан тестовый сценарий для уровня: **{level_label}**\n"
        f"Broadcast ID: `{broadcast.id}`\n\n"
        "Сейчас ниже придёт то самое сообщение после созвона.",
        parse_mode="Markdown",
    )

    await message.answer(
        FEEDBACK_INTRO,
        reply_markup=get_feedback_start_keyboard(broadcast.id),
    )
