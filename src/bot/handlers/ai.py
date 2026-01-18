from logging import getLogger

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, Message
from aiogram.utils.chat_action import ChatActionSender
from openai import BadRequestError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.ai_client import AIClient
from bot.config import Settings
from bot.controllers.base import (
    refactor_string,
    validate_image_limit,
    validate_message_length,
)
from bot.controllers.gpt import get_or_create_ai_thread
from bot.controllers.user import check_action_limit
from bot.controllers.voice import process_voice

#  from bot.handlers.base import extract_health_score
from bot.internal.enums import AIState
from bot.internal.keyboards import refresh_pictures_kb, subscription_kb
from bot.internal.lexicon import replies
from database.models import User

router = Router()
logger = getLogger(__name__)


def split_markdown_message(text: str, limit: int = 3500) -> list[str]:
    """
    Split MarkdownV2 text into chunks below limit, trying to cut on paragraph/line boundaries.
    Avoid cutting inside italic spans (*...*) and avoid leaving trailing backslashes.
    """
    chunks: list[str] = []
    current: str = ""

    def find_split_position(block: str) -> int:
        if len(block) <= limit:
            return len(block)

        # ranges of italic spans to avoid splitting inside
        italic_spans: list[tuple[int, int]] = []
        start = 0
        while True:
            open_idx = block.find("*", start)
            if open_idx == -1 or (open_idx > 0 and block[open_idx - 1] == "\\"):
                break
            close_idx = block.find("*", open_idx + 1)
            while close_idx != -1 and block[close_idx - 1] == "\\":
                close_idx = block.find("*", close_idx + 1)
            if close_idx == -1:
                break
            italic_spans.append((open_idx, close_idx))
            start = close_idx + 1

        split_at = block.rfind(" ", 0, limit)
        if split_at <= 0:
            split_at = limit

        def inside_italic(pos: int) -> bool:
            for s, e in italic_spans:
                if s < pos < e:
                    return True
            return False

        if inside_italic(split_at):
            # move split before the italic span
            spans_before = [span for span in italic_spans if span[0] < split_at]
            if spans_before:
                target = spans_before[-1][0]
                split_at = block.rfind(" ", 0, target)
                if split_at <= 0:
                    split_at = target

        # avoid ending with a lone backslash
        while split_at > 0 and block[split_at - 1] == "\\":
            split_at -= 1

        if split_at <= 0:
            split_at = limit
        return split_at

    for paragraph in text.split("\n\n"):
        candidate = paragraph if not current else current + "\n\n" + paragraph
        if len(candidate) <= limit:
            current = candidate
            continue

        if current:
            chunks.append(current)
        current = paragraph

        while len(current) > limit:
            split_at = find_split_position(current)
            chunks.append(current[:split_at].rstrip())
            current = current[split_at:].lstrip("\n ")

    if current:
        chunks.append(current)

    return chunks

'''
@router.message(AIState.IN_AI_DIALOG, F.photo)
async def ai_assistant_photo_handler(
    message: Message,
    openai_client: AIClient,
    user: User,
    settings: Settings,
    db_session: AsyncSession,
    forced_user_text: str | None = None,
):
    if not check_action_limit(user, settings):
        await message.forward(settings.bot.CHAT_LOG_ID)
        await message.answer_photo(
            FSInputFile(path="src/bot/data/greetings.png"),
            replies["action_limit_exceeded"],
            reply_markup=subscription_kb(),
        )
        log_text = replies["action_limit_exceeded_log"].format(username=user.username)
        logger.info(log_text)
        await message.bot.send_message(settings.bot.CHAT_LOG_ID, log_text)
        return

    if not await validate_message_length(message, state):
        await message.answer(replies["message_lenght_limit_exceeded"])
        logger.info(replies["message_lenght_limit_exceeded_log"].format(username=user.username))
        return

    thread_id = await get_or_create_ai_thread(user, openai_client, db_session)
    await message.forward(settings.bot.CHAT_LOG_ID)

    async with ChatActionSender.typing(bot=message.bot, chat_id=message.chat.id):
        response = await openai_client.get_response(thread_id, message.text, message, user.fullname)
        if response is None:
            return

        cleaned_response = refactor_string(response)
        sent_messages = []
        for chunk in split_markdown_message(cleaned_response):
            msg_answer = await message.answer(chunk, parse_mode=ParseMode.MARKDOWN_V2)
            sent_messages.append(msg_answer)
        for msg in sent_messages:
            await msg.forward(settings.bot.CHAT_LOG_ID)
    if not user.is_subscribed and user.tg_id not in settings.bot.ADMINS:
        user.action_count += 1
    db_session.add(user)
'''

@router.message(AIState.IN_AI_DIALOG, F.voice)
async def ai_assistant_voice_handler(
    message: Message,
    openai_client: AIClient,
    user: User,
    settings: Settings,
    db_session: AsyncSession,
):
    if not check_action_limit(user, settings):
        await message.forward(settings.bot.CHAT_LOG_ID)
        await message.answer_photo(
            photo = FSInputFile(path="src/bot/data/greetings.png"),
            caption=replies["action_limit_exceeded"],
            reply_markup=subscription_kb(),
        )
        log_text = replies["action_limit_exceeded_log"].format(username=user.username)
        logger.info(log_text)
        await message.bot.send_message(settings.bot.CHAT_LOG_ID, log_text)
        return
    thread_id = await get_or_create_ai_thread(user, openai_client, db_session)
    await message.forward(settings.bot.CHAT_LOG_ID)
    async with ChatActionSender.typing(bot=message.bot, chat_id=message.chat.id):
        transcription = await process_voice(message, openai_client)
        response = await openai_client.get_response(thread_id, transcription, message, user.fullname)
        if response is None:
            return
        cleaned_response = refactor_string(response)
        sent_messages = []
        for chunk in split_markdown_message(cleaned_response):
            msg_answer = await message.answer(chunk, parse_mode=ParseMode.MARKDOWN_V2)
            sent_messages.append(msg_answer)
        for msg in sent_messages:
            await msg.forward(settings.bot.CHAT_LOG_ID)
    if not user.is_subscribed and user.tg_id not in settings.bot.ADMINS:
        user.action_count += 1
    db_session.add(user)


@router.message(AIState.IN_AI_DIALOG, F.photo)
async def ai_assistant_photo_handler(
    message: Message,
    state: FSMContext,
    openai_client: AIClient,
    user: User,
    settings: Settings,
    db_session: AsyncSession,
    forced_user_text: str | None = None,
):
    if not check_action_limit(user, settings):
        await message.forward(settings.bot.CHAT_LOG_ID)
        await message.answer_photo(
            photo=FSInputFile(path="src/bot/data/greetings.png"),
            caption=replies["action_limit_exceeded"],
            reply_markup=subscription_kb(),
        )
        log_text = replies["action_limit_exceeded_log"].format(username=user.username)
        logger.info(log_text)
        await message.bot.send_message(settings.bot.CHAT_LOG_ID, log_text)
        return
    if message.media_group_id is not None:
        await message.answer(
            "Пожалуйста, отправляйте только по одному изображению за раз, чтобы я мог корректно ответить."
        )
        return
    if user.tg_id not in settings.bot.ADMINS:
        if not await validate_image_limit(user.tg_id, settings, db_session):
            await message.answer_photo(
                photo=FSInputFile(path="src/bot/data/not_happy.png"),
                caption=replies["photo_limit_exceeded"],
                reply_markup=refresh_pictures_kb(),
            )
            await message.forward(settings.bot.CHAT_LOG_ID)
            await message.bot.send_message(
                settings.bot.CHAT_LOG_ID,
                replies["pictures_limit_exceeded_log"].format(username=user.username),
            )
            return
    thread_id = await get_or_create_ai_thread(user, openai_client, db_session)
    await message.forward(settings.bot.CHAT_LOG_ID)
    user_text = (
        forced_user_text
        if forced_user_text is not None
        else message.caption or "Пользователь отправил изображение без дополнительного текста."
    )
    current_state = await state.get_state()

    if current_state == AIState.WAITING_PLANT_PHOTO:
        user_text = forced_user_text
    else:

        user_text = "Пользователь отправил изображение без дополнительного текста."


    # user_text = message.caption or "Пользователь отправил изображение без дополнительного текста."

    async with ChatActionSender.typing(bot=message.bot, chat_id=message.chat.id):
        try:
            photo = message.photo[-1]
            file_info = await message.bot.get_file(photo.file_id)

            file_bytes = await message.bot.download_file(file_info.file_path)
            image_bytes = file_bytes.read()

            prompt_text = (
                f"{user_text}\n\nОпиши, что на изображении, и ответь пользователю с учётом текущего контекста диалога."
            )
            print(prompt_text)

            response = await openai_client.get_response_with_image(
                thread_id=thread_id,
                text=prompt_text,
                image_bytes=image_bytes,
                message=message,
                fullname=user.fullname,
            )

            if response is None:
                return

            cleaned_response = refactor_string(response)
            sent_messages = []
            for chunk in split_markdown_message(cleaned_response):
                msg_answer = await message.answer(chunk, parse_mode=ParseMode.MARKDOWN_V2)
                sent_messages.append(msg_answer)
            for msg in sent_messages:
                await msg.forward(settings.bot.CHAT_LOG_ID)

        except BadRequestError as e:
            logger.exception(f"OpenAI API Error: {e}")
            if e.status_code == 429:
                await message.answer("Превышены лимиты запросов. Пожалуйста, попробуйте позже.")
            else:
                await message.answer(
                    "Ошибка при обработке изображения. "
                    "Убедитесь, что изображение корректного формата (jpg, png) и попробуйте снова."
                )
        except Exception as e:
            logger.exception(f"Unexpected error: {e}")
            await message.answer("Произошла непредвиденная ошибка. Пожалуйста, попробуйте позже.")

    if user.tg_id not in settings.bot.ADMINS:
        if not user.is_subscribed:
            user.action_count += 1
            db_session.add(user)


@router.message(AIState.IN_AI_DIALOG, F.text)
async def ai_assistant_text_handler(
    message: Message,
    openai_client: AIClient,
    user: User,
    settings: Settings,
    state: FSMContext,
    db_session: AsyncSession,
):
    if not check_action_limit(user, settings):
        await message.forward(settings.bot.CHAT_LOG_ID)
        await message.answer_photo(
            photo = FSInputFile(path="src/bot/data/greetings.png"),
            caption = replies["action_limit_exceeded"],
            reply_markup=subscription_kb(),
        )
        log_text = replies["action_limit_exceeded_log"].format(username=user.username)
        logger.info(log_text)
        await message.bot.send_message(settings.bot.CHAT_LOG_ID, log_text)
        return

    if not await validate_message_length(message, state):
        await message.answer(replies["message_lenght_limit_exceeded"])
        logger.info(replies["message_lenght_limit_exceeded_log"].format(username=user.username))
        return

    thread_id = await get_or_create_ai_thread(user, openai_client, db_session)
    await message.forward(settings.bot.CHAT_LOG_ID)

    async with ChatActionSender.typing(bot=message.bot, chat_id=message.chat.id):
        response = await openai_client.get_response(thread_id, message.text, message, user.fullname)
        if response is None:
            return

        cleaned_response = refactor_string(response)
        sent_messages = []
        for chunk in split_markdown_message(cleaned_response):
            msg_answer = await message.answer(chunk, parse_mode=ParseMode.MARKDOWN_V2)
            sent_messages.append(msg_answer)
        for msg in sent_messages:
            await msg.forward(settings.bot.CHAT_LOG_ID)
    if not user.is_subscribed and user.tg_id not in settings.bot.ADMINS:
        user.action_count += 1
    db_session.add(user)


