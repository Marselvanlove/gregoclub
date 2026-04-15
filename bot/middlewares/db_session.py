# Middleware для инъекции сессии БД в хендлеры
# Каждый хендлер получает session через data["session"]

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class DbSessionMiddleware(BaseMiddleware):
    """
    Middleware, который создаёт сессию БД для каждого апдейта.
    
    Использование в хендлере:
        async def handler(message: Message, session: AsyncSession):
            user = await get_user_by_telegram_id(session, message.from_user.id)
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        super().__init__()
        self.session_factory = session_factory

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # Создаём сессию и передаём её в data
        # Сессия автоматически закроется после выхода из контекста
        async with self.session_factory() as session:
            data["session"] = session
            return await handler(event, data)
