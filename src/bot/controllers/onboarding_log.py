from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.config import Settings
from database.models import User


async def log_onboarding_step(
    message: Message,
    state: FSMContext | None,
    user: User,
    settings: Settings,
    step: str,
    extra: str | None = None,
) -> None:
    current_state = await state.get_state() if state else None
    lines = [
        "🧭 onboarding_3",
        f"user: {user.tg_id} ({user.fullname})",
        f"step: {step}",
        f"state: {current_state or 'none'}",
    ]
    if extra:
        lines.append(f"extra: {extra}")
    await message.bot.send_message(settings.bot.CHAT_LOG_ID, "\n".join(lines))