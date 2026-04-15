import logging
from typing import Optional

import gspread
from aiogram import Bot
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from database.requests import get_payment_order_by_id, get_user_analytics_profile
from services.analytics import track_event
from utils.config import Config

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/r", tags=["redirects"])


def create_checkout_redirect_endpoint(
    session_factory: async_sessionmaker[AsyncSession],
    bot: Bot,
    config: Config,
    gspread_client: Optional[gspread.Client] = None,
) -> APIRouter:
    @router.get("/checkout/{provider}/{order_id}")
    async def checkout_redirect(provider: str, order_id: int) -> RedirectResponse:
        async with session_factory() as session:
            order = await get_payment_order_by_id(session, order_id)
            if order is None or order.provider.value != provider:
                raise HTTPException(status_code=404, detail="Checkout order not found")
            if not order.payment_url:
                raise HTTPException(status_code=400, detail="Checkout link is unavailable")

            profile = await get_user_analytics_profile(session, order.telegram_id)
            await track_event(
                session,
                telegram_id=order.telegram_id,
                journey="payment",
                onboarding_version=profile.onboarding_version if profile and profile.onboarding_version else "core",
                event_name="checkout_redirect_opened",
                step_key=f"checkout:{provider}",
                source=f"redirect:{provider}",
                provider=order.provider,
                metadata={
                    "order_id": order.id,
                    "tariff": order.tariff,
                    "external_invoice_id": order.external_invoice_id,
                },
                config=config,
                gspread_client=gspread_client,
            )

        logger.info(
            "Checkout redirect opened: provider=%s order_id=%s telegram_id=%s",
            provider,
            order_id,
            order.telegram_id,
        )
        return RedirectResponse(order.payment_url, status_code=302)

    return router
