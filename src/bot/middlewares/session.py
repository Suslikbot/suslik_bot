from collections.abc import Awaitable, Callable
import logging
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message

from database.database_connector import DatabaseConnector
logger = logging.getLogger(__name__)

class DBSessionMiddleware(BaseMiddleware):
    def __init__(self, db: DatabaseConnector):
        self.db = db

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        logger.info("middleware start", extra={"middleware": "DBSessionMiddleware"})
        async with self.db.session_factory() as db_session:
            data["db_session"] = db_session
            try:
                res = await handler(event, data)
                logger.info("db commit")
                await db_session.commit()
                return res
            except Exception:
                logger.info("db rollback")
                await db_session.rollback()
                raise
            finally:
                logger.info("middleware end", extra={"middleware": "DBSessionMiddleware"})

