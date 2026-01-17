from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message

from bot.controllers.user import add_user_to_db, get_user_from_db_by_tg_id
from asyncpg.exceptions import UniqueViolationError
from sqlalchemy.exc import IntegrityError

class AuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        db_session = data["db_session"]
        user = await get_user_from_db_by_tg_id(event.from_user.id, db_session)
        data["is_new_user"] = False
        if not user:
            data["is_new_user"] = True
            source = None
            if event.text and event.text.startswith("/start"):
                parts = event.text.split(maxsplit=1)
                if len(parts) == 2:
                    source = parts[1].strip()
            try:
                user = await add_user_to_db(event.from_user, db_session, source)
            except (UniqueViolationError, IntegrityError):
                await db_session.rollback()
                user = await get_user_from_db_by_tg_id(event.from_user.id, db_session)
                data["is_new_user"] = True
        data["user"] = user
        return await handler(event, data)
