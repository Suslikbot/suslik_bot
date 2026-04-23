from asyncio import sleep
from datetime import datetime, timedelta
from html import escape
from logging import getLogger
from random import randint

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message
from aiogram.utils.chat_action import ChatActionSender
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from bot.config import Settings
from bot.controllers.statistics import (
    build_stats_snapshot,
    list_stat_log_paths,
    iter_stat_events,
    build_stat_message,
)
from bot.controllers.base import imitate_typing
from bot.controllers.user import ask_next_question, get_user_counter
from bot.internal.enums import AIState, Form, SupportState
from bot.internal.keyboards import support_kb, support_request_kb
from bot.internal.lexicon import replies, support_text, WELCOME_BY_SOURCE
from database.models import User, UserCounters
from sqlalchemy import select
from bot.onboarding.start_variants import ONBOARDING_VARIANTS
from dateutil.relativedelta import relativedelta





router = Router()
logger = getLogger(__name__)

async def restore_support_context(state: FSMContext, support_context: dict) -> None:
    previous_state = support_context.get("support_prev_state")
    previous_data = support_context.get("support_prev_data") or {}
    if previous_state:
        await state.set_state(previous_state)
        await state.set_data(previous_data)
    else:
        await state.clear()


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
            logger.info(build_stat_message("Start_bot", user.tg_id))
            current_state = await state.get_state()

            if current_state in {
                AIState.WAITING_PLANT_PHOTO,
                AIState.WAITING_CITY,
                Form.space,
                Form.geography,
                Form.request,
            }:
                start_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📸 Отправить фото", callback_data="onb:send_photo")],
                    [InlineKeyboardButton(text="🚫 Нет растения под рукой? Попробуй Демо", callback_data="onb:demo")],
                ])
                await message.answer(
                    "Мы уже начали знакомство! 👀\n"
                    "Продолжай — я жду твой ответ или фото.",
                    reply_markup=start_keyboard,
                )
                return
            source = user.source or "default"
            cfg = WELCOME_BY_SOURCE.get(source, WELCOME_BY_SOURCE["default"])

            if cfg.get("photo"):
                await message.answer_photo(FSInputFile(cfg["photo"]))

            if cfg.get("text"):
                await message.answer(cfg["text"].format(fullname=user.fullname))

            if user.is_context_added:
                await state.set_state(AIState.IN_AI_DIALOG)
                await message.answer(
                    "Мы уже знакомы 🌿\n"
                    "Просто задай вопрос или пришли фото растения."
                )
                return

            variant = cfg.get("onboarding", "onboarding_3")
            if variant not in ONBOARDING_VARIANTS:
                logger.warning(
                    "Unknown onboarding variant '%s' for source '%s'; fallback to onboarding_3",
                    variant,
                    source,
                )
                variant = "onboarding_3"
            await ONBOARDING_VARIANTS[variant](
                message=message,
                state=state,
                user=user,
                db_session=db_session,
                settings=settings,
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
                    photo=picture,
                    caption=support_text["subscribed"].format(days=days, photos=photos),
                    reply_markup=support_kb(is_subscribed=True),
                )
            else:
                await message.answer_photo(
                    photo=picture,
                    caption=support_text["unsubscribed"].format(
                        actions=(settings.bot.ACTIONS_THRESHOLD - user.action_count)),
                    reply_markup=support_kb(is_subscribed=False),
                )
        case "share":
            await message.answer("Выберите, кому хотите подарить подписку", reply_markup=contact_kb)

@router.callback_query(F.data == "support:write")
async def start_support_request(callback: CallbackQuery, state: FSMContext) -> None:
    previous_state = await state.get_state()
    previous_data = await state.get_data()
    if previous_state != SupportState.WAITING_REQUEST_TEXT.state:
        await state.update_data(
            support_prev_state=previous_state,
            support_prev_data=previous_data,
        )
    await state.set_state(SupportState.WAITING_REQUEST_TEXT)
    await callback.message.answer(
        support_text["request_prompt"],
        reply_markup=support_request_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "support:cancel")
async def cancel_support_request(callback: CallbackQuery, state: FSMContext) -> None:
    support_context = await state.get_data()
    await restore_support_context(state, support_context)
    await callback.message.answer(support_text["request_cancelled"])
    await callback.answer()


@router.message(SupportState.WAITING_REQUEST_TEXT, F.text)
async def receive_support_request(
    message: Message,
    user: User,
    settings: Settings,
    state: FSMContext,
) -> None:
    support_context = await state.get_data()
    support_chat_id = settings.bot.SUPPORT_CHAT_ID
    if support_chat_id is None:
        logger.error("SUPPORT_CHAT_ID is not configured, support request from user %s was not forwarded", user.tg_id)
        await message.answer("⚠️ Поддержка временно недоступна. Попробуйте позже.")
        return
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
    username = f"@{user.username}" if user.username else "без username"
    request_text = escape(message.text)
    try:
        await message.bot.send_message(
            chat_id=support_chat_id,
            text=(
                "🆘 <b>Новое обращение в поддержку</b>\n"
                f"👤 <b>Пользователь:</b> {escape(user.fullname)} ({username})\n"
                f"🆔 <b>TG ID:</b> <code>{user.tg_id}</code>\n"
                f"🕒 <b>Время:</b> {timestamp}\n\n"
                f"💬 <b>Текст обращения:</b>\n{request_text}"
            ),
        )
    except Exception:
        logger.exception("Failed to send support request to chat %s for user %s", support_chat_id, user.tg_id)
        await message.answer(
            support_text["request_send_error"],
            reply_markup=support_request_kb(),
        )
        return

    await restore_support_context(state, support_context)
    await message.answer(support_text["request_sent"])


@router.message(SupportState.WAITING_REQUEST_TEXT)
async def receive_support_request_non_text(message: Message) -> None:
    await message.answer(support_text["request_text_only"])




@router.message(Command("static"))
async def stats_handler(
    message: Message,
    settings: Settings,
    db_session: AsyncSession,
) -> None:
    if message.from_user.id not in settings.bot.ADMINS:
        await message.answer("❌ У вас нет прав на просмотр статистики")
        return

    now = datetime.now().astimezone()
    current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    events = iter_stat_events(list_stat_log_paths())
    periods = [
        ("За все время", None, now),
        ("За последние 2 месяца", now - relativedelta(months=2), now),
        ("За текущий месяц", current_month_start, now),
        ("За последнюю неделю", now - timedelta(days=7), now),
    ]

    sections: list[str] = ["📊 Статистика"]
    for title, start_at, end_at in periods:
        stats = build_stats_snapshot(events, start_at, end_at)
        sections.append(
            "\n".join(
                [
                    "",
                    f"{title}:",
                    f"- Start_bot: {stats.start_bot}",
                    f"- Photo_upload (первое фото): {stats.photo_upload}",
                    f"- Paywall_view: {stats.paywall_view}",
                    f"- Payment_success: {stats.payment_success}",
                    f"- Diagnosis_result: {stats.diagnosis_result}",
                ]
            )
        )

    await message.answer("\n".join(sections))


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
