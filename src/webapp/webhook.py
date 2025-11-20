from logging import getLogger

from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import FSInputFile
from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status
from starlette.requests import Request
from starlette.responses import JSONResponse

from bot.config import Settings
from bot.controllers.payments import get_payment_from_db
from bot.controllers.user import (
    get_user_from_db_by_tg_id,
    reset_user_image_counter,
    update_user_expiration,
)
from bot.internal.enums import AIState, PaidEntity
from bot.internal.lexicon import payment_text
from database.models import Payment, User
from webapp.deps import get_bot, get_db_session, get_settings

router = APIRouter()
logger = getLogger(__name__)


class YooKassaEvent(BaseModel):
    type: str
    event: str
    object: dict


@router.post("/")
async def yookassa_webhook(
    request: Request,
    bot: Bot = Depends(get_bot),
    settings: Settings = Depends(get_settings),
    db_session: AsyncSession = Depends(get_db_session),
):
    bot_id = request.app.state.bot_id
    redis_client = Redis(
        host=settings.redis.HOST,
        port=settings.redis.PORT,
        username=settings.redis.USERNAME,
        password=settings.redis.PASSWORD.get_secret_value(),
        decode_responses=True,
    )
    storage = RedisStorage(redis_client)
    try:
        payload = await request.json()
        logger.info(
            "YooKassa webhook received",
            extra={
                "event_type": payload.get("event"),
                "object_id": payload.get("object", {}).get("id"),
                "status": payload.get("object", {}).get("status"),
            },
        )
        data = YooKassaEvent(**payload)
        metadata = data.object.get("metadata") or {}
        entity = metadata.get("entity")
        payment_type = metadata.get("payment_type")
        payment: Payment = await get_payment_from_db(data.object.get("id"), db_session)
        user: User = await get_user_from_db_by_tg_id(payment.user_tg_id, db_session)

        logger.info(
            "Parsed webhook payload",
            extra={
                "event": data.event,
                "entity": entity,
                "payment_type": payment_type,
                "telegram_id": user.tg_id,
                "payment_id": payment.payment_id,
                "status": data.object.get("status"),
            },
        )

        if data.event == "payment.succeeded":
            if data.object.get("status") == "succeeded" and data.object.get("paid"):
                payment.is_paid = True
                db_session.add(payment)
                await db_session.flush()

            await bot.send_message(
                settings.bot.CHAT_LOG_ID,
                payment_text["user_payment_log"].format(
                    username=user.username,
                    payload=entity.replace("_", " "),
                    payment_type=payment.payment_type,
                ),
            )
            user.payment_method_id = payment.payment_id
            fsm_context = FSMContext(
                storage=storage,
                key=StorageKey(bot_id=bot_id, chat_id=user.tg_id, user_id=user.tg_id),
            )
            if entity in (
                PaidEntity.ONE_MONTH_SUBSCRIPTION,
                PaidEntity.ONE_YEAR_SUBSCRIPTION,
            ):
                text = (
                    payment_text["1 month success"]
                    if entity == PaidEntity.ONE_MONTH_SUBSCRIPTION
                    else payment_text["1 year success"]
                )
                dutation = (
                    relativedelta(months=1) if entity == PaidEntity.ONE_MONTH_SUBSCRIPTION else relativedelta(years=1)
                )
                new_expired_at = await update_user_expiration(user, dutation, db_session)
                if not payment_type:
                    user.is_autopayment_enabled = True
                    user.subscription_duration = entity
                    await bot.send_photo(
                        payment.user_tg_id,
                        FSInputFile(
                            path="src/bot/data/gardener1.png",
                        ),
                        caption=text,
                    )
                    logger.info(
                        "Successful payment",
                        extra={
                            "username": user.username,
                            "telegram_id": user.tg_id,
                            "entity": entity,
                            "expire_at": new_expired_at.isoformat() if new_expired_at else None,
                            "autopayment_enabled": True,
                        },
                    )
                else:
                    logger.info(
                        "Successful recurrent payment",
                        extra={
                            "username": user.username,
                            "telegram_id": user.tg_id,
                            "entity": entity,
                            "expire_at": new_expired_at.isoformat() if new_expired_at else None,
                        },
                    )
                await fsm_context.set_data({})
            elif entity == PaidEntity.PICTURES_COUNTER_REFRESH:
                await reset_user_image_counter(payment.user_tg_id, db_session)
                await bot.send_photo(
                    payment.user_tg_id,
                    FSInputFile(path="src/bot/data/taking_photo.png"),
                    caption=payment_text["refresh_pictures_limit_success"],
                )
                logger.info(
                    "Refreshed picture limit after payment",
                    extra={
                        "username": user.username,
                        "telegram_id": user.tg_id,
                        "entity": entity,
                    },
                )
            await fsm_context.set_state(AIState.IN_AI_DIALOG)
        elif data.event == "payment.canceled":
            await bot.send_message(
                settings.bot.CHAT_LOG_ID,
                payment_text["user_payment_error_log"].format(
                    username=user.username,
                    payload=entity.replace("_", " "),
                    payment_type=payment.payment_type,
                    error=data.object.get("cancellation_details"),
                ),
            )
            user.is_autopayment_enabled = False

            logger.warning(
                "Payment canceled",
                extra={
                    "username": user.username,
                    "telegram_id": user.tg_id,
                    "entity": entity,
                    "status": data.object.get("status"),
                    "reason": data.object.get("cancellation_details"),
                },
            )
        else:
            logger.info(
                "Unhandled webhook event type",
                extra={"event": data.event, "object_id": data.object.get("id")},
            )

        db_session.add(user)
        await db_session.commit()
        logger.info(
            "Webhook processing finished",
            extra={
                "event": data.event,
                "payment_id": payment.payment_id,
                "telegram_id": user.tg_id,
            },
        )
    except ValidationError as ve:
        logger.error(f"Payload validation error: {ve}")
    except Exception as e:
        logger.exception(f"Unexpected error in webhook handler: {e}")
    return JSONResponse(status_code=status.HTTP_200_OK, content={"result": "ok"})
