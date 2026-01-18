import logging
import traceback
from html import escape
import aiogram
from aiogram import Router
from aiogram.types import ErrorEvent

from bot.config import Settings

router = Router()


@router.errors()
async def error_handler(error_event: ErrorEvent, bot: aiogram.Bot, settings: Settings):
    exc_info = error_event.exception
    exc_traceback = "".join(
        traceback.format_exception(None, exc_info, exc_info.__traceback__),
    )
    tb = exc_traceback[-3500:]
    safe_traceback = escape(tb)
    safe_message = escape(str(exc_info))
    error_message = (
        f"🚨 <b>An error occurred</b> 🚨\n\n"
        f"<b>Type:</b> {type(exc_info).__name__}\n"
        f"<b>Message:</b> {safe_message}\n\n"
        f"<b>Traceback:</b>\n<code>{safe_traceback}</code>"
    )
    logging.exception("Exception: ", exc_info=exc_info)
    try:
        await bot.send_message(settings.bot.ADMINS[0], error_message)
    except Exception as e:
        logging.exception(f"Failed to send error message to admin: {e}")
