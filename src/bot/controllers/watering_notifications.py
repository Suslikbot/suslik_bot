from datetime import datetime, timedelta
from logging import getLogger

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from bot.controllers.garden import get_due_plants, mark_notified, should_notify
from bot.internal.keyboards import garden_plant_kb
from bot.internal.lexicon import garden_text

logger = getLogger(__name__)


class NotificationDispatcher:
    async def send_watering_reminder(self, *, chat_id: int, plant_id: int, plant_name: str) -> None:
        raise NotImplementedError


class TelegramNotificationDispatcher(NotificationDispatcher):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def send_watering_reminder(self, *, chat_id: int, plant_id: int, plant_name: str) -> None:
        await self.bot.send_message(
            chat_id=chat_id,
            text=garden_text["watering_reminder"].format(name=plant_name),
            reply_markup=garden_plant_kb(plant_id),
            disable_notification=True,
        )


class WateringNotificationService:
    def __init__(self, dispatcher: NotificationDispatcher) -> None:
        self.dispatcher = dispatcher

    async def notify_user_due_plants(
        self,
        *,
        user_tg_id: int,
        db_session: AsyncSession,
        now: datetime,
        test_repeat_minutes: int | None = None,
    ) -> int:
        sent_count = 0
        due_plants = await get_due_plants(user_tg_id, db_session, now)
        for plant in due_plants:
            if not should_notify(plant, now):
                continue

            await self.dispatcher.send_watering_reminder(
                chat_id=user_tg_id,
                plant_id=plant.id,
                plant_name=plant.name,
            )
            await mark_notified(plant, db_session, now)
            if test_repeat_minutes and test_repeat_minutes > 0:
                plant.next_watering_at = now + timedelta(minutes=test_repeat_minutes)
            sent_count += 1

        if sent_count:
            logger.info("Sent %s watering reminders to user %s", sent_count, user_tg_id)
        return sent_count