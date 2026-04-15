# Обработчики команд для админа: /admin (статистика, рассылка, sync CRM)
import logging
import math
from html import escape
from typing import Any, Dict, Optional

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import (
    get_admin_panel_keyboard,
    get_add_user_duration_keyboard,
    get_stats_detail_keyboard,
    get_broadcast_segment_keyboard,
    get_broadcast_confirm_keyboard,
    get_broadcast_menu_keyboard,
    get_scheduled_segment_keyboard,
    get_rsvp_choice_keyboard,
    get_scheduled_confirm_keyboard,
    get_zoom_link_keyboard,
    get_broadcast_history_back_keyboard,
    get_inactive_participants_keyboard,
)
from bot.states import BroadcastStates, ScheduleStates, ScheduledBroadcastStates, AdminStates
import gspread

from database.models import UserStatus
from database.requests import (
    build_inactive_custom_segment,
    count_users_by_status,
    get_all_users,
    get_inactive_participants_page,
    parse_inactive_custom_segment,
    get_users_by_status,
    get_users_for_broadcast_segment,
)
from services.scheduler import run_sync_now
from utils.config import Config

router = Router(name="admin")
logger = logging.getLogger(__name__)

INACTIVE_PARTICIPANTS_SEGMENT = "inactive_last5_active"
INACTIVE_LT5_SEGMENT = "inactive_lt5_active"
INACTIVE_PARTICIPANTS_PAGE_SIZE = 10
DEFAULT_INACTIVE_MISSED_EVENTS = 5


def _get_default_inactive_custom_segment() -> str:
    return build_inactive_custom_segment(0, DEFAULT_INACTIVE_MISSED_EVENTS)


def _get_inactive_filter_values(segment: str) -> tuple[int, int]:
    custom_segment_filters = parse_inactive_custom_segment(segment)
    if custom_segment_filters is not None:
        return custom_segment_filters
    if segment == INACTIVE_PARTICIPANTS_SEGMENT:
        return 0, 5
    return 0, 0


def _parse_inactive_segment_page(callback_data: str) -> tuple[str, int]:
    parts = callback_data.split(":")
    if len(parts) == 4:
        return parts[2], int(parts[3])
    if len(parts) < 5:
        raise ValueError(f"Unexpected inactive callback payload: {callback_data}")
    segment = ":".join(parts[2:-1])
    page = int(parts[-1])
    return segment, page


def _parse_inactive_set_callback(callback_data: str) -> tuple[str, int]:
    parts = callback_data.split(":")
    if len(parts) != 5:
        raise ValueError(f"Unexpected inactive set payload: {callback_data}")
    _, _, days_str, missed_str, page_str = parts
    segment = build_inactive_custom_segment(int(days_str), int(missed_str))
    return segment, int(page_str)


def _get_segment_display(segment: str, level: Optional[str] = None) -> str:
    if segment == "level" and level:
        return f"Уровень {level}"
    if segment.startswith("level:"):
        return f"Уровень {segment.split(':', 1)[1]}"
    custom_segment_filters = parse_inactive_custom_segment(segment)
    if custom_segment_filters is not None:
        inactivity_days, missed_events = custom_segment_filters
        parts = []
        if inactivity_days > 0:
            parts.append(f"{inactivity_days} дн.")
        if missed_events > 0:
            parts.append(f"{missed_events} встреч")
        if parts:
            return f"Неактивные ({', '.join(parts)})"
        return "Неактивные"
    segment_names = {
        "all": "Все пользователи",
        "new": "Новые (New)",
        "pending": "Думающие (Pending)",
        "thinking": "Пока думаю",
        "active": "Активные",
        "expired": "Истёкшие",
        INACTIVE_PARTICIPANTS_SEGMENT: "Неактивные (пропустили 5 последних встреч)",
        INACTIVE_LT5_SEGMENT: "Неактивные (меньше 5 записей за всё время)",
    }
    return segment_names.get(segment, segment)


def _get_inactive_filter_description(segment: str) -> str:
    custom_segment_filters = parse_inactive_custom_segment(segment)
    if custom_segment_filters is not None:
        inactivity_days, missed_events = custom_segment_filters
        conditions = []
        if inactivity_days > 0:
            conditions.append(f"не нажимали «Я буду» минимум {inactivity_days} дн.")
        if missed_events > 0:
            conditions.append(f"пропустили последние {missed_events} RSVP-встреч")
        if conditions:
            return "Активные пользователи, для которых одновременно выполняются условия: " + " и ".join(conditions) + "."
        return "Меняй порог по дням и по встречам кнопками ниже."
    if segment == INACTIVE_LT5_SEGMENT:
        return "Активные пользователи, у которых меньше 5 нажатий «Я буду» за всё время."
    return "Активные пользователи, которые не нажимали «Я буду» на последних 5 прошедших встречах."


def _format_inactive_datetime(value: Any) -> str:
    if value is None:
        return "никогда"
    if hasattr(value, "strftime"):
        return value.strftime("%d.%m.%Y %H:%M")
    return str(value)


def _format_inactive_participants_text(
    items: list[dict],
    total_count: int,
    recent_events: list,
    page: int,
    total_pages: int,
    segment: str,
) -> str:
    inactivity_days, missed_events = _get_inactive_filter_values(segment)
    event_lines = []
    for event in recent_events:
        title = escape((event.rsvp_event_title or event.content_text or "Без названия")[:70])
        if len((event.rsvp_event_title or event.content_text or "")) > 70:
            title += "..."
        event_dt = event.rsvp_event_datetime.strftime("%d.%m %H:%M") if event.rsvp_event_datetime else "—"
        event_lines.append(f"- <b>{event_dt}</b> — {title}")

    lines = [
        "💤 <b>Неактивные участники</b>",
        "",
        escape(_get_inactive_filter_description(segment)),
        "",
        f"Дней без «Я буду»: <b>{inactivity_days if inactivity_days > 0 else 'не задано'}</b>",
        f"Пропущено последних встреч подряд: <b>{missed_events if missed_events > 0 else 'не задано'}</b>",
        f"Найдено: <b>{total_count}</b>",
        f"Страница: <b>{page}/{total_pages}</b>",
    ]

    if recent_events:
        lines.extend([
            "",
            f"Последние {len(recent_events)} встречи:",
            *event_lines,
        ])

    lines.append("")

    if not items:
        lines.append("Пока никого нет в этом сегменте.")
        return "\n".join(lines)

    lines.append("Список:")
    start_index = (page - 1) * INACTIVE_PARTICIPANTS_PAGE_SIZE
    for index, item in enumerate(items, start=start_index + 1):
        username = f"@{escape(item['username'])}" if item.get("username") else "без username"
        full_name = escape(item.get("full_name") or "Без имени")
        last_attending = escape(_format_inactive_datetime(item.get("last_attending_at")))
        last_attending_title = escape(item.get("last_attending_title") or "—")
        total_attending = item.get("total_attending", 0)
        telegram_id = item.get("telegram_id")
        lines.append(
            f"{index}. <b>{full_name}</b> ({username})\n"
            f"Последняя запись: <b>{last_attending}</b>\n"
            f"На встречу: <b>{last_attending_title}</b>\n"
            f"Всего записей: <b>{total_attending}</b> · <code>{telegram_id}</code>"
        )

    return "\n".join(lines)


async def _show_inactive_participants(
    message: Message,
    session: AsyncSession,
    page: int,
    segment: str,
) -> None:
    items, total_count, recent_events = await get_inactive_participants_page(
        session,
        page=page,
        page_size=INACTIVE_PARTICIPANTS_PAGE_SIZE,
        recent_events_limit=5,
        statuses=[UserStatus.active],
        segment=segment,
    )
    total_pages = max(math.ceil(total_count / INACTIVE_PARTICIPANTS_PAGE_SIZE), 1)
    safe_page = min(max(page, 1), total_pages)
    if safe_page != page:
        items, total_count, recent_events = await get_inactive_participants_page(
            session,
            page=safe_page,
            page_size=INACTIVE_PARTICIPANTS_PAGE_SIZE,
            recent_events_limit=5,
            statuses=[UserStatus.active],
            segment=segment,
        )

    text = _format_inactive_participants_text(
        items,
        total_count,
        list(recent_events),
        safe_page,
        total_pages,
        segment,
    )
    inactivity_days, missed_events = _get_inactive_filter_values(segment)
    await message.edit_text(
        text,
        reply_markup=get_inactive_participants_keyboard(
            page=safe_page,
            total_pages=total_pages,
            has_items=bool(items),
            segment=segment,
            inactivity_days=inactivity_days,
            missed_events=missed_events,
        ),
        parse_mode="HTML",
    )


# =============================================================================
# Фильтр: проверка, что пользователь — админ
# =============================================================================

async def is_admin(message: Message, config: Config) -> bool:
    """Фильтр: пропускает только если user.id в списке ADMIN_IDS."""
    return message.from_user is not None and message.from_user.id in config.admin_ids


# =============================================================================
# /get_id_foto — получение file_id фотографий для воронки
# =============================================================================

@router.message(Command("get_id_foto"), is_admin)
async def cmd_get_id_foto(message: Message, state: FSMContext) -> None:
    """Включает режим получения file_id для фотографий."""
    from bot.states import AdminStates
    await state.set_state(AdminStates.waiting_for_photo)
    await message.answer(
        "📸 **Режим получения file_id**\n\n"
        "Отправьте фото — я верну его file_id.\n\n"
        "Для выхода: /cancel",
        parse_mode="Markdown",
    )


@router.message(Command("cancel"), is_admin)
async def cmd_cancel_photo_mode(message: Message, state: FSMContext) -> None:
    """Отмена режима получения file_id."""
    current_state = await state.get_state()
    if current_state:
        await state.clear()
        await message.answer("❌ Режим отменён.")
    else:
        await message.answer("Нет активного режима для отмены.")


@router.message(AdminStates.waiting_for_photo, F.photo)
async def handle_photo_for_id(message: Message) -> None:
    """Получает file_id отправленного фото."""
    if not message.photo:
        return
    
    # Берём самое большое фото (последнее в списке)
    photo = message.photo[-1]
    file_id = photo.file_id
    
    await message.answer(
        f"✅ file_id получен:\n\n"
        f"<code>{file_id}</code>\n\n"
        "Скопируйте и добавьте в .env\n"
        "Отправьте следующее фото или /cancel для выхода.",
        parse_mode="HTML",
    )


@router.message(AdminStates.waiting_for_photo)
async def handle_non_photo(message: Message) -> None:
    """Обработка не-фото в режиме получения file_id."""
    if message.text and message.text.startswith("/"):
        return  # Пропускаем команды
    await message.answer("❌ Отправьте фото, а не текст.")


# =============================================================================
# /reset_me — сброс статуса для тестирования воронки
# =============================================================================

@router.message(Command("send_invitations"), is_admin)
async def cmd_send_invitations(message: Message, session: AsyncSession) -> None:
    """Отправляет приглашения на события пользователям без приглашений."""
    from database.requests import get_user_by_telegram_id
    from services.payment_activation import send_upcoming_event_invitation
    import asyncio
    
    # Список пользователей без приглашений
    users_without_invitations = [
        191383006, 208095345, 307795119, 359377079, 465668480,
        474148376, 508844314, 962635019, 996882498, 1585092618,
        5259777311, 5344209216, 6065175645, 8413059761, 8696373484
    ]
    
    await message.answer(f"🚀 Начинаю отправку приглашений для {len(users_without_invitations)} пользователей...")
    
    success_count = 0
    error_count = 0
    
    for telegram_id in users_without_invitations:
        try:
            user = await get_user_by_telegram_id(session, telegram_id)
            if not user:
                logger.warning(f"Пользователь {telegram_id} не найден")
                error_count += 1
                continue
            
            if user.status.value != "active":
                logger.warning(f"Пользователь {telegram_id} не активен (статус: {user.status.value})")
                error_count += 1
                continue
            
            logger.info(f"Отправка приглашений пользователю {telegram_id} ({user.full_name})...")
            await send_upcoming_event_invitation(session, message.bot, telegram_id)
            success_count += 1
            
            # Пауза между отправками
            await asyncio.sleep(2)
            
        except Exception as e:
            logger.error(f"Ошибка при отправке приглашений пользователю {telegram_id}: {e}")
            error_count += 1
    
    await message.answer(
        f"✅ Отправка завершена!\n\n"
        f"Успешно: {success_count}\n"
        f"Ошибок: {error_count}"
    )


@router.message(Command("reset_me"), is_admin)
async def cmd_reset_me(message: Message, session: AsyncSession) -> None:
    """Сбрасывает статус админа на NEW для тестирования воронки."""
    from database.requests import update_user_status, get_user_by_telegram_id
    from database.models import User
    from sqlalchemy import update
    from datetime import datetime
    
    # Сбрасываем статус на NEW и обновляем registration_date
    stmt = update(User).where(User.telegram_id == message.from_user.id).values(
        status=UserStatus.new,
        registration_date=datetime.utcnow(),
        new_reminder_step=0,
        pending_reminder_step=0,
        last_pay_click_at=None,
    )
    await session.execute(stmt)
    await session.commit()
    
    await message.answer(
        "✅ Статус сброшен на NEW.\n"
        "Время регистрации обновлено.\n\n"
        "Теперь отправьте /start для теста воронки.",
        parse_mode="Markdown"
    )


# =============================================================================
# /add_user — ручное добавление пользователя (выбор: 1 или 3 месяца)
# =============================================================================

@router.message(Command("add_user"), is_admin)
async def cmd_add_user(message: Message, state: FSMContext) -> None:
    """Начинает процесс ручного добавления пользователя."""
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        await state.update_data(user_id_arg=args[1])
        await state.set_state(AdminStates.waiting_for_user_id)
        message.text = args[1]
        return
    
    await state.set_state(AdminStates.waiting_for_user_id)
    await message.answer(
        "📝 **Добавление пользователя вручную**\n\n"
        "Отправьте Telegram ID пользователя.\n\n"
        "Для отмены: /cancel",
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "admin:add_user")
async def callback_add_user(callback: CallbackQuery, state: FSMContext) -> None:
    """Callback для кнопки добавления пользователя."""
    await callback.answer()
    await state.set_state(AdminStates.waiting_for_user_id)
    await callback.message.answer(
        "📝 **Добавление пользователя вручную**\n\n"
        "Отправьте Telegram ID пользователя.\n\n"
        "Для отмены: /cancel",
        parse_mode="Markdown"
    )


@router.message(AdminStates.waiting_for_user_id)
async def handle_add_user_id(message: Message, state: FSMContext) -> None:
    """Сохраняет ID пользователя и предлагает выбрать срок подписки."""
    logger.info(f"handle_add_user_id вызван с текстом: {message.text}")
    
    if message.text and message.text.startswith("/"):
        await state.clear()
        return
    
    try:
        user_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Неверный формат. Отправьте числовой ID.")
        return
    
    await state.update_data(add_user_id=user_id)
    await state.set_state(AdminStates.waiting_for_duration)
    await message.answer(
        f"👤 Telegram ID: `{user_id}`\n\n"
        "Выберите срок подписки:",
        reply_markup=get_add_user_duration_keyboard(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data.startswith("admin:duration:"), AdminStates.waiting_for_duration)
async def handle_add_user_duration(
    callback: CallbackQuery, session: AsyncSession, config: Config, state: FSMContext
) -> None:
    """Обрабатывает выбор срока и добавляет подписку."""
    from datetime import datetime, timedelta
    from database.requests import add_user, get_user_by_telegram_id
    from services.payment_activation import grant_manual_subscription

    choice = callback.data.split(":")[2]

    if choice == "cancel":
        await state.clear()
        await callback.answer("Отменено")
        await callback.message.edit_text(
            "❌ Добавление пользователя отменено.",
            parse_mode="Markdown",
        )
        return

    await callback.answer()

    data = await state.get_data()
    user_id = data.get("add_user_id")
    if not user_id:
        await callback.message.edit_text("❌ Ошибка: ID пользователя не найден.")
        await state.clear()
        return

    now = datetime.utcnow()
    if choice == "3months":
        end_date = now + timedelta(days=90)
        duration_label = "3 месяца"
    else:
        end_date = now + timedelta(days=30)
        duration_label = "1 месяц"

    user = await get_user_by_telegram_id(session, user_id)
    if not user:
        await add_user(
            session=session,
            telegram_id=user_id,
            username=None,
            full_name="Manual User",
        )

    try:
        await grant_manual_subscription(
            session=session,
            bot=callback.bot,
            config=config,
            telegram_id=user_id,
            subscription_end=end_date,
        )
    except Exception as e:
        await callback.message.edit_text(
            f"⚠️ Пользователь добавлен в базу, но активация выполнена не полностью.\n"
            f"Ошибка: {e}",
            parse_mode="Markdown"
        )
        await state.clear()
        return

    await callback.message.edit_text(
        f"✅ Пользователь {user_id} добавлен!\n"
        f"Срок: **{duration_label}**\n"
        f"Подписка до: {end_date.strftime('%d.%m.%Y')}\n"
        f"Доступ и приглашения отправлены.",
        parse_mode="Markdown"
    )

    await state.clear()


# =============================================================================
# /admin — главная панель администратора
# =============================================================================

@router.message(Command("admin"), is_admin)
async def cmd_admin(message: Message) -> None:
    """
    Обработчик команды /admin.
    Показывает инлайн-панель с кнопками: Статистика, Рассылка, Sync CRM.
    """
    text = (
        "🔐 **Панель администратора**\n\n"
        "Выбери действие:"
    )
    await message.answer(
        text=text,
        reply_markup=get_admin_panel_keyboard(),
        parse_mode="Markdown",
    )


# =============================================================================
# Статистика
# =============================================================================

@router.callback_query(F.data == "admin:stats")
async def callback_admin_stats(callback: CallbackQuery, session: AsyncSession, config: Config) -> None:
    """
    Обработчик кнопки "Статистика".
    Показывает количество пользователей по статусам.
    """
    # Проверяем, что это админ
    if callback.from_user.id not in config.admin_ids:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    # Получаем статистику из БД
    stats = await count_users_by_status(session)

    total = sum(stats.values())

    text = (
        "📊 **Статистика пользователей**\n\n"
        f"👥 Всего: **{total}**\n\n"
        f"🆕 Новые (new): **{stats.get('new', 0)}**\n"
        f"⏳ Думают (pending): **{stats.get('pending', 0)}**\n"
        f"✅ Активные (active): **{stats.get('active', 0)}**\n"
        f"❌ Истекшие (expired): **{stats.get('expired', 0)}**\n"
    )

    await callback.answer()
    await callback.message.edit_text(
        text=text,
        reply_markup=get_stats_detail_keyboard(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "admin:back")
async def callback_admin_back(callback: CallbackQuery, config: Config) -> None:
    """Возврат в главное меню админ-панели."""
    if callback.from_user.id not in config.admin_ids:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text(
        "🔐 **Панель администратора**\n\n"
        "Выбери действие:",
        reply_markup=get_admin_panel_keyboard(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("stats:"))
async def callback_stats_detail(callback: CallbackQuery, session: AsyncSession, config: Config) -> None:
    """
    Обработчик кнопок "Активные" и "Истекшие".
    Показывает список пользователей с пагинацией (по 40 на сообщение).
    """
    if callback.from_user.id not in config.admin_ids:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    status_key = callback.data.split(":")[1]  # "active" или "expired"
    
    if status_key == "active":
        status = UserStatus.active
        emoji = "✅"
        title = "Активные пользователи"
    else:
        status = UserStatus.expired
        emoji = "❌"
        title = "Истекшие пользователи"

    users = await get_users_by_status(session, status)

    if not users:
        await callback.answer()
        await callback.message.edit_text(
            f"{emoji} **{title}**\n\nСписок пуст.",
            reply_markup=get_stats_detail_keyboard(),
            parse_mode="Markdown",
        )
        return

    # Получаем количество платежей для каждого пользователя (для expired)
    from database.requests import get_user_payments

    # Формируем список строк
    lines = []
    for user in users:
        username = f"@{user.username}" if user.username else f"ID:{user.telegram_id}"
        
        if status == UserStatus.active:
            # Для активных: дата окончания подписки
            end_date = user.subscription_end_date.strftime("%d.%m.%Y") if user.subscription_end_date else "—"
            lines.append(f"• {username} — до {end_date}")
        else:
            # Для истекших: количество платежей
            payments = await get_user_payments(session, user.id)
            payment_count = len([p for p in payments if p.status == "success"])
            reg_date = user.registration_date.strftime("%d.%m.%Y") if user.registration_date else "—"
            lines.append(f"• {username} — рег: {reg_date}, платежей: {payment_count}")

    await callback.answer()

    # Пагинация: по 40 пользователей на сообщение
    CHUNK_SIZE = 40
    chunks = [lines[i:i + CHUNK_SIZE] for i in range(0, len(lines), CHUNK_SIZE)]

    # Первое сообщение — редактируем текущее
    first_chunk = chunks[0]
    header = f"{emoji} <b>{title}</b> ({len(users)} чел.)\n\n"
    await callback.message.edit_text(
        header + "\n".join(first_chunk),
        reply_markup=get_stats_detail_keyboard() if len(chunks) == 1 else None,
        parse_mode="HTML",
    )

    # Остальные — отправляем новыми сообщениями
    for i, chunk in enumerate(chunks[1:], start=2):
        is_last = i == len(chunks)
        await callback.message.answer(
            f"📄 <b>Страница {i}/{len(chunks)}</b>\n\n" + "\n".join(chunk),
            reply_markup=get_stats_detail_keyboard() if is_last else None,
            parse_mode="HTML",
        )


# =============================================================================
# Расписание — редактирование
# =============================================================================

@router.callback_query(F.data == "admin:schedule")
async def callback_admin_schedule(
    callback: CallbackQuery,
    session: AsyncSession,
    config: Config,
    state: FSMContext,
) -> None:
    """
    Обработчик кнопки "Расписание".
    Показывает текущее расписание и предлагает его изменить.
    """
    if callback.from_user.id not in config.admin_ids:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    from database.requests import get_schedule
    current_schedule = await get_schedule(session)

    await callback.answer()
    await state.set_state(ScheduleStates.waiting_for_schedule)
    await callback.message.edit_text(
        f"📅 **Текущее расписание:**\n\n{current_schedule}\n\n"
        "—————————\n"
        "Отправьте новый текст расписания или /cancel для отмены:",
        parse_mode="Markdown",
    )


@router.message(ScheduleStates.waiting_for_schedule, Command("cancel"))
async def cancel_schedule_edit(message: Message, config: Config, state: FSMContext) -> None:
    """Отмена редактирования расписания."""
    if message.from_user.id not in config.admin_ids:
        return
    await state.clear()
    await message.answer(
        "❌ Редактирование расписания отменено.",
        reply_markup=get_admin_panel_keyboard(),
        parse_mode="Markdown",
    )


@router.message(ScheduleStates.waiting_for_schedule)
async def save_schedule(message: Message, session: AsyncSession, config: Config, state: FSMContext) -> None:
    """Сохранение нового расписания."""
    if message.from_user.id not in config.admin_ids:
        return

    if not message.text:
        await message.answer("❌ Отправьте текст расписания.")
        return

    from database.requests import set_schedule
    await set_schedule(session, message.text)
    await state.clear()

    await message.answer(
        "✅ **Расписание обновлено!**\n\n"
        f"{message.text}",
        reply_markup=get_admin_panel_keyboard(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "admin:inactive_participants")
async def callback_inactive_participants(
    callback: CallbackQuery,
    session: AsyncSession,
    config: Config,
) -> None:
    if callback.from_user.id not in config.admin_ids:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    await callback.answer()
    await _show_inactive_participants(callback.message, session, page=1, segment=_get_default_inactive_custom_segment())


@router.callback_query(F.data.startswith("inactive_participants:filter:"))
async def callback_inactive_participants_filter(
    callback: CallbackQuery,
    session: AsyncSession,
    config: Config,
) -> None:
    if callback.from_user.id not in config.admin_ids:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    segment, page = _parse_inactive_segment_page(callback.data)
    await callback.answer()
    await _show_inactive_participants(callback.message, session, page=page, segment=segment)


@router.callback_query(F.data.startswith("inactive_participants:set:"))
async def callback_inactive_participants_set(
    callback: CallbackQuery,
    session: AsyncSession,
    config: Config,
) -> None:
    if callback.from_user.id not in config.admin_ids:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    segment, page = _parse_inactive_set_callback(callback.data)
    await callback.answer()
    await _show_inactive_participants(callback.message, session, page=page, segment=segment)


@router.callback_query(F.data.startswith("inactive_participants:page:"))
async def callback_inactive_participants_page(
    callback: CallbackQuery,
    session: AsyncSession,
    config: Config,
) -> None:
    if callback.from_user.id not in config.admin_ids:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    segment, page = _parse_inactive_segment_page(callback.data)
    await callback.answer()
    await _show_inactive_participants(callback.message, session, page=page, segment=segment)


@router.callback_query(F.data.startswith("inactive_participants:refresh:"))
async def callback_inactive_participants_refresh(
    callback: CallbackQuery,
    session: AsyncSession,
    config: Config,
) -> None:
    if callback.from_user.id not in config.admin_ids:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    segment, page = _parse_inactive_segment_page(callback.data)
    await callback.answer("Обновлено")
    await _show_inactive_participants(callback.message, session, page=page, segment=segment)


@router.callback_query(F.data.startswith("inactive_participants:broadcast:"))
async def callback_inactive_participants_broadcast(
    callback: CallbackQuery,
    config: Config,
    state: FSMContext,
) -> None:
    if callback.from_user.id not in config.admin_ids:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    segment = callback.data.split(":", 2)[2]
    await state.clear()
    await state.update_data(segment=segment)
    await callback.answer()
    await callback.message.edit_text(
        f"📢 Сегмент: **{_get_segment_display(segment)}**\n\n"
        "Теперь отправь текст или фото для рассылки:",
        parse_mode="Markdown",
    )
    await state.set_state(BroadcastStates.waiting_for_content)


# =============================================================================
# Рассылка — выбор сегмента
# =============================================================================

@router.callback_query(F.data == "admin:broadcast")
async def callback_admin_broadcast(callback: CallbackQuery, config: Config, state: FSMContext) -> None:
    """
    Обработчик кнопки "Рассылка".
    Показывает выбор сегмента для рассылки.
    """
    if callback.from_user.id not in config.admin_ids:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    await callback.answer()
    await callback.message.edit_text(
        "📢 **Рассылка**\n\nВыбери сегмент пользователей:",
        reply_markup=get_broadcast_segment_keyboard(),
        parse_mode="Markdown",
    )
    await state.set_state(BroadcastStates.waiting_for_segment)


@router.callback_query(F.data.startswith("broadcast:"), BroadcastStates.waiting_for_segment)
async def callback_broadcast_segment(callback: CallbackQuery, config: Config, state: FSMContext) -> None:
    """
    Обработчик выбора сегмента рассылки.
    """
    if callback.from_user.id not in config.admin_ids:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    parts = callback.data.split(":")
    segment = parts[1]  # all, pending, active, cancel, level
    
    # Проверяем, выбран ли уровень (broadcast:level:A1-A2)
    if segment == "level" and len(parts) > 2:
        level = parts[2]  # A1-A2, B1-B2, C1+
        await state.update_data(segment="level", level=level)
        await callback.answer()
        await callback.message.edit_text(
            f"📢 Сегмент: **Уровень {level}**\n\n"
            "Теперь отправь текст или фото для рассылки:",
            parse_mode="Markdown",
        )
        await state.set_state(BroadcastStates.waiting_for_content)
        return

    if segment == "cancel":
        await state.clear()
        await callback.answer("Рассылка отменена")
        await callback.message.edit_text(
            "🔐 **Панель администратора**\n\nВыбери действие:",
            reply_markup=get_admin_panel_keyboard(),
            parse_mode="Markdown",
        )
        return

    # Сохраняем выбранный сегмент в FSM
    await state.update_data(segment=segment)

    await callback.answer()
    await callback.message.edit_text(
        f"📢 Сегмент: **{_get_segment_display(segment)}**\n\n"
        "Теперь отправь текст или фото для рассылки:",
        parse_mode="Markdown",
    )
    await state.set_state(BroadcastStates.waiting_for_content)


# =============================================================================
# Рассылка — ввод контента
# =============================================================================

@router.message(BroadcastStates.waiting_for_content)
async def message_broadcast_content(message: Message, config: Config, state: FSMContext) -> None:
    """
    Обработчик ввода контента для рассылки (текст или фото).
    """
    if message.from_user.id not in config.admin_ids:
        return

    # Сохраняем контент в FSM
    content_data: Dict[str, Any] = {}

    if message.photo:
        # Фото с подписью
        content_data["type"] = "photo"
        content_data["file_id"] = message.photo[-1].file_id  # Берём самое большое фото
        content_data["caption"] = message.caption or ""
    elif message.text:
        # Просто текст
        content_data["type"] = "text"
        content_data["text"] = message.text
    else:
        await message.answer("❌ Поддерживается только текст или фото. Попробуй ещё раз.")
        return

    await state.update_data(content=content_data)
    data = await state.get_data()

    # Показываем превью и запрашиваем подтверждение
    segment = data.get("segment", "all")
    preview_text = (
        f"📢 **Подтверждение рассылки**\n\n"
        f"Сегмент: **{_get_segment_display(segment, data.get('level'))}**\n"
        f"Тип: **{'Фото' if content_data['type'] == 'photo' else 'Текст'}**\n\n"
        "Отправить?"
    )

    await message.answer(
        text=preview_text,
        reply_markup=get_broadcast_confirm_keyboard(),
        parse_mode="Markdown",
    )
    await state.set_state(BroadcastStates.waiting_for_confirm)


# =============================================================================
# Рассылка — подтверждение и отправка
# =============================================================================

@router.callback_query(F.data == "broadcast:confirm", BroadcastStates.waiting_for_confirm)
async def callback_broadcast_confirm(
    callback: CallbackQuery,
    session: AsyncSession,
    config: Config,
    state: FSMContext,
) -> None:
    """
    Обработчик подтверждения рассылки.
    Отправляет сообщения выбранному сегменту пользователей.
    """
    if callback.from_user.id not in config.admin_ids:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    data = await state.get_data()
    segment = data.get("segment", "all")
    content = data.get("content", {})

    if segment == "level":
        level = data.get("level", "")
        users = await get_users_for_broadcast_segment(session, f"level:{level}")
    else:
        users = await get_users_for_broadcast_segment(session, segment)

    await callback.answer()
    await callback.message.edit_text(
        f"⏳ Рассылка началась... ({len(users)} получателей)",
        parse_mode="Markdown",
    )

    # Отправляем сообщения
    success_count = 0
    fail_count = 0
    bot = callback.bot

    for user in users:
        try:
            if content.get("type") == "photo":
                await bot.send_photo(
                    chat_id=user.telegram_id,
                    photo=content["file_id"],
                    caption=content.get("caption"),
                )
            else:
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=content.get("text", ""),
                )
            success_count += 1
        except Exception as e:
            logger.warning(f"Не удалось отправить сообщение пользователю {user.telegram_id}: {e}")
            fail_count += 1

    await state.clear()
    await callback.message.edit_text(
        f"✅ **Рассылка завершена!**\n\n"
        f"✔️ Успешно: **{success_count}**\n"
        f"❌ Ошибки: **{fail_count}**",
        reply_markup=get_admin_panel_keyboard(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "broadcast:cancel")
async def callback_broadcast_cancel(callback: CallbackQuery, config: Config, state: FSMContext) -> None:
    """
    Обработчик отмены рассылки.
    """
    if callback.from_user.id not in config.admin_ids:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    await state.clear()
    await callback.answer("Рассылка отменена")
    await callback.message.edit_text(
        "🔐 **Панель администратора**\n\nВыбери действие:",
        reply_markup=get_admin_panel_keyboard(),
        parse_mode="Markdown",
    )


# =============================================================================
# Меню рассылок (обычная / запланированная / история)
# =============================================================================

@router.callback_query(F.data == "admin:broadcast_menu")
async def callback_broadcast_menu(callback: CallbackQuery, config: Config, state: FSMContext) -> None:
    """Меню рассылок: обычная, запланированная, история."""
    if callback.from_user.id not in config.admin_ids:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    await state.clear()
    await callback.answer()
    await callback.message.edit_text(
        "📢 **Рассылки**\n\nВыбери тип:",
        reply_markup=get_broadcast_menu_keyboard(),
        parse_mode="Markdown",
    )


# =============================================================================
# Запланированная рассылка — полный флоу
# =============================================================================

@router.callback_query(F.data == "admin:scheduled_broadcast")
async def callback_scheduled_broadcast_start(callback: CallbackQuery, config: Config, state: FSMContext) -> None:
    """Начало создания запланированной рассылки: выбор сегмента."""
    if callback.from_user.id not in config.admin_ids:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text(
        "🕐 **Запланированная рассылка**\n\nВыбери сегмент:",
        reply_markup=get_scheduled_segment_keyboard(),
        parse_mode="Markdown",
    )
    await state.set_state(ScheduledBroadcastStates.waiting_for_segment)


@router.callback_query(F.data.startswith("sched_seg:"), ScheduledBroadcastStates.waiting_for_segment)
async def callback_scheduled_segment(callback: CallbackQuery, config: Config, state: FSMContext) -> None:
    """Обработчик выбора сегмента для запланированной рассылки."""
    if callback.from_user.id not in config.admin_ids:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    parts = callback.data.split(":")
    segment = parts[1]

    if segment == "cancel":
        await state.clear()
        await callback.answer("Отменено")
        await callback.message.edit_text(
            "📢 **Рассылки**\n\nВыбери тип:",
            reply_markup=get_broadcast_menu_keyboard(),
            parse_mode="Markdown",
        )
        return

    if segment == "level" and len(parts) > 2:
        level = parts[2]
        await state.update_data(segment=f"level:{level}")
        segment_display = f"Уровень {level}"
    else:
        await state.update_data(segment=segment)
        segment_display = _get_segment_display(segment)

    await callback.answer()
    await callback.message.edit_text(
        f"🕐 Сегмент: **{segment_display}**\n\n"
        "Отправь текст или фото для рассылки:",
        parse_mode="Markdown",
    )
    await state.set_state(ScheduledBroadcastStates.waiting_for_content)


@router.message(ScheduledBroadcastStates.waiting_for_content)
async def message_scheduled_content(message: Message, config: Config, state: FSMContext) -> None:
    """Обработка контента для запланированной рассылки."""
    if message.from_user.id not in config.admin_ids:
        return

    content_data: Dict[str, Any] = {}
    if message.photo:
        content_data["type"] = "photo"
        content_data["file_id"] = message.photo[-1].file_id
        content_data["caption"] = message.caption or ""
    elif message.text:
        content_data["type"] = "text"
        content_data["text"] = message.text
    else:
        await message.answer("❌ Поддерживается только текст или фото.")
        return

    await state.update_data(content=content_data)
    await message.answer(
        "🎙 **Добавить кнопки RSVP?**\n\n"
        "Кнопки «Я буду» / «Не смогу» для созвона:",
        reply_markup=get_rsvp_choice_keyboard(),
        parse_mode="Markdown",
    )
    await state.set_state(ScheduledBroadcastStates.waiting_for_rsvp_choice)


@router.callback_query(F.data.startswith("sched_rsvp:"), ScheduledBroadcastStates.waiting_for_rsvp_choice)
async def callback_rsvp_choice(callback: CallbackQuery, config: Config, state: FSMContext) -> None:
    """Обработка выбора: добавить RSVP или нет."""
    if callback.from_user.id not in config.admin_ids:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    choice = callback.data.split(":")[1]
    await callback.answer()

    if choice == "yes":
        await state.update_data(has_rsvp=True)
        await callback.message.edit_text(
            "📝 **Название созвона**\n\n"
            "Введи название события (для Google Calendar):\n"
            "Например: «Разговорный клуб — La Casa de Papel»",
            parse_mode="Markdown",
        )
        await state.set_state(ScheduledBroadcastStates.waiting_for_rsvp_title)
    else:
        await state.update_data(has_rsvp=False)
        await callback.message.edit_text(
            "🕐 **Время отправки рассылки**\n\n"
            "Введи дату и время в формате:\n"
            "`ЧЧ:ММ/ДД/ММ/ГГГГ`\n\n"
            "Например: `14:00/17/02/2026`",
            parse_mode="Markdown",
        )
        await state.set_state(ScheduledBroadcastStates.waiting_for_schedule_time)


@router.message(ScheduledBroadcastStates.waiting_for_rsvp_title)
async def message_rsvp_title(message: Message, config: Config, state: FSMContext) -> None:
    """Ввод названия созвона для RSVP."""
    if message.from_user.id not in config.admin_ids:
        return
    if not message.text:
        await message.answer("❌ Отправьте текст.")
        return

    await state.update_data(rsvp_event_title=message.text.strip())
    await message.answer(
        "📅 **Дата и время созвона**\n\n"
        "Введи дату/время самого созвона (для Google Calendar):\n"
        "`ЧЧ:ММ/ДД/ММ/ГГГГ`\n\n"
        "Например: `19:00/22/02/2026`",
        parse_mode="Markdown",
    )
    await state.set_state(ScheduledBroadcastStates.waiting_for_rsvp_date)


@router.message(ScheduledBroadcastStates.waiting_for_rsvp_date)
async def message_rsvp_date(message: Message, config: Config, state: FSMContext) -> None:
    """Ввод даты/времени созвона для Google Calendar."""
    if message.from_user.id not in config.admin_ids:
        return
    if not message.text:
        await message.answer("❌ Отправьте дату.")
        return

    from datetime import datetime as dt
    try:
        rsvp_event_dt = dt.strptime(message.text.strip(), "%H:%M/%d/%m/%Y")
    except ValueError:
        await message.answer(
            "❌ Неверный формат. Используй: `ЧЧ:ММ/ДД/ММ/ГГГГ`\nНапример: `19:00/22/02/2026`",
            parse_mode="Markdown",
        )
        return

    await state.update_data(rsvp_event_datetime=rsvp_event_dt.isoformat())
    await message.answer(
        "� **Ссылка на Zoom**\n\n"
        "Отправьте ссылку на Zoom-конференцию.\n"
        "Она будет отправлена участникам за 5 минут до начала.\n\n"
        "Если ссылки нет — нажмите «Пропустить».",
        parse_mode="Markdown",
        reply_markup=get_zoom_link_keyboard(),
    )
    await state.set_state(ScheduledBroadcastStates.waiting_for_zoom_link)


@router.callback_query(F.data == "sched_zoom:skip")
async def callback_zoom_skip(callback: CallbackQuery, config: Config, state: FSMContext) -> None:
    """Пропуск ввода Zoom ссылки."""
    if callback.from_user.id not in config.admin_ids:
        return
    await callback.answer()
    await state.update_data(zoom_link=None)
    await callback.message.edit_text(
        "🕐 **Время отправки рассылки**\n\n"
        "Когда отправить рассылку?\n"
        "`ЧЧ:ММ/ДД/ММ/ГГГГ`\n\n"
        "Например: `14:00/17/02/2026`",
        parse_mode="Markdown",
    )
    await state.set_state(ScheduledBroadcastStates.waiting_for_schedule_time)


@router.message(ScheduledBroadcastStates.waiting_for_zoom_link)
async def message_zoom_link(message: Message, config: Config, state: FSMContext) -> None:
    """Ввод ссылки на Zoom."""
    if message.from_user.id not in config.admin_ids:
        return
    if not message.text:
        await message.answer("❌ Отправьте ссылку или нажмите «Пропустить».")
        return

    zoom_link = message.text.strip()
    if not zoom_link.startswith(("http://", "https://")):
        await message.answer("❌ Ссылка должна начинаться с http:// или https://")
        return
    await state.update_data(zoom_link=zoom_link)
    await message.answer(
        "🕐 **Время отправки рассылки**\n\n"
        "Когда отправить рассылку?\n"
        "`ЧЧ:ММ/ДД/ММ/ГГГГ`\n\n"
        "Например: `14:00/17/02/2026`",
        parse_mode="Markdown",
    )
    await state.set_state(ScheduledBroadcastStates.waiting_for_schedule_time)


@router.message(ScheduledBroadcastStates.waiting_for_schedule_time)
async def message_schedule_time(message: Message, config: Config, state: FSMContext) -> None:
    """Ввод времени отправки рассылки."""
    if message.from_user.id not in config.admin_ids:
        return
    if not message.text:
        await message.answer("❌ Отправьте дату.")
        return

    from datetime import datetime as dt
    try:
        scheduled_at = dt.strptime(message.text.strip(), "%H:%M/%d/%m/%Y")
    except ValueError:
        await message.answer(
            "❌ Неверный формат. Используй: `ЧЧ:ММ/ДД/ММ/ГГГГ`\nНапример: `14:00/17/02/2026`",
            parse_mode="Markdown",
        )
        return

    await state.update_data(scheduled_at=scheduled_at.isoformat())
    data = await state.get_data()

    # Формируем превью
    segment = data.get("segment", "all")
    if segment.startswith("level:"):
        seg_display = f"Уровень {segment.split(':', 1)[1]}"
    else:
        seg_display = _get_segment_display(segment)

    content = data.get("content", {})
    content_type_display = "Фото" if content.get("type") == "photo" else "Текст"
    content_preview = (content.get("caption") or content.get("text") or "")[:80]
    if len(content.get("caption", content.get("text", ""))) > 80:
        content_preview += "..."

    has_rsvp = data.get("has_rsvp", False)
    rsvp_info = ""
    if has_rsvp:
        rsvp_title = data.get("rsvp_event_title", "—")
        rsvp_dt_str = data.get("rsvp_event_datetime", "")
        if rsvp_dt_str:
            rsvp_dt = dt.fromisoformat(rsvp_dt_str)
            rsvp_dt_display = rsvp_dt.strftime("%H:%M %d.%m.%Y")
        else:
            rsvp_dt_display = "—"
        rsvp_info = (
            f"\n🎙 RSVP: **Да**\n"
            f"Событие: {rsvp_title}\n"
            f"Дата созвона: {rsvp_dt_display}"
        )

    preview = (
        f"📋 **Подтверждение рассылки**\n\n"
        f"Сегмент: **{seg_display}**\n"
        f"Тип: **{content_type_display}**\n"
        f"Отправка: **{scheduled_at.strftime('%H:%M %d.%m.%Y')}**\n"
        f"{rsvp_info}\n\n"
        f"> {content_preview}\n\n"
        f"Запланировать?"
    )

    await message.answer(
        text=preview,
        reply_markup=get_scheduled_confirm_keyboard(),
        parse_mode="Markdown",
    )
    await state.set_state(ScheduledBroadcastStates.waiting_for_confirm)


@router.callback_query(F.data == "sched_confirm:yes", ScheduledBroadcastStates.waiting_for_confirm)
async def callback_scheduled_confirm(
    callback: CallbackQuery, session: AsyncSession, config: Config, state: FSMContext
) -> None:
    """Подтверждение и сохранение запланированной рассылки в БД."""
    if callback.from_user.id not in config.admin_ids:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    from datetime import datetime as dt
    from database.requests import create_scheduled_broadcast

    data = await state.get_data()
    content = data.get("content", {})
    scheduled_at = dt.fromisoformat(data["scheduled_at"])

    rsvp_event_datetime = None
    if data.get("rsvp_event_datetime"):
        rsvp_event_datetime = dt.fromisoformat(data["rsvp_event_datetime"])

    broadcast = await create_scheduled_broadcast(
        session=session,
        segment=data.get("segment", "all"),
        content_type=content.get("type", "text"),
        scheduled_at=scheduled_at,
        content_text=content.get("caption") or content.get("text"),
        content_file_id=content.get("file_id"),
        has_rsvp=data.get("has_rsvp", False),
        rsvp_event_title=data.get("rsvp_event_title"),
        rsvp_event_datetime=rsvp_event_datetime,
        zoom_link=data.get("zoom_link"),
    )

    await state.clear()
    await callback.answer("Рассылка запланирована!")
    await callback.message.edit_text(
        f"✅ **Рассылка #{broadcast.id} запланирована!**\n\n"
        f"Отправка: **{scheduled_at.strftime('%H:%M %d.%m.%Y')}**\n"
        f"Сегмент: **{_get_segment_display(data.get('segment', 'all'))}**",
        reply_markup=get_broadcast_menu_keyboard(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "sched_confirm:cancel")
async def callback_scheduled_cancel(callback: CallbackQuery, config: Config, state: FSMContext) -> None:
    """Отмена запланированной рассылки."""
    if callback.from_user.id not in config.admin_ids:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    await state.clear()
    await callback.answer("Отменено")
    await callback.message.edit_text(
        "📢 **Рассылки**\n\nВыбери тип:",
        reply_markup=get_broadcast_menu_keyboard(),
        parse_mode="Markdown",
    )


# =============================================================================
# История рассылок
# =============================================================================

@router.callback_query(F.data == "admin:broadcast_history")
async def callback_broadcast_history(
    callback: CallbackQuery, session: AsyncSession, config: Config
) -> None:
    """Показывает историю запланированных рассылок."""
    if callback.from_user.id not in config.admin_ids:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    from database.requests import get_all_scheduled_broadcasts, count_rsvp_attending

    broadcasts = await get_all_scheduled_broadcasts(session, limit=15)

    if not broadcasts:
        await callback.answer()
        await callback.message.edit_text(
            "📋 **История рассылок**\n\nПока нет запланированных рассылок.",
            reply_markup=get_broadcast_history_back_keyboard(),
            parse_mode="Markdown",
        )
        return

    lines = []
    for b in broadcasts:
        status_emoji = {"pending": "⏳", "sent": "✅", "cancelled": "🚫"}.get(b.status.value, "❓")
        
        # Для событий с RSVP показываем дату СОБЫТИЯ, а не дату отправки рассылки
        if b.has_rsvp and b.rsvp_event_datetime:
            time_str = b.rsvp_event_datetime.strftime("%H:%M %d.%m.%Y")
        else:
            time_str = b.scheduled_at.strftime("%H:%M %d.%m.%Y") if b.scheduled_at else "—"

        seg = b.segment
        if seg.startswith("level:"):
            seg_display = seg.split(":", 1)[1]
        else:
            seg_display = _get_segment_display(seg)

        text_preview = (b.content_text or "")[:60]
        if len(b.content_text or "") > 60:
            text_preview += "..."

        line = f"{status_emoji} **{time_str}** → {seg_display}\n> {text_preview}"

        if b.status.value == "sent":
            line += f"\n✔️ {b.sent_count} / ❌ {b.fail_count}"

        if b.has_rsvp:
            attending = await count_rsvp_attending(session, b.id)
            line += f"\n👥 Придут: **{attending}**"

        lines.append(line)

    text = "📋 **История рассылок**\n\n" + "\n\n".join(lines)

    await callback.answer()
    await callback.message.edit_text(
        text[:4096],
        reply_markup=get_broadcast_history_back_keyboard(),
        parse_mode="Markdown",
    )


# =============================================================================
# Sync CRM (Google Sheets)
# =============================================================================

@router.callback_query(F.data == "admin:sync_crm")
async def callback_admin_sync_crm(
    callback: CallbackQuery,
    session: AsyncSession,
    config: Config,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    """
    Обработчик кнопки "Sync CRM".
    Запускает принудительную синхронизацию с Google Sheets.
    """
    if callback.from_user.id not in config.admin_ids:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    if gspread_client is None:
        await callback.answer("Google Sheets не настроен", show_alert=True)
        await callback.message.edit_text(
            "❌ **Google Sheets не настроен**\n\n"
            "Проверь файл `google_sheet_creds.json` и переменные окружения.",
            reply_markup=get_admin_panel_keyboard(),
            parse_mode="Markdown",
        )
        return

    await callback.answer()
    await callback.message.edit_text(
        "🔄 **Синхронизация с CRM...**\n\n"
        "Пожалуйста, подожди...",
        parse_mode="Markdown",
    )

    try:
        # Синхронизируем ВСЕХ пользователей в CRM
        from database.requests import get_user_ltv, count_users_by_status
        from database.models import UserStatus
        from services.google_sheets import sync_users_to_sheets

        # Получаем всех пользователей
        users = await get_all_users(session)
        
        # Собираем LTV для каждого пользователя
        ltv_map: Dict[int, float] = {}
        for user in users:
            ltv = await get_user_ltv(session, user.id)
            if ltv > 0:
                ltv_map[user.id] = ltv

        count = await sync_users_to_sheets(
            client=gspread_client,
            config=config,
            users=users,
            ltv_map=ltv_map,
        )

        # Получаем статистику по сегментам
        stats = await count_users_by_status(session)
        
        await callback.message.edit_text(
            f"✅ **Синхронизация завершена!**\n\n"
            f"📊 **CRM (всего: {count})**:\n"
            f"  • 🆕 Новые: **{stats.get('new', 0)}**\n"
            f"  • 🤔 Думают: **{stats.get('pending', 0)}**\n"
            f"  • ✅ Активные: **{stats.get('active', 0)}**\n"
            f"  • ⏰ Истекшие: **{stats.get('expired', 0)}**\n\n"
            f"💰 С LTV: **{len(ltv_map)}**",
            reply_markup=get_admin_panel_keyboard(),
            parse_mode="Markdown",
        )
    except Exception as e:
        import traceback
        logger.error(f"Ошибка синхронизации: {e}\n{traceback.format_exc()}")
        await callback.message.edit_text(
            f"❌ **Ошибка синхронизации**\n\n"
            f"```{str(e)[:200]}```",
            reply_markup=get_admin_panel_keyboard(),
            parse_mode="Markdown",
        )
