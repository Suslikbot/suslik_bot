from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from aiogram import Bot
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings

if TYPE_CHECKING:
    from database.database_connector import DatabaseConnector


async def get_bot(request: Request) -> Bot:
    return request.app.state.bot


async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    db: DatabaseConnector = request.app.state.db
    async for session in db.session_getter():
        yield session


async def get_settings(request: Request) -> Settings:
    return request.app.state.settings
