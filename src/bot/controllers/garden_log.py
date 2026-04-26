from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.config import Settings
from database.models import User


async def log_garden_action(  # noqa: PLR0913
    message: Message,
    state: FSMContext | None,
    user: User,
    settings: Settings,
    action: str,
    plant_name: str | None = None,
    details: str | None = None,
    user_message: str | None = None,
    bot_response: str | None = None,
) -> None:
    current_state = await state.get_state() if state else None
    username = f"@{user.username}" if user.username else "without_username"
    lines = [
        "🪴 garden",
        f"user: {user.tg_id} ({user.fullname}) {username}",
        f"action: {action}",
        f"state: {current_state or 'none'}",
    ]
    if plant_name:
        lines.append(f"plant: {plant_name}")
    if details:
        lines.append(f"details: {details}")
    if user_message:
        lines.append(f"user_message: {user_message}")
    if bot_response:
        lines.append(f"bot_response: {bot_response}")
    await message.bot.send_message(settings.bot.CHAT_LOG_ID, "\n".join(lines))
