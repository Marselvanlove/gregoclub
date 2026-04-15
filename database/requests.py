# Функции работы с БД: add_user, get_user, update_user и т.д.
# CRUD-операции для таблиц users и payments.

import logging
from datetime import datetime, timedelta
from typing import Optional, Sequence

from sqlalchemy import delete, func, literal, or_, select, update
from sqlalchemy.sql import Select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from database.models import (
    AnalyticsEvent,
    BroadcastDeliveryLog,
    BroadcastRSVP,
    BroadcastStatus,
    EventFeedback,
    LevelComfort,
    Payment,
    PaymentOrder,
    PaymentOrderStatus,
    PaymentProvider,
    RSVPResponse,
    ScheduledBroadcast,
    Setting,
    UserAnalyticsProfile,
    User,
    UserStatus,
    WillAttendNext,
)


INACTIVE_CUSTOM_SEGMENT_PREFIX = "inactive_custom_active"


def build_inactive_custom_segment(inactivity_days: int, missed_events: int) -> str:
    return f"{INACTIVE_CUSTOM_SEGMENT_PREFIX}:{max(inactivity_days, 0)}:{max(missed_events, 0)}"


def parse_inactive_custom_segment(segment: str) -> Optional[tuple[int, int]]:
    if not segment.startswith(f"{INACTIVE_CUSTOM_SEGMENT_PREFIX}:"):
        return None

    parts = segment.split(":")
    if len(parts) != 3:
        return None

    _, inactivity_days_str, missed_events_str = parts
    try:
        return max(int(inactivity_days_str), 0), max(int(missed_events_str), 0)
    except ValueError:
        return None


# =============================================================================
# USERS: CRUD-операции
# =============================================================================

async def add_user(
    session: AsyncSession,
    telegram_id: int,
    username: Optional[str] = None,
    full_name: Optional[str] = None,
) -> User:
    """
    Создаёт нового пользователя в БД.
    Если пользователь с таким telegram_id уже есть — возвращает существующего.
    Использует upsert-логику для избежания race conditions.
    """
    # Сначала проверяем, есть ли уже такой пользователь
    existing = await get_user_by_telegram_id(session, telegram_id)
    if existing is not None:
        # Обновляем username и full_name если изменились
        if existing.username != username or existing.full_name != full_name:
            existing.username = username
            existing.full_name = full_name
            await session.commit()
        return existing

    # Пробуем создать нового пользователя
    try:
        user = User(
            telegram_id=telegram_id,
            username=username,
            full_name=full_name,
            status=UserStatus.new,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user
    except Exception:
        # Если произошла ошибка (race condition), откатываем и возвращаем существующего
        await session.rollback()
        existing = await get_user_by_telegram_id(session, telegram_id)
        if existing:
            return existing
        raise  # Если и после этого нет — пробрасываем ошибку


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> Optional[User]:
    """Находит пользователя по его Telegram ID."""
    stmt = select(User).where(User.telegram_id == telegram_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_by_stripe_customer_id(session: AsyncSession, stripe_customer_id: str) -> Optional[User]:
    """Находит пользователя по его Stripe Customer ID (для обработки вебхуков)."""
    stmt = select(User).where(User.stripe_customer_id == stripe_customer_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_by_payment_customer_id(
    session: AsyncSession,
    payment_customer_id: str,
) -> Optional[User]:
    stmt = select(User).where(User.payment_customer_id == payment_customer_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def update_user_status(session: AsyncSession, telegram_id: int, new_status: UserStatus) -> None:
    """Обновляет статус пользователя."""
    stmt = update(User).where(User.telegram_id == telegram_id).values(status=new_status)
    await session.execute(stmt)
    await session.commit()


async def mark_user_pay_click(session: AsyncSession, telegram_id: int) -> None:
    stmt = (
        update(User)
        .where(User.telegram_id == telegram_id)
        .values(last_pay_click_at=datetime.utcnow(), pending_reminder_step=0)
    )
    await session.execute(stmt)
    await session.commit()


async def increment_pending_reminder_step(session: AsyncSession, telegram_id: int) -> None:
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        return
    new_step = (user.pending_reminder_step or 0) + 1
    stmt = update(User).where(User.telegram_id == telegram_id).values(pending_reminder_step=new_step)
    await session.execute(stmt)
    await session.commit()


async def mark_expiry_warning_sent(session: AsyncSession, telegram_id: int) -> None:
    stmt = update(User).where(User.telegram_id == telegram_id).values(expiry_warning_sent_at=datetime.utcnow())
    await session.execute(stmt)
    await session.commit()


async def update_user_language_level(session: AsyncSession, telegram_id: int, language_level: str) -> None:
    """Обновляет уровень языка пользователя (после выбора в /start)."""
    stmt = update(User).where(User.telegram_id == telegram_id).values(language_level=language_level)
    await session.execute(stmt)
    await session.commit()


async def mark_demo_completed(session: AsyncSession, telegram_id: int) -> None:
    """Помечает, что пользователь прошёл демо AI."""
    stmt = update(User).where(User.telegram_id == telegram_id).values(demo_completed=True)
    await session.execute(stmt)
    await session.commit()


async def is_demo_completed(session: AsyncSession, telegram_id: int) -> bool:
    """Проверяет, прошёл ли пользователь демо AI."""
    stmt = select(User.demo_completed).where(User.telegram_id == telegram_id)
    result = await session.execute(stmt)
    value = result.scalar_one_or_none()
    return value is True


async def update_user_subscription(
    session: AsyncSession,
    telegram_id: int,
    subscription_end_date: datetime,
    stripe_customer_id: Optional[str] = None,
    payment_provider: Optional[PaymentProvider] = None,
    payment_customer_id: Optional[str] = None,
) -> None:
    """
    Обновляет подписку пользователя:
    - Устанавливает дату окончания подписки
    - Устанавливает статус active
    - (опционально) Сохраняет Stripe Customer ID
    - Отмечает время покупки для отправки проверки входа в группу
    """
    values: dict = {
        "subscription_end_date": subscription_end_date,
        "status": UserStatus.active,
        "pending_reminder_step": None,
        "expiry_warning_sent_at": None,
        "last_purchase_at": datetime.utcnow(),
        "group_join_check_sent": False,
    }
    if stripe_customer_id is not None:
        values["stripe_customer_id"] = stripe_customer_id
        values["payment_provider"] = PaymentProvider.stripe
        values["payment_customer_id"] = stripe_customer_id
    if payment_provider is not None:
        values["payment_provider"] = payment_provider
    if payment_customer_id is not None:
        values["payment_customer_id"] = payment_customer_id

    stmt = update(User).where(User.telegram_id == telegram_id).values(**values)
    await session.execute(stmt)
    await session.commit()


async def save_user_email(session: AsyncSession, telegram_id: int, email: str) -> None:
    stmt = update(User).where(User.telegram_id == telegram_id).values(email=email)
    await session.execute(stmt)
    await session.commit()


async def get_users_for_group_join_check(session: AsyncSession) -> Sequence[User]:
    """
    Получает пользователей, которым нужно отправить проверку входа в группу.
    Условия:
    - last_purchase_at не None
    - group_join_check_sent = False
    - Прошло 5 минут с момента покупки
    """
    five_minutes_ago = datetime.utcnow() - timedelta(minutes=5)
    stmt = (
        select(User)
        .where(
            User.last_purchase_at.isnot(None),
            User.group_join_check_sent == False,
            User.last_purchase_at <= five_minutes_ago,
        )
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def mark_group_join_check_sent(session: AsyncSession, telegram_id: int) -> None:
    """Отмечает, что проверка входа в группу отправлена."""
    stmt = update(User).where(User.telegram_id == telegram_id).values(group_join_check_sent=True)
    await session.execute(stmt)
    await session.commit()


async def get_expired_users(session: AsyncSession) -> Sequence[User]:
    """
    Возвращает пользователей с истёкшей подпиской.
    Используется планировщиком для ежедневной проверки.
    """
    now = datetime.utcnow()
    stmt = select(User).where(
        User.status == UserStatus.active,
        User.subscription_end_date < now,
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_pending_users_for_reminder(session: AsyncSession, step: int) -> Sequence[User]:
    """
    PENDING напоминания:
    step=1: через 2 часа — помощь с оплатой
    step=2: через 24 часа
    step=3: через 48 часов
    """
    now = datetime.utcnow()
    if step == 1:
        cutoff = now - timedelta(hours=2)
    elif step == 2:
        cutoff = now - timedelta(hours=24)
    else:
        cutoff = now - timedelta(hours=48)

    step_filter = (
        (User.pending_reminder_step.is_(None) | (User.pending_reminder_step == 0))
        if step == 1
        else (User.pending_reminder_step == (step - 1))
    )

    stmt = select(User).where(
        User.status == UserStatus.pending,
        step_filter,
        User.last_pay_click_at.is_not(None),
        User.last_pay_click_at < cutoff,
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_active_users_expiring_soon(session: AsyncSession, days: int = 3) -> Sequence[User]:
    now = datetime.utcnow()
    cutoff = now + timedelta(days=days)
    stmt = select(User).where(
        User.status == UserStatus.active,
        User.subscription_end_date.is_not(None),
        User.subscription_end_date <= cutoff,
        (User.expiry_warning_sent_at.is_(None) | (User.expiry_warning_sent_at < now - timedelta(days=1))),
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_users_by_status(session: AsyncSession, status: UserStatus) -> Sequence[User]:
    """Возвращает всех пользователей с заданным статусом."""
    stmt = select(User).where(User.status == status)
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_users_by_level(session: AsyncSession, level: str) -> Sequence[User]:
    """Возвращает всех пользователей с заданным уровнем испанского."""
    stmt = select(User).where(User.language_level == level)
    result = await session.execute(stmt)
    return result.scalars().all()


async def create_analytics_event(
    session: AsyncSession,
    *,
    telegram_id: int,
    journey: str,
    onboarding_version: str,
    event_name: str,
    step_key: Optional[str] = None,
    source: Optional[str] = None,
    provider: Optional[str] = None,
    metadata_json: Optional[dict] = None,
) -> AnalyticsEvent:
    user = await get_user_by_telegram_id(session, telegram_id)
    event = AnalyticsEvent(
        user_id=user.id if user else None,
        telegram_id=telegram_id,
        journey=journey,
        onboarding_version=onboarding_version,
        event_name=event_name,
        step_key=step_key,
        source=source,
        provider=provider,
        metadata_json=metadata_json or {},
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


async def analytics_event_exists(
    session: AsyncSession,
    *,
    telegram_id: int,
    event_name: str,
) -> bool:
    stmt = (
        select(AnalyticsEvent.id)
        .where(
            AnalyticsEvent.telegram_id == telegram_id,
            AnalyticsEvent.event_name == event_name,
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def get_user_analytics_events(
    session: AsyncSession,
    telegram_id: int,
    limit: Optional[int] = None,
) -> Sequence[AnalyticsEvent]:
    stmt = (
        select(AnalyticsEvent)
        .where(AnalyticsEvent.telegram_id == telegram_id)
        .order_by(AnalyticsEvent.created_at.asc(), AnalyticsEvent.id.asc())
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_latest_analytics_event(
    session: AsyncSession,
    telegram_id: int,
) -> Optional[AnalyticsEvent]:
    stmt = (
        select(AnalyticsEvent)
        .where(AnalyticsEvent.telegram_id == telegram_id)
        .order_by(AnalyticsEvent.created_at.desc(), AnalyticsEvent.id.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_latest_analytics_event_by_name(
    session: AsyncSession,
    *,
    telegram_id: int,
    event_name: str,
) -> Optional[AnalyticsEvent]:
    stmt = (
        select(AnalyticsEvent)
        .where(
            AnalyticsEvent.telegram_id == telegram_id,
            AnalyticsEvent.event_name == event_name,
        )
        .order_by(AnalyticsEvent.created_at.desc(), AnalyticsEvent.id.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_first_analytics_event_by_name(
    session: AsyncSession,
    *,
    telegram_id: int,
    event_name: str,
) -> Optional[AnalyticsEvent]:
    stmt = (
        select(AnalyticsEvent)
        .where(
            AnalyticsEvent.telegram_id == telegram_id,
            AnalyticsEvent.event_name == event_name,
        )
        .order_by(AnalyticsEvent.created_at.asc(), AnalyticsEvent.id.asc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_analytics_profile(
    session: AsyncSession,
    telegram_id: int,
) -> Optional[UserAnalyticsProfile]:
    stmt = select(UserAnalyticsProfile).where(UserAnalyticsProfile.telegram_id == telegram_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_all_user_analytics_profiles(
    session: AsyncSession,
) -> Sequence[UserAnalyticsProfile]:
    stmt = select(UserAnalyticsProfile)
    result = await session.execute(stmt)
    return result.scalars().all()


async def upsert_user_analytics_profile(
    session: AsyncSession,
    *,
    telegram_id: int,
    user_id: Optional[int],
    onboarding_version: Optional[str] = None,
    entry_source: Optional[str] = None,
    last_event: Optional[str] = None,
    last_event_at: Optional[datetime] = None,
    state_choice: Optional[str] = None,
    payment_provider: Optional[str] = None,
    first_paid_at: Optional[datetime] = None,
    first_rsvp_at: Optional[datetime] = None,
    first_feedback_at: Optional[datetime] = None,
    feedback_prompt_at: Optional[datetime] = None,
    stuck_bucket: Optional[str] = None,
) -> UserAnalyticsProfile:
    profile = await get_user_analytics_profile(session, telegram_id)
    values = {
        "user_id": user_id,
        "onboarding_version": onboarding_version,
        "entry_source": entry_source,
        "last_event": last_event,
        "last_event_at": last_event_at,
        "state_choice": state_choice,
        "payment_provider": payment_provider,
        "first_paid_at": first_paid_at,
        "first_rsvp_at": first_rsvp_at,
        "first_feedback_at": first_feedback_at,
        "feedback_prompt_at": feedback_prompt_at,
        "stuck_bucket": stuck_bucket,
    }
    if profile is None:
        profile = UserAnalyticsProfile(telegram_id=telegram_id, **values)
        session.add(profile)
    else:
        for key, value in values.items():
            setattr(profile, key, value)
    await session.commit()
    await session.refresh(profile)
    return profile


async def get_new_users_for_reminder(session: AsyncSession, step: int) -> Sequence[User]:
    """
    Возвращает NEW пользователей для напоминания.
    step=1: через 1 час — GregoChat подарок
    step=2: через 3 часа
    step=3: через 24 часа
    """
    now = datetime.utcnow()
    if step == 1:
        cutoff = now - timedelta(hours=1)
    elif step == 2:
        cutoff = now - timedelta(hours=3)
    else:
        cutoff = now - timedelta(hours=24)

    step_filter = (
        (User.new_reminder_step.is_(None) | (User.new_reminder_step == 0))
        if step == 1
        else (User.new_reminder_step == (step - 1))
    )

    stmt = select(User).where(
        User.status == UserStatus.new,
        step_filter,
        User.registration_date < cutoff,
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def increment_new_reminder_step(session: AsyncSession, telegram_id: int) -> None:
    """Увеличивает шаг напоминания для NEW пользователя."""
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        return
    new_step = (user.new_reminder_step or 0) + 1
    stmt = update(User).where(User.telegram_id == telegram_id).values(new_reminder_step=new_step)
    await session.execute(stmt)
    await session.commit()


async def get_expired_users_for_winback(session: AsyncSession, step: int) -> Sequence[User]:
    """
    Возвращает EXPIRED пользователей для winback-напоминания.
    step=1: через 3 дня после expired_at
    step=2: через 7 дней после expired_at
    """
    now = datetime.utcnow()
    if step == 1:
        cutoff = now - timedelta(days=3)
    else:
        cutoff = now - timedelta(days=7)

    step_filter = (
        (User.winback_step.is_(None) | (User.winback_step == 0))
        if step == 1
        else (User.winback_step == (step - 1))
    )

    stmt = select(User).where(
        User.status == UserStatus.expired,
        step_filter,
        User.expired_at.is_not(None),
        User.expired_at < cutoff,
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def increment_winback_step(session: AsyncSession, telegram_id: int) -> None:
    """Увеличивает шаг winback-напоминания для EXPIRED пользователя."""
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        return
    new_step = (user.winback_step or 0) + 1
    stmt = update(User).where(User.telegram_id == telegram_id).values(winback_step=new_step)
    await session.execute(stmt)
    await session.commit()


async def mark_user_expired(session: AsyncSession, telegram_id: int) -> None:
    """Помечает пользователя как expired и сохраняет дату для winback."""
    stmt = (
        update(User)
        .where(User.telegram_id == telegram_id)
        .values(status=UserStatus.expired, expired_at=datetime.utcnow(), winback_step=0)
    )
    await session.execute(stmt)
    await session.commit()


async def get_all_users(session: AsyncSession) -> Sequence[User]:
    """Возвращает всех пользователей (для рассылки "Все" и синхронизации с Google Sheets)."""
    stmt = select(User)
    result = await session.execute(stmt)
    return result.scalars().all()


def _build_recent_past_rsvp_events_query(limit: int = 5) -> Select:
    import pytz

    madrid_now = datetime.now(pytz.timezone("Europe/Madrid")).replace(tzinfo=None)
    return (
        select(ScheduledBroadcast)
        .where(
            ScheduledBroadcast.has_rsvp == True,
            ScheduledBroadcast.status == BroadcastStatus.sent,
            ScheduledBroadcast.rsvp_event_datetime.isnot(None),
            ScheduledBroadcast.rsvp_event_datetime < madrid_now,
        )
        .order_by(ScheduledBroadcast.rsvp_event_datetime.desc())
        .limit(limit)
    )


async def get_recent_past_rsvp_events(
    session: AsyncSession,
    limit: int = 5,
) -> Sequence[ScheduledBroadcast]:
    """Возвращает последние прошедшие RSVP-события."""
    result = await session.execute(_build_recent_past_rsvp_events_query(limit=limit))
    return result.scalars().all()


async def get_users_missing_recent_rsvp_events(
    session: AsyncSession,
    limit: int = 5,
    statuses: Optional[Sequence[UserStatus]] = None,
) -> Sequence[User]:
    """Возвращает пользователей, не записавшихся на последние прошедшие RSVP-события."""
    recent_events = await get_recent_past_rsvp_events(session, limit=limit)
    if not recent_events:
        return []

    event_ids = [event.id for event in recent_events]
    attended_subquery = (
        select(BroadcastRSVP.telegram_id)
        .where(
            BroadcastRSVP.response == RSVPResponse.attending,
            BroadcastRSVP.broadcast_id.in_(event_ids),
        )
        .distinct()
    )

    stmt = select(User).where(~User.telegram_id.in_(attended_subquery))
    if statuses:
        stmt = stmt.where(User.status.in_(statuses))

    stmt = stmt.order_by(User.full_name.asc().nullslast(), User.username.asc().nullslast(), User.telegram_id.asc())
    result = await session.execute(stmt)
    return result.scalars().all()


async def count_users_missing_recent_rsvp_events(
    session: AsyncSession,
    limit: int = 5,
    statuses: Optional[Sequence[UserStatus]] = None,
) -> int:
    """Считает пользователей, не записавшихся на последние прошедшие RSVP-события."""
    recent_events = await get_recent_past_rsvp_events(session, limit=limit)
    if not recent_events:
        return 0

    event_ids = [event.id for event in recent_events]
    attended_subquery = (
        select(BroadcastRSVP.telegram_id)
        .where(
            BroadcastRSVP.response == RSVPResponse.attending,
            BroadcastRSVP.broadcast_id.in_(event_ids),
        )
        .distinct()
    )

    stmt = select(func.count(User.id)).where(~User.telegram_id.in_(attended_subquery))
    if statuses:
        stmt = stmt.where(User.status.in_(statuses))

    result = await session.execute(stmt)
    return result.scalar_one() or 0


async def get_users_with_attending_count_below(
    session: AsyncSession,
    threshold: int,
    statuses: Optional[Sequence[UserStatus]] = None,
) -> Sequence[User]:
    """Возвращает пользователей, у которых количество RSVP attending меньше порога."""
    attending_stats = (
        select(
            BroadcastRSVP.telegram_id.label("telegram_id"),
            func.count(BroadcastRSVP.id).label("total_attending"),
        )
        .where(BroadcastRSVP.response == RSVPResponse.attending)
        .group_by(BroadcastRSVP.telegram_id)
        .subquery()
    )

    stmt = (
        select(User)
        .outerjoin(attending_stats, attending_stats.c.telegram_id == User.telegram_id)
        .where(func.coalesce(attending_stats.c.total_attending, 0) < threshold)
    )
    if statuses:
        stmt = stmt.where(User.status.in_(statuses))

    stmt = stmt.order_by(
        func.coalesce(attending_stats.c.total_attending, 0).asc(),
        User.full_name.asc().nullslast(),
        User.username.asc().nullslast(),
        User.telegram_id.asc(),
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def count_users_with_attending_count_below(
    session: AsyncSession,
    threshold: int,
    statuses: Optional[Sequence[UserStatus]] = None,
) -> int:
    """Считает пользователей, у которых количество RSVP attending меньше порога."""
    attending_stats = (
        select(
            BroadcastRSVP.telegram_id.label("telegram_id"),
            func.count(BroadcastRSVP.id).label("total_attending"),
        )
        .where(BroadcastRSVP.response == RSVPResponse.attending)
        .group_by(BroadcastRSVP.telegram_id)
        .subquery()
    )

    stmt = (
        select(func.count(User.id))
        .select_from(User)
        .outerjoin(attending_stats, attending_stats.c.telegram_id == User.telegram_id)
        .where(func.coalesce(attending_stats.c.total_attending, 0) < threshold)
    )
    if statuses:
        stmt = stmt.where(User.status.in_(statuses))

    result = await session.execute(stmt)
    return result.scalar_one() or 0


async def get_users_with_inactive_rsvp_filters(
    session: AsyncSession,
    inactivity_days: int = 0,
    missed_events: int = 0,
    statuses: Optional[Sequence[UserStatus]] = None,
) -> Sequence[User]:
    if inactivity_days <= 0 and missed_events <= 0:
        return []

    attending_stats = (
        select(
            BroadcastRSVP.telegram_id.label("telegram_id"),
            func.count(BroadcastRSVP.id).label("total_attending"),
            func.max(
                func.coalesce(ScheduledBroadcast.rsvp_event_datetime, BroadcastRSVP.created_at)
            ).label("last_attending_at"),
        )
        .join(ScheduledBroadcast, ScheduledBroadcast.id == BroadcastRSVP.broadcast_id)
        .where(BroadcastRSVP.response == RSVPResponse.attending)
        .group_by(BroadcastRSVP.telegram_id)
        .subquery()
    )

    filters = []
    recent_attending = None

    if inactivity_days > 0:
        cutoff = datetime.utcnow() - timedelta(days=inactivity_days)
        filters.append(
            or_(
                attending_stats.c.last_attending_at.is_(None),
                attending_stats.c.last_attending_at < cutoff,
            )
        )

    if missed_events > 0:
        recent_events = await get_recent_past_rsvp_events(session, limit=missed_events)
        if recent_events:
            event_ids = [event.id for event in recent_events]
            recent_attending = (
                select(BroadcastRSVP.telegram_id.label("telegram_id"))
                .where(
                    BroadcastRSVP.response == RSVPResponse.attending,
                    BroadcastRSVP.broadcast_id.in_(event_ids),
                )
                .distinct()
                .subquery()
            )
            filters.append(recent_attending.c.telegram_id.is_(None))
        elif inactivity_days <= 0:
            return []

    stmt = (
        select(User)
        .select_from(User)
        .outerjoin(attending_stats, attending_stats.c.telegram_id == User.telegram_id)
    )
    if recent_attending is not None:
        stmt = stmt.outerjoin(recent_attending, recent_attending.c.telegram_id == User.telegram_id)
    if statuses:
        filters.append(User.status.in_(statuses))
    if filters:
        stmt = stmt.where(*filters)

    stmt = stmt.order_by(
        attending_stats.c.last_attending_at.desc().nullslast(),
        User.full_name.asc().nullslast(),
        User.username.asc().nullslast(),
        User.telegram_id.asc(),
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_inactive_participants_page(
    session: AsyncSession,
    page: int = 1,
    page_size: int = 10,
    recent_events_limit: int = 5,
    statuses: Optional[Sequence[UserStatus]] = None,
    segment: str = "inactive_last5_active",
) -> tuple[list[dict], int, Sequence[ScheduledBroadcast]]:
    """Возвращает страницу неактивных участников с датой последнего RSVP attending."""
    page = max(page, 1)
    page_size = max(page_size, 1)
    offset = (page - 1) * page_size

    attending_stats = (
        select(
            BroadcastRSVP.telegram_id.label("telegram_id"),
            func.count(BroadcastRSVP.id).label("total_attending"),
            func.max(
                func.coalesce(ScheduledBroadcast.rsvp_event_datetime, BroadcastRSVP.created_at)
            ).label("last_attending_at"),
        )
        .join(ScheduledBroadcast, ScheduledBroadcast.id == BroadcastRSVP.broadcast_id)
        .where(BroadcastRSVP.response == RSVPResponse.attending)
        .group_by(BroadcastRSVP.telegram_id)
        .subquery()
    )
    custom_segment_filters = parse_inactive_custom_segment(segment)
    recent_events: Sequence[ScheduledBroadcast] = []
    filters = []
    recent_attending = None

    if custom_segment_filters is not None:
        inactivity_days, missed_events = custom_segment_filters
        if inactivity_days <= 0 and missed_events <= 0:
            return [], 0, recent_events
        if inactivity_days > 0:
            cutoff = datetime.utcnow() - timedelta(days=inactivity_days)
            filters.append(
                or_(
                    attending_stats.c.last_attending_at.is_(None),
                    attending_stats.c.last_attending_at < cutoff,
                )
            )

        if missed_events > 0:
            recent_events = await get_recent_past_rsvp_events(session, limit=missed_events)
            if recent_events:
                event_ids = [event.id for event in recent_events]
                recent_attending = (
                    select(BroadcastRSVP.telegram_id.label("telegram_id"))
                    .where(
                        BroadcastRSVP.response == RSVPResponse.attending,
                        BroadcastRSVP.broadcast_id.in_(event_ids),
                    )
                    .distinct()
                    .subquery()
                )
                filters.append(recent_attending.c.telegram_id.is_(None))
            elif inactivity_days <= 0:
                return [], 0, recent_events
    elif segment == "inactive_last5_active":
        recent_events = await get_recent_past_rsvp_events(session, limit=recent_events_limit)
        if not recent_events:
            return [], 0, recent_events

        event_ids = [event.id for event in recent_events]
        recent_attending = (
            select(BroadcastRSVP.telegram_id.label("telegram_id"))
            .where(
                BroadcastRSVP.response == RSVPResponse.attending,
                BroadcastRSVP.broadcast_id.in_(event_ids),
            )
            .distinct()
            .subquery()
        )
        filters.append(recent_attending.c.telegram_id.is_(None))
    elif segment == "inactive_lt5_active":
        filters.append(func.coalesce(attending_stats.c.total_attending, 0) < 5)
    else:
        raise ValueError(f"Unsupported inactive segment: {segment}")

    if statuses:
        filters.append(User.status.in_(statuses))

    count_stmt = select(func.count(User.id)).select_from(User).outerjoin(
        attending_stats, attending_stats.c.telegram_id == User.telegram_id
    )
    if recent_attending is not None:
        count_stmt = count_stmt.outerjoin(recent_attending, recent_attending.c.telegram_id == User.telegram_id)
    count_stmt = count_stmt.where(*filters)

    total_result = await session.execute(count_stmt)
    total_count = total_result.scalar_one() or 0

    last_attending_title_subquery = (
        select(
            func.coalesce(
                ScheduledBroadcast.rsvp_event_title,
                ScheduledBroadcast.content_text,
                literal("Без названия"),
            )
        )
        .select_from(BroadcastRSVP)
        .join(ScheduledBroadcast, ScheduledBroadcast.id == BroadcastRSVP.broadcast_id)
        .where(
            BroadcastRSVP.telegram_id == User.telegram_id,
            BroadcastRSVP.response == RSVPResponse.attending,
        )
        .order_by(
            func.coalesce(ScheduledBroadcast.rsvp_event_datetime, BroadcastRSVP.created_at).desc()
        )
        .limit(1)
        .scalar_subquery()
    )

    stmt = select(
        User.telegram_id.label("telegram_id"),
        User.username.label("username"),
        User.full_name.label("full_name"),
        User.status.label("status"),
        func.coalesce(attending_stats.c.total_attending, 0).label("total_attending"),
        attending_stats.c.last_attending_at.label("last_attending_at"),
        last_attending_title_subquery.label("last_attending_title"),
    ).select_from(User).outerjoin(attending_stats, attending_stats.c.telegram_id == User.telegram_id)

    if recent_attending is not None:
        stmt = stmt.outerjoin(recent_attending, recent_attending.c.telegram_id == User.telegram_id)

    stmt = stmt.where(*filters)

    if segment == "inactive_lt5_active":
        stmt = stmt.order_by(
            func.coalesce(attending_stats.c.total_attending, 0).asc(),
            attending_stats.c.last_attending_at.desc().nullslast(),
            User.full_name.asc().nullslast(),
            User.username.asc().nullslast(),
            User.telegram_id.asc(),
        )
    else:
        stmt = stmt.order_by(
            attending_stats.c.last_attending_at.desc().nullslast(),
            User.full_name.asc().nullslast(),
            User.username.asc().nullslast(),
            User.telegram_id.asc(),
        )

    stmt = stmt.offset(offset).limit(page_size)

    result = await session.execute(stmt)
    items = [dict(row) for row in result.mappings().all()]
    return items, total_count, recent_events


async def get_users_for_broadcast_segment(session: AsyncSession, segment: str) -> Sequence[User]:
    """Возвращает пользователей для сегмента рассылки."""
    custom_segment_filters = parse_inactive_custom_segment(segment)
    if custom_segment_filters is not None:
        inactivity_days, missed_events = custom_segment_filters
        return await get_users_with_inactive_rsvp_filters(
            session,
            inactivity_days=inactivity_days,
            missed_events=missed_events,
            statuses=[UserStatus.active],
        )
    if segment == "all":
        return await get_all_users(session)
    if segment == "new":
        return await get_users_by_status(session, UserStatus.new)
    if segment == "pending":
        return await get_users_by_status(session, UserStatus.pending)
    if segment == "active":
        return await get_users_by_status(session, UserStatus.active)
    if segment == "expired":
        return await get_users_by_status(session, UserStatus.expired)
    if segment == "inactive_last5_active":
        return await get_users_missing_recent_rsvp_events(
            session,
            limit=5,
            statuses=[UserStatus.active],
        )
    if segment == "inactive_lt5_active":
        return await get_users_with_attending_count_below(
            session,
            threshold=5,
            statuses=[UserStatus.active],
        )
    if segment.startswith("level:"):
        return await get_users_by_level(session, segment.split(":", 1)[1])
    return []


async def count_users_by_status(session: AsyncSession) -> dict[str, int]:
    """
    Подсчитывает количество пользователей по статусам.
    Возвращает словарь: {"new": X, "pending": Y, "active": Z, "expired": W}
    """
    stmt = select(User.status, func.count(User.id)).group_by(User.status)
    result = await session.execute(stmt)
    rows = result.all()
    # Преобразуем в словарь с дефолтами
    counts = {status.value: 0 for status in UserStatus}
    for status, count in rows:
        counts[status.value] = count
    return counts


# =============================================================================
# PAYMENTS: CRUD-операции
# =============================================================================

async def add_payment(
    session: AsyncSession,
    user_id: int,
    amount: float,
    stripe_payment_id: str,
    status: str,
    currency: str = "EUR",
    provider: PaymentProvider = PaymentProvider.stripe,
    external_payment_id: Optional[str] = None,
) -> Payment:
    """Создаёт запись о платеже."""
    payment = Payment(
        user_id=user_id,
        amount=amount,
        currency=currency,
        provider=provider,
        external_payment_id=external_payment_id or stripe_payment_id,
        stripe_payment_id=stripe_payment_id,
        status=status,
    )
    session.add(payment)
    await session.commit()
    await session.refresh(payment)
    return payment


async def create_payment_order(
    session: AsyncSession,
    telegram_id: int,
    provider: PaymentProvider,
    tariff: str,
    email: str,
    external_invoice_id: str,
    amount: Optional[float] = None,
    currency: str = "EUR",
    payment_url: Optional[str] = None,
    external_parent_invoice_id: Optional[str] = None,
    external_customer_id: Optional[str] = None,
) -> PaymentOrder:
    order = PaymentOrder(
        telegram_id=telegram_id,
        provider=provider,
        tariff=tariff,
        email=email,
        external_invoice_id=external_invoice_id,
        external_parent_invoice_id=external_parent_invoice_id,
        external_customer_id=external_customer_id,
        amount=amount,
        currency=currency,
        payment_url=payment_url,
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    return order


async def get_payment_order_by_external_invoice_id(
    session: AsyncSession,
    external_invoice_id: str,
) -> Optional[PaymentOrder]:
    stmt = select(PaymentOrder).where(PaymentOrder.external_invoice_id == external_invoice_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_payment_order_by_id(
    session: AsyncSession,
    payment_order_id: int,
) -> Optional[PaymentOrder]:
    stmt = select(PaymentOrder).where(PaymentOrder.id == payment_order_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_payment_order_by_parent_invoice_id(
    session: AsyncSession,
    external_parent_invoice_id: str,
) -> Optional[PaymentOrder]:
    stmt = select(PaymentOrder).where(PaymentOrder.external_parent_invoice_id == external_parent_invoice_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def update_payment_order_status(
    session: AsyncSession,
    external_invoice_id: str,
    status: PaymentOrderStatus,
    external_parent_invoice_id: Optional[str] = None,
    external_customer_id: Optional[str] = None,
) -> None:
    values: dict = {"status": status}
    if external_parent_invoice_id is not None:
        values["external_parent_invoice_id"] = external_parent_invoice_id
    if external_customer_id is not None:
        values["external_customer_id"] = external_customer_id
    stmt = (
        update(PaymentOrder)
        .where(PaymentOrder.external_invoice_id == external_invoice_id)
        .values(**values)
    )
    await session.execute(stmt)
    await session.commit()


async def get_recent_pending_lavatop_orders(
    session: AsyncSession,
    minutes: int = 10080,
    limit: int = 50,
) -> Sequence[PaymentOrder]:
    cutoff = datetime.utcnow() - timedelta(minutes=minutes)
    stmt = (
        select(PaymentOrder)
        .where(
            PaymentOrder.provider == PaymentProvider.lavatop,
            PaymentOrder.status == PaymentOrderStatus.created,
            PaymentOrder.created_at >= cutoff,
        )
        .order_by(PaymentOrder.created_at.asc(), PaymentOrder.id.asc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_recent_pending_payment_orders(
    session: AsyncSession,
    telegram_id: int,
    provider: PaymentProvider,
    minutes: int = 45,
    limit: int = 10,
) -> Sequence[PaymentOrder]:
    cutoff = datetime.utcnow() - timedelta(minutes=minutes)
    stmt = (
        select(PaymentOrder)
        .where(
            PaymentOrder.telegram_id == telegram_id,
            PaymentOrder.provider == provider,
            PaymentOrder.status == PaymentOrderStatus.created,
            PaymentOrder.created_at >= cutoff,
        )
        .order_by(PaymentOrder.created_at.desc(), PaymentOrder.id.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_user_payments(session: AsyncSession, user_id: int) -> Sequence[Payment]:
    """Возвращает все платежи пользователя."""
    stmt = select(Payment).where(Payment.user_id == user_id).order_by(Payment.created_at.desc())
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_user_ltv(session: AsyncSession, user_id: int) -> float:
    """
    Рассчитывает LTV (Lifetime Value) пользователя.
    Сумма всех успешных платежей.
    """
    stmt = select(func.sum(Payment.amount)).where(
        Payment.user_id == user_id,
        Payment.status == "success",
    )
    result = await session.execute(stmt)
    total = result.scalar_one_or_none()
    return float(total) if total else 0.0


# =============================================================================
# SETTINGS: ключ-значение настройки (расписание и др.)
# =============================================================================

# Дефолтный текст расписания
DEFAULT_SCHEDULE = """📅 Расписание на эти выходные

Вы выбрали — мы подготовили!

🇪🇸 Суббота, 14:00 (Мадрид)
Тема: 🎬 "La Casa de Papel" — обсуждаем 1 сезон.
Словарь: Скинули в закрытый канал.

🥂 Воскресенье, 19:00 (Мадрид)
Тема: Игра "Alias" на испанском.

👉 /pay — Успеть на эфир"""


async def get_setting(session: AsyncSession, key: str, default: Optional[str] = None) -> Optional[str]:
    """Получает значение настройки по ключу."""
    stmt = select(Setting).where(Setting.key == key)
    result = await session.execute(stmt)
    setting = result.scalar_one_or_none()
    return setting.value if setting else default


async def set_setting(session: AsyncSession, key: str, value: str) -> None:
    """Устанавливает значение настройки (создаёт или обновляет)."""
    stmt = select(Setting).where(Setting.key == key)
    result = await session.execute(stmt)
    setting = result.scalar_one_or_none()
    
    if setting:
        setting.value = value
    else:
        setting = Setting(key=key, value=value)
        session.add(setting)
    
    await session.commit()


async def get_schedule(session: AsyncSession) -> str:
    """Получает текущее расписание."""
    return await get_setting(session, "schedule", DEFAULT_SCHEDULE) or DEFAULT_SCHEDULE


async def set_schedule(session: AsyncSession, text: str) -> None:
    """Устанавливает новое расписание."""
    await set_setting(session, "schedule", text)


# =============================================================================
# SCHEDULED BROADCASTS: CRUD-операции
# =============================================================================

async def create_scheduled_broadcast(
    session: AsyncSession,
    segment: str,
    content_type: str,
    scheduled_at: datetime,
    content_text: Optional[str] = None,
    content_file_id: Optional[str] = None,
    has_rsvp: bool = False,
    rsvp_event_title: Optional[str] = None,
    rsvp_event_datetime: Optional[datetime] = None,
    zoom_link: Optional[str] = None,
) -> ScheduledBroadcast:
    """Создаёт запланированную рассылку."""
    broadcast = ScheduledBroadcast(
        segment=segment,
        content_type=content_type,
        content_text=content_text,
        content_file_id=content_file_id,
        scheduled_at=scheduled_at,
        status=BroadcastStatus.pending,
        has_rsvp=has_rsvp,
        rsvp_event_title=rsvp_event_title,
        rsvp_event_datetime=rsvp_event_datetime,
        zoom_link=zoom_link,
    )
    session.add(broadcast)
    await session.commit()
    await session.refresh(broadcast)
    return broadcast


async def get_scheduled_broadcast(session: AsyncSession, broadcast_id: int) -> Optional[ScheduledBroadcast]:
    """Получает запланированную рассылку по ID."""
    stmt = select(ScheduledBroadcast).where(ScheduledBroadcast.id == broadcast_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_pending_broadcasts(session: AsyncSession) -> Sequence[ScheduledBroadcast]:
    """Возвращает все рассылки со статусом pending, время отправки которых наступило."""
    import pytz
    madrid_tz = pytz.timezone("Europe/Madrid")
    now = datetime.now(madrid_tz).replace(tzinfo=None)
    stmt = (
        select(ScheduledBroadcast)
        .where(
            ScheduledBroadcast.status == BroadcastStatus.pending,
            ScheduledBroadcast.scheduled_at <= now,
        )
        .order_by(ScheduledBroadcast.scheduled_at.asc())
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_all_scheduled_broadcasts(session: AsyncSession, limit: int = 20) -> Sequence[ScheduledBroadcast]:
    """Возвращает последние рассылки (для истории)."""
    stmt = (
        select(ScheduledBroadcast)
        .order_by(ScheduledBroadcast.scheduled_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def mark_broadcast_sent(
    session: AsyncSession,
    broadcast_id: int,
    sent_count: int,
    fail_count: int,
) -> None:
    """Помечает рассылку как отправленную."""
    stmt = (
        update(ScheduledBroadcast)
        .where(ScheduledBroadcast.id == broadcast_id)
        .values(
            status=BroadcastStatus.sent,
            sent_count=sent_count,
            fail_count=fail_count,
        )
    )
    await session.execute(stmt)
    await session.commit()


async def replace_broadcast_delivery_logs(
    session: AsyncSession,
    broadcast_id: int,
    logs: Sequence[dict[str, object]],
) -> None:
    await session.execute(
        delete(BroadcastDeliveryLog).where(BroadcastDeliveryLog.broadcast_id == broadcast_id)
    )

    session.add_all(
        [
            BroadcastDeliveryLog(
                broadcast_id=broadcast_id,
                telegram_id=int(log["telegram_id"]),
                username=log.get("username") if isinstance(log.get("username"), str) else None,
                full_name=log.get("full_name") if isinstance(log.get("full_name"), str) else None,
                delivery_status=str(log["delivery_status"]),
                error_message=log.get("error_message") if isinstance(log.get("error_message"), str) else None,
            )
            for log in logs
        ]
    )
    await session.commit()


async def cancel_broadcast(session: AsyncSession, broadcast_id: int) -> None:
    """Отменяет запланированную рассылку."""
    stmt = (
        update(ScheduledBroadcast)
        .where(ScheduledBroadcast.id == broadcast_id)
        .values(status=BroadcastStatus.cancelled)
    )
    await session.execute(stmt)
    await session.commit()


# =============================================================================
# BROADCAST RSVP: CRUD-операции
# =============================================================================

async def add_rsvp(
    session: AsyncSession,
    broadcast_id: int,
    telegram_id: int,
    response: RSVPResponse,
) -> BroadcastRSVP:
    """Добавляет или обновляет RSVP-ответ пользователя."""
    stmt = select(BroadcastRSVP).where(
        BroadcastRSVP.broadcast_id == broadcast_id,
        BroadcastRSVP.telegram_id == telegram_id,
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        existing.response = response
        await session.commit()
        return existing

    rsvp = BroadcastRSVP(
        broadcast_id=broadcast_id,
        telegram_id=telegram_id,
        response=response,
    )
    session.add(rsvp)
    await session.commit()
    await session.refresh(rsvp)
    return rsvp


async def count_rsvp_attending(session: AsyncSession, broadcast_id: int) -> int:
    """Считает количество пользователей, ответивших 'Я буду'."""
    stmt = select(func.count(BroadcastRSVP.id)).where(
        BroadcastRSVP.broadcast_id == broadcast_id,
        BroadcastRSVP.response == RSVPResponse.attending,
    )
    result = await session.execute(stmt)
    return result.scalar_one() or 0


async def count_rsvp_declined(session: AsyncSession, broadcast_id: int) -> int:
    """Считает количество пользователей, ответивших 'Не смогу'."""
    stmt = select(func.count(BroadcastRSVP.id)).where(
        BroadcastRSVP.broadcast_id == broadcast_id,
        BroadcastRSVP.response == RSVPResponse.declined,
    )
    result = await session.execute(stmt)
    return result.scalar_one() or 0


async def get_rsvp_attending_users(session: AsyncSession, broadcast_id: int) -> list[int]:
    """Возвращает список telegram_id пользователей, ответивших 'Я буду'."""
    stmt = select(BroadcastRSVP.telegram_id).where(
        BroadcastRSVP.broadcast_id == broadcast_id,
        BroadcastRSVP.response == RSVPResponse.attending,
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_broadcasts_needing_15min_reminder(session: AsyncSession) -> Sequence[ScheduledBroadcast]:
    """Возвращает рассылки, для которых нужно отправить напоминание за 15 минут."""
    import pytz
    from datetime import timedelta
    madrid_tz = pytz.timezone("Europe/Madrid")
    now = datetime.now(madrid_tz).replace(tzinfo=None)
    reminder_window_start = now + timedelta(minutes=14)
    reminder_window_end = now + timedelta(minutes=16)

    stmt = (
        select(ScheduledBroadcast)
        .where(
            ScheduledBroadcast.has_rsvp == True,
            ScheduledBroadcast.rsvp_event_datetime.isnot(None),
            ScheduledBroadcast.reminder_15min_sent == False,
            ScheduledBroadcast.status != BroadcastStatus.cancelled,
            ScheduledBroadcast.rsvp_event_datetime >= reminder_window_start,
            ScheduledBroadcast.rsvp_event_datetime <= reminder_window_end,
        )
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_broadcasts_needing_24h_reminder(session: AsyncSession) -> Sequence[ScheduledBroadcast]:
    """
    Возвращает рассылки, для которых нужно отправить напоминание примерно за 24 часа.
    Используем окно +/- 30 минут, чтобы не терять событие из-за кратковременного лага scheduler.
    """
    import pytz

    madrid_tz = pytz.timezone("Europe/Madrid")
    now = datetime.now(madrid_tz).replace(tzinfo=None)
    reminder_window_start = now + timedelta(hours=23, minutes=30)
    reminder_window_end = now + timedelta(hours=24, minutes=30)

    stmt = (
        select(ScheduledBroadcast)
        .where(
            ScheduledBroadcast.has_rsvp == True,
            ScheduledBroadcast.rsvp_event_datetime.isnot(None),
            ScheduledBroadcast.reminder_24h_sent == False,
            ScheduledBroadcast.status != BroadcastStatus.cancelled,
            ScheduledBroadcast.rsvp_event_datetime >= reminder_window_start,
            ScheduledBroadcast.rsvp_event_datetime <= reminder_window_end,
        )
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_broadcasts_needing_5min_reminder(session: AsyncSession) -> Sequence[ScheduledBroadcast]:
    """Возвращает рассылки, для которых нужно отправить напоминание за 5 минут."""
    import pytz
    from datetime import timedelta
    madrid_tz = pytz.timezone("Europe/Madrid")
    now = datetime.now(madrid_tz).replace(tzinfo=None)
    reminder_window_start = now + timedelta(minutes=4)
    reminder_window_end = now + timedelta(minutes=6)

    stmt = (
        select(ScheduledBroadcast)
        .where(
            ScheduledBroadcast.has_rsvp == True,
            ScheduledBroadcast.rsvp_event_datetime.isnot(None),
            ScheduledBroadcast.reminder_5min_sent == False,
            ScheduledBroadcast.status != BroadcastStatus.cancelled,
            ScheduledBroadcast.rsvp_event_datetime >= reminder_window_start,
            ScheduledBroadcast.rsvp_event_datetime <= reminder_window_end,
        )
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def mark_reminder_15min_sent(session: AsyncSession, broadcast_id: int) -> None:
    """Отмечает, что напоминание за 15 минут отправлено."""
    stmt = (
        update(ScheduledBroadcast)
        .where(ScheduledBroadcast.id == broadcast_id)
        .values(reminder_15min_sent=True)
    )
    await session.execute(stmt)
    await session.commit()


async def mark_reminder_24h_sent(session: AsyncSession, broadcast_id: int) -> None:
    """Отмечает, что напоминание за 24 часа отправлено."""
    stmt = (
        update(ScheduledBroadcast)
        .where(ScheduledBroadcast.id == broadcast_id)
        .values(reminder_24h_sent=True)
    )
    await session.execute(stmt)
    await session.commit()


async def mark_reminder_5min_sent(session: AsyncSession, broadcast_id: int) -> None:
    """Отмечает, что напоминание за 5 минут отправлено."""
    stmt = (
        update(ScheduledBroadcast)
        .where(ScheduledBroadcast.id == broadcast_id)
        .values(reminder_5min_sent=True)
    )
    await session.execute(stmt)
    await session.commit()


async def get_upcoming_events(session: AsyncSession, limit: int = 100) -> Sequence[ScheduledBroadcast]:
    """Возвращает будущие RSVP-события для отображения в расписании."""
    import pytz
    madrid_tz = pytz.timezone("Europe/Madrid")
    now = datetime.now(madrid_tz).replace(tzinfo=None)

    stmt = (
        select(ScheduledBroadcast)
        .where(
            ScheduledBroadcast.has_rsvp == True,
            ScheduledBroadcast.rsvp_event_datetime.isnot(None),
            ScheduledBroadcast.rsvp_event_datetime > now,
            ScheduledBroadcast.status != BroadcastStatus.cancelled,
        )
        .order_by(ScheduledBroadcast.rsvp_event_datetime.asc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_user_rsvp_statuses(
    session: AsyncSession, telegram_id: int, broadcast_ids: list[int]
) -> dict[int, str]:
    """Возвращает статусы RSVP пользователя для списка событий."""
    if not broadcast_ids:
        return {}
    stmt = select(BroadcastRSVP.broadcast_id, BroadcastRSVP.response).where(
        BroadcastRSVP.telegram_id == telegram_id,
        BroadcastRSVP.broadcast_id.in_(broadcast_ids),
    )
    result = await session.execute(stmt)
    return {row[0]: row[1].value for row in result.all()}


# =============================================================================
# EVENT FEEDBACK: CRUD-операции для опросов после встреч
# =============================================================================

EVENT_DURATION_MINUTES = 90  # Длительность встречи в минутах
FEEDBACK_DELAY_MINUTES = 20   # Задержка перед отправкой опроса


async def get_or_create_event_feedback(
    session: AsyncSession,
    broadcast_id: int,
    telegram_id: int,
) -> EventFeedback:
    """
    Получает или создаёт запись feedback для пользователя по конкретному событию.
    """
    stmt = select(EventFeedback).where(
        EventFeedback.broadcast_id == broadcast_id,
        EventFeedback.telegram_id == telegram_id,
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        return existing

    feedback = EventFeedback(
        broadcast_id=broadcast_id,
        telegram_id=telegram_id,
    )
    session.add(feedback)
    await session.commit()
    await session.refresh(feedback)
    return feedback


async def update_feedback_rating(
    session: AsyncSession,
    broadcast_id: int,
    telegram_id: int,
    rating: int,
) -> EventFeedback:
    """Сохраняет оценку (1-5 звёзд)."""
    feedback = await get_or_create_event_feedback(session, broadcast_id, telegram_id)
    feedback.rating = rating
    await session.commit()
    return feedback


async def update_feedback_level_comfort(
    session: AsyncSession,
    broadcast_id: int,
    telegram_id: int,
    level_comfort: LevelComfort,
) -> EventFeedback:
    """Сохраняет ответ о комфортности уровня."""
    feedback = await get_or_create_event_feedback(session, broadcast_id, telegram_id)
    feedback.level_comfort = level_comfort
    await session.commit()
    return feedback


async def update_feedback_will_attend(
    session: AsyncSession,
    broadcast_id: int,
    telegram_id: int,
    will_attend: WillAttendNext,
    awaiting_improvement_comment: bool = False,
) -> EventFeedback:
    """Сохраняет ответ о планах на следующую встречу."""
    feedback = await get_or_create_event_feedback(session, broadcast_id, telegram_id)
    feedback.will_attend_next = will_attend
    feedback.awaiting_improvement_comment = awaiting_improvement_comment
    await session.commit()
    return feedback


async def update_feedback_improvement_comment(
    session: AsyncSession,
    broadcast_id: int,
    telegram_id: int,
    improvement_comment: str,
) -> EventFeedback:
    feedback = await get_or_create_event_feedback(session, broadcast_id, telegram_id)
    feedback.improvement_comment = improvement_comment
    feedback.awaiting_improvement_comment = False
    await session.commit()
    return feedback


async def get_event_feedback(
    session: AsyncSession,
    broadcast_id: int,
    telegram_id: int,
) -> Optional[EventFeedback]:
    """Получает feedback пользователя по событию."""
    stmt = select(EventFeedback).where(
        EventFeedback.broadcast_id == broadcast_id,
        EventFeedback.telegram_id == telegram_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_broadcasts_needing_feedback(session: AsyncSession) -> Sequence[ScheduledBroadcast]:
    """
    Возвращает события, для которых нужно отправить опрос.
    Условия:
    - has_rsvp = True
    - rsvp_event_datetime + 110 минут <= now (90 мин встреча + 20 мин задержка)
    - feedback_sent = False
    """
    import pytz
    madrid_tz = pytz.timezone("Europe/Madrid")
    now = datetime.now(madrid_tz).replace(tzinfo=None)
    
    total_delay = timedelta(minutes=EVENT_DURATION_MINUTES + FEEDBACK_DELAY_MINUTES)
    cutoff = now - total_delay

    stmt = (
        select(ScheduledBroadcast)
        .where(
            ScheduledBroadcast.has_rsvp == True,
            ScheduledBroadcast.rsvp_event_datetime.isnot(None),
            ScheduledBroadcast.feedback_sent == False,
            ScheduledBroadcast.rsvp_event_datetime <= cutoff,
        )
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def mark_feedback_sent(session: AsyncSession, broadcast_id: int) -> None:
    """Отмечает, что опрос после встречи отправлен."""
    stmt = (
        update(ScheduledBroadcast)
        .where(ScheduledBroadcast.id == broadcast_id)
        .values(feedback_sent=True)
    )
    await session.execute(stmt)
    await session.commit()


async def has_recent_rsvp(session: AsyncSession, telegram_id: int, days: int = 2) -> bool:
    """
    Проверяет, записался ли пользователь на встречу за последние N дней.
    Используется для follow-up: если записался — не отправлять напоминание.
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    stmt = select(BroadcastRSVP.id).where(
        BroadcastRSVP.telegram_id == telegram_id,
        BroadcastRSVP.response == RSVPResponse.attending,
        BroadcastRSVP.created_at > cutoff,
    ).limit(1)
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def get_feedbacks_for_followup(
    session: AsyncSession,
    days_since_feedback: int = 1,
) -> Sequence[EventFeedback]:
    """
    Возвращает feedbacks для отправки follow-up сообщений.
    Условия:
    - Опрос заполнен (rating есть)
    - followup_sent_at = None
    - Прошло нужное количество дней
    """
    cutoff = datetime.utcnow() - timedelta(days=days_since_feedback)
    
    stmt = select(EventFeedback).where(
        EventFeedback.rating.isnot(None),
        EventFeedback.followup_sent_at.is_(None),
        EventFeedback.created_at < cutoff,
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_feedbacks_not_coming_for_followup(
    session: AsyncSession,
    days_since_feedback: int = 7,
) -> Sequence[EventFeedback]:
    """
    Возвращает feedbacks с ответом "не приду" для отправки напоминания через неделю.
    """
    cutoff = datetime.utcnow() - timedelta(days=days_since_feedback)
    
    stmt = select(EventFeedback).where(
        EventFeedback.will_attend_next == WillAttendNext.no,
        EventFeedback.followup_sent_at.is_(None),
        EventFeedback.created_at < cutoff,
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def mark_followup_sent(session: AsyncSession, feedback_id: int) -> None:
    """Отмечает, что follow-up сообщение отправлено."""
    stmt = (
        update(EventFeedback)
        .where(EventFeedback.id == feedback_id)
        .values(followup_sent_at=datetime.utcnow())
    )
    await session.execute(stmt)
    await session.commit()


async def get_feedbacks_not_synced(session: AsyncSession) -> Sequence[EventFeedback]:
    """
    Возвращает завершённые feedbacks, которые ещё не синхронизированы в Google Sheets.
    Условие: will_attend_next заполнен (опрос завершён) и synced_to_sheets = False.
    """
    stmt = select(EventFeedback).where(
        EventFeedback.will_attend_next.isnot(None),
        EventFeedback.synced_to_sheets == False,
        EventFeedback.awaiting_improvement_comment == False,
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def mark_feedback_synced(session: AsyncSession, feedback_id: int) -> None:
    """Отмечает, что feedback синхронизирован в Google Sheets."""
    stmt = (
        update(EventFeedback)
        .where(EventFeedback.id == feedback_id)
        .values(synced_to_sheets=True)
    )
    await session.execute(stmt)
    await session.commit()


async def get_feedback_with_details(
    session: AsyncSession,
    feedback_id: int,
) -> tuple:
    """
    Возвращает feedback с данными пользователя и встречи для синхронизации.
    """
    from sqlalchemy.orm import selectinload
    
    stmt = select(EventFeedback).where(
        EventFeedback.id == feedback_id
    ).options(selectinload(EventFeedback.broadcast))
    
    result = await session.execute(stmt)
    feedback = result.scalar_one_or_none()
    
    if not feedback:
        return None, None, None
    
    user = await get_user_by_telegram_id(session, feedback.telegram_id)
    return feedback, user, feedback.broadcast


async def get_users_inactive_for_days(
    session: AsyncSession,
    days: int = 7,
) -> Sequence[User]:
    """
    Возвращает активных пользователей, которые не записывались на встречи больше N дней.
    Используется для отправки "Мы давно вас не видели".
    """
    import pytz
    from sqlalchemy import and_, exists
    
    madrid_tz = pytz.timezone("Europe/Madrid")
    now = datetime.now(madrid_tz).replace(tzinfo=None)
    cutoff = now - timedelta(days=days)
    
    recent_rsvp_subquery = (
        select(BroadcastRSVP.telegram_id)
        .where(
            BroadcastRSVP.response == RSVPResponse.attending,
            BroadcastRSVP.created_at > cutoff,
        )
    )
    
    stmt = select(User).where(
        User.status == UserStatus.active,
        ~User.telegram_id.in_(recent_rsvp_subquery),
    )
    result = await session.execute(stmt)
    return result.scalars().all()


# =============================================================================
# PENDING EVENT INVITATIONS: CRUD-операции
# =============================================================================

async def create_pending_invitation(
    session: AsyncSession,
    telegram_id: int,
    broadcast_id: int,
    send_at: datetime,
) -> Optional["PendingEventInvitation"]:
    """
    Создаёт отложенное приглашение на событие.
    Возвращает None если такая запись уже существует (защита от дубликатов).
    """
    from database.models import PendingEventInvitation
    from sqlalchemy.exc import IntegrityError
    
    # Проверяем существование записи
    stmt = select(PendingEventInvitation).where(
        PendingEventInvitation.telegram_id == telegram_id,
        PendingEventInvitation.broadcast_id == broadcast_id,
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()
    
    if existing:
        logger.info(f"Отложенное приглашение уже существует: tg_id={telegram_id}, broadcast_id={broadcast_id}")
        return None
    
    # Создаём новую запись
    invitation = PendingEventInvitation(
        telegram_id=telegram_id,
        broadcast_id=broadcast_id,
        send_at=send_at,
        sent=False,
    )
    session.add(invitation)
    
    try:
        await session.commit()
        await session.refresh(invitation)
        logger.info(f"Создано отложенное приглашение: tg_id={telegram_id}, broadcast_id={broadcast_id}, send_at={send_at}")
        return invitation
    except IntegrityError:
        await session.rollback()
        logger.warning(f"Дубликат отложенного приглашения (race condition): tg_id={telegram_id}, broadcast_id={broadcast_id}")
        return None


async def get_pending_invitations_to_send(session: AsyncSession) -> Sequence["PendingEventInvitation"]:
    """
    Возвращает отложенные приглашения, которые нужно отправить сейчас.
    Критерии: send_at <= now AND sent = False
    """
    from database.models import PendingEventInvitation
    import pytz
    
    madrid_tz = pytz.timezone("Europe/Madrid")
    now = datetime.now(madrid_tz).replace(tzinfo=None)
    
    stmt = (
        select(PendingEventInvitation)
        .where(
            PendingEventInvitation.send_at <= now,
            PendingEventInvitation.sent == False,
        )
        .order_by(PendingEventInvitation.send_at.asc())
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def mark_invitation_sent(session: AsyncSession, invitation_id: int) -> None:
    """Отмечает отложенное приглашение как отправленное."""
    from database.models import PendingEventInvitation
    
    stmt = (
        update(PendingEventInvitation)
        .where(PendingEventInvitation.id == invitation_id)
        .values(sent=True)
    )
    await session.execute(stmt)
    await session.commit()


async def cleanup_old_pending_invitations(session: AsyncSession, days: int = 7) -> int:
    """
    Удаляет старые отправленные приглашения.
    Возвращает количество удалённых записей.
    """
    from database.models import PendingEventInvitation
    import pytz
    
    madrid_tz = pytz.timezone("Europe/Madrid")
    now = datetime.now(madrid_tz).replace(tzinfo=None)
    cutoff_date = now - timedelta(days=days)
    
    stmt = delete(PendingEventInvitation).where(
        PendingEventInvitation.sent == True,
        PendingEventInvitation.created_at < cutoff_date,
    )
    result = await session.execute(stmt)
    await session.commit()
    
    deleted_count = result.rowcount
    logger.info(f"Удалено {deleted_count} старых отложенных приглашений (>{days} дней)")
    return deleted_count


async def get_user_rsvp(
    session: AsyncSession,
    telegram_id: int,
    broadcast_id: int,
) -> Optional["BroadcastRSVP"]:
    """Возвращает RSVP-ответ пользователя на событие (если есть)."""
    stmt = select(BroadcastRSVP).where(
        BroadcastRSVP.telegram_id == telegram_id,
        BroadcastRSVP.broadcast_id == broadcast_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


# =============================================================================
# UNAUTHORIZED MEMBERS: Управление неавторизованными пользователями
# =============================================================================

async def add_unauthorized_member(
    session: AsyncSession,
    telegram_id: int,
    full_name: Optional[str] = None,
    username: Optional[str] = None,
) -> None:
    """
    Добавляет пользователя в список неавторизованных.
    Вызывается когда пользователь присоединяется к каналу, но отсутствует в БД.
    """
    from database.models import UnauthorizedMember
    
    # Проверяем, нет ли уже такой записи
    existing_stmt = select(UnauthorizedMember).where(
        UnauthorizedMember.telegram_id == telegram_id
    )
    existing = await session.execute(existing_stmt)
    if existing.scalar_one_or_none():
        return  # Уже есть в списке
    
    unauthorized = UnauthorizedMember(
        telegram_id=telegram_id,
        full_name=full_name,
        username=username,
    )
    session.add(unauthorized)
    await session.commit()


async def get_unauthorized_members_to_kick(
    session: AsyncSession,
    minutes: int = 15,
) -> Sequence["UnauthorizedMember"]:
    """
    Возвращает неавторизованных пользователей, которые присоединились более {minutes} минут назад.
    Используется планировщиком для автоматического кика.
    """
    from database.models import UnauthorizedMember
    
    cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)
    stmt = select(UnauthorizedMember).where(
        UnauthorizedMember.joined_at < cutoff_time
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def remove_unauthorized_member(
    session: AsyncSession,
    telegram_id: int,
) -> None:
    """
    Удаляет пользователя из списка неавторизованных.
    Вызывается после кика или если пользователь оплатил подписку.
    """
    from database.models import UnauthorizedMember
    
    stmt = delete(UnauthorizedMember).where(
        UnauthorizedMember.telegram_id == telegram_id
    )
    await session.execute(stmt)
    await session.commit()
