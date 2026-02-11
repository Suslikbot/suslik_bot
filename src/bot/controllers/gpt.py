from sqlalchemy.ext.asyncio import AsyncSession
from openai import NotFoundError
from bot.ai_client import AIClient
from database.models import User


async def get_or_create_ai_thread(
    user: User,
    openai_client: AIClient,
    db_session: AsyncSession,
) -> str:
    if user.ai_thread:
        try:
            await openai_client.client.beta.threads.retrieve(user.ai_thread)
            return user.ai_thread
        except NotFoundError:
            user.ai_thread = None
            db_session.add(user)
            await db_session.flush()

    thread_id = await openai_client.new_thread()
    user.ai_thread = thread_id
    db_session.add(user)
    await db_session.flush()
    return thread_id
