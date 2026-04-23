import logging
from sqlalchemy import Result, select
from sqlalchemy.ext.asyncio import AsyncSession
from yookassa import Payment as YookassaPayment
from yookassa.domain.response import PaymentResponse

from database.models import Payment
logger = logging.getLogger(__name__)

async def get_subscription_payment(amount: int, description: str, user_id: int, entity: str) -> PaymentResponse:
    logger.info(
        "external api request",
        extra={
            "provider": "yookassa",
            "operation": "payment.create",
            "user_id": user_id,
            "entity": entity,
            "payment_kind": "subscription",
        },
    )
    payment = YookassaPayment.create(
        {
            "amount": {"value": f"{amount}.00", "currency": "RUB"},
            "payment_method_data": {"type": "bank_card"},
            "confirmation": {
                "type": "redirect",
                "return_url": "https://t.me/SuslikAI_bot",
            },
            "receipt": {
                "customer": {"email": "suslikaibot@gmail.com"},
                "items": [
                    {
                        "description": description,
                        "quantity": 1,
                        "amount": {
                            "value": f"{amount}.00",
                            "currency": "RUB",
                        },
                        "vat_code": 1,
                        "payment_mode": "full_payment",
                        "payment_subject": "service",
                    }
                ],
            },
            "metadata": {
                "entity": entity,
            },
            "capture": True,
            "description": f"{description}",
            "save_payment_method": True,
            "tax_system_code": 1,
            "merchant_customer_id": user_id,
        }
    )
    logger.info(
        "external api response",
        extra={
            "provider": "yookassa",
            "operation": "payment.create",
            "payment_id": payment.id,
            "status": payment.status,
        },
    )
    return payment


async def create_recurrent_payment(
    amount: int,
    description: str,
    user_id: int,
    entity: str,
    payment_method_id: str,
) -> PaymentResponse:
    logger.info(
        "external api request",
        extra={
            "provider": "yookassa",
            "operation": "payment.create",
            "user_id": user_id,
            "entity": entity,
            "payment_kind": "recurrent",
        },
    )
    payment = YookassaPayment.create(
        {
            "amount": {"value": f"{amount}.00", "currency": "RUB"},
            "payment_method_id": payment_method_id,
            "capture": True,
            "description": description,
            "receipt": {
                "customer": {"email": "suslikaibot@gmail.com"},
                "items": [
                    {
                        "description": description,
                        "quantity": 1,
                        "amount": {
                            "value": f"{amount}.00",
                            "currency": "RUB",
                        },
                        "vat_code": 1,
                        "payment_mode": "full_payment",
                        "payment_subject": "service",
                    }
                ],
            },
            "metadata": {
                "entity": entity,
                "payment_type": "recurrent",
            },
            "merchant_customer_id": user_id,
        }
    )
    logger.info(
        "external api response",
        extra={
            "provider": "yookassa",
            "operation": "payment.create",
            "payment_id": payment.id,
            "status": payment.status,
        },
    )
    return payment


async def add_payment_to_db(
    payment_id: str,
    amount: int,
    description: str,
    user_id: int,
    db_session: AsyncSession,
):
    new_payment = Payment(
        payment_id=payment_id,
        user_tg_id=user_id,
        price=amount,
        description=description,
    )
    db_session.add(new_payment)
    await db_session.flush()


async def get_payment_from_db(
    payment_id: str,
    db_session: AsyncSession,
) -> Payment | None:
    query = select(Payment).filter(Payment.payment_id == payment_id)
    result: Result = await db_session.execute(query)
    return result.scalar_one_or_none()
