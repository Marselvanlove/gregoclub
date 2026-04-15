#!/usr/bin/env python3
"""
Скрипт для массовой отправки приглашений на события пользователям,
которые не получили их при активации подписки.

ЗАПУСК: python3 -m send_missing_invitations
"""
import asyncio
import logging
import sys
import os

# Добавляем текущую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.requests import get_user_by_telegram_id
from services.payment_activation import send_upcoming_event_invitation

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s'
)
logger = logging.getLogger(__name__)

# Список пользователей без приглашений (из запроса к БД)
USERS_WITHOUT_INVITATIONS = [
    191383006,  # Marina Nikitenko
    208095345,  # Irene
    307795119,  # Lena🩵
    359377079,  # Natalia Krylova
    465668480,  # Dasha Kontorovich (Prokhorova)
    474148376,  # Irina
    508844314,  # Anastasiia
    962635019,  # Кати
    996882498,  # Kim Johnson
    1585092618, # Анна Регент
    5259777311, # Veronika
    5344209216, # Volodymyr
    6065175645, # Dana Kozhabayeva
    8413059761, # Tatiana
    8696373484, # Zhansaya Bukanova
]


async def send_invitations_to_users(session, bot):
    """Отправляет приглашения на события всем пользователям из списка."""
    success_count = 0
    error_count = 0
    
    logger.info(f"Начинаем отправку приглашений для {len(USERS_WITHOUT_INVITATIONS)} пользователей...")
    
    for telegram_id in USERS_WITHOUT_INVITATIONS:
        try:
            # Проверяем что пользователь существует и активен
            user = await get_user_by_telegram_id(session, telegram_id)
            if not user:
                logger.warning(f"Пользователь {telegram_id} не найден в базе, пропускаем")
                error_count += 1
                continue
            
            if user.status.value != "active":
                logger.warning(f"Пользователь {telegram_id} не активен (статус: {user.status.value}), пропускаем")
                error_count += 1
                continue
            
            # Отправляем приглашения
            logger.info(f"Отправка приглашений пользователю {telegram_id} ({user.full_name})...")
            await send_upcoming_event_invitation(session, bot, telegram_id)
            success_count += 1
            
            # Пауза между отправками чтобы не спамить
            await asyncio.sleep(2)
            
        except Exception as e:
            logger.error(f"Ошибка при отправке приглашений пользователю {telegram_id}: {e}")
            error_count += 1
    
    logger.info(f"\n=== ИТОГО ===")
    logger.info(f"Успешно отправлено: {success_count}")
    logger.info(f"Ошибок: {error_count}")
    return success_count, error_count
