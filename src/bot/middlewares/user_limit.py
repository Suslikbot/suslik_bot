from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from aiogram import BaseMiddleware

from bot.config import get_settings
from bot.internal.lexicon import replies

if TYPE_CHECKING:
    from database.models import User


settings = get_settings()


class UserLimitMiddleware(BaseMiddleware):
    def __init__(self, limit: int = settings.bot.USERS_THRESHOLD):
        self.limit = limit

    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: dict[str, Any],
    ) -> Any:
        user: User = data.get("user")
        if not user:
            return await handler(event, data)

        if user.id <= self.limit or user.tg_id in settings.bot.ADMINS:
            return await handler(event, data)
        await event.answer(replies["users_limit_exceeded"])
        return None
