import logging
from datetime import UTC, datetime

from aiogram.types import User
from dateutil.relativedelta import relativedelta
from sqlalchemy import Result, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.internal.lexicon import ORDER, QUESTIONS
from database.models import User as BotUser
from database.models import UserCounters

logger = logging.getLogger(__name__)

# new function add_user_to_db
async def add_user_to_db(user, db_session: AsyncSession, source: str | None = None) -> BotUser:
    new_user = BotUser(
        tg_id=user.id,
        fullname=user.full_name,
        username=compose_username(user),
        source=source,
    )
    try:
        async with db_session.begin_nested():
            db_session.add(new_user)
            await db_session.flush()
    except IntegrityError:
        existing_user = await get_user_from_db_by_tg_id(user.id, db_session)
        if existing_user:
            logger.info("User already exists, returning existing record: %s", existing_user)
            return existing_user
        raise
    logger.info("New user created: %s", new_user)
    return new_user



async def get_user_from_db_by_tg_id(telegram_id: int, db_session: AsyncSession) -> BotUser | None:
    query = select(BotUser).filter(BotUser.tg_id == telegram_id)
    result: Result = await db_session.execute(query)
    return result.scalar_one_or_none()


async def update_user_expiration(user: BotUser, duration: relativedelta, db_session: AsyncSession):
    current_time = datetime.now(UTC)
    if user.expired_at is None or user.expired_at <= current_time:
        user.expired_at = current_time + duration
    else:
        user.expired_at = current_time + duration
    user.is_subscribed = True
    db_session.add(user)
    logger.info(f"Subscription for {user.tg_id} prolonged to {user.expired_at}")
    return user.expired_at


def compose_username(user: User):
    return "@" + user.username if user.username else user.full_name.replace(" ", "_")


async def ask_next_question(user: User, index: int) -> tuple:
    for field in ORDER:
        if getattr(user, field) is None:
            question = QUESTIONS[field][index]
            return field, question
    return None, None


def generate_user_context(user: BotUser) -> str:
    return (
        "Контекст пользователя:\n"
        f"- Имя пользователя: {user.fullname}\n"
        f"- Тип участка: {user.space or 'не указано'}\n"
        f"- Местоположение: {user.geography or 'не указано'}\n"
        f"- Запрос пользователя: {user.request or 'не указано'}\n"
    )


async def get_user_counter(telegram_id: int, db_session: AsyncSession) -> UserCounters:
    query = select(UserCounters).filter(UserCounters.tg_id == telegram_id)
    counter = await db_session.execute(query)
    counter = counter.scalar_one_or_none()
    if not counter:
        counter = UserCounters(tg_id=telegram_id)
        db_session.add(counter)
        await db_session.flush()
    return counter


async def reset_user_image_counter(telegram_id: int, db_session: AsyncSession):
    user_counter: UserCounters = await get_user_counter(telegram_id, db_session)
    user_counter.image_count = 0
    await db_session.flush()


async def get_all_users_with_active_subscription(
    db_session: AsyncSession,
) -> list[BotUser]:
    now = datetime.now(UTC)
    query = select(BotUser).where(
        BotUser.is_subscribed.is_(True),
        BotUser.expired_at.isnot(None),
        BotUser.expired_at > now,
    )
    result = await db_session.execute(query)
    return list(result.scalars().all())


def check_action_limit(user: BotUser, settings: Settings) -> bool:
    if user.tg_id in settings.bot.ADMINS:
        return True
    if not user.is_subscribed and user.action_count >= settings.bot.ACTIONS_THRESHOLD:
        return False
    return True
