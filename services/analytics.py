import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional, Sequence

import gspread
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import BroadcastRSVP, EventFeedback, Payment, RSVPResponse
from database.requests import (
    analytics_event_exists,
    create_analytics_event,
    get_latest_analytics_event_by_name,
    get_user_analytics_events,
    get_user_analytics_profile,
    get_user_by_telegram_id,
    upsert_user_analytics_profile,
)
from services.google_sheets import add_funnel_event_to_sheets, upsert_user_in_crm
from utils.config import Config

logger = logging.getLogger(__name__)

ENGAGEMENT_AFTER_INTRO = {
    "state_picker_opened",
    "state_selected",
    "branch_offer_sent",
    "more_info_opened",
    "schedule_opened",
    "payment_flow_entered",
    "tariff_selected",
    "checkout_redirect_opened",
    "payment_succeeded",
}

ENGAGEMENT_AFTER_OFFER = {
    "more_info_opened",
    "schedule_opened",
    "payment_flow_entered",
    "tariff_selected",
    "checkout_redirect_opened",
    "payment_succeeded",
}


def _normalize_provider(provider: Optional[Any]) -> Optional[str]:
    if provider is None:
        return None
    return getattr(provider, "value", str(provider))


def _normalize_metadata(metadata: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not metadata:
        return {}
    return {
        key: value
        for key, value in metadata.items()
        if value is not None and value != ""
    }


def _metadata_to_details(
    *,
    onboarding_version: str,
    step_key: Optional[str],
    source: Optional[str],
    provider: Optional[str],
    metadata: dict[str, Any],
) -> str:
    payload: dict[str, Any] = {"onboarding_version": onboarding_version}
    if step_key:
        payload["step_key"] = step_key
    if source:
        payload["source"] = source
    if provider:
        payload["provider"] = provider
    payload.update(metadata)
    details: list[str] = []
    for key in sorted(payload.keys()):
        value = payload[key]
        if isinstance(value, (dict, list)):
            compact = json.dumps(value, ensure_ascii=False, sort_keys=True)
        else:
            compact = str(value)
        details.append(f"{key}={compact}")
    return ", ".join(details)


def _find_latest_event(events: Sequence, *event_names: str):
    names = set(event_names)
    for event in reversed(events):
        if event.event_name in names:
            return event
    return None


def _has_later_event(
    events: Sequence,
    *,
    after_event,
    event_names: set[str],
) -> bool:
    if after_event is None:
        return False
    for event in events:
        if event.created_at <= after_event.created_at:
            continue
        if event.event_name in event_names:
            return True
    return False


def _extract_state_choice(events: Sequence) -> Optional[str]:
    state_event = _find_latest_event(events, "state_selected")
    if not state_event:
        return None
    state_value = (state_event.metadata_json or {}).get("state")
    return str(state_value) if state_value is not None else None


def _compute_stuck_bucket(
    *,
    status: Optional[str],
    events: Sequence,
    first_paid_at: Optional[datetime],
    first_rsvp_at: Optional[datetime],
    first_feedback_at: Optional[datetime],
    feedback_prompt_at: Optional[datetime],
) -> Optional[str]:
    now = datetime.utcnow()

    if first_paid_at and not first_rsvp_at and first_paid_at <= now - timedelta(hours=72):
        return "paid_no_rsvp_72h"

    if feedback_prompt_at and feedback_prompt_at <= now - timedelta(hours=24):
        if first_feedback_at is None or first_feedback_at < feedback_prompt_at:
            return "attended_no_feedback_24h_after_prompt"

    checkout_event = _find_latest_event(events, "checkout_redirect_opened")
    payment_succeeded_event = _find_latest_event(events, "payment_succeeded")
    if checkout_event and (payment_succeeded_event is None or payment_succeeded_event.created_at < checkout_event.created_at):
        age = now - checkout_event.created_at
        if age >= timedelta(hours=48):
            return "checkout_no_payment_48h"
        if age >= timedelta(hours=24):
            return "checkout_no_payment_24h"
        if age >= timedelta(hours=2):
            return "checkout_no_payment_2h"

    schedule_event = _find_latest_event(events, "schedule_opened")
    if schedule_event and not _has_later_event(events, after_event=schedule_event, event_names={"payment_succeeded"}):
        if now - schedule_event.created_at >= timedelta(hours=24):
            return "schedule_no_payment_24h"

    offer_event = _find_latest_event(events, "branch_offer_sent")
    if offer_event and not _has_later_event(events, after_event=offer_event, event_names=ENGAGEMENT_AFTER_OFFER):
        if now - offer_event.created_at >= timedelta(hours=24):
            return "offer_no_next_step_24h"

    state_picker_event = _find_latest_event(events, "state_picker_opened")
    if state_picker_event and not _has_later_event(events, after_event=state_picker_event, event_names={"state_selected"}):
        if now - state_picker_event.created_at >= timedelta(minutes=10):
            return "state_not_selected_10m"

    intro_event = _find_latest_event(events, "intro_sent")
    if intro_event and not _has_later_event(events, after_event=intro_event, event_names=ENGAGEMENT_AFTER_INTRO):
        if now - intro_event.created_at >= timedelta(minutes=10):
            return "intro_no_action_10m"

    return None


async def refresh_user_analytics_profile(
    session: AsyncSession,
    telegram_id: int,
):
    user = await get_user_by_telegram_id(session, telegram_id)
    events = list(await get_user_analytics_events(session, telegram_id))
    latest_event = events[-1] if events else None

    onboarding_started_event = next((event for event in events if event.event_name == "onboarding_started"), None)
    state_choice = _extract_state_choice(events)

    payment_provider = _normalize_provider(getattr(user, "payment_provider", None))
    if payment_provider is None:
        payment_event = _find_latest_event(events, "payment_succeeded")
        payment_provider = payment_event.provider if payment_event else None

    first_paid_at = None
    first_rsvp_at = None
    first_feedback_at = None

    if user is not None:
        payment_stmt = select(func.min(Payment.created_at)).where(Payment.user_id == user.id)
        first_paid_at = (await session.execute(payment_stmt)).scalar_one_or_none()

    rsvp_stmt = select(func.min(BroadcastRSVP.created_at)).where(
        BroadcastRSVP.telegram_id == telegram_id,
        BroadcastRSVP.response == RSVPResponse.attending,
    )
    first_rsvp_at = (await session.execute(rsvp_stmt)).scalar_one_or_none()

    first_feedback_event = await get_latest_analytics_event_by_name(
        session,
        telegram_id=telegram_id,
        event_name="first_feedback_completed",
    )
    if first_feedback_event is not None:
        first_feedback_at = first_feedback_event.created_at
    else:
        feedback_stmt = select(func.min(EventFeedback.created_at)).where(
            EventFeedback.telegram_id == telegram_id,
            EventFeedback.will_attend_next.is_not(None),
        )
        first_feedback_at = (await session.execute(feedback_stmt)).scalar_one_or_none()

    feedback_prompt_event = _find_latest_event(events, "feedback_prompt_sent")
    feedback_prompt_at = feedback_prompt_event.created_at if feedback_prompt_event else None

    stuck_bucket = _compute_stuck_bucket(
        status=getattr(user.status, "value", None) if user else None,
        events=events,
        first_paid_at=first_paid_at,
        first_rsvp_at=first_rsvp_at,
        first_feedback_at=first_feedback_at,
        feedback_prompt_at=feedback_prompt_at,
    )

    profile = await upsert_user_analytics_profile(
        session,
        telegram_id=telegram_id,
        user_id=user.id if user else None,
        onboarding_version=onboarding_started_event.onboarding_version if onboarding_started_event else None,
        entry_source=onboarding_started_event.source if onboarding_started_event else None,
        last_event=latest_event.event_name if latest_event else None,
        last_event_at=latest_event.created_at if latest_event else None,
        state_choice=state_choice,
        payment_provider=payment_provider,
        first_paid_at=first_paid_at,
        first_rsvp_at=first_rsvp_at,
        first_feedback_at=first_feedback_at,
        feedback_prompt_at=feedback_prompt_at,
        stuck_bucket=stuck_bucket,
    )
    return profile


async def track_event(
    session: AsyncSession,
    *,
    telegram_id: int,
    journey: str,
    onboarding_version: str,
    event_name: str,
    step_key: Optional[str] = None,
    source: Optional[str] = None,
    provider: Optional[Any] = None,
    metadata: Optional[dict[str, Any]] = None,
    once_per_user: bool = False,
    config: Optional[Config] = None,
    gspread_client: Optional[gspread.Client] = None,
):
    normalized_provider = _normalize_provider(provider)
    normalized_metadata = _normalize_metadata(metadata)

    if once_per_user:
        already_exists = await analytics_event_exists(
            session,
            telegram_id=telegram_id,
            event_name=event_name,
        )
        if already_exists:
            return await get_user_analytics_profile(session, telegram_id)

    await create_analytics_event(
        session,
        telegram_id=telegram_id,
        journey=journey,
        onboarding_version=onboarding_version,
        event_name=event_name,
        step_key=step_key,
        source=source,
        provider=normalized_provider,
        metadata_json=normalized_metadata,
    )

    profile = await refresh_user_analytics_profile(session, telegram_id)

    if config is None or gspread_client is None or not config.google_sheet_id:
        return profile

    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        return profile

    from database.requests import get_user_ltv

    ltv = await get_user_ltv(session, user.id)
    details = _metadata_to_details(
        onboarding_version=onboarding_version,
        step_key=step_key,
        source=source,
        provider=normalized_provider,
        metadata=normalized_metadata,
    )
    try:
        await upsert_user_in_crm(
            gspread_client,
            config,
            user,
            ltv,
            analytics_profile=profile,
        )
        await add_funnel_event_to_sheets(
            gspread_client,
            config,
            user,
            event_name,
            details,
        )
    except Exception as exc:
        logger.warning("Не удалось синхронизировать аналитику пользователя %s: %s", telegram_id, exc)

    return profile
