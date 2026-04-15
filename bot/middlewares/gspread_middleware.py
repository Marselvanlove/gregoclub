# Middleware для инъекции gspread_client в хендлеры

from typing import Any, Awaitable, Callable, Dict, Optional

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
import gspread


class GspreadMiddleware(BaseMiddleware):
    """
    Middleware, который передаёт gspread_client в хендлеры.
    """

    def __init__(self, gspread_client: Optional[gspread.Client]) -> None:
        super().__init__()
        self.gspread_client = gspread_client

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        data["gspread_client"] = self.gspread_client
        return await handler(event, data)
