from asyncio import sleep
from datetime import datetime
from logging import getLogger
from random import randint

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, Message
from aiogram.utils.chat_action import ChatActionSender
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.controllers.base import imitate_typing
from bot.controllers.user import ask_next_question, get_user_counter
from bot.internal.enums import AIState, Form
from bot.internal.keyboards import cancel_autopayment_kb, subscription_kb
from bot.internal.lexicon import replies, support_text
from database.models import User, UserCounters

router = Router()
logger = getLogger(__name__)


@router.message(Command("start", "support", "share"))
async def command_handler(
    message: Message,
    command: CommandObject,
    user: User,
    settings: Settings,
    state: FSMContext,
    db_session: AsyncSession,
) -> None:
    match command.command:
        case "start":
            # start_file_path = "src/bot/data/start.png"
            # await message.answer_photo(
            #    FSInputFile(path=start_file_path),
            #)
            async with ChatActionSender.typing(bot=message.bot, chat_id=message.chat.id):
                if not user.is_context_added:
                    await sleep(1)
                    await message.answer(replies[0].format(fullname=user.fullname))
                    # random_index = randint(0, 9)
                    # await state.update_data(question_index=random_index)
                    # await imitate_typing()
                    # field, question = await ask_next_question(user, random_index)
                    # await state.set_state(getattr(Form, field))
                    # await message.answer(question)
                    await imitate_typing()
                    await state.set_state(AIState.IN_AI_DIALOG)
                else:
                    await sleep(1)
                    await message.answer(replies[1].format(fullname=user.fullname))
                    # user.is_context_added = True
                    # db_session.add(user)
                    # await db_session.flush()
                    await imitate_typing()
                    await state.set_state(AIState.IN_AI_DIALOG)
        case "support":
            picture = FSInputFile(path="src/bot/data/with_book.png")
            if user.is_subscribed and user.expired_at and user.expired_at > datetime.now(user.expired_at.tzinfo):
                current_date = datetime.now(user.expired_at.tzinfo)
                days = (user.expired_at.date() - current_date.date()).days
                user_counter: UserCounters = await get_user_counter(user.tg_id, db_session)
                photos = settings.bot.PICTURES_THRESHOLD - user_counter.image_count
                await message.answer_photo(
                    picture,
                    support_text["subscribed"].format(days=days, photos=photos),
                    reply_markup=cancel_autopayment_kb(),
                )
            else:
                await message.answer_photo(
                    picture,
                    support_text["unsubscribed"].format(actions=(settings.bot.ACTIONS_THRESHOLD - user.action_count)),
                    reply_markup=subscription_kb(),
                )
        case "share":
            await message.answer("Выберите, кому хотите подарить подписку", reply_markup=contact_kb)
