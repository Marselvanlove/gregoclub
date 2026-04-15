# Логика работы со Stripe: создание Checkout Session, Customer Portal, обработка событий
# Используем Stripe Python SDK для подписок (subscription mode).

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
import asyncio

import stripe
from stripe import StripeClient

from utils.config import Config

logger = logging.getLogger(__name__)


def init_stripe(config: Config) -> StripeClient:
    """
    Инициализирует Stripe клиент с API ключом из конфига.
    Возвращает StripeClient для дальнейших операций.
    """
    return StripeClient(api_key=config.stripe_api_key)


async def create_checkout_session(
    client: StripeClient,
    config: Config,
    telegram_id: int,
    tariff: str,  # "1month" или "3months"
) -> dict[str, str]:
    """
    Создаёт Stripe Checkout Session для подписки.
    
    Возвращает URL страницы оплаты Stripe.
    
    Параметры:
    - telegram_id: ID пользователя в Telegram (передаём как client_reference_id)
    - tariff: выбранный тариф
    """
    # Выбираем Price ID в зависимости от тарифа
    if tariff == "1month":
        price_id = config.stripe_price_1_month
    elif tariff == "3months":
        price_id = config.stripe_price_3_months
    else:  # 6months
        price_id = config.stripe_price_6_months

    # Создаём Checkout Session в режиме подписки
    # client_reference_id — чтобы связать сессию с telegram_id при получении вебхука
    bot_username = config.bot_username.lstrip("@")
    session = await asyncio.to_thread(
        client.checkout.sessions.create,
        params={
            "mode": "subscription",
            "payment_method_types": ["card"],
            "line_items": [
                {
                    "price": price_id,
                    "quantity": 1,
                }
            ],
            # Передаём telegram_id, чтобы найти пользователя при обработке вебхука
            "client_reference_id": str(telegram_id),
            # URL после успешной оплаты — редирект на /status вместо /start
            "success_url": f"https://t.me/{bot_username}" if bot_username else "https://t.me",
            # URL при отмене оплаты
            "cancel_url": f"https://t.me/{bot_username}" if bot_username else "https://t.me",
            # Метаданные для дебага
            "metadata": {
                "telegram_id": str(telegram_id),
                "tariff": tariff,
            },
            "subscription_data": {
                "metadata": {
                    "telegram_id": str(telegram_id),
                    "tariff": tariff,
                },
            },
        }
    )

    logger.info(f"Создана Checkout Session {session.id} для telegram_id={telegram_id}, tariff={tariff}")
    return {
        "id": session.id,
        "url": session.url,
    }


async def create_customer_portal_session(
    client: StripeClient,
    stripe_customer_id: str,
    return_url: str,
) -> str:
    """
    Создаёт сессию Stripe Customer Portal.
    Позволяет пользователю управлять подпиской (отмена, смена карты).
    
    Возвращает URL портала.
    """
    session = await asyncio.to_thread(
        client.billing_portal.sessions.create,
        params={
            "customer": stripe_customer_id,
            "return_url": return_url,
        }
    )

    logger.info(f"Создана Portal Session для customer={stripe_customer_id}")
    return session.url


async def get_subscription_status(
    client: StripeClient,
    stripe_customer_id: str,
) -> Optional[Dict]:
    """
    Получает текущий статус подписки пользователя.
    Возвращает dict с информацией или None, если подписки нет.
    """
    subscriptions = await asyncio.to_thread(
        client.subscriptions.list,
        params={
            "customer": stripe_customer_id,
            "status": "active",
            "limit": 1,
        },
    )

    if subscriptions.data:
        sub = subscriptions.data[0]
        return {
            "id": sub.id,
            "status": sub.status,
            "current_period_end": datetime.fromtimestamp(sub.current_period_end),
            "cancel_at_period_end": sub.cancel_at_period_end,
        }
    return None


async def get_subscription_by_id(
    client: StripeClient,
    subscription_id: str,
) -> Optional[Dict]:
    try:
        subscription = await asyncio.to_thread(client.subscriptions.retrieve, subscription_id)
    except Exception as e:
        logger.warning(f"Не удалось получить Stripe subscription {subscription_id}: {e}")
        return None

    current_period_end = getattr(subscription, "current_period_end", None)
    return {
        "id": subscription.id,
        "status": subscription.status,
        "customer": subscription.customer,
        "current_period_end": datetime.fromtimestamp(current_period_end) if current_period_end else None,
        "cancel_at_period_end": subscription.cancel_at_period_end,
        "metadata": dict(subscription.metadata or {}),
    }


def verify_webhook_signature(
    payload: bytes,
    sig_header: str,
    webhook_secret: str,
) -> Optional[stripe.Event]:
    """
    Проверяет подпись вебхука Stripe.
    
    Возвращает Event если подпись валидна, иначе None.
    """
    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=webhook_secret,
        )
        return event
    except stripe.SignatureVerificationError as e:
        logger.warning(f"Невалидная подпись вебхука: {e}")
        return None
    except Exception as e:
        logger.error(f"Ошибка при проверке вебхука: {e}")
        return None


def calculate_subscription_end_date(tariff: str) -> datetime:
    """
    Рассчитывает дату окончания подписки.
    - 1month: +30 дней
    - 3months: +90 дней
    - 6months: +180 дней
    """
    now = datetime.utcnow()
    if tariff == "1month":
        return now + timedelta(days=30)
    elif tariff == "3months":
        return now + timedelta(days=90)
    else:  # 6months
        return now + timedelta(days=180)
