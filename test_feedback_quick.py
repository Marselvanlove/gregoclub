#!/usr/bin/env python3
"""
Скрипт для быстрого тестирования Feedback System.
Временно изменяет временные окна для немедленной проверки.

ВАЖНО: Запускать ТОЛЬКО в тестовом окружении!
После тестов вернуть изменения обратно.
"""

import asyncio
from datetime import datetime, timedelta
import pytz

from database import init_db, get_session_factory
from database.requests import (
    get_broadcasts_needing_feedback,
    get_rsvp_attending_users,
)

MADRID_TZ = pytz.timezone("Europe/Madrid")


async def test_feedback_timing():
    """
    Проверяет логику определения времени отправки опроса.
    """
    print("🧪 Тест: Проверка временных окон для отправки опроса\n")
    
    await init_db("sqlite+aiosqlite:///./data/app.db")
    session_factory = get_session_factory()
    
    async with session_factory() as session:
        broadcasts = await get_broadcasts_needing_feedback(session)
        
        if not broadcasts:
            print("❌ Нет встреч для отправки опроса")
            print("\nДля теста создайте встречу с:")
            print("  - has_rsvp = True")
            print("  - rsvp_event_datetime = текущее время + 5 минут")
            print("  - feedback_sent = False")
            return
        
        print(f"✅ Найдено встреч для опроса: {len(broadcasts)}\n")
        
        for broadcast in broadcasts:
            print(f"📅 Встреча #{broadcast.id}: {broadcast.rsvp_event_title}")
            print(f"   Время события: {broadcast.rsvp_event_datetime}")
            
            now = datetime.now(MADRID_TZ).replace(tzinfo=None)
            meeting_end = broadcast.rsvp_event_datetime + timedelta(minutes=90)
            survey_time = broadcast.rsvp_event_datetime + timedelta(minutes=110)
            
            print(f"   Окончание встречи: {meeting_end}")
            print(f"   Время опроса: {survey_time}")
            print(f"   Сейчас: {now}")
            print(f"   До отправки: {(survey_time - now).total_seconds() / 60:.1f} минут")
            
            attending = await get_rsvp_attending_users(session, broadcast.id)
            print(f"   Участников: {len(attending)}")
            print(f"   Список: {attending}")
            print()


async def check_feedback_records(telegram_id: int = 614771593):
    """
    Проверяет записи feedback для указанного пользователя.
    """
    print(f"🔍 Проверка feedback для пользователя {telegram_id}\n")
    
    await init_db("sqlite+aiosqlite:///./data/app.db")
    session_factory = get_session_factory()
    
    async with session_factory() as session:
        from sqlalchemy import select
        from database.models import EventFeedback
        
        stmt = select(EventFeedback).where(
            EventFeedback.telegram_id == telegram_id
        ).order_by(EventFeedback.created_at.desc())
        
        result = await session.execute(stmt)
        feedbacks = result.scalars().all()
        
        if not feedbacks:
            print("❌ Нет записей feedback")
            return
        
        print(f"✅ Найдено записей: {len(feedbacks)}\n")
        
        for fb in feedbacks:
            print(f"📝 Feedback #{fb.id}")
            print(f"   Встреча: #{fb.broadcast_id}")
            print(f"   Оценка: {fb.rating} ⭐")
            print(f"   Комфорт: {fb.level_comfort}")
            print(f"   Придёт: {fb.will_attend_next}")
            print(f"   Создан: {fb.created_at}")
            print(f"   Follow-up: {fb.followup_sent_at or 'Не отправлен'}")
            print()


async def main():
    """Главное меню тестирования."""
    print("=" * 60)
    print("🧪 Быстрое тестирование Feedback System")
    print("=" * 60)
    print()
    print("Выберите тест:")
    print("1. Проверить временные окна для опроса")
    print("2. Проверить записи feedback в БД")
    print("3. Оба теста")
    print()
    
    choice = input("Введите номер (1-3): ").strip()
    
    print()
    
    if choice in ("1", "3"):
        await test_feedback_timing()
    
    if choice in ("2", "3"):
        await check_feedback_records()
    
    print("=" * 60)
    print("✅ Тестирование завершено")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
