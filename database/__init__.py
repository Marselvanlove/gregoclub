# Пакет database — SQLAlchemy модели и функции работы с БД
#
# Здесь создаём асинхронный движок (engine) и фабрику сессий (async_sessionmaker).
# Используем паттерн "фабрика" — сессии создаются по запросу, а не глобально.

from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from database.models import Base

# Глобальные переменные для движка и фабрики сессий.
# Инициализируются при старте приложения через init_db().
engine: Optional[AsyncEngine] = None
async_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


async def init_db(database_url: str) -> None:
    """
    Инициализирует подключение к БД:
    1. Создаёт асинхронный движок (engine)
    2. Создаёт фабрику сессий (sessionmaker)
    3. Создаёт все таблицы, если их нет (create_all)

    Вызывать один раз при старте приложения (в main.py).
    """
    global engine, async_session_factory

    # echo=False — не логировать каждый SQL-запрос (можно включить для дебага)
    engine = create_async_engine(database_url, echo=False)

    # expire_on_commit=False — объекты остаются доступны после commit
    # (иначе нужно делать refresh после каждого коммита)
    async_session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Создаём таблицы, если их ещё нет (аналог Alembic для простых случаев)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        if engine.dialect.name != "sqlite":
            return

        result = await conn.execute(text("PRAGMA table_info(users)"))
        existing_columns = {row[1] for row in result.all()}

        alter_statements: list[str] = []
        if "email" not in existing_columns:
            alter_statements.append("ALTER TABLE users ADD COLUMN email VARCHAR(255)")
        if "last_pay_click_at" not in existing_columns:
            alter_statements.append("ALTER TABLE users ADD COLUMN last_pay_click_at DATETIME")
        if "pending_reminder_step" not in existing_columns:
            alter_statements.append("ALTER TABLE users ADD COLUMN pending_reminder_step INTEGER")
        if "expiry_warning_sent_at" not in existing_columns:
            alter_statements.append("ALTER TABLE users ADD COLUMN expiry_warning_sent_at DATETIME")
        if "last_purchase_at" not in existing_columns:
            alter_statements.append("ALTER TABLE users ADD COLUMN last_purchase_at DATETIME")
        if "group_join_check_sent" not in existing_columns:
            alter_statements.append("ALTER TABLE users ADD COLUMN group_join_check_sent BOOLEAN DEFAULT 0")
        if "payment_provider" not in existing_columns:
            alter_statements.append("ALTER TABLE users ADD COLUMN payment_provider VARCHAR(32)")
        if "payment_customer_id" not in existing_columns:
            alter_statements.append("ALTER TABLE users ADD COLUMN payment_customer_id VARCHAR(128)")

        for stmt in alter_statements:
            await conn.execute(text(stmt))

        result = await conn.execute(text("PRAGMA table_info(payments)"))
        payment_columns = {row[1] for row in result.all()}

        payment_alter: list[str] = []
        if "provider" not in payment_columns:
            payment_alter.append("ALTER TABLE payments ADD COLUMN provider VARCHAR(32) DEFAULT 'stripe'")
        if "external_payment_id" not in payment_columns:
            payment_alter.append("ALTER TABLE payments ADD COLUMN external_payment_id VARCHAR(128)")

        for stmt in payment_alter:
            await conn.execute(text(stmt))

        # Миграция для scheduled_broadcasts
        result = await conn.execute(text("PRAGMA table_info(scheduled_broadcasts)"))
        sb_columns = {row[1] for row in result.all()}

        sb_alter: list[str] = []
        if "zoom_link" not in sb_columns:
            sb_alter.append("ALTER TABLE scheduled_broadcasts ADD COLUMN zoom_link VARCHAR(512)")
        if "reminder_24h_sent" not in sb_columns:
            sb_alter.append("ALTER TABLE scheduled_broadcasts ADD COLUMN reminder_24h_sent BOOLEAN DEFAULT 0")
        if "reminder_15min_sent" not in sb_columns:
            sb_alter.append("ALTER TABLE scheduled_broadcasts ADD COLUMN reminder_15min_sent BOOLEAN DEFAULT 0")
        if "reminder_5min_sent" not in sb_columns:
            sb_alter.append("ALTER TABLE scheduled_broadcasts ADD COLUMN reminder_5min_sent BOOLEAN DEFAULT 0")

        for stmt in sb_alter:
            await conn.execute(text(stmt))

        result = await conn.execute(text("PRAGMA table_info(event_feedbacks)"))
        feedback_columns = {row[1] for row in result.all()}

        feedback_alter: list[str] = []
        if "improvement_comment" not in feedback_columns:
            feedback_alter.append("ALTER TABLE event_feedbacks ADD COLUMN improvement_comment VARCHAR(2000)")
        if "awaiting_improvement_comment" not in feedback_columns:
            feedback_alter.append("ALTER TABLE event_feedbacks ADD COLUMN awaiting_improvement_comment BOOLEAN DEFAULT 0")

        for stmt in feedback_alter:
            await conn.execute(text(stmt))


async def close_db() -> None:
    """
    Закрывает соединение с БД.
    Вызывать при завершении приложения.
    """
    global engine
    if engine is not None:
        await engine.dispose()
        engine = None


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """
    Возвращает фабрику сессий.
    Использовать так:
        async with get_session_factory()() as session:
            ...
    Или через dependency injection в хендлерах.
    """
    if async_session_factory is None:
        raise RuntimeError("База данных не инициализирована. Сначала вызовите init_db().")
    return async_session_factory
