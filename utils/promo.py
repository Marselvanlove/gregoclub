import asyncio
import logging
from datetime import datetime

import pytz
from aiogram import Bot

logger = logging.getLogger(__name__)

_MADRID_TZ = pytz.timezone("Europe/Madrid")
_PROMO_DEADLINE = _MADRID_TZ.localize(datetime(2026, 3, 5, 0, 0, 0))

_PROMO_TEXT = (
    "Оформите подписку сейчас, чтобы забронировать место в Клубе! "
    "Ваша карта будет привязана, а оплаченный месяц начнет действовать только с первого занятия (5 марта). "
    "Следующее списание будет 5 апреля."
)


async def maybe_send_promo(bot: Bot, chat_id: int) -> None:
    """
    Фоновая задача: ждёт 5 секунд, затем отправляет маркетинговое сообщение,
    если текущее время строго до 5 марта 2026 года 00:00 (Europe/Madrid).
    """
    await asyncio.sleep(5)
    now = datetime.now(_MADRID_TZ)
    if now < _PROMO_DEADLINE:
        try:
            await bot.send_message(chat_id=chat_id, text=_PROMO_TEXT)
        except Exception as e:
            logger.warning("maybe_send_promo: не удалось отправить для chat_id=%s: %s", chat_id, e)
