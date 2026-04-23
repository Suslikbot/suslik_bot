import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.dispatcher.event.bases import UNHANDLED
from aiogram.types import TelegramObject, Update

logger = logging.getLogger(__name__)


class UpdatesDumperMiddleware(BaseMiddleware):
    def __init__(self, debug_mode: bool = False) -> None:
        self.debug_mode = debug_mode

    @staticmethod
    def _extract_event_type(event: Update) -> str:
        event_payload = event.model_dump(exclude_unset=True)
        for key in event_payload:
            if key != "update_id":
                return key
        return "unknown"

    @staticmethod
    def _extract_user_id(event: Update) -> int | None:
        for candidate in (
                event.message,
                event.edited_message,
                event.callback_query,
                event.inline_query,
                event.chosen_inline_result,
                event.my_chat_member,
                event.chat_member,
                event.chat_join_request,
        ):
            if not candidate:
                continue
            from_user = getattr(candidate, "from_user", None)
            if from_user and getattr(from_user, "id", None) is not None:
                return from_user.id
            user = getattr(candidate, "user", None)
            if user and getattr(user, "id", None) is not None:
                return user.id
        return None
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: dict[str, Any],
    ) -> Any:
        event_type = self._extract_event_type(event)
        user_id = self._extract_user_id(event)

        logger.info(
            "inbound update",
            extra={
                "update_id": event.update_id,
                "event_type": event_type,
                "user_id": user_id,
            },
        )
        if self.debug_mode:
            logger.debug(
                "inbound update payload",
                extra={
                    "update_id": event.update_id,
                    "event_type": event_type,
                    "user_id": user_id,
                    "payload": event.model_dump_json(exclude_unset=True),
                },
            )
        res = await handler(event, data)
        if res is UNHANDLED:
            logger.info("UNHANDLED")
        return res
