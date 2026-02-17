from sqlalchemy.ext.asyncio import AsyncSession
from bot.ai_client import AIClient
from database.models import User


async def get_or_create_ai_thread(
    user: User,
    openai_client: AIClient,
    db_session: AsyncSession,
) -> str | None:
    del openai_client
    del db_session
    return user.ai_thread
