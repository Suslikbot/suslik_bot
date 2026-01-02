# start_variants.py

from random import randint
from asyncio import sleep
from aiogram.types import FSInputFile
from aiogram.utils.chat_action import ChatActionSender
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton
)
from logging import getLogger

from aiogram import Router
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
router = Router()
logger = getLogger(__name__)

async def onboarding_1(
    message,
    state,
    user,
    db_session,
    replies,
    ask_next_question,
    imitate_typing,
    Form,
    AIState,
):
    start_file_path = "src/bot/data/start.png"

    await message.answer_photo(FSInputFile(path=start_file_path))

    async with ChatActionSender.typing(
        bot=message.bot,
        chat_id=message.chat.id
    ):
        if not user.is_context_added:
            await sleep(1)
            await message.answer(replies[0].format(fullname=user.fullname))

            random_index = randint(0, 9)
            await state.update_data(question_index=random_index)

            await imitate_typing()
            field, question = await ask_next_question(user, random_index)

            await state.set_state(getattr(Form, field))
            await message.answer(question)

        else:
            await sleep(1)
            await message.answer(replies[1].format(fullname=user.fullname))

            user.is_context_added = True
            db_session.add(user)
            await db_session.flush()

            await imitate_typing()
            await state.set_state(AIState.IN_AI_DIALOG)


async def onboarding_2(
    message,
    state,
    user,
    db_session,
    replies,
    ask_next_question,
    imitate_typing,
    Form,
    AIState,
):
    await message.answer("👋 Привет! Начнём по-другому")

    await imitate_typing()

    await state.set_state(AIState.IN_AI_DIALOG)

async def onboarding_3(
    message,
    state,
    user,
    db_session,
    replies,
    ask_next_question,
    imitate_typing,
    Form,
    AIState,
):
    # await state.clear()
    text = (
        "Я твой карманный эксперт по растениям: вижу их состояние, "
        "нахожу болезни и знаю, как помочь им расти быстрее и лучше.\n\n"
        "Давай проверим любое твое растение прямо сейчас.\n"
        "Отправь мне фото (желательно при хорошем свете) 👇"
    )
    user.is_context_added = True
    start_keyboard  = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📸 Отправить фото", callback_data="onb:send_photo")],
        [InlineKeyboardButton(text="🚫 Нет растения под рукой? Попробуй Демо", callback_data="onb:demo")]
    ])

    await message.answer(
        text=text,
        reply_markup=start_keyboard
    )

    await imitate_typing()

    # await state.set_state(AIState.IN_AI_DIALOG)


ONBOARDING_VARIANTS = {
    "onboarding_1": onboarding_1,
    "onboarding_2": onboarding_2,
    "onboarding_3": onboarding_3,
}
