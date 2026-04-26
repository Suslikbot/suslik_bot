# start_variants.py

from asyncio import sleep
from logging import getLogger
from random import randint

from aiogram import Router
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.chat_action import ChatActionSender

from bot.controllers.onboarding_log import log_onboarding_step

router = Router()
logger = getLogger(__name__)

async def onboarding_1(  # noqa: PLR0913
    message,
    state,
    user,
    db_session,
    replies,
    ask_next_question,
    imitate_typing,
    Form, # noqa: N803
    AIState, # noqa: N803
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

            random_index = randint(0, 9) # noqa: S311
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
    imitate_typing,
    AIState, # noqa: N803
):
    await message.answer("👋 Привет! Начнём по-другому")

    await imitate_typing()

    await state.set_state(AIState.IN_AI_DIALOG)

async def onboarding_3( # noqa: PLR0913
    message,
    state,
    user,
    settings,
    imitate_typing,
    AIState, # noqa: N803
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
        text = text,
        reply_markup=start_keyboard,
    )
    await state.update_data(wait_reason="onboarding_plant_photo")
    await state.set_state(AIState.WAITING_PLANT_PHOTO)
    await log_onboarding_step(
        message=message,
        state=state,
        user=user,
        settings=settings,
        step="start_screen_shown",
    )
    await imitate_typing()

    # await state.set_state(AIState.IN_AI_DIALOG)


ONBOARDING_VARIANTS = {
    "onboarding_1": onboarding_1,
    "onboarding_2": onboarding_2,
    "onboarding_3": onboarding_3,
}
