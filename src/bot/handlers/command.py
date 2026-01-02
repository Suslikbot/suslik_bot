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
from bot.internal.lexicon import replies, support_text, WELCOME_BY_SOURCE
from database.models import User, UserCounters
from sqlalchemy import select
from bot.onboarding.start_variants import ONBOARDING_VARIANTS





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
            source = user.source or "default"
            cfg = WELCOME_BY_SOURCE.get(source, WELCOME_BY_SOURCE["default"])

            if cfg.get("photo"):
                await message.answer_photo(FSInputFile(cfg["photo"]))

            if cfg.get("text"):
                await message.answer(cfg["text"].format(fullname=user.fullname))

            current_state = await state.get_state()

            if user.is_context_added:
                await state.set_state(AIState.IN_AI_DIALOG)
                await message.answer(
                    "Мы уже знакомы 🌿\n"
                    "Просто задай вопрос или пришли фото растения."
                )
                return

            if current_state in {
                AIState.WAITING_PLANT_PHOTO,
                AIState.WAITING_CITY,
                Form.space,
                Form.geography,
                Form.request,
            }:
                await message.answer(
                    "Мы уже начали 👀\n"
                    "Продолжай — я жду твой ответ или фото."
                )
                return


            variant = "onboarding_3"  # Change onboarding
            await ONBOARDING_VARIANTS[variant](
                message=message,
                state=state,
                user=user,
                db_session=db_session,
                replies=replies,
                ask_next_question=ask_next_question,
                imitate_typing=imitate_typing,
                Form=Form,
                AIState=AIState,
            )
            '''start_file_path = "src/bot/data/start.png"
            await message.answer_photo(
              FSInputFile(path=start_file_path) )
            async with ChatActionSender.typing(bot=message.bot, chat_id=message.chat.id):
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
                    await state.set_state(AIState.IN_AI_DIALOG) '''

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


@router.message(Command("broadcast"))
async def broadcast_handler(
    message: Message,
    command: CommandObject,
    settings: Settings,
    db_session: AsyncSession,
) -> None:
    if message.from_user.id not in settings.bot.ADMINS:
        await message.answer("❌ У вас нет прав на рассылку")
        return

    text = command.args
    if not text:
        await message.answer(
            "Использование:\n"
            "<code>/broadcast текст сообщения</code>"
        )
        return

    result = await db_session.execute(
        select(User.tg_id)
    )
    user_ids: list[int] = result.scalars().all()

    if not user_ids:
        await message.answer("Пользователи не найдены")
        return

    sent = 0
    failed = 0

    for user_id in user_ids:
        try:
            await message.bot.send_message(user_id, text)
            sent += 1
            await sleep(0.05)
        except Exception:
            failed += 1

    await message.answer(
        "📢 <b>Рассылка завершена</b>\n\n"
        f"👥 Всего пользователей: {len(user_ids)}\n"
        f"✅ Отправлено: {sent}\n"
        f"❌ Ошибок: {failed}"
    )

@router.message(Command("broadcast_photo"))
async def broadcast_photo_handler(
    message: Message,
    settings: Settings,
    db_session: AsyncSession,
) -> None:
    if message.from_user.id not in settings.bot.ADMINS:
        await message.answer("❌ У вас нет прав на рассылку")
        return

    if not message.reply_to_message or not message.reply_to_message.photo:
        await message.answer(
            "Использование:\n"
            "Ответьте командой <code>/broadcast_photo</code> "
            "на сообщение с картинкой"
        )
        return

    photo = message.reply_to_message.photo[-1]
    caption = message.reply_to_message.caption or ""

    result = await db_session.execute(
        select(User.tg_id)
    )
    user_ids = result.scalars().all()

    sent = 0
    failed = 0

    for user_id in user_ids:
        try:
            await message.bot.send_photo(
                chat_id=user_id,
                photo=photo.file_id,
                caption=caption,
            )
            sent += 1
            await sleep(0.05)
        except Exception:
            failed += 1

    await message.answer(
        "📢 <b>Рассылка с картинкой завершена</b>\n\n"
        f"👥 Всего: {len(user_ids)}\n"
        f"✅ Отправлено: {sent}\n"
        f"❌ Ошибок: {failed}"
    )
