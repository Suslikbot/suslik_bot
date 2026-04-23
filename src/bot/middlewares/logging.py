import functools
import logging
from uuid import uuid4
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import TelegramObject

from bot.log_context import reset_log_context, set_log_context

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        name = self._get_name(handler)
        user = data.get("event_from_user")
        fsm_context: FSMContext | None = data.get("state")
        state = await fsm_context.get_state() if fsm_context else None
        correlation_id = self._get_correlation_id(event)
        token = set_log_context(
            correlation_id=correlation_id,
            user_id=getattr(user, "id", None),
            state=state,
            operation=name,
        )
        try:
            logger.info(f"calling {name}")
            return await handler(event, data)
        finally:
            reset_log_context(token)

    def _get_name(self, handler):
        while isinstance(handler, functools.partial):
            handler = handler.args[0]

        name = handler.__wrapped__.__self__.callback.__name__
        return name

    def _get_correlation_id(self, event: TelegramObject) -> str:
        update_id = getattr(event, "update_id", None)
        if update_id is not None:
            return f"tg-{update_id}"
        return f"tg-{uuid4()}"
