from datetime import datetime

from sqlalchemy import (
    BOOLEAN,
    TIMESTAMP,
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    func,
    Text,
    Column
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from bot.internal.enums import PaidEntity, PaymentType


class Base(DeclarativeBase):
    __abstract__ = True
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"

    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    fullname: Mapped[str]
    username: Mapped[str]
    ai_thread: Mapped[str | None]
    action_count: Mapped[int] = mapped_column(Integer, default=0)
    is_subscribed: Mapped[bool] = mapped_column(BOOLEAN, default=False)
    subscription_duration: Mapped[PaidEntity | None]
    is_autopayment_enabled: Mapped[bool] = mapped_column(BOOLEAN, default=False, server_default="false")
    is_context_added: Mapped[bool] = mapped_column(BOOLEAN, default=False)
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    space: Mapped[str | None]
    geography: Mapped[str | None]
    request: Mapped[str | None]
    payment_method_id: Mapped[str | None]
    source: Mapped[str | None]

    def __str__(self):
        return f"{self.__class__.__name__}(id: {self.tg_id}, fullname: {self.fullname})"

    def __repr__(self):
        return str(self)


class UserCounters(Base):
    __tablename__ = "user_counters"

    tg_id: Mapped[int] = mapped_column(ForeignKey("users.tg_id", ondelete="CASCADE"))
    period_started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    image_count: Mapped[int] = mapped_column(Integer, default=0)


class Payment(Base):
    __tablename__ = "payments"

    payment_id: Mapped[str]
    user_tg_id: Mapped[int] = mapped_column(ForeignKey("users.tg_id", ondelete="CASCADE"))
    payment_type: Mapped[PaymentType] = mapped_column(
        default=PaymentType.ONE_TIME, server_default=PaymentType.ONE_TIME
    )
    price: Mapped[int]
    description: Mapped[str]
    is_paid: Mapped[bool] = mapped_column(BOOLEAN, default=False)

# database/models/plant_analysis.py

class PlantAnalysis(Base):
    __tablename__ = "plant_analyses"

    user_tg_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.tg_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    thread_id: Mapped[str | None]

    tg_file_id: Mapped[str] = mapped_column(nullable=False)
    tg_file_unique_id: Mapped[str | None]

    ai_response: Mapped[str] = mapped_column(Text, nullable=False)
    health_score: Mapped[int | None] = mapped_column(Integer)

class OneTimePurchase(Base):
    __tablename__ = "one_time_purchases"

    id: Mapped[int]
    user_id: Mapped[int]
    product_code: Mapped[str]  # "RECIPE_PLAN"
    is_consumed: Mapped[bool]  # False → True
    created_at: Mapped[datetime]
