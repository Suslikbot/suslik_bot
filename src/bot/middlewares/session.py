from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message

from database.database_connector import DatabaseConnector


class DBSessionMiddleware(BaseMiddleware):
    def __init__(self, db: DatabaseConnector):
        self.db = db

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        async with self.db.session_factory.begin() as db_session:
            data["db_session"] = db_session
            try:
                res = await handler(event, data)
                await db_session.commit()
                return res
            except:
                await db_session.rollback()
                raise

