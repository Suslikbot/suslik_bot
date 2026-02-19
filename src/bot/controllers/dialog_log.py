from sqlalchemy.ext.asyncio import AsyncSession

from database.models import BotResponseLog, User, UserRequestLog


async def log_user_request(user: User, request_text: str, db_session: AsyncSession) -> UserRequestLog:
    request_log = UserRequestLog(
        user_tg_id=user.tg_id,
        request_text=request_text,
    )
    db_session.add(request_log)
    await db_session.flush()
    return request_log


async def log_bot_response(
    user: User,
    response_text: str,
    db_session: AsyncSession,
    user_request_log_id: int | None = None,
) -> None:
    db_session.add(
        BotResponseLog(
            user_tg_id=user.tg_id,
            response_text=response_text,
            user_request_log_id=user_request_log_id,
        )
    )
    await db_session.flush()