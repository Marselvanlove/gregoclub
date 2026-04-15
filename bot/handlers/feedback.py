# Handlers для опроса после встречи (Feedback System)
# Обрабатывает callback'и от кнопок опроса

import logging
from typing import Optional

import gspread
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline import (
    get_feedback_level_keyboard,
    get_feedback_next_keyboard,
    get_feedback_rating_keyboard,
    get_feedback_thanks_keyboard,
    get_followup_schedule_keyboard,
)
from bot.states import FeedbackStates
from bot.texts import (
    FEEDBACK_Q1_RATING,
    FEEDBACK_Q2_LEVEL,
    FEEDBACK_Q3_NEXT,
    FEEDBACK_Q4_IMPROVEMENT,
    FEEDBACK_THANKS,
    FEEDBACK_FOLLOWUP_HARD_LEVEL,
)
from database.models import LevelComfort, WillAttendNext
from database.requests import (
    get_event_feedback,
    get_scheduled_broadcast,
    get_user_analytics_profile,
    mark_followup_sent,
    update_feedback_improvement_comment,
    update_feedback_level_comfort,
    update_feedback_rating,
    update_feedback_will_attend,
)
from services.analytics import track_event
from utils.config import Config

logger = logging.getLogger(__name__)

router = Router(name="feedback")


def _is_b_level_broadcast(segment: Optional[str]) -> bool:
    return bool(segment and segment.startswith("level:B"))


async def _send_hard_level_followup(
    callback_or_message,
    session: AsyncSession,
    feedback,
) -> None:
    if not feedback or feedback.level_comfort != LevelComfort.hard or feedback.followup_sent_at:
        return

    broadcast = await get_scheduled_broadcast(session, feedback.broadcast_id)
    if not broadcast or not _is_b_level_broadcast(broadcast.segment):
        return

    try:
        await callback_or_message.bot.send_message(
            chat_id=feedback.telegram_id,
            text=FEEDBACK_FOLLOWUP_HARD_LEVEL,
            reply_markup=get_followup_schedule_keyboard(),
        )
        await mark_followup_sent(session, feedback.id)
        logger.info(f"Follow-up (hard level) отправлен пользователю {feedback.telegram_id}")
    except Exception as e:
        logger.warning(f"Не удалось отправить follow-up: {e}")


@router.callback_query(F.data.startswith("feedback:start:"))
async def on_feedback_start(
    callback: CallbackQuery,
    session: AsyncSession,
    config: Config,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    """
    Обработчик нажатия кнопки "Оставить отзыв".
    Показывает первый вопрос — оценка встречи.
    """
    broadcast_id = int(callback.data.split(":")[2])
    
    await callback.message.edit_text(
        text=FEEDBACK_Q1_RATING,
        reply_markup=get_feedback_rating_keyboard(broadcast_id),
    )
    profile = await get_user_analytics_profile(session, callback.from_user.id)
    await track_event(
        session,
        telegram_id=callback.from_user.id,
        journey="engagement",
        onboarding_version=profile.onboarding_version if profile and profile.onboarding_version else "core",
        event_name="first_feedback_started",
        step_key="feedback:start",
        source="feedback:start",
        metadata={"broadcast_id": broadcast_id},
        once_per_user=True,
        config=config,
        gspread_client=gspread_client,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("feedback:rating:"))
async def on_feedback_rating(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    """
    Обработчик выбора оценки (1-5 звёзд).
    Сохраняет оценку и показывает вопрос о комфортности уровня.
    """
    parts = callback.data.split(":")
    broadcast_id = int(parts[2])
    rating = int(parts[3])
    telegram_id = callback.from_user.id

    await update_feedback_rating(session, broadcast_id, telegram_id, rating)

    stars = "⭐️" * rating
    logger.info(f"Feedback rating {rating} from user {telegram_id} for broadcast {broadcast_id}")

    await callback.message.edit_text(
        text=FEEDBACK_Q2_LEVEL,
        reply_markup=get_feedback_level_keyboard(broadcast_id),
    )
    await callback.answer(f"Оценка: {stars}")


@router.callback_query(F.data.startswith("feedback:level:"))
async def on_feedback_level(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    """
    Обработчик ответа о комфортности уровня.
    Сохраняет ответ и показывает вопрос о следующей встрече.
    """
    parts = callback.data.split(":")
    broadcast_id = int(parts[2])
    answer = parts[3]
    telegram_id = callback.from_user.id

    level_comfort = LevelComfort(answer)

    await update_feedback_level_comfort(session, broadcast_id, telegram_id, level_comfort)

    logger.info(f"Feedback level '{answer}' from user {telegram_id} for broadcast {broadcast_id}")

    await callback.message.edit_text(
        text=FEEDBACK_Q3_NEXT,
        reply_markup=get_feedback_next_keyboard(broadcast_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("feedback:next:"))
async def on_feedback_next(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    config: Config,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    """
    Обработчик ответа о следующей встрече.
    Сохраняет ответ и показывает финальное сообщение.
    Затем отправляет follow-up если "было сложно" для B1+ уровня.
    """
    parts = callback.data.split(":")
    broadcast_id = int(parts[2])
    answer = parts[3]
    telegram_id = callback.from_user.id

    will_attend = WillAttendNext(answer)

    feedback = await get_event_feedback(session, broadcast_id, telegram_id)
    rating = feedback.rating if feedback else None

    await update_feedback_will_attend(
        session,
        broadcast_id,
        telegram_id,
        will_attend,
        awaiting_improvement_comment=bool(rating and rating < 5),
    )

    logger.info(f"Feedback next '{answer}' from user {telegram_id} for broadcast {broadcast_id}")

    if rating and rating < 5:
        await state.update_data(feedback_broadcast_id=broadcast_id)
        await state.set_state(FeedbackStates.waiting_for_improvement_comment)
        await callback.message.edit_text(text=FEEDBACK_Q4_IMPROVEMENT)
        await callback.answer()
        return

    await callback.message.edit_text(
        text=FEEDBACK_THANKS,
        reply_markup=get_feedback_thanks_keyboard(),
    )
    await callback.answer("Спасибо за отзыв! 💚")

    profile = await get_user_analytics_profile(session, telegram_id)
    await track_event(
        session,
        telegram_id=telegram_id,
        journey="engagement",
        onboarding_version=profile.onboarding_version if profile and profile.onboarding_version else "core",
        event_name="first_feedback_completed",
        step_key="feedback:complete",
        source="feedback:next",
        metadata={"broadcast_id": broadcast_id},
        once_per_user=True,
        config=config,
        gspread_client=gspread_client,
    )

    feedback = await get_event_feedback(session, broadcast_id, telegram_id)
    await _send_hard_level_followup(callback, session, feedback)


@router.message(FeedbackStates.waiting_for_improvement_comment, F.text)
async def on_feedback_improvement_comment(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    config: Config,
    gspread_client: Optional[gspread.Client] = None,
) -> None:
    data = await state.get_data()
    broadcast_id = data.get("feedback_broadcast_id")
    if not broadcast_id:
        await state.clear()
        return

    improvement_comment = message.text.strip()
    if not improvement_comment:
        await message.answer(FEEDBACK_Q4_IMPROVEMENT)
        return

    await update_feedback_improvement_comment(
        session,
        broadcast_id,
        message.from_user.id,
        improvement_comment,
    )
    await state.clear()

    await message.answer(
        text=FEEDBACK_THANKS,
        reply_markup=get_feedback_thanks_keyboard(),
    )

    profile = await get_user_analytics_profile(session, message.from_user.id)
    await track_event(
        session,
        telegram_id=message.from_user.id,
        journey="engagement",
        onboarding_version=profile.onboarding_version if profile and profile.onboarding_version else "core",
        event_name="first_feedback_completed",
        step_key="feedback:complete",
        source="feedback:improvement_comment",
        metadata={"broadcast_id": broadcast_id},
        once_per_user=True,
        config=config,
        gspread_client=gspread_client,
    )

    feedback = await get_event_feedback(session, broadcast_id, message.from_user.id)
    await _send_hard_level_followup(message, session, feedback)


@router.message(FeedbackStates.waiting_for_improvement_comment)
async def on_feedback_improvement_comment_invalid(
    message: Message,
) -> None:
    await message.answer(FEEDBACK_Q4_IMPROVEMENT)
