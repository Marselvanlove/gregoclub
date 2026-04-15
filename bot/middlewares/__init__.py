# Мидлвари (например, проверка админа, инъекция сессии БД)

from bot.middlewares.db_session import DbSessionMiddleware

__all__ = ["DbSessionMiddleware"]
