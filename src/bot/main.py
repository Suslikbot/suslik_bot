import logging
from asyncio import create_task, run

import sentry_sdk
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis
from yookassa import Configuration
from bot.handlers.onboarding_callbacks import router as onboarding_callbacks_router

from bot.ai_client import AIClient
from bot.config import get_settings
from bot.controllers.base import daily_routine
from bot.handlers.ai import router as ai_router
from bot.handlers.base import router as base_router
from bot.handlers.command import router as commands_router
from bot.handlers.errors import router as error_router
from bot.handlers.payment import router as payment_router
from bot.internal.enums import Stage
from bot.internal.helpers import setup_logs
from bot.internal.notify_admin import on_shutdown, on_startup
from bot.middlewares.auth import AuthMiddleware
from bot.middlewares.logging import LoggingMiddleware
from bot.middlewares.session import DBSessionMiddleware
from bot.middlewares.updates_dumper import UpdatesDumperMiddleware
from bot.middlewares.user_limit import UserLimitMiddleware
from database.database_connector import get_db


async def main():
    setup_logs("suslik_robot")
    settings = get_settings()
    if settings.bot.SENTRY_DSN and settings.bot.STAGE == Stage.PROD:
        sentry_sdk.init(
            dsn=settings.bot.SENTRY_DSN.get_secret_value(),
            # Set traces_sample_rate to 1.0 to capture 100%
            # of transactions for performance monitoring.
            traces_sample_rate=1.0,
            # Set profiles_sample_rate to 1.0 to profile 100%
            # of sampled transactions.
            # We recommend adjusting this value in production.
            profiles_sample_rate=1.0,
        )
    bot = Bot(
        token=settings.bot.TOKEN.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    openai_client = AIClient(
        token=settings.gpt.OPENAI_API_KEY.get_secret_value(),
        assistant_id=settings.gpt.ASSISTANT_ID.get_secret_value(),
    )
    redis_client = Redis(
        host=settings.redis.HOST,
        port=settings.redis.PORT,
        username=settings.redis.USERNAME,
        password=settings.redis.PASSWORD.get_secret_value(),
        decode_responses=True,
    )
    Configuration.configure(settings.shop.ID, settings.shop.API_KEY.get_secret_value())
    storage = RedisStorage(redis_client)
    dispatcher = Dispatcher(storage=storage, settings=settings, openai_client=openai_client)
    db = get_db(settings)
    db_session_middleware = DBSessionMiddleware(db)
    dispatcher.update.outer_middleware(UpdatesDumperMiddleware())
    dispatcher.startup.register(on_startup)
    dispatcher.shutdown.register(on_shutdown)
    dispatcher.message.middleware(db_session_middleware)
    dispatcher.callback_query.middleware(db_session_middleware)
    dispatcher.message.middleware(AuthMiddleware())
    dispatcher.callback_query.middleware(AuthMiddleware())
    dispatcher.update.middleware(UserLimitMiddleware())
    dispatcher.message.middleware.register(LoggingMiddleware())
    dispatcher.callback_query.middleware.register(LoggingMiddleware())
    dispatcher.include_routers(
        commands_router,
        payment_router,
        base_router,
        onboarding_callbacks_router,
        ai_router,
        # onboarding_callbacks_router,
        error_router,
    )
    # noinspection PyUnusedLocal
    daily_task = create_task(daily_routine(bot, settings, dispatcher, db))
    logging.info("suslik robot started")
    await dispatcher.start_polling(bot, skip_updates=True)


def run_main():
    run(main())


if __name__ == "__main__":
    run_main()
