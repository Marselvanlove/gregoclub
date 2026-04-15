import logging
from datetime import datetime, timedelta
from typing import Optional

import gspread
from aiogram import Bot
from fastapi import APIRouter, Query
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from database.models import UserStatus
from database.requests import add_user, get_user_by_telegram_id
from services.payment_activation import grant_manual_subscription
from utils.config import Config

logger = logging.getLogger(__name__)
router = APIRouter(tags=["integrations"])


def _resolve_subscription_end(existing_end: Optional[datetime]) -> datetime:
    now = datetime.utcnow()
    default_end = now + timedelta(days=90)

    if existing_end and existing_end > default_end:
        return existing_end

    return default_end


def _has_active_access(subscription_end: Optional[datetime], status: Optional[UserStatus]) -> bool:
    if subscription_end is None:
        return False
    return status == UserStatus.active and subscription_end > datetime.utcnow()


def create_salebot_webhook_endpoint(
    session_factory: async_sessionmaker[AsyncSession],
    bot: Bot,
    config: Config,
    gspread_client: Optional[gspread.Client] = None,
) -> APIRouter:
    @router.get("/add_user")
    async def add_user_from_salebot(
        telegram_id: int = Query(..., gt=0),
    ) -> dict[str, str]:
        logger.info("Salebot add_user request received: telegram_id=%s", telegram_id)

        try:
            async with session_factory() as session:
                user = await get_user_by_telegram_id(session, telegram_id)

                if user is not None and _has_active_access(user.subscription_end_date, user.status):
                    logger.info("Salebot add_user skipped: telegram_id=%s already has active access", telegram_id)
                    return {"status": "success", "message": "user added"}

                # Если пользователя ещё нет, сначала создаём запись в users.
                if user is None:
                    user = await add_user(
                        session=session,
                        telegram_id=telegram_id,
                        username=None,
                        full_name="Salebot User",
                    )

                # Повторно используем ту же логику выдачи доступа,
                # что и в ручном добавлении через админку.
                subscription_end = _resolve_subscription_end(user.subscription_end_date)
                await grant_manual_subscription(
                    session=session,
                    bot=bot,
                    config=config,
                    telegram_id=telegram_id,
                    subscription_end=subscription_end,
                    gspread_client=gspread_client,
                )
        except Exception:
            logger.exception("Salebot add_user failed: telegram_id=%s", telegram_id)
            raise

        logger.info("Salebot add_user completed: telegram_id=%s", telegram_id)
        return {"status": "success", "message": "user added"}

    return router
