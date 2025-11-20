from logging import getLogger

from aiogram import Router
from aiogram.types import CallbackQuery, PreCheckoutQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.controllers.payments import add_payment_to_db, get_subscription_payment
from bot.internal.callbacks import PaidEntityCallbackFactory, SubscriptionActionsCallbackFactory
from bot.internal.enums import PaidEntity, SubscriptionAction
from bot.internal.keyboards import autopayment_cancelled_kb, payment_link_kb, share_contact_kb
from bot.internal.lexicon import payment_text
from database.models import User

router = Router()
logger = getLogger(__name__)


@router.pre_checkout_query()
async def on_pre_checkout_query(
    pre_checkout_query: PreCheckoutQuery,
):
    await pre_checkout_query.answer(ok=True)


@router.callback_query(PaidEntityCallbackFactory.filter())
async def payment_handler(
    callback: CallbackQuery,
    callback_data: PaidEntityCallbackFactory,
    db_session: AsyncSession,
):
    await callback.answer()
    match callback_data.entity:
        case PaidEntity.ONE_MONTH_SUBSCRIPTION:
            description = "Оплата подписки, длительность: 1 месяц."
            amount = 390
        case PaidEntity.ONE_YEAR_SUBSCRIPTION:
            description = "Оплата подписки, длительность: 1 год."
            amount = 3900
        case PaidEntity.PICTURES_COUNTER_REFRESH:
            description = "Сброс лимита картинок."
            amount = 150
        case _:
            assert False, "Unexpected paid entity"
    payment = await get_subscription_payment(amount, description, callback.from_user.id, callback_data.entity)
    confirmation_url = payment.confirmation.confirmation_url
    await add_payment_to_db(payment.id, amount, description, callback.from_user.id, db_session)
    await callback.message.answer(
        text=payment_text["payment_url_text"].format(description=description),
        reply_markup=payment_link_kb(amount, confirmation_url),
    )


@router.callback_query(SubscriptionActionsCallbackFactory.filter())
async def subscription_handler(
    callback: CallbackQuery,
    callback_data: SubscriptionActionsCallbackFactory,
    user: User,
    db_session: AsyncSession,
):
    await callback.answer()
    if user.expired_at:
        date = user.expired_at.strftime("%d.%m.%Y")
    match callback_data.action:
        case SubscriptionAction.CANCEL_SUB_DIALOG:
            await callback.message.answer(
                text=payment_text["cancel_payment"].format(date=date),
                reply_markup=autopayment_cancelled_kb(),
            )
        case SubscriptionAction.CANCEL_SUB:
            user.is_autopayment_enabled = False
            user.subscription_duration = None
            await callback.message.edit_text(
                text=payment_text["payment_cancelled"].format(date=date),
            )
            db_session.add(user)
        case SubscriptionAction.GIFT_SUB:
            await callback.message.answer(
                text=payment_text["gift_sub"],
                reply_markup=share_contact_kb,
            )
