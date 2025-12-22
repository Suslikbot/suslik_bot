from logging import getLogger
from random import choice

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, LabeledPrice, Message
from aiogram.utils.chat_action import ChatActionSender
from dateutil.relativedelta import relativedelta
from sqlalchemy.ext.asyncio import AsyncSession

from bot.ai_client import AIClient
from bot.config import Settings
from bot.controllers.base import imitate_typing
from bot.controllers.user import (
    ask_next_question,
    generate_user_context,
    get_user_from_db_by_tg_id,
    update_user_expiration,
)
from bot.controllers.voice import extract_text_from_message
from bot.internal.enums import AIState, Form, PaidEntity
from bot.internal.lexicon import ORDER, REACTIONS, payment_text
from database.models import Payment, User

router = Router()
logger = getLogger(__name__)


@router.message(StateFilter(Form), F.text | F.voice)
async def form_handler(
    message: Message,
    user: User,
    state: FSMContext,
    db_session: AsyncSession,
    openai_client: AIClient,
):
    current_state = await state.get_state()
    field = current_state.split(":")[-1]

    user_answer = await extract_text_from_message(message, openai_client)
    if not user_answer:
        return

    setattr(user, field, user_answer)
    db_session.add(user)
    await db_session.flush()
    data = await state.get_data()
    question_index = data.get("question_index", choice(list(REACTIONS[field].keys())))
    reaction = REACTIONS[field][question_index].format(**{field: user_answer})

    async with ChatActionSender.typing(bot=message.bot, chat_id=message.chat.id):
        await imitate_typing()
        await message.answer(reaction)
        await imitate_typing()

        if all(getattr(user, f) for f in ORDER):
            await state.clear()
            user_context = generate_user_context(user)
            # if not user.ai_thread:
            #     await openai_client.apply_context_to_thread(user, user_context, db_session)
            # else:
            await openai_client.apply_context_to_thread(user, user_context, db_session, use_existing_thread=True)
            await imitate_typing()
            msg = await message.answer_photo(
                FSInputFile(path="src/bot/data/magic_wand.png"),
                payment_text["capability"],
            )
            await msg.pin(disable_notification=True)
            await imitate_typing()
            await message.answer(payment_text["free actions"])
            await state.set_state(AIState.IN_AI_DIALOG)
        else:
            next_field, next_question = await ask_next_question(user, question_index)
            await state.set_state(getattr(Form, next_field))
            await state.update_data(question_index=question_index)
            await imitate_typing()
            await message.answer(next_question)


# @router.message(Command("settings"))
# async def command_settings_handler(
#     message: Message,
#     user: User,
#     state: FSMContext,
# ) -> None:
#     if user.is_context_added:
#         await message.answer('[вот тут нужен правильный текст] Чтобы добавить настройки в контекст диалога, нужно пройти короткий опрос. Начать опрос?',
#                              reply_markup=new_dialog_kb())
#     else:
#         start_file_path = "src/bot/data/start.png"
#         await message.answer_photo(
#             FSInputFile(path=start_file_path),
#         )
#         async with ChatActionSender.typing(bot=message.bot, chat_id=message.chat.id):
#             await sleep(1)
#             await message.answer(replies[1])
#             await imitate_typing()
#
#             field, question = await ask_next_question(user, randint(0, 9))
#             await state.set_state(getattr(Form, field))
#             await message.answer(question)


# @router.callback_query(NewDialogCallbackFactory.filter())
# async def dialog_handler(
#     callback: CallbackQuery,
#     callback_data: NewDialogCallbackFactory,
#     state: FSMContext,
#     user: User,
#     db_session: AsyncSession,
# ) -> None:
#     await callback.answer()
#     match callback_data.choice:
#         case MenuButtons.YES:
#             await callback.message.delete()
#             await state.clear()
#             user.is_context_added = False
#             user.ai_thread = None
#             user.budget = None
#             user.space = None
#             user.geography = None
#             user.style = None
#             db_session.add(user)
#             await db_session.flush()
#             start_file_path = "src/bot/data/start.png"
#             await callback.message.answer_photo(
#                 FSInputFile(path=start_file_path),
#             )
#             async with ChatActionSender.typing(bot=callback.message.bot, chat_id=callback.message.chat.id):
#                 await sleep(1)
#                 await callback.message.answer(replies[1])
#                 await sleep(1)
#                 field, question = await ask_next_question(user, randint(0, 9))
#                 await state.set_state(getattr(Form, field))
#                 await callback.message.answer(question)
#         case MenuButtons.NO:
#             await callback.message.delete()


@router.message(F.user_shared)
async def contact_handler(message: Message, settings: Settings, db_session: AsyncSession):
    # await message.delete_reply_markup()
    contact = message.users_shared.user_ids[0]
    target_user = await get_user_from_db_by_tg_id(contact, db_session)
    if not target_user:
        await message.answer(payment_text["gift_sub_no_user"])
        return
    await message.answer_invoice(
        title="Подписка",
        description=payment_text["gift_sub_user"].format(target_user.fullname),
        payload=PaidEntity.ONE_YEAR_GIFT_SUBSCRIPTION + ">" + str(contact),
        currency="RUB",
        prices=[LabeledPrice(label="Подписка на год в подарок", amount=3900 * 100)],
        provider_token=settings.shop.PROVIDER_TOKEN.get_secret_value(),
    )


@router.message(F.successful_payment)
async def on_successful_payment(
    message: Message,
    user: User,
    settings: Settings,
    db_session: AsyncSession,
):
    payload = message.successful_payment.invoice_payload
    target_user_id = int(payload.split(">")[1])
    amount = int(message.successful_payment.total_amount / 100)
    payment = Payment(
        payment_id=message.successful_payment.provider_payment_charge_id,
        user_tg_id=user.tg_id,
        price=amount,
        description=payload,
        is_paid=True,
    )
    db_session.add(payment)
    await db_session.flush()
    target_user = await get_user_from_db_by_tg_id(target_user_id, db_session)
    await update_user_expiration(target_user, relativedelta(years=1), db_session)
    await message.answer(payment_text["gift_sub_report_to_buyer"].format(username=target_user.fullname))
    await message.bot.send_message(
        target_user_id,
        payment_text["gift_sub_report_to_receiver"],
    )
    await message.bot.send_message(
        settings.bot.CHAT_LOG_ID,
        payment_text["user_gift_payment_log"].format(
            username=user.fullname,
            target_username=target_user.fullname,
            amount=amount,
        ),
    )
    logger.info(f"Successful gift subscription from {user.fullname} to {target_user.fullname}")


import re

def extract_health_score(text: str) -> int | None:
    """
    Ищет 'Health Score: ... X/10'
    """
    match = re.search(r'(\d{1,2})/10', text)
    if not match:
        return None
    return int(match.group(1))
