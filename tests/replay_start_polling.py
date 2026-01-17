import asyncio
import random
import time
from typing import Any
from typing import Any, AsyncIterator
from aiogram.client.session.base import BaseSession
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ChatType, ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import Chat, Message, Update, User as TgUser
from redis.asyncio import Redis

from bot.config import get_settings
from bot.handlers.command import router as commands_router
from bot.middlewares.auth import AuthMiddleware
from bot.middlewares.logging import LoggingMiddleware
from bot.middlewares.session import DBSessionMiddleware
from bot.middlewares.updates_dumper import UpdatesDumperMiddleware
from bot.middlewares.user_limit import UserLimitMiddleware
from database.database_connector import get_db


# --- Telegram transport stub: никакого реального Telegram API ---
class DummySession(BaseSession):
    async def make_request(
        self,
        bot,
        method,
        timeout: Any = None,
    ) -> Any:
        # Имитируем успешный ответ Telegram API
        return {"ok": True, "result": None}

    async def stream_content(
        self,
        url: str,
        timeout: int | None = None,
        chunk_size: int = 65536,
    ) -> AsyncIterator[bytes]:
        # Файлы мы не скачиваем — просто пустой генератор
        if False:
            yield b""

    async def close(self) -> None:
        return

def make_message(user_id: int, text: str) -> Message:
    return Message(
        message_id=random.randint(1, 10_000_000),
        date=int(time.time()),
        chat=Chat(id=user_id, type=ChatType.PRIVATE),
        from_user=TgUser(
            id=user_id,
            is_bot=False,
            first_name="Replay",
            last_name="User",
            username=f"replay_{user_id}",
        ),
        text=text,
    )


async def feed(dp: Dispatcher, bot: Bot, user_id: int, text: str) -> None:
    msg = make_message(user_id, text)
    update = Update(update_id=random.randint(1, 10_000_000), message=msg)
    await dp.feed_update(bot=bot, update=update)


def build_dispatcher_and_bot() -> tuple[Dispatcher, Bot]:
    settings = get_settings()

    # Важно: Bot нужен FSM (bot.id берётся из токена, поэтому токен должен быть валидного формата)
    # Реальный токен можно оставить — запросов к Telegram не будет из-за DummySession.
    bot = Bot(
        token=settings.bot.TOKEN.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=DummySession(),
    )

    # Storage как в проде
    redis = Redis(
        host=settings.redis.HOST,
        port=settings.redis.PORT,
        username=settings.redis.USERNAME,
        password=settings.redis.PASSWORD.get_secret_value(),
        decode_responses=True,
    )
    storage = RedisStorage(redis)

    dp = Dispatcher(storage=storage, settings=settings)

    # DB middleware как в проде
    db = get_db(settings)
    db_session_middleware = DBSessionMiddleware(db)

    # middlewares — порядок как в main.py
    dp.update.outer_middleware(UpdatesDumperMiddleware())

    dp.message.middleware(db_session_middleware)
    dp.callback_query.middleware(db_session_middleware)

    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    dp.update.middleware(UserLimitMiddleware())

    dp.message.middleware.register(LoggingMiddleware())
    dp.callback_query.middleware.register(LoggingMiddleware())

    # Для воспроизведения /start достаточно commands_router
    dp.include_router(commands_router)

    return dp, bot


async def scenario_deeplink_then_start(dp: Dispatcher, bot: Bot, user_id: int) -> None:
    await feed(dp, bot, user_id, "/start event")
    await asyncio.sleep(random.uniform(5, 20))
    await feed(dp, bot, user_id, "/start")


async def scenario_double_start_race(dp: Dispatcher, bot: Bot, user_id: int) -> None:
    # Два /start почти одновременно — имитация гонки
    await asyncio.gather(
        feed(dp, bot, user_id, "/start"),
        feed(dp, bot, user_id, "/start"),
    )


async def main() -> None:
    dp, bot = build_dispatcher_and_bot()

    # Возьми здесь свой реальный tg_id или любой — Telegram API всё равно не вызывается
    user_id = 342699578

    # 1) deep-link -> пауза -> /start
    # 2) гонка /start + /start
    await asyncio.gather(
        scenario_deeplink_then_start(dp, bot, user_id),
        scenario_double_start_race(dp, bot, user_id),
    )


if __name__ == "__main__":
    asyncio.run(main())
