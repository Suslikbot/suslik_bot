import logging
from asyncio import run, sleep
from datetime import UTC, datetime

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from sentry_sdk import init as sentry_init

from bot.config import get_settings
from bot.controllers.user import get_all_users_with_active_subscription
from bot.controllers.watering_notifications import (
    TelegramNotificationDispatcher,
    WateringNotificationService,
)
from bot.internal.enums import Stage
from bot.internal.helpers import setup_logs
from database.database_connector import get_db

logger = logging.getLogger(__name__)

DEFAULT_WORKER_INTERVAL_SECONDS = 60
DEFAULT_TEST_REPEAT_MINUTES = 0


async def main() -> None:
    settings = get_settings()
    setup_logs("watering_worker", settings.bot.STAGE)

    if settings.bot.SENTRY_DSN and settings.bot.STAGE == Stage.PROD:
        sentry_init(
            dsn=settings.bot.SENTRY_DSN.get_secret_value(),
            traces_sample_rate=1.0,
            profiles_sample_rate=1.0,
        )

    bot = Bot(
        token=settings.bot.TOKEN.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    db = get_db(settings)
    notification_service = WateringNotificationService(TelegramNotificationDispatcher(bot))

    worker_interval_seconds = int(getattr(settings.bot, "WATERING_WORKER_INTERVAL_SECONDS", DEFAULT_WORKER_INTERVAL_SECONDS))
    test_repeat_minutes = int(getattr(settings.bot, "WATERING_TEST_REPEAT_MINUTES", DEFAULT_TEST_REPEAT_MINUTES))

    logger.info(
        "watering worker started (interval=%ss, test_repeat_minutes=%s)",
        worker_interval_seconds,
        test_repeat_minutes,
    )

    while True:
        utcnow = datetime.now(UTC)
        async with db.session_factory() as session:
            users = await get_all_users_with_active_subscription(session)
            for user in users:
                sent_count = await notification_service.notify_user_due_plants(
                    user_tg_id=user.tg_id,
                    db_session=session,
                    now=utcnow,
                    test_repeat_minutes=test_repeat_minutes,
                )
                if sent_count:
                    await sleep(0.1)
            await session.commit()

        await sleep(worker_interval_seconds)


def run_main() -> None:
    run(main())


if __name__ == "__main__":
    run_main()
