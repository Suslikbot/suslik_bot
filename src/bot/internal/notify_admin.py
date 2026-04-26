import logging
from pathlib import Path

from aiogram import Bot
from aiogram.types import BotCommand

from bot.config import Settings

logger = logging.getLogger(__name__)


async def on_startup(bot: Bot, settings: Settings):
    folder = Path.cwd().name
    # MVP-SUB-7: команды в меню остаются статичными (без динамического скрытия по подписке).
    # Ограничения доступа контролируются в handlers/guards.
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Запустить бота"),
            BotCommand(command="dialog", description="Режим AI-диалога"),
            BotCommand(command="garden", description="Раздел «Мой сад»"),
            BotCommand(command="support", description="Техническая поддержка"),
        ]
    )
    try:
        await bot.send_message(
            settings.bot.ADMINS[0],
            f"<b>{folder.replace('_', ' ')} started</b>\n\n/start",
            disable_notification=True,
        )
    except Exception: # noqa: BLE001
        logger.warning("Failed to send on startup notify")


async def on_shutdown(bot: Bot, settings: Settings):
    folder = Path.cwd().name
    try:
        await bot.send_message(
            settings.bot.ADMINS[0],
            f"<b>{folder.replace('_', ' ')} shutdown</b>",
            disable_notification=True,
        )
    except Exception: # noqa: BLE001
        logger.warning("Failed to send on shutdown notify")
