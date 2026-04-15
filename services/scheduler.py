import logging
from datetime import datetime, timedelta
from typing import Optional

import gspread
import pytz
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from database.models import BroadcastStatus, PaymentOrderStatus, PaymentProvider, UserStatus, RSVPResponse, LevelComfort
from database.requests import (
    get_all_user_analytics_profiles,
    get_all_users,
    get_active_users_expiring_soon,
    get_broadcasts_needing_feedback,
    get_broadcasts_needing_24h_reminder,
    get_expired_users,
    get_expired_users_for_winback,
    get_feedback_with_details,
    get_feedbacks_for_followup,
    get_feedbacks_not_coming_for_followup,
    get_feedbacks_not_synced,
    get_new_users_for_reminder,
    get_pending_users_for_reminder,
    get_recent_pending_lavatop_orders,
    get_pending_broadcasts,
    get_rsvp_attending_users,
    get_scheduled_broadcast,
    get_user_rsvp,
    get_user_by_telegram_id,
    get_user_ltv,
    get_user_analytics_profile,
    get_users_for_broadcast_segment,
    get_users_for_group_join_check,
    get_users_inactive_for_days,
    has_recent_rsvp,
    increment_new_reminder_step,
    increment_pending_reminder_step,
    increment_winback_step,
    mark_broadcast_sent,
    mark_expiry_warning_sent,
    mark_feedback_sent,
    mark_feedback_synced,
    mark_followup_sent,
    mark_group_join_check_sent,
    mark_reminder_24h_sent,
    mark_user_expired,
    replace_broadcast_delivery_logs,
    update_payment_order_status,
)
from services.analytics import track_event
from bot.texts import (
    ACTIVE_GROUP_JOIN_CHECK,
    EXPIRED_SUBSCRIPTION_ENDED,
    EXPIRED_WINBACK_1,
    EXPIRED_WINBACK_2,
    FEEDBACK_FOLLOWUP_HARD_LEVEL,
    FEEDBACK_FOLLOWUP_HIGH_RATING,
    FEEDBACK_FOLLOWUP_INACTIVE,
    FEEDBACK_FOLLOWUP_NOT_COMING,
    FEEDBACK_INTRO,
    NEW_REMINDER_1,
    NEW_REMINDER_2,
    NEW_REMINDER_3,
    PENDING_REMINDER_1,
    PENDING_REMINDER_2,
    PENDING_REMINDER_3,
    ACTIVE_EXPIRY_WARNING_7D,
    ACTIVE_EVENT_REGISTRATION_24H,
    format_text,
)
from bot.keyboards.inline import (
    get_feedback_start_keyboard,
    get_followup_schedule_keyboard,
    get_group_join_check_keyboard,
    get_rsvp_buttons_keyboard,
    get_rsvp_only_decline_keyboard,
)
from services.google_sheets import sync_users_to_sheets, add_feedback_to_sheets
from services.lavatop_api import init_lavatop
from services.payment_activation import activate_initial_subscription, calculate_initial_subscription_end
from utils.config import Config

logger = logging.getLogger(__name__)
LAVATOP_PENDING_STATUSES = {"", "NEW", "CREATED", "PENDING", "IN_PROGRESS"}
LAVATOP_PAID_STATUSES = {"PAID", "SUCCESS", "COMPLETED"}
LAVATOP_FAILED_STATUSES = {"FAILED", "CANCELLED", "EXPIRED"}
LAVATOP_PENDING_TIMEOUT_MINUTES = 5

# Таймзона Мадрида (по ТЗ)
MADRID_TZ = pytz.timezone("Europe/Madrid")


def _is_b_level_broadcast(segment: Optional[str]) -> bool:
    return bool(segment and segment.startswith("level:B"))


def _compact_broadcast_value(value: Optional[str]) -> str:
    if not value:
        return "—"
    return " ".join(value.split())


def _format_broadcast_target(telegram_id: int, username: Optional[str], full_name: Optional[str]) -> str:
    username_part = f"@{username}" if username else "@—"
    full_name_part = _compact_broadcast_value(full_name)
    return f"id={telegram_id} | {username_part} | {full_name_part}"


def _format_broadcast_error(error: Exception) -> str:
    error_text = " ".join(str(error).split())
    if not error_text:
        error_text = error.__class__.__name__
    return error_text[:500]


async def _get_users_for_segment(session: AsyncSession, segment: str) -> list:
    return list(await get_users_for_broadcast_segment(session, segment))


async def _track_scheduler_event(
    session: AsyncSession,
    config: Config,
    gspread_client: Optional[gspread.Client],
    *,
    telegram_id: int,
    event_name: str,
    journey: str,
    step_key: Optional[str] = None,
    metadata: Optional[dict] = None,
    once_per_user: bool = False,
) -> None:
    profile = await get_user_analytics_profile(session, telegram_id)
    onboarding_version = profile.onboarding_version if profile and profile.onboarding_version else "core"
    await track_event(
        session,
        telegram_id=telegram_id,
        journey=journey,
        onboarding_version=onboarding_version,
        event_name=event_name,
        step_key=step_key,
        source="scheduler",
        metadata=metadata,
        once_per_user=once_per_user,
        config=config,
        gspread_client=gspread_client,
    )


def _format_event_datetime_parts(event_datetime: datetime) -> tuple[str, str]:
    event_dt = MADRID_TZ.localize(event_datetime)
    day_name = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][event_dt.weekday()]
    return event_dt.strftime(f"{day_name}, %d.%m.%Y"), event_dt.strftime("%H:%M Madrid")


def _is_tomorrow_in_madrid(event_datetime: datetime, now: datetime) -> bool:
    event_dt = MADRID_TZ.localize(event_datetime)
    now_dt = MADRID_TZ.localize(now)
    return event_dt.date() == (now_dt + timedelta(days=1)).date()


def _chunk_broadcast_lines(title: str, lines: list[str], limit: int = 3500) -> list[str]:
    if not lines:
        return []

    messages: list[str] = []
    current_message = title
    for line in lines:
        candidate = f"{current_message}\n{line}"
        if len(candidate) > limit and current_message != title:
            messages.append(current_message)
            current_message = f"{title}\n{line}"
            continue
        current_message = candidate

    messages.append(current_message)
    return messages


async def _send_broadcast_admin_messages(bot: Bot, admin_ids: list[int], messages: list[str]) -> None:
    if not admin_ids or not messages:
        return

    for admin_id in admin_ids:
        for message in messages:
            try:
                await bot.send_message(chat_id=admin_id, text=message)
            except Exception as e:
                logger.warning(f"Не удалось отправить админ-уведомление {admin_id}: {e}")
                break


async def _notify_broadcast_started(bot: Bot, config: Config, broadcast, recipient_count: int) -> None:
    preview = _compact_broadcast_value(broadcast.content_text)[:200]
    messages = [
        "📣 Старт запланированной рассылки\n"
        f"broadcast_id={broadcast.id}\n"
        f"segment={broadcast.segment}\n"
        f"recipients={recipient_count}\n"
        f"content_type={broadcast.content_type}\n"
        f"has_rsvp={broadcast.has_rsvp}\n"
        f"preview={preview}"
    ]
    await _send_broadcast_admin_messages(bot, config.admin_ids, messages)


async def _notify_broadcast_completed(
    bot: Bot,
    config: Config,
    broadcast,
    recipient_count: int,
    success_count: int,
    fail_count: int,
    success_details: list[str],
    fail_details: list[str],
) -> None:
    summary = (
        "📬 Итог запланированной рассылки\n"
        f"broadcast_id={broadcast.id}\n"
        f"segment={broadcast.segment}\n"
        f"recipients={recipient_count}\n"
        f"success={success_count}\n"
        f"failed={fail_count}"
    )

    messages = [summary]
    messages.extend(_chunk_broadcast_lines("✅ Доставлено:", success_details))
    messages.extend(_chunk_broadcast_lines("❌ Не доставлено:", fail_details))
    await _send_broadcast_admin_messages(bot, config.admin_ids, messages)


async def check_expired_subscriptions(
    session_factory: async_sessionmaker[AsyncSession],
    bot: Bot,
    config: Config,
) -> None:
    """
    Ежедневная проверка истёкших подписок (09:00 Madrid Time).
    
    Логика:
    1. Находим пользователей с subscription_end_date < today и статусом active
    2. Меняем статус на expired
    3. Исключаем из канала (kick + unban)
    4. Отправляем уведомление
    """
    logger.info("Запуск ежедневной проверки подписок...")
    
    async with session_factory() as session:
        expired_users = await get_expired_users(session)
        
        if not expired_users:
            logger.info("Нет истёкших подписок")
            return
        
        logger.info(f"Найдено {len(expired_users)} истёкших подписок")
        
        for user in expired_users:
            try:
                # Меняем статус на expired и сохраняем дату для winback
                await mark_user_expired(session, user.telegram_id)
                
                # Исключаем из канала
                try:
                    await bot.ban_chat_member(
                        chat_id=config.channel_id,
                        user_id=user.telegram_id,
                    )
                    # Сразу разбаниваем, чтобы мог вернуться
                    await bot.unban_chat_member(
                        chat_id=config.channel_id,
                        user_id=user.telegram_id,
                    )
                    logger.info(f"Пользователь {user.telegram_id} исключён из канала")
                except Exception as e:
                    logger.warning(f"Не удалось исключить {user.telegram_id}: {e}")
                
                # Отправляем уведомление
                try:
                    await bot.send_message(
                        chat_id=user.telegram_id,
                        text=EXPIRED_SUBSCRIPTION_ENDED,
                        parse_mode="Markdown",
                    )
                except Exception as e:
                    logger.warning(f"Не удалось уведомить {user.telegram_id}: {e}")
                    
            except Exception as e:
                logger.error(f"Ошибка при обработке пользователя {user.telegram_id}: {e}")
    
    logger.info("Проверка подписок завершена")


async def kick_unauthorized_members(
    session_factory: async_sessionmaker[AsyncSession],
    bot: Bot,
    config: Config,
) -> None:
    """
    Проверка и кик неавторизованных пользователей.
    Запускается каждые 5 минут.
    
    Логика:
    1. Находим пользователей в unauthorized_members, которые присоединились >15 минут назад
    2. Еще раз проверяем БД (может пользователь оплатил за это время)
    3. Если все еще нет в БД — кикаем и отправляем уведомление
    """
    from database.requests import (
        get_unauthorized_members_to_kick,
        get_user_by_telegram_id,
        remove_unauthorized_member,
    )
    from bot.texts import UNAUTHORIZED_MEMBER_KICKED
    
    async with session_factory() as session:
        # Получаем пользователей для кика (>15 минут в unauthorized)
        unauthorized = await get_unauthorized_members_to_kick(session, minutes=15)
        
        if not unauthorized:
            return
        
        logger.info(f"Найдено {len(unauthorized)} неавторизованных пользователей для проверки")
        
        for member in unauthorized:
            try:
                # Еще раз проверяем БД (может пользователь оплатил)
                db_user = await get_user_by_telegram_id(session, member.telegram_id)
                
                if db_user is not None:
                    # Пользователь оплатил — удаляем из неавторизованных
                    await remove_unauthorized_member(session, member.telegram_id)
                    logger.info(
                        f"Пользователь {member.telegram_id} оплатил подписку, убираем из списка на кик"
                    )
                    continue
                
                # Пользователя все еще нет в БД — кикаем
                try:
                    await bot.ban_chat_member(
                        chat_id=config.channel_id,
                        user_id=member.telegram_id,
                    )
                    # Разбаниваем, чтобы мог вернуться после оплаты
                    await bot.unban_chat_member(
                        chat_id=config.channel_id,
                        user_id=member.telegram_id,
                    )
                    logger.info(
                        f"Неавторизованный пользователь {member.telegram_id} (@{member.username}) исключён из канала"
                    )
                except Exception as e:
                    logger.warning(f"Не удалось исключить {member.telegram_id}: {e}")
                
                # Отправляем уведомление
                try:
                    await bot.send_message(
                        chat_id=member.telegram_id,
                        text=UNAUTHORIZED_MEMBER_KICKED,
                        parse_mode="Markdown",
                    )
                except Exception as e:
                    logger.warning(f"Не удалось уведомить {member.telegram_id}: {e}")
                
                # Удаляем из таблицы unauthorized_members
                await remove_unauthorized_member(session, member.telegram_id)
                    
            except Exception as e:
                logger.error(f"Ошибка при обработке неавторизованного {member.telegram_id}: {e}")


async def sync_google_sheets(
    session_factory: async_sessionmaker[AsyncSession],
    gspread_client: gspread.Client,
    config: Config,
) -> None:
    """
    Синхронизация с Google Sheets (раз в 1 час).
    Выгружает всех пользователей с их LTV.
    """
    logger.info("Запуск синхронизации с Google Sheets...")
    
    async with session_factory() as session:
        # Получаем всех пользователей
        users = await get_all_users(session)
        
        # Собираем LTV для каждого пользователя
        ltv_map: Dict[int, float] = {}
        for user in users:
            ltv = await get_user_ltv(session, user.id)
            if ltv > 0:
                ltv_map[user.id] = ltv
        analytics_profiles = await get_all_user_analytics_profiles(session)
        analytics_profile_map = {
            profile.telegram_id: profile
            for profile in analytics_profiles
        }
        
        # Синхронизируем
        try:
            count = await sync_users_to_sheets(
                client=gspread_client,
                config=config,
                users=users,
                ltv_map=ltv_map,
                analytics_profile_map=analytics_profile_map,
            )
            logger.info(f"Синхронизация завершена: {count} записей")
        except Exception as e:
            logger.error(f"Ошибка синхронизации с Google Sheets: {e}")


async def send_pending_reminders(
    session_factory: async_sessionmaker[AsyncSession],
    bot: Bot,
    config: Config,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    """
    Отправляет напоминания пользователям в статусе pending (выбрали тариф, но не оплатили).
    Тексты из texts.py: PENDING_REMINDER_1, PENDING_REMINDER_2, PENDING_REMINDER_3
    """
    # Соответствие step -> шаблон
    reminder_templates = {
        1: PENDING_REMINDER_1,
        2: PENDING_REMINDER_2,
        3: PENDING_REMINDER_3,
    }
    
    async with session_factory() as session:
        for step in (1, 2, 3):
            users = await get_pending_users_for_reminder(session, step=step)
            if not users:
                continue

            template = reminder_templates.get(step, PENDING_REMINDER_1)

            for user in users:
                try:
                    first_name = user.full_name.split()[0] if user.full_name else "Друг"
                    text = format_text(template, first_name=first_name)
                    await bot.send_message(chat_id=user.telegram_id, text=text)
                    await increment_pending_reminder_step(session, user.telegram_id)
                    await _track_scheduler_event(
                        session,
                        config,
                        gspread_client,
                        telegram_id=user.telegram_id,
                        event_name="pending_reminder_sent",
                        journey="lifecycle",
                        step_key=f"pending_reminder:{step}",
                        metadata={"step": step},
                    )
                    logger.info(f"PENDING напоминание #{step} отправлено: {user.telegram_id}")
                except Exception as e:
                    logger.warning(f"Не удалось отправить pending-напоминание пользователю {user.telegram_id}: {e}")


async def send_expiry_warnings(
    session_factory: async_sessionmaker[AsyncSession],
    bot: Bot,
) -> None:
    """
    Отправляет предупреждения пользователям, у которых подписка заканчивается скоро.
    Текст из texts.py: ACTIVE_EXPIRY_WARNING_7D
    """
    async with session_factory() as session:
        users = await get_active_users_expiring_soon(session, days=3)
        if not users:
            return

        for user in users:
            try:
                first_name = user.full_name.split()[0] if user.full_name else "Друг"
                end_date = user.subscription_end_date.strftime("%d.%m.%Y") if user.subscription_end_date else ""
                text = format_text(ACTIVE_EXPIRY_WARNING_7D, first_name=first_name, end_date=end_date)
                await bot.send_message(chat_id=user.telegram_id, text=text, parse_mode="Markdown")
                await mark_expiry_warning_sent(session, user.telegram_id)
            except Exception as e:
                logger.warning(f"Не удалось отправить предупреждение об окончании пользователю {user.telegram_id}: {e}")


async def send_new_reminders(
    session_factory: async_sessionmaker[AsyncSession],
    bot: Bot,
    config: Config,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    """
    Отправляет напоминания NEW пользователям (не выбрали тариф).
    step=1: через 1 час после /start
    step=2: через 3 часа после /start (GregoChat подарок)
    step=3: через 24 часа после /start
    """
    reminder_templates = {
        1: NEW_REMINDER_1,
        2: NEW_REMINDER_2,
        3: NEW_REMINDER_3,
    }

    async with session_factory() as session:
        for step in (1, 2, 3):
            users = await get_new_users_for_reminder(session, step=step)
            logger.info(f"NEW reminder step {step}: найдено {len(users)} пользователей")
            if not users:
                continue

            template = reminder_templates.get(step, NEW_REMINDER_1)

            for user in users:
                try:
                    first_name = user.full_name.split()[0] if user.full_name else "Друг"
                    text = format_text(template, first_name=first_name)
                    await bot.send_message(chat_id=user.telegram_id, text=text)
                    await increment_new_reminder_step(session, user.telegram_id)
                    await _track_scheduler_event(
                        session,
                        config,
                        gspread_client,
                        telegram_id=user.telegram_id,
                        event_name="new_reminder_sent",
                        journey="lifecycle",
                        step_key=f"new_reminder:{step}",
                        metadata={"step": step},
                    )
                    logger.info(f"NEW напоминание #{step} отправлено: {user.telegram_id}")
                except Exception as e:
                    logger.warning(f"Не удалось отправить NEW напоминание пользователю {user.telegram_id}: {e}")


async def send_winback_reminders(
    session_factory: async_sessionmaker[AsyncSession],
    bot: Bot,
    config: Config,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    """
    Отправляет winback-напоминания EXPIRED пользователям.
    step=1: через 3 дня после expired_at
    step=2: через 7 дней после expired_at
    """
    reminder_templates = {
        1: EXPIRED_WINBACK_1,
        2: EXPIRED_WINBACK_2,
    }

    async with session_factory() as session:
        for step in (1, 2):
            users = await get_expired_users_for_winback(session, step=step)
            if not users:
                continue

            template = reminder_templates.get(step, EXPIRED_WINBACK_1)

            for user in users:
                try:
                    first_name = user.full_name.split()[0] if user.full_name else "Друг"
                    text = format_text(template, first_name=first_name)
                    await bot.send_message(chat_id=user.telegram_id, text=text, parse_mode="Markdown")
                    await increment_winback_step(session, user.telegram_id)
                    await _track_scheduler_event(
                        session,
                        config,
                        gspread_client,
                        telegram_id=user.telegram_id,
                        event_name="winback_sent",
                        journey="lifecycle",
                        step_key=f"winback:{step}",
                        metadata={"step": step},
                    )
                    logger.info(f"WINBACK напоминание #{step} отправлено: {user.telegram_id}")
                except Exception as e:
                    logger.warning(f"Не удалось отправить WINBACK напоминание пользователю {user.telegram_id}: {e}")


async def send_scheduled_broadcasts(
    session_factory: async_sessionmaker[AsyncSession],
    bot: Bot,
    config: Config,
) -> None:
    """
    Проверяет и отправляет запланированные рассылки, время которых наступило.
    Вызывается каждую минуту из APScheduler.
    
    Для событий (has_rsvp=True):
    - Пользователям с RSVP=attending: напоминание "Вы записаны"
    - Остальным: приглашение с кнопками записи
    """
    from bot.texts import ACTIVE_EVENT_REMINDER
    
    async with session_factory() as session:
        broadcasts = await get_pending_broadcasts(session)

        if not broadcasts:
            return

        for broadcast in broadcasts:
            logger.info(f"Отправка запланированной рассылки #{broadcast.id}...")

            # Получаем пользователей по сегменту
            users = await _get_users_for_segment(session, broadcast.segment)

            recipient_count = len(users)
            success_count = 0
            fail_count = 0
            success_details: list[str] = []
            fail_details: list[str] = []
            delivery_logs: list[dict[str, object]] = []

            await _notify_broadcast_started(bot, config, broadcast, recipient_count)

            for user in users:
                target = _format_broadcast_target(user.telegram_id, user.username, user.full_name)
                logger.info(f"Рассылка #{broadcast.id}: попытка отправки {target}")
                try:
                    # Проверяем, записался ли пользователь на событие заранее
                    user_is_registered = False
                    if broadcast.has_rsvp:
                        rsvp = await get_user_rsvp(session, user.telegram_id, broadcast.id)
                        user_is_registered = rsvp and rsvp.response == RSVPResponse.attending
                    
                    # Определяем текст и клавиатуру
                    if user_is_registered:
                        # Напоминание для уже записавшихся
                        event_date, event_time = _format_event_datetime_parts(broadcast.rsvp_event_datetime)
                        reminder_text = ACTIVE_EVENT_REMINDER.format(
                            event_title=broadcast.rsvp_event_title or "Встреча",
                            event_date=event_date,
                            event_time=event_time,
                        )
                        reply_markup = get_rsvp_only_decline_keyboard(broadcast.id)
                        
                        if broadcast.content_type == "photo" and broadcast.content_file_id:
                            await bot.send_photo(
                                chat_id=user.telegram_id,
                                photo=broadcast.content_file_id,
                                caption=reminder_text,
                                reply_markup=reply_markup,
                            )
                        else:
                            await bot.send_message(
                                chat_id=user.telegram_id,
                                text=reminder_text,
                                reply_markup=reply_markup,
                            )
                    else:
                        # Стандартное приглашение
                        reply_markup = None
                        if broadcast.has_rsvp:
                            reply_markup = get_rsvp_buttons_keyboard(broadcast.id)
                        
                        if broadcast.content_type == "photo" and broadcast.content_file_id:
                            await bot.send_photo(
                                chat_id=user.telegram_id,
                                photo=broadcast.content_file_id,
                                caption=broadcast.content_text or "",
                                reply_markup=reply_markup,
                            )
                        else:
                            await bot.send_message(
                                chat_id=user.telegram_id,
                                text=broadcast.content_text or "",
                                reply_markup=reply_markup,
                            )
                    
                    success_count += 1
                    success_details.append(target)
                    delivery_logs.append(
                        {
                            "telegram_id": user.telegram_id,
                            "username": user.username,
                            "full_name": user.full_name,
                            "delivery_status": "success",
                            "error_message": None,
                        }
                    )
                    logger.info(f"Рассылка #{broadcast.id}: успешно отправлено {target}")
                except Exception as e:
                    error_message = _format_broadcast_error(e)
                    logger.warning(
                        f"Не удалось отправить рассылку #{broadcast.id} пользователю {target}: {error_message}"
                    )
                    fail_count += 1
                    fail_details.append(f"{target} | reason={error_message}")
                    delivery_logs.append(
                        {
                            "telegram_id": user.telegram_id,
                            "username": user.username,
                            "full_name": user.full_name,
                            "delivery_status": "failed",
                            "error_message": error_message,
                        }
                    )
  
            try:
                await replace_broadcast_delivery_logs(session, broadcast.id, delivery_logs)
            except Exception as e:
                logger.exception(f"Не удалось сохранить delivery logs для рассылки #{broadcast.id}: {e}")
 
            await mark_broadcast_sent(session, broadcast.id, success_count, fail_count)
            logger.info(
                f"Рассылка #{broadcast.id} завершена: {success_count} успешно, {fail_count} ошибок"
            )
            await _notify_broadcast_completed(
                bot,
                config,
                broadcast,
                recipient_count,
                success_count,
                fail_count,
                success_details,
                fail_details,
            )


async def send_event_24h_registration_reminders(
    session_factory: async_sessionmaker[AsyncSession],
    bot: Bot,
) -> None:
    """
    Отправляет напоминание о записи на завтрашнее событие пользователям без RSVP.
    Работает по тому же паттерну, что и прочие relative-time reminders: БД + sent flag.
    """
    async with session_factory() as session:
        broadcasts = await get_broadcasts_needing_24h_reminder(session)

        if not broadcasts:
            return

        now = datetime.now(MADRID_TZ).replace(tzinfo=None)

        for broadcast in broadcasts:
            if not broadcast.rsvp_event_datetime:
                await mark_reminder_24h_sent(session, broadcast.id)
                continue

            # Защита от ложного текста "завтра", если событие попало в окно некорректно.
            if not _is_tomorrow_in_madrid(broadcast.rsvp_event_datetime, now):
                logger.info(
                    "24h reminder для события #%s пропущен: дата события не попадает на завтра",
                    broadcast.id,
                )
                await mark_reminder_24h_sent(session, broadcast.id)
                continue

            users = await _get_users_for_segment(session, broadcast.segment)
            event_date, event_time = _format_event_datetime_parts(broadcast.rsvp_event_datetime)
            text = format_text(
                ACTIVE_EVENT_REGISTRATION_24H,
                event_title=broadcast.rsvp_event_title or "Встреча",
                event_date=event_date,
                event_time=event_time,
            )

            success_count = 0
            for user in users:
                existing_rsvp = await get_user_rsvp(session, user.telegram_id, broadcast.id)
                if existing_rsvp is not None:
                    continue

                try:
                    await bot.send_message(
                        chat_id=user.telegram_id,
                        text=text,
                        reply_markup=get_rsvp_buttons_keyboard(broadcast.id),
                        parse_mode="Markdown",
                    )
                    success_count += 1
                except Exception as e:
                    logger.warning(
                        "Не удалось отправить 24h reminder пользователю %s для события #%s: %s",
                        user.telegram_id,
                        broadcast.id,
                        e,
                    )

            await mark_reminder_24h_sent(session, broadcast.id)
            logger.info(
                "24h reminder для события #%s отправлен %s пользователям",
                broadcast.id,
                success_count,
            )


async def send_event_reminders(
    session_factory: async_sessionmaker[AsyncSession],
    bot: Bot,
) -> None:
    """
    Отправляет напоминания о событиях участникам RSVP.
    - За 15 минут: "Через 15 минут созвон: {тема}"
    - За 5 минут: ссылка на Zoom или сообщение о группе
    """
    from database.requests import (
        get_broadcasts_needing_15min_reminder,
        get_broadcasts_needing_5min_reminder,
        get_rsvp_attending_users,
        mark_reminder_15min_sent,
        mark_reminder_5min_sent,
    )

    async with session_factory() as session:
        # Напоминания за 15 минут
        broadcasts_15 = await get_broadcasts_needing_15min_reminder(session)
        for broadcast in broadcasts_15:
            logger.info(f"Отправка напоминания за 15 минут для рассылки #{broadcast.id}...")
            attending_users = await get_rsvp_attending_users(session, broadcast.id)

            if not attending_users:
                logger.info(f"Нет участников для напоминания 15мин рассылки #{broadcast.id}")
                await mark_reminder_15min_sent(session, broadcast.id)
                continue

            for telegram_id in attending_users:
                try:
                    await bot.send_message(
                        chat_id=telegram_id,
                        text=f"Через 15 минут созвон: {broadcast.rsvp_event_title}",
                    )
                except Exception as e:
                    logger.warning(f"Не удалось отправить напоминание 15мин пользователю {telegram_id}: {e}")

            await mark_reminder_15min_sent(session, broadcast.id)
            logger.info(f"Напоминание 15мин для #{broadcast.id} отправлено {len(attending_users)} пользователям")

        # Напоминания за 5 минут
        broadcasts_5 = await get_broadcasts_needing_5min_reminder(session)
        for broadcast in broadcasts_5:
            logger.info(f"Отправка напоминания за 5 минут для рассылки #{broadcast.id}...")
            attending_users = await get_rsvp_attending_users(session, broadcast.id)

            if not attending_users:
                logger.info(f"Нет участников для напоминания 5мин рассылки #{broadcast.id}")
                await mark_reminder_5min_sent(session, broadcast.id)
                continue

            if broadcast.zoom_link:
                text = f"Созвон начинается через 5 минут!\nСсылка: {broadcast.zoom_link}"
            else:
                text = "Созвон начинается! Заходите в группу, в течение 5 минут отправим ссылку."

            for telegram_id in attending_users:
                try:
                    await bot.send_message(
                        chat_id=telegram_id,
                        text=text,
                    )
                except Exception as e:
                    logger.warning(f"Не удалось отправить напоминание 5мин пользователю {telegram_id}: {e}")

            await mark_reminder_5min_sent(session, broadcast.id)
            logger.info(f"Напоминание 5мин для #{broadcast.id} отправлено {len(attending_users)} пользователям")


async def send_post_event_feedback(
    session_factory: async_sessionmaker[AsyncSession],
    bot: Bot,
    config: Config,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    """
    Отправляет опрос участникам через 20 минут после окончания встречи.
    Время отправки = rsvp_event_datetime + 110 минут (90 мин встреча + 20 мин задержка)
    """
    async with session_factory() as session:
        broadcasts = await get_broadcasts_needing_feedback(session)

        if not broadcasts:
            return

        for broadcast in broadcasts:
            logger.info(f"Отправка опроса после встречи #{broadcast.id} ({broadcast.rsvp_event_title})...")
            attending_users = await get_rsvp_attending_users(session, broadcast.id)

            if not attending_users:
                logger.info(f"Нет участников для опроса рассылки #{broadcast.id}")
                await mark_feedback_sent(session, broadcast.id)
                continue

            success_count = 0
            for telegram_id in attending_users:
                try:
                    await bot.send_message(
                        chat_id=telegram_id,
                        text=FEEDBACK_INTRO,
                        reply_markup=get_feedback_start_keyboard(broadcast.id),
                    )
                    await _track_scheduler_event(
                        session,
                        config,
                        gspread_client,
                        telegram_id=telegram_id,
                        event_name="feedback_prompt_sent",
                        journey="engagement",
                        step_key="feedback_prompt",
                        metadata={
                            "broadcast_id": broadcast.id,
                            "event_title": broadcast.rsvp_event_title,
                        },
                    )
                    success_count += 1
                except Exception as e:
                    logger.warning(f"Не удалось отправить опрос пользователю {telegram_id}: {e}")

            await mark_feedback_sent(session, broadcast.id)
            logger.info(f"Опрос для #{broadcast.id} отправлен {success_count} пользователям")


async def send_feedback_followups(
    session_factory: async_sessionmaker[AsyncSession],
    bot: Bot,
) -> None:
    """
    Отправляет follow-up сообщения на основе ответов опроса:
    - 4-5 звёзд + не записался → через 1-2 дня
    - "было сложно" для B1-C → предложить A1-A2
    - "не приду" → через неделю напоминание
    """
    from database.models import LevelComfort

    async with session_factory() as session:
        processed_feedback_ids: set[int] = set()

        # 1. Follow-up для высоких оценок (4-5 звёзд) + НЕ ЗАПИСАЛСЯ через 1-2 дня
        feedbacks_high = await get_feedbacks_for_followup(session, days_since_feedback=1)
        for feedback in feedbacks_high:
            if feedback.rating and feedback.rating >= 4:
                # Проверяем, записался ли пользователь на встречу за последние 2 дня
                has_rsvp = await has_recent_rsvp(session, feedback.telegram_id, days=2)
                if has_rsvp:
                    # Уже записался — не отправляем follow-up, но помечаем как обработанный
                    await mark_followup_sent(session, feedback.id)
                    processed_feedback_ids.add(feedback.id)
                    logger.info(f"Follow-up (high rating) пропущен — пользователь {feedback.telegram_id} уже записался")
                    continue
                
                try:
                    await bot.send_message(
                        chat_id=feedback.telegram_id,
                        text=FEEDBACK_FOLLOWUP_HIGH_RATING,
                        reply_markup=get_followup_schedule_keyboard(),
                    )
                    await mark_followup_sent(session, feedback.id)
                    processed_feedback_ids.add(feedback.id)
                    logger.info(f"Follow-up (high rating) отправлен пользователю {feedback.telegram_id}")
                except Exception as e:
                    logger.warning(f"Не удалось отправить follow-up пользователю {feedback.telegram_id}: {e}")

        # 2. Follow-up для "было сложно" — предложить уровень ниже (для B-встреч)
        for feedback in feedbacks_high:
            if feedback.id in processed_feedback_ids:
                continue

            if feedback.level_comfort == LevelComfort.hard:
                broadcast = await get_scheduled_broadcast(session, feedback.broadcast_id)
                if not broadcast or not _is_b_level_broadcast(broadcast.segment):
                    continue

                try:
                    await bot.send_message(
                        chat_id=feedback.telegram_id,
                        text=FEEDBACK_FOLLOWUP_HARD_LEVEL,
                        reply_markup=get_followup_schedule_keyboard(),
                    )
                    await mark_followup_sent(session, feedback.id)
                    logger.info(f"Follow-up (hard level) отправлен пользователю {feedback.telegram_id}")
                except Exception as e:
                    logger.warning(f"Не удалось отправить follow-up пользователю {feedback.telegram_id}: {e}")

        # 3. Follow-up для "не приду" через неделю
        feedbacks_not_coming = await get_feedbacks_not_coming_for_followup(session, days_since_feedback=7)
        for feedback in feedbacks_not_coming:
            try:
                await bot.send_message(
                    chat_id=feedback.telegram_id,
                    text=FEEDBACK_FOLLOWUP_NOT_COMING,
                    reply_markup=get_followup_schedule_keyboard(),
                )
                await mark_followup_sent(session, feedback.id)
                logger.info(f"Follow-up (not coming) отправлен пользователю {feedback.telegram_id}")
            except Exception as e:
                logger.warning(f"Не удалось отправить follow-up пользователю {feedback.telegram_id}: {e}")


async def send_group_join_check(
    session_factory: async_sessionmaker[AsyncSession],
    bot: Bot,
    config: Config,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    """
    Отправляет проверку входа в группу через 5 минут после покупки.
    Спрашивает пользователя: "Вы зашли в группу?"
    """
    async with session_factory() as session:
        users = await get_users_for_group_join_check(session)
        
        if not users:
            return
        
        for user in users:
            try:
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=ACTIVE_GROUP_JOIN_CHECK,
                    reply_markup=get_group_join_check_keyboard(),
                )
                await mark_group_join_check_sent(session, user.telegram_id)
                await _track_scheduler_event(
                    session,
                    config,
                    gspread_client,
                    telegram_id=user.telegram_id,
                    event_name="group_join_check_sent",
                    journey="activation",
                    step_key="group_join_check",
                )
                logger.info(f"Проверка входа в группу отправлена пользователю {user.telegram_id}")
            except Exception as e:
                logger.warning(f"Не удалось отправить проверку входа пользователю {user.telegram_id}: {e}")


async def send_inactive_user_reminders(
    session_factory: async_sessionmaker[AsyncSession],
    bot: Bot,
) -> None:
    """
    Отправляет напоминание пользователям, которые не записывались на встречи больше недели.
    """
    async with session_factory() as session:
        inactive_users = await get_users_inactive_for_days(session, days=7)

        for user in inactive_users:
            try:
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=FEEDBACK_FOLLOWUP_INACTIVE,
                    reply_markup=get_followup_schedule_keyboard(),
                )
                logger.info(f"Напоминание неактивному пользователю {user.telegram_id}")
            except Exception as e:
                logger.warning(f"Не удалось отправить напоминание пользователю {user.telegram_id}: {e}")


async def sync_feedbacks_to_sheets(
    session_factory: async_sessionmaker[AsyncSession],
    gspread_client: gspread.Client,
    config: Config,
) -> None:
    """
    Синхронизирует завершённые отзывы в Google Sheets (лист "Отзывы").
    """
    async with session_factory() as session:
        feedbacks = await get_feedbacks_not_synced(session)
        
        if not feedbacks:
            return
        
        for feedback in feedbacks:
            fb, user, broadcast = await get_feedback_with_details(session, feedback.id)
            if not fb:
                continue
            
            try:
                await add_feedback_to_sheets(
                    client=gspread_client,
                    config=config,
                    telegram_id=fb.telegram_id,
                    user_name=user.full_name if user else "Неизвестно",
                    meeting_title=broadcast.rsvp_event_title if broadcast else "Встреча",
                    rating=fb.rating or 0,
                    level_comfort=fb.level_comfort.value if fb.level_comfort else "",
                    will_attend=fb.will_attend_next.value if fb.will_attend_next else "",
                    improvement_comment=fb.improvement_comment or "",
                )
                await mark_feedback_synced(session, fb.id)
            except Exception as e:
                logger.warning(f"Ошибка синхронизации отзыва {fb.id}: {e}")


async def send_pending_invitations(
    session_factory: async_sessionmaker[AsyncSession],
    bot: Bot,
) -> None:
    """
    Отправляет отложенные персональные приглашения на события.
    Вызывается каждый час из APScheduler.
    
    Логика:
    1. Получить записи где send_at <= now AND sent = False
    2. Для каждой записи проверить:
       - Пользователь ещё не ответил на RSVP
       - Событие ещё не прошло
    3. Отправить приглашение и отметить как отправленное
    """
    from database.requests import (
        get_pending_invitations_to_send,
        get_scheduled_broadcast,
        get_user_rsvp,
        mark_invitation_sent,
    )
    from bot.keyboards.inline import get_rsvp_buttons_keyboard
    from bot.texts import ACTIVE_EVENT_INVITATION, format_text
    import pytz
    
    async with session_factory() as session:
        invitations = await get_pending_invitations_to_send(session)
        
        if not invitations:
            return
        
        madrid_tz = pytz.timezone("Europe/Madrid")
        now = datetime.now(madrid_tz).replace(tzinfo=None)
        
        logger.info(f"Обработка {len(invitations)} отложенных приглашений...")
        
        for invitation in invitations:
            telegram_id = invitation.telegram_id
            broadcast_id = invitation.broadcast_id
            
            # Проверка 1: Пользователь уже ответил на RSVP?
            existing_rsvp = await get_user_rsvp(session, telegram_id, broadcast_id)
            if existing_rsvp:
                logger.info(f"Пользователь {telegram_id} уже ответил на RSVP для события #{broadcast_id}, пропускаем")
                await mark_invitation_sent(session, invitation.id)
                continue
            
            # Проверка 2: Событие ещё актуально?
            broadcast = await get_scheduled_broadcast(session, broadcast_id)
            if not broadcast or not broadcast.rsvp_event_datetime:
                logger.warning(f"Событие #{broadcast_id} не найдено или нет даты, пропускаем")
                await mark_invitation_sent(session, invitation.id)
                continue

            if broadcast.status == BroadcastStatus.cancelled:
                logger.info(f"Событие #{broadcast_id} отменено, пропускаем отправку пользователю {telegram_id}")
                await mark_invitation_sent(session, invitation.id)
                continue
            
            if broadcast.rsvp_event_datetime < now:
                logger.info(f"Событие #{broadcast_id} уже прошло, пропускаем отправку пользователю {telegram_id}")
                await mark_invitation_sent(session, invitation.id)
                continue
            
            # Отправляем приглашение
            try:
                event_dt = madrid_tz.localize(broadcast.rsvp_event_datetime)
                
                # Форматируем дату и время
                day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
                day_name = day_names[event_dt.weekday()]
                event_date = event_dt.strftime(f"{day_name}, %d.%m.%Y")
                event_time = event_dt.strftime("%H:%M Madrid")
                
                text = format_text(
                    ACTIVE_EVENT_INVITATION,
                    event_title=broadcast.rsvp_event_title,
                    event_date=event_date,
                    event_time=event_time,
                )
                
                await bot.send_message(
                    chat_id=telegram_id,
                    text=text,
                    reply_markup=get_rsvp_buttons_keyboard(broadcast_id),
                    parse_mode="Markdown",
                )
                
                logger.info(f"Отложенное приглашение на событие #{broadcast_id} отправлено пользователю {telegram_id}")
                await mark_invitation_sent(session, invitation.id)
                
            except Exception as e:
                logger.warning(f"Не удалось отправить отложенное приглашение пользователю {telegram_id}: {e}")


async def cleanup_old_pending_invitations(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """
    Удаляет старые отправленные отложенные приглашения (>7 дней).
    Вызывается раз в сутки из APScheduler.
    """
    from database.requests import cleanup_old_pending_invitations as cleanup_func
    
    async with session_factory() as session:
        deleted_count = await cleanup_func(session, days=7)
        if deleted_count > 0:
            logger.info(f"Очистка: удалено {deleted_count} старых отложенных приглашений")


async def sync_lavatop_pending_orders(
    session_factory: async_sessionmaker[AsyncSession],
    bot: Bot,
    config: Config,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    lavatop_client = init_lavatop(config)
    if lavatop_client is None:
        return

    async with session_factory() as session:
        orders = await get_recent_pending_lavatop_orders(session)
        if not orders:
            return

        logger.info(f"LavaTop polling: найдено {len(orders)} pending заказов для проверки")

        for order in orders:
            try:
                invoice = await lavatop_client.get_invoice(order.external_invoice_id)
            except Exception as e:
                logger.warning(f"LavaTop polling: не удалось получить invoice {order.external_invoice_id}: {e}")
                continue

            remote_status = (invoice.status or "").upper()
            logger.info(
                "LavaTop polling: order_id=%s telegram_id=%s invoice=%s remote_status=%s invoice_type=%s parent_invoice_id=%s",
                order.id,
                order.telegram_id,
                order.external_invoice_id,
                remote_status,
                invoice.invoice_type,
                invoice.parent_invoice_id,
            )

            if remote_status in LAVATOP_PENDING_STATUSES:
                stale_cutoff = datetime.utcnow() - timedelta(minutes=LAVATOP_PENDING_TIMEOUT_MINUTES)
                if order.created_at is not None and order.created_at < stale_cutoff:
                    await update_payment_order_status(
                        session=session,
                        external_invoice_id=order.external_invoice_id,
                        status=PaymentOrderStatus.failed,
                        external_parent_invoice_id=invoice.parent_invoice_id,
                        external_customer_id=invoice.parent_invoice_id or order.external_customer_id or order.external_invoice_id,
                    )
                    logger.warning(
                        "LavaTop polling: stale pending order marked failed order_id=%s telegram_id=%s invoice=%s age_limit_minutes=%s remote_status=%s",
                        order.id,
                        order.telegram_id,
                        order.external_invoice_id,
                        LAVATOP_PENDING_TIMEOUT_MINUTES,
                        remote_status,
                    )
                continue

            if remote_status in LAVATOP_FAILED_STATUSES:
                await update_payment_order_status(
                    session=session,
                    external_invoice_id=order.external_invoice_id,
                    status=PaymentOrderStatus.failed,
                    external_parent_invoice_id=invoice.parent_invoice_id,
                    external_customer_id=invoice.parent_invoice_id or order.external_customer_id,
                )
                logger.info(
                    "LavaTop polling: order %s переведён в failed по API status=%s",
                    order.external_invoice_id,
                    remote_status,
                )
                continue

            if remote_status not in LAVATOP_PAID_STATUSES:
                logger.warning(
                    "LavaTop polling: неизвестный статус invoice=%s status=%s",
                    order.external_invoice_id,
                    remote_status,
                )
                continue

            await update_payment_order_status(
                session=session,
                external_invoice_id=order.external_invoice_id,
                status=PaymentOrderStatus.paid,
                external_parent_invoice_id=invoice.parent_invoice_id,
                external_customer_id=invoice.parent_invoice_id or order.external_customer_id or order.external_invoice_id,
            )

            await activate_initial_subscription(
                session=session,
                bot=bot,
                config=config,
                telegram_id=order.telegram_id,
                subscription_end=calculate_initial_subscription_end(order.tariff),
                amount=invoice.amount or float(order.amount or 0),
                provider=PaymentProvider.lavatop,
                external_payment_id=order.external_invoice_id,
                payment_customer_id=invoice.parent_invoice_id or order.external_customer_id or order.external_invoice_id,
                gspread_client=gspread_client,
            )

            logger.info(
                "LavaTop polling: initial payment activated for telegram_id=%s invoice=%s",
                order.telegram_id,
                order.external_invoice_id,
            )


def create_scheduler(
    session_factory: async_sessionmaker[AsyncSession],
    bot: Bot,
    config: Config,
    gspread_client: Optional[gspread.Client] = None,
) -> AsyncIOScheduler:
    """
    Создаёт и настраивает планировщик задач.
    
    Задачи:
    1. Ежедневная проверка подписок в 09:00 по Мадриду
    2. Синхронизация с Google Sheets каждый час (если есть gspread_client)
    """
    scheduler = AsyncIOScheduler(timezone=MADRID_TZ)
    
    # Задача 1: Ежедневная проверка подписок в 09:00 Madrid Time
    scheduler.add_job(
        check_expired_subscriptions,
        trigger=CronTrigger(hour=9, minute=0, timezone=MADRID_TZ),
        args=[session_factory, bot, config],
        id="check_expired_subscriptions",
        name="Ежедневная проверка истёкших подписок",
        replace_existing=True,
    )
    logger.info("Задача 'check_expired_subscriptions' добавлена (09:00 Madrid)")
    
    # Задача 2: Синхронизация с Google Sheets каждый час
    if gspread_client is not None:
        scheduler.add_job(
            sync_google_sheets,
            trigger=IntervalTrigger(hours=1),
            args=[session_factory, gspread_client, config],
            id="sync_google_sheets",
            name="Синхронизация с Google Sheets",
            replace_existing=True,
        )
        logger.info("Задача 'sync_google_sheets' добавлена (каждый час)")
        
        # Задача: Синхронизация отзывов в Google Sheets каждые 5 минут
        scheduler.add_job(
            sync_feedbacks_to_sheets,
            trigger=IntervalTrigger(minutes=5),
            args=[session_factory, gspread_client, config],
            id="sync_feedbacks_to_sheets",
            name="Синхронизация отзывов в Sheets",
            replace_existing=True,
        )
        logger.info("Задача 'sync_feedbacks_to_sheets' добавлена (каждые 5 минут)")

    scheduler.add_job(
        send_pending_reminders,
        trigger=IntervalTrigger(minutes=10),
        args=[session_factory, bot, config, gspread_client],
        id="send_pending_reminders",
        name="Напоминания для pending",
        replace_existing=True,
    )
    logger.info("Задача 'send_pending_reminders' добавлена (каждые 10 минут)")

    # Задача: Кик неавторизованных пользователей (каждые 5 минут)
    scheduler.add_job(
        kick_unauthorized_members,
        trigger=IntervalTrigger(minutes=5),
        args=[session_factory, bot, config],
        id="kick_unauthorized_members",
        name="Кик неавторизованных пользователей",
        replace_existing=True,
    )
    logger.info("Задача 'kick_unauthorized_members' добавлена (каждые 5 минут)")

    scheduler.add_job(
        send_expiry_warnings,
        trigger=IntervalTrigger(hours=6),
        args=[session_factory, bot],
        id="send_expiry_warnings",
        name="Предупреждения об окончании",
        replace_existing=True,
    )

    # Задача: Напоминания для NEW пользователей (каждые 30 минут)
    scheduler.add_job(
        send_new_reminders,
        trigger=IntervalTrigger(minutes=30),
        args=[session_factory, bot, config, gspread_client],
        id="send_new_reminders",
        name="Напоминания для NEW",
        replace_existing=True,
    )
    logger.info("Задача 'send_new_reminders' добавлена (каждые 30 минут)")

    # Задача: Winback напоминания для EXPIRED (каждые 6 часов)
    scheduler.add_job(
        send_winback_reminders,
        trigger=IntervalTrigger(hours=6),
        args=[session_factory, bot, config, gspread_client],
        id="send_winback_reminders",
        name="Winback для EXPIRED",
        replace_existing=True,
    )
    logger.info("Задача 'send_winback_reminders' добавлена (каждые 6 часов)")

    # Задача: Проверка и отправка запланированных рассылок (каждую минуту)
    scheduler.add_job(
        send_scheduled_broadcasts,
        trigger=IntervalTrigger(minutes=1),
        args=[session_factory, bot, config],
        id="send_scheduled_broadcasts",
        name="Запланированные рассылки",
        replace_existing=True,
    )
    logger.info("Задача 'send_scheduled_broadcasts' добавлена (каждую минуту)")

    # Задача: Напоминания о событиях RSVP (каждую минуту)
    scheduler.add_job(
        send_event_24h_registration_reminders,
        trigger=IntervalTrigger(minutes=1),
        args=[session_factory, bot],
        id="send_event_24h_registration_reminders",
        name="Напоминания за 24 часа до события",
        replace_existing=True,
    )
    logger.info("Задача 'send_event_24h_registration_reminders' добавлена (каждую минуту)")

    # Задача: Напоминания о событиях RSVP (каждую минуту)
    scheduler.add_job(
        send_event_reminders,
        trigger=IntervalTrigger(minutes=1),
        args=[session_factory, bot],
        id="send_event_reminders",
        name="Напоминания о событиях",
        replace_existing=True,
    )
    logger.info("Задача 'send_event_reminders' добавлена (каждую минуту)")

    # Задача: Опрос после встречи (каждую минуту)
    scheduler.add_job(
        send_post_event_feedback,
        trigger=IntervalTrigger(minutes=1),
        args=[session_factory, bot, config, gspread_client],
        id="send_post_event_feedback",
        name="Опрос после встречи",
        replace_existing=True,
    )
    logger.info("Задача 'send_post_event_feedback' добавлена (каждую минуту)")

    # Задача: Follow-up сообщения на основе ответов (каждые 6 часов)
    scheduler.add_job(
        send_feedback_followups,
        trigger=IntervalTrigger(hours=6),
        args=[session_factory, bot],
        id="send_feedback_followups",
        name="Follow-up после опроса",
        replace_existing=True,
    )
    logger.info("Задача 'send_feedback_followups' добавлена (каждые 6 часов)")

    # Задача: Напоминания неактивным пользователям (раз в день в 12:00)
    scheduler.add_job(
        send_inactive_user_reminders,
        trigger=CronTrigger(hour=12, minute=0, timezone=MADRID_TZ),
        args=[session_factory, bot],
        id="send_inactive_user_reminders",
        name="Напоминания неактивным",
        replace_existing=True,
    )
    logger.info("Задача 'send_inactive_user_reminders' добавлена (12:00 Madrid)")
    
    # Задача: Проверка входа в группу после покупки (каждую минуту)
    scheduler.add_job(
        send_group_join_check,
        trigger=IntervalTrigger(minutes=1),
        args=[session_factory, bot, config, gspread_client],
        id="send_group_join_check",
        name="Проверка входа в группу",
        replace_existing=True,
    )
    logger.info("Задача 'send_group_join_check' добавлена (каждую минуту)")

    scheduler.add_job(
        sync_lavatop_pending_orders,
        trigger=IntervalTrigger(minutes=1),
        args=[session_factory, bot, config, gspread_client],
        id="sync_lavatop_pending_orders",
        name="Синхронизация pending LavaTop оплат",
        replace_existing=True,
    )
    logger.info("Задача 'sync_lavatop_pending_orders' добавлена (каждую минуту)")

    # Задача: Отправка отложенных персональных приглашений на события (каждый час)
    scheduler.add_job(
        send_pending_invitations,
        trigger=IntervalTrigger(minutes=1),
        args=[session_factory, bot],
        id="send_pending_invitations",
        name="Отложенные приглашения на события",
        replace_existing=True,
    )
    logger.info("Задача 'send_pending_invitations' добавлена (каждую минуту)")
    
    # Задача: Очистка старых отложенных приглашений (раз в сутки в 03:00)
    scheduler.add_job(
        cleanup_old_pending_invitations,
        trigger=CronTrigger(hour=3, minute=0, timezone=MADRID_TZ),
        args=[session_factory],
        id="cleanup_old_pending_invitations",
        name="Очистка старых отложенных приглашений",
        replace_existing=True,
    )
    logger.info("Задача 'cleanup_old_pending_invitations' добавлена (03:00 Madrid)")
    
    return scheduler


async def run_sync_now(
    session_factory: async_sessionmaker[AsyncSession],
    gspread_client: gspread.Client,
    config: Config,
) -> int:
    """
    Запускает синхронизацию с Google Sheets немедленно.
    Используется из админ-панели (кнопка "Sync CRM").
    
    Возвращает количество синхронизированных записей.
    """
    async with session_factory() as session:
        users = await get_all_users(session)
        analytics_profiles = await get_all_user_analytics_profiles(session)
        
        ltv_map: Dict[int, float] = {}
        for user in users:
            ltv = await get_user_ltv(session, user.id)
            if ltv > 0:
                ltv_map[user.id] = ltv
        analytics_profile_map = {
            profile.telegram_id: profile
            for profile in analytics_profiles
        }
        
        count = await sync_users_to_sheets(
            client=gspread_client,
            config=config,
            users=users,
            ltv_map=ltv_map,
            analytics_profile_map=analytics_profile_map,
        )
        return count
