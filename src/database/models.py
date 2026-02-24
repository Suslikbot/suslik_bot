from datetime import datetime

from sqlalchemy import (
    BOOLEAN,
    TIMESTAMP,
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
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

class GardenPlant(Base):
    __tablename__ = "garden_plants"

    user_tg_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.tg_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str]
    status: Mapped[str]
    watering_interval_days: Mapped[int] = mapped_column(Integer, default=7)
    last_watered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_watering_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notifications_enabled: Mapped[bool] = mapped_column(BOOLEAN, default=True, server_default="true")
    last_notification_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class GardenPlantPhoto(Base):
    __tablename__ = "garden_plant_photos"

    plant_id: Mapped[int] = mapped_column(
        ForeignKey("garden_plants.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    analysis: Mapped[str | None] = mapped_column(Text)
    is_primary: Mapped[bool] = mapped_column(BOOLEAN, default=True, server_default="true")



class GardenPlantHistory(Base):
    __tablename__ = "garden_plant_history"

    plant_id: Mapped[int] = mapped_column(
        ForeignKey("garden_plants.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)


class PlantSpecies(Base):
    __tablename__ = "plant_species"

    latin_name: Mapped[str] = mapped_column(Text, nullable=False)
    common_name: Mapped[str | None] = mapped_column(Text)
    water_days_min: Mapped[int | None] = mapped_column(Integer)
    water_days_max: Mapped[int | None] = mapped_column(Integer)
    spray_interval: Mapped[int | None] = mapped_column(Integer)
    light_type: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)


class UserPlant(Base):
    __tablename__ = "user_plants"

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.tg_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    species_id: Mapped[int | None] = mapped_column(
        ForeignKey("plant_species.id", ondelete="SET NULL"),
        index=True,
    )
    nickname: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="healthy", server_default="healthy")
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    notifications_enabled: Mapped[bool] = mapped_column(BOOLEAN, default=True, server_default="true")


class PlantPhoto(Base):
    __tablename__ = "plant_photos"

    user_plant_id: Mapped[int] = mapped_column(
        ForeignKey("user_plants.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    ml_guess: Mapped[str | None] = mapped_column(Text)
    ml_confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    confirmed: Mapped[bool] = mapped_column(BOOLEAN, nullable=False, default=False, server_default="false")


class CareProfile(Base):
    __tablename__ = "care_profiles"

    user_plant_id: Mapped[int] = mapped_column(
        ForeignKey("user_plants.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    water_interval: Mapped[int | None] = mapped_column(Integer)
    spray_interval: Mapped[int | None] = mapped_column(Integer)
    last_watered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_water_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Notification(Base):
    __tablename__ = "notifications"

    user_plant_id: Mapped[int] = mapped_column(
        ForeignKey("user_plants.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    cron_expr: Mapped[str] = mapped_column(Text, nullable=False)
    next_run: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enabled: Mapped[bool] = mapped_column(BOOLEAN, nullable=False, default=True, server_default="true")


class PlantCareLog(Base):
    __tablename__ = "plant_care_logs"

    user_plant_id: Mapped[int] = mapped_column(
        ForeignKey("user_plants.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)

class UserRequestLog(Base):
    __tablename__ = "user_request_logs"

    user_tg_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.tg_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    request_text: Mapped[str] = mapped_column(Text, nullable=False)


class BotResponseLog(Base):
    __tablename__ = "bot_response_logs"

    user_tg_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.tg_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_request_log_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_request_logs.id", ondelete="SET NULL"),
        index=True,
    )
    response_text: Mapped[str] = mapped_column(Text, nullable=False)