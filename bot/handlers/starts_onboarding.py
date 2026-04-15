"""
Новый онбординг /starts для A/B тестирования
"""
import logging
import asyncio
from typing import Optional

import gspread
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message, InputMediaPhoto, ReplyKeyboardRemove
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session_factory
from database.requests import add_user, get_user_by_telegram_id
from bot.texts import (
    STARTS_SUBSCRIPTION_INFO,
    STARTS_TARGET_AUDIENCE,
    STARTS1_CULTURE_OFFER_TEXT,
    STARTS1_INTRO,
    STARTS1_STATE_SELECTION,
    STARTS1_THAW_TITLE,
    STARTS1_THAW_TEXT,
)
from bot.keyboards.inline import (
    get_starts_keyboard,
    get_starts1_cta_keyboard,
    get_starts1_state_keyboard,
)
from bot.keyboards.reply import get_main_reply_keyboard
from services.analytics import track_event
from utils.config import Config

router = Router(name="starts_onboarding")
logger = logging.getLogger(__name__)


VIDEO_NOTE_ID = "DQACAgQAAxkBAAIhb2mq8tN_wyjQ5USOcThN3iJ9yr78AAICHQACbGNZUfOtmFjIg069OgQ"
PHOTO_1_ID = "AgACAgIAAxkBAAIhf2mq9Ft1DlzxE_NPzPavp9qubvVfAALyFmsbEO1YSZwOom6l4ry9AQADAgADeQADOgQ"
PHOTO_2_ID = "AgACAgIAAxkBAAIhgWmq9GH0GfyfOzNZKa6NlnudwGwIAALzFmsbEO1YSZxXtSG9RC-zAQADAgADeQADOgQ"
PHOTO_3_ID = "AgACAgIAAxkBAAIkWmmsKCUTjsqzWPk6XpXhhDmT2AOHAAKYFWsb9LVhSVr24hrTBCrDAQADAgADeQADOgQ"
STARTS1_CULTURE_PHOTO_1_ID = "AgACAgIAAxkBAAI5HGneTKJxYZxrMZEulYQT5BZNbY0-AALHGGsb3UHxSrezEuXo0wK2AQADAgADeQADOwQ"
STARTS1_CULTURE_PHOTO_2_ID = "AgACAgIAAxkBAAI5HmneTLaiJflBWqsRZ1fztJQq25LzAALJGGsb3UHxSkhZzcYFl04DAQADAgADeQADOwQ"
STARTS1_INTRO_DELAY_SECONDS = 6
STARTS1_TARIFF_DELAY_SECONDS = 600

_pending_starts1_tariff_tasks: dict[int, asyncio.Task] = {}


def get_starts1_intro_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="Выбрать свое состояние",
            callback_data="starts1:choose_state",
        ),
    )
    return builder.as_markup()


async def _sync_starts_onboarding_reporting(
    session: AsyncSession,
    config: Config,
    gspread_client: Optional[gspread.Client],
    telegram_id: int,
    onboarding_version: str,
    event_name: str,
    *,
    step_key: Optional[str] = None,
    source: Optional[str] = None,
    metadata: Optional[dict[str, object]] = None,
    once_per_user: bool = False,
) -> None:
    await track_event(
        session,
        telegram_id=telegram_id,
        journey="onboarding",
        onboarding_version=onboarding_version,
        event_name=event_name,
        step_key=step_key,
        source=source,
        metadata=metadata,
        once_per_user=once_per_user,
        config=config,
        gspread_client=gspread_client,
    )


async def send_starts_onboarding(
    message: Message,
    session: AsyncSession,
    config: Config,
    gspread_client: Optional[gspread.Client] = None,
    source: str = "/start",
) -> None:
    try:
        await _sync_starts_onboarding_reporting(
            session=session,
            config=config,
            gspread_client=gspread_client,
            telegram_id=message.from_user.id,
            onboarding_version="starts",
            event_name="onboarding_started",
            step_key="start",
            source=source,
        )
        
        # Шаг 1: Отправить кружок
        try:
            await message.answer_video_note(
                video_note=VIDEO_NOTE_ID,
            )
            logger.info("starts_onboarding step=video_note_sent user=%s source=%s", message.from_user.id, source)
            await _sync_starts_onboarding_reporting(
                session=session,
                config=config,
                gspread_client=gspread_client,
                telegram_id=message.from_user.id,
                onboarding_version="starts",
                event_name="video_note_sent",
                step_key="video_note",
                source=source,
            )
        except TelegramBadRequest as e:
            error_text = str(e).upper()
            if "VOICE_MESSAGES_FORBIDDEN" in error_text:
                logger.warning(
                    "starts_onboarding step=video_note_skipped user=%s source=%s reason=%s",
                    message.from_user.id,
                    source,
                    e,
                )
                await _sync_starts_onboarding_reporting(
                    session=session,
                    config=config,
                    gspread_client=gspread_client,
                    telegram_id=message.from_user.id,
                    onboarding_version="starts",
                    event_name="video_note_skipped",
                    step_key="video_note",
                    source=source,
                    metadata={"reason": str(e)},
                )
            else:
                raise
        
        # Небольшая задержка для естественности
        await asyncio.sleep(5)
        
        # Шаг 2: Отправить 2 фото с текстом про подписку (media group)
        # Создаем media group из 2 фото
        media_group = [
            InputMediaPhoto(
                media=PHOTO_1_ID,
                caption=STARTS_SUBSCRIPTION_INFO,
                parse_mode="HTML",
            ),
            InputMediaPhoto(
                media=PHOTO_2_ID,
            ),
        ]
        
        await message.answer_media_group(media=media_group)
        logger.info("starts_onboarding step=intro_media_group_sent user=%s source=%s", message.from_user.id, source)
        await _sync_starts_onboarding_reporting(
            session=session,
            config=config,
            gspread_client=gspread_client,
            telegram_id=message.from_user.id,
            onboarding_version="starts",
            event_name="intro_sent",
            step_key="intro_media",
            source=source,
        )
        
        # Небольшая задержка
        await asyncio.sleep(5)
        
        # Шаг 3: Отправить карточку "Кому подходит" с кнопками
        await message.answer_photo(
            photo=PHOTO_3_ID,
            caption=STARTS_TARGET_AUDIENCE,
            reply_markup=get_starts_keyboard(),
            parse_mode="HTML",
        )
        logger.info("starts_onboarding step=target_audience_sent user=%s source=%s", message.from_user.id, source)
        await _sync_starts_onboarding_reporting(
            session=session,
            config=config,
            gspread_client=gspread_client,
            telegram_id=message.from_user.id,
            onboarding_version="starts",
            event_name="branch_offer_sent",
            step_key="target_audience",
            source=source,
            metadata={"branch": "generic"},
        )
        
        logger.info(f"Пользователь {message.from_user.id} запустил новый онбординг /starts")
        
    except Exception as e:
        logger.error(f"Ошибка в обработчике /starts: {e}", exc_info=True)
        await message.answer(
            "Произошла ошибка при загрузке онбординга. Попробуйте позже или напишите /support"
        )


async def _send_photo_or_text(
    message: Message,
    *,
    photo_id: str,
    text: str,
    parse_mode: Optional[str] = None,
    reply_markup=None,
) -> None:
    """Отправляет фото с подписью и откатывается к тексту, если фото недоступно."""
    try:
        await message.answer_photo(
            photo=photo_id,
            caption=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
    except Exception:
        logger.warning("Не удалось отправить фото для starts1, отправляем текст", exc_info=True)
        await message.answer(
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )


async def _send_starts1_branch(
    message: Message,
    *,
    title: Optional[str] = None,
    text: str,
    title_photo_id: Optional[str] = PHOTO_3_ID,
    extra_photo_ids: Optional[list[str]] = None,
    parse_mode: Optional[str] = None,
) -> None:
    """Отправляет ветку /starts1 с временной иллюстрацией и CTA."""
    if title and title_photo_id:
        await _send_photo_or_text(
            message,
            photo_id=title_photo_id,
            text=title,
        )
    elif title:
        await message.answer(title)
    if extra_photo_ids:
        try:
            media_group = [InputMediaPhoto(media=photo_id) for photo_id in extra_photo_ids]
            await message.answer_media_group(media=media_group)
        except Exception:
            logger.warning("Не удалось отправить дополнительные фото для starts1", exc_info=True)
    await message.answer(
        text=text,
        reply_markup=get_starts1_cta_keyboard(),
        parse_mode=parse_mode,
    )


def _cancel_starts1_tariff_task(telegram_id: int) -> None:
    task = _pending_starts1_tariff_tasks.pop(telegram_id, None)
    if task and not task.done():
        task.cancel()


async def _send_starts1_tariffs_delayed(
    bot,
    telegram_id: int,
    config: Config,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    try:
        await asyncio.sleep(STARTS1_TARIFF_DELAY_SECONDS)

        from database.models import UserStatus
        from bot.handlers.user import send_tariff_selection_to_chat

        async with get_session_factory()() as session:
            user = await get_user_by_telegram_id(session, telegram_id)
            if user and user.status in {UserStatus.pending, UserStatus.active}:
                return

        await send_tariff_selection_to_chat(bot, telegram_id, config)
        async with get_session_factory()() as session:
            await _sync_starts_onboarding_reporting(
                session=session,
                config=config,
                gspread_client=gspread_client,
                telegram_id=telegram_id,
                onboarding_version="starts1",
                event_name="delayed_tariffs_sent",
                step_key="delayed_tariffs",
                source="starts1:offer",
            )
        logger.info("starts1_onboarding step=delayed_tariffs_sent user=%s", telegram_id)
    except asyncio.CancelledError:
        logger.debug("Отложенная отправка тарифов starts1 отменена для user=%s", telegram_id)
    finally:
        _pending_starts1_tariff_tasks.pop(telegram_id, None)


async def _hide_reply_keyboard(message: Message) -> None:
    service_message = await message.answer("\u2060", reply_markup=ReplyKeyboardRemove())
    try:
        await service_message.delete()
    except Exception:
        logger.debug("Не удалось удалить сервисное сообщение скрытия клавиатуры")


async def _show_reply_keyboard(message: Message) -> None:
    await message.answer("👋", reply_markup=get_main_reply_keyboard())


async def _send_starts1_more_info_content(message: Message) -> None:
    """Отправляет 2 и 3 сообщения старого /starts без кружка."""
    media_group = [
        InputMediaPhoto(
            media=PHOTO_1_ID,
            caption=STARTS_SUBSCRIPTION_INFO,
            parse_mode="HTML",
        ),
        InputMediaPhoto(
            media=PHOTO_2_ID,
        ),
    ]
    await message.answer_media_group(media=media_group)
    await asyncio.sleep(5)
    await message.answer_photo(
        photo=PHOTO_3_ID,
        caption=STARTS_TARGET_AUDIENCE,
        reply_markup=get_starts_keyboard(),
        parse_mode="HTML",
    )
    await _show_reply_keyboard(message)


async def send_starts1_onboarding(
    message: Message,
    session: AsyncSession,
    config: Config,
    gspread_client: Optional[gspread.Client] = None,
    source: str = "/start",
) -> None:
    try:
        try:
            await message.answer_video_note(
                video_note=VIDEO_NOTE_ID,
                reply_markup=ReplyKeyboardRemove(),
            )
            logger.info("starts1_onboarding step=video_note_sent user=%s source=%s", message.from_user.id, source)
            await _sync_starts_onboarding_reporting(
                session=session,
                config=config,
                gspread_client=gspread_client,
                telegram_id=message.from_user.id,
                onboarding_version="starts1",
                event_name="onboarding_started",
                step_key="start",
                source=source,
            )
            await _sync_starts_onboarding_reporting(
                session=session,
                config=config,
                gspread_client=gspread_client,
                telegram_id=message.from_user.id,
                onboarding_version="starts1",
                event_name="video_note_sent",
                step_key="video_note",
                source=source,
            )
        except TelegramBadRequest as e:
            error_text = str(e).upper()
            if "VOICE_MESSAGES_FORBIDDEN" in error_text:
                await _hide_reply_keyboard(message)
                await _sync_starts_onboarding_reporting(
                    session=session,
                    config=config,
                    gspread_client=gspread_client,
                    telegram_id=message.from_user.id,
                    onboarding_version="starts1",
                    event_name="onboarding_started",
                    step_key="start",
                    source=source,
                )
                logger.warning(
                    "starts1_onboarding step=video_note_skipped user=%s source=%s reason=%s",
                    message.from_user.id,
                    source,
                    e,
                )
                await _sync_starts_onboarding_reporting(
                    session=session,
                    config=config,
                    gspread_client=gspread_client,
                    telegram_id=message.from_user.id,
                    onboarding_version="starts1",
                    event_name="video_note_skipped",
                    step_key="video_note",
                    source=source,
                    metadata={"reason": str(e)},
                )
            else:
                raise

        await asyncio.sleep(STARTS1_INTRO_DELAY_SECONDS)
        await message.answer(
            STARTS1_INTRO,
            reply_markup=get_starts1_intro_keyboard(),
        )
        logger.info("starts1_onboarding step=intro_sent user=%s source=%s", message.from_user.id, source)
        await _sync_starts_onboarding_reporting(
            session=session,
            config=config,
            gspread_client=gspread_client,
            telegram_id=message.from_user.id,
            onboarding_version="starts1",
            event_name="intro_sent",
            step_key="intro",
            source=source,
        )
    except Exception as e:
        logger.error("Ошибка в обработчике /starts1: %s", e, exc_info=True)
        await message.answer(
            "Произошла ошибка при загрузке онбординга. Попробуйте позже или напишите /support"
        )


@router.message(Command("starts"))
async def cmd_starts_onboarding(
    message: Message,
    session: AsyncSession,
    config: Config,
    state: FSMContext,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    user = message.from_user
    if not user:
        return

    await add_user(
        session=session,
        telegram_id=user.id,
        username=user.username,
        full_name=user.full_name,
    )

    await send_starts_onboarding(message, session, config, gspread_client, source="/starts")


@router.message(Command("starts1"))
async def cmd_starts1_onboarding(
    message: Message,
    session: AsyncSession,
    config: Config,
    state: FSMContext,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    user = message.from_user
    if not user:
        return

    await add_user(
        session=session,
        telegram_id=user.id,
        username=user.username,
        full_name=user.full_name,
    )

    await send_starts1_onboarding(message, session, config, gspread_client, source="/starts1")


@router.callback_query(F.data.in_({"starts1:state:1", "starts1:state:2", "starts1:state:3"}))
async def callback_starts1_state(
    callback: CallbackQuery,
    session: AsyncSession,
    config: Config,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    if not callback.data or not callback.message:
        return

    await callback.answer()
    state_choice = callback.data.rsplit(":", 1)[-1]
    branch = "culture" if state_choice == "2" else "thaw"

    if callback.from_user:
        await _sync_starts_onboarding_reporting(
            session=session,
            config=config,
            gspread_client=gspread_client,
            telegram_id=callback.from_user.id,
            onboarding_version="starts1",
            event_name="state_selected",
            step_key=f"state:{state_choice}",
            source="starts1:state",
            metadata={"state": state_choice},
        )
        await _sync_starts_onboarding_reporting(
            session=session,
            config=config,
            gspread_client=gspread_client,
            telegram_id=callback.from_user.id,
            onboarding_version="starts1",
            event_name="branch_offer_sent",
            step_key=f"branch:{branch}",
            source="starts1:state",
            metadata={"state": state_choice, "branch": branch},
        )

    if state_choice == "2":
        await _send_starts1_branch(
            callback.message,
            text=STARTS1_CULTURE_OFFER_TEXT,
            title_photo_id=None,
            parse_mode="HTML",
        )
        return

    await _send_starts1_branch(
        callback.message,
        title=STARTS1_THAW_TITLE,
        title_photo_id=None,
        text=STARTS1_THAW_TEXT,
        parse_mode="HTML",
    )


@router.callback_query(F.data == "starts1:choose_state")
async def callback_starts1_choose_state(
    callback: CallbackQuery,
    session: AsyncSession,
    config: Config,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    if callback.message is None:
        return

    await callback.answer()
    await callback.message.answer(
        STARTS1_STATE_SELECTION,
        parse_mode="HTML",
        reply_markup=get_starts1_state_keyboard(),
    )
    logger.info(
        "starts1_onboarding step=state_selection_sent user=%s",
        callback.from_user.id if callback.from_user else "unknown",
    )
    if callback.from_user:
        await _sync_starts_onboarding_reporting(
            session=session,
            config=config,
            gspread_client=gspread_client,
            telegram_id=callback.from_user.id,
            onboarding_version="starts1",
            event_name="state_picker_opened",
            step_key="state_picker",
            source="starts1:choose_state",
        )


@router.callback_query(F.data == "starts1:offer")
async def callback_starts1_offer(
    callback: CallbackQuery,
    session: AsyncSession,
    config: Config,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    if callback.from_user is None or callback.message is None:
        return

    await callback.answer()

    _cancel_starts1_tariff_task(callback.from_user.id)

    from bot.handlers.user import build_smart_schedule
    from bot.keyboards.inline import get_starts1_schedule_keyboard

    text, is_subscribed = await build_smart_schedule(session, callback.from_user.id)
    await callback.message.answer(
        text=text,
        reply_markup=get_starts1_schedule_keyboard(is_subscribed),
        parse_mode="HTML",
    )
    await _show_reply_keyboard(callback.message)
    await _sync_starts_onboarding_reporting(
        session=session,
        config=config,
        gspread_client=gspread_client,
        telegram_id=callback.from_user.id,
        onboarding_version="starts1",
        event_name="schedule_opened",
        step_key="schedule",
        source="starts1:offer",
    )

    if not is_subscribed:
        _pending_starts1_tariff_tasks[callback.from_user.id] = asyncio.create_task(
            _send_starts1_tariffs_delayed(
                callback.message.bot,
                callback.from_user.id,
                config,
                gspread_client,
            )
        )


@router.callback_query(F.data == "starts1:more_info")
async def callback_starts1_more_info(
    callback: CallbackQuery,
    session: AsyncSession,
    config: Config,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    if callback.from_user is None or callback.message is None:
        return

    await callback.answer()

    _cancel_starts1_tariff_task(callback.from_user.id)
    await _sync_starts_onboarding_reporting(
        session=session,
        config=config,
        gspread_client=gspread_client,
        telegram_id=callback.from_user.id,
        onboarding_version="starts1",
        event_name="more_info_opened",
        step_key="more_info",
        source="starts1:more_info",
    )
    await _send_starts1_more_info_content(callback.message)


@router.callback_query(F.data == "starts1:pay")
async def callback_starts1_pay(
    callback: CallbackQuery,
    session: AsyncSession,
    config: Config,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    if callback.from_user is None or callback.message is None:
        return

    await callback.answer()
    _cancel_starts1_tariff_task(callback.from_user.id)

    from bot.handlers.user import open_payment_flow

    await open_payment_flow(
        message=callback.message,
        session=session,
        config=config,
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        full_name=callback.from_user.full_name,
        source="starts1:pay",
        onboarding_version="starts1",
        gspread_client=gspread_client,
    )
