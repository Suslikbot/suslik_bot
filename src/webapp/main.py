import logging
from contextlib import asynccontextmanager
from typing import cast

import uvicorn
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from fastapi import FastAPI
from starlette.datastructures import State

from bot.config import get_settings
from bot.internal.helpers import setup_logs
from database.database_connector import get_db
from webapp.webhook import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    session = AiohttpSession()
    settings = get_settings()
    db = get_db(settings)
    bot = Bot(
        token=settings.bot.TOKEN.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )
    me = await bot.get_me()
    app.state.bot_id = me.id
    app.state.bot = bot
    app.state.settings = settings
    app.state.db = db
    yield
    await db.dispose()
    await session.close()


app = FastAPI(lifespan=lifespan)
app.state = cast(State, app.state)


setup_logs("yookassa_webhook", get_settings().bot.STAGE)

app.include_router(router, prefix="/webhook")


def run_main():
    logging.info("webapp started")
    uvicorn.run("webapp.main:app", host="127.0.0.1", port=8080)


if __name__ == "__main__":
    run_main()
