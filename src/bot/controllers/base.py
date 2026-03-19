import logging
import re
from asyncio import sleep
from datetime import UTC, datetime, timedelta
from random import randint

from aiogram import Bot, Dispatcher
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.controllers.payments import create_recurrent_payment
from bot.controllers.user import (
    get_all_users_with_active_subscription,
    get_user_counter,
)
from bot.internal.consts import BLOCK_DURATION, MAX_MESSAGE_LENGTH
from bot.internal.enums import PaidEntity, PaymentType
from bot.internal.keyboards import subscription_kb
from bot.internal.lexicon import support_text
from database.database_connector import DatabaseConnector
from database.models import Payment

logger = logging.getLogger(__name__)


def escape_markdown_v2(string: str) -> str:
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    return re.sub(r"([%s])" % re.escape(escape_chars), r"\\\1", string)


def escape_stars(s):
    process = s.split("**")
    return "*".join([escape_markdown_v2(i) for i in process])


def extract_content(messages: list[dict[str, str]]) -> str:
    return " ".join(message["content"] for message in messages)


def starts_with_hash_space(s: str) -> bool:
    pattern = r"^#+\s"
    return bool(re.match(pattern, s))


def refactor_string(string: str) -> str:
    lines = string.splitlines()
    indices_to_wrap = []

    for i, line in enumerate(lines):
        if starts_with_hash_space(line):
            lines[i] = re.sub(r"^#+\s", "", line)
            indices_to_wrap.append(i)
        lines[i] = escape_stars(lines[i])

    for i in indices_to_wrap:
        lines[i] = f"*{lines[i]}*"

    return "\n".join(lines)


async def imitate_typing(delay_from=1, delay_to=3):
    await sleep(randint(delay_from, delay_to))


def get_seconds_until_starting_mark(sttngs: Settings, utcnow):
    mark = utcnow.replace(hour=sttngs.bot.UTC_STARTING_MARK, minute=0, second=0, microsecond=0)
    if utcnow >= mark:
        mark += timedelta(days=1)
    return (mark - utcnow).total_seconds()


async def daily_routine(
    bot: Bot,
    sttngs: Settings,
    dispatcher: Dispatcher,
    db_connector: DatabaseConnector,
):
    while True:
        utcnow = datetime.now(UTC)
        seconds_to_sleep = get_seconds_until_starting_mark(sttngs, utcnow)
        await sleep(seconds_to_sleep)
        async with db_connector.session_factory() as session:
            for user in await get_all_users_with_active_subscription(session):
                days_left = (user.expired_at.date() - utcnow.date()).days
                if not user.is_autopayment_enabled:
                    storage = dispatcher.fsm.storage
                    me = await bot.get_me()
                    bot_id = me.id
                    key = StorageKey(bot_id=bot_id, chat_id=user.tg_id, user_id=user.tg_id)
                    fsm_context = FSMContext(storage=storage, key=key)
                    data = await fsm_context.get_data()
                    notified_days = data.get("notified_days", [])
                    if days_left in (2, 0) and days_left not in notified_days:
                        if days_left == 2:
                            await bot.send_message(
                                chat_id=user.tg_id,
                                text=support_text["subscription_2_days_left"],
                                reply_markup=subscription_kb(prolong=True),
                                disable_notification=True,
                            )
                            logger.info(f"ending subscription reminder was sent to {user}")

                        elif days_left == 0:
                            user.is_subscribed = False
                            user.expired_at = None
                            user.subscription_duration = None
                            await bot.send_message(
                                chat_id=user.tg_id,
                                text=support_text["subscription_0_days_left"],
                                reply_markup=subscription_kb(prolong=True),
                                disable_notification=True,
                            )
                            logger.info(f"ending subscription notification was sent to {user}")

                        notified_days.append(days_left)
                        await fsm_context.update_data(notified_days=notified_days)

                    await sleep(0.1)
                elif days_left == 0:
                    if user.subscription_duration == PaidEntity.ONE_MONTH_SUBSCRIPTION:
                        duration = "1 месяц"
                        amount = 390
                    elif user.subscription_duration == PaidEntity.ONE_YEAR_SUBSCRIPTION:
                        duration = "1 год"
                        amount = 3900
                    else:
                        return
                    description_text = f"Оплата подписки, длительность: {duration}."
                    payment = await create_recurrent_payment(
                        amount,
                        description_text,
                        user.tg_id,
                        user.subscription_duration,
                        user.payment_method_id,
                    )
                    new_payment = Payment(
                        payment_id=payment.id,
                        user_tg_id=user.tg_id,
                        description=description_text,
                        payment_type=PaymentType.RECURRENT,
                        price=amount,
                    )
                    if payment.status == "succeeded":
                        logger.info(f"payment for {user} was successful")
                    else:
                        logger.error(f"error with payment for {user}: {payment.status}")
                    session.add(new_payment)
            await session.commit()


async def validate_message_length(
    message: Message,
    state: FSMContext,
) -> bool:
    raw_text = message.text or message.caption or ""
    now = datetime.now(UTC)
    data = await state.get_data()
    block_until = data.get("block_until")

    if block_until and now < block_until:
        return False

    if len(raw_text) >= MAX_MESSAGE_LENGTH:
        await state.update_data(block_until=now + BLOCK_DURATION)
        return False

    await state.update_data(block_until=None)
    return True


async def validate_image_limit(telegram_id: int, settings: Settings, db_session: AsyncSession) -> bool:
    now = datetime.now(UTC)
    counter = await get_user_counter(telegram_id, db_session)

    if counter.period_started_at is None:
        counter.period_started_at = now
        counter.image_count = 1
        await db_session.flush()
        return True

    db_time = counter.period_started_at
    if db_time.tzinfo is None:
        db_time = db_time.replace(tzinfo=UTC)

    if now - db_time > timedelta(days=settings.bot.PICTURES_WINDOW_DAYS):
        counter.period_started_at = now
        counter.image_count = 1
        await db_session.flush()
        return True

    if counter.image_count >= settings.bot.PICTURES_THRESHOLD:
        return False

    counter.image_count += 1
    await db_session.flush()
    return True
