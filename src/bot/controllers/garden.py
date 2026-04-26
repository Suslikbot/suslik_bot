from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import GardenPlant, GardenPlantHistory, GardenPlantPhoto

DEFAULT_WATERING_INTERVAL_DAYS = 7
DEFAULT_PLANT_STATUS = "здоров"

GARDEN_STATUS_CRITICAL = "критическое"
GARDEN_STATUS_NEEDS_HELP = "нуждается в помощи"
GARDEN_STATUS_HEALTHY = "здоров"


def resolve_next_watering_at(
    last_watered_at: datetime,
    watering_interval_days: int,
    *,
    now: datetime | None = None,
) -> datetime:
    if now is None:
        now = datetime.now(UTC)
    scheduled_at = last_watered_at + timedelta(days=watering_interval_days)
    return max(scheduled_at, now)


def was_watered_today(plant: GardenPlant, *, now: datetime | None = None) -> bool:
    if plant.last_watered_at is None:
        return False
    if now is None:
        now = datetime.now(UTC)
    last_watered_at = plant.last_watered_at
    if last_watered_at.tzinfo is None:
        last_watered_at = last_watered_at.replace(tzinfo=UTC)
    return last_watered_at.date() == now.date()


async def list_user_plants(user_tg_id: int, db_session: AsyncSession) -> list[GardenPlant]:
    result = await db_session.execute(
        select(GardenPlant)
        .where(GardenPlant.user_tg_id == user_tg_id)
        .order_by(GardenPlant.created_at)
    )
    return list(result.scalars().all())


async def get_plant(plant_id: int, user_tg_id: int, db_session: AsyncSession) -> GardenPlant | None:
    result = await db_session.execute(
        select(GardenPlant).where(
            GardenPlant.id == plant_id,
            GardenPlant.user_tg_id == user_tg_id,
        )
    )
    return result.scalar_one_or_none()

async def add_plant(
    user_tg_id: int,
    name: str,
    db_session: AsyncSession,
    watering_interval_days: int = DEFAULT_WATERING_INTERVAL_DAYS,
) -> GardenPlant:
    now = datetime.now(UTC)
    next_watering_at = now + timedelta(days=watering_interval_days)
    plant = GardenPlant(
        user_tg_id=user_tg_id,
        name=name,
        status=DEFAULT_PLANT_STATUS,
        watering_interval_days=watering_interval_days,
        last_watered_at=None,
        next_watering_at=next_watering_at,
        notifications_enabled=True,
        last_notification_at=None,
    )
    db_session.add(plant)
    await db_session.flush()
    await _add_history(plant.id, f"Добавлено в сад ({now:%d.%m})", db_session)
    return plant


async def add_plant_photo(
    plant_id: int,
    file_path: str,
    db_session: AsyncSession,
    analysis: str | None = None,
    *,
    is_primary: bool = True,
) -> GardenPlantPhoto:
    if is_primary:
        await db_session.execute(
            update(GardenPlantPhoto)
            .where(
                GardenPlantPhoto.plant_id == plant_id,
                GardenPlantPhoto.is_primary.is_(True),
            )
            .values(is_primary=False)
        )

    photo = GardenPlantPhoto(
        plant_id=plant_id,
        file_path=file_path,
        analysis=analysis,
        is_primary=is_primary,
    )
    db_session.add(photo)
    await db_session.flush()
    return photo


async def get_primary_plant_photo(plant_id: int, db_session: AsyncSession) -> GardenPlantPhoto | None:
    result = await db_session.execute(
        select(GardenPlantPhoto)
        .where(GardenPlantPhoto.plant_id == plant_id)
        .order_by(desc(GardenPlantPhoto.is_primary), desc(GardenPlantPhoto.created_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def rename_plant(plant: GardenPlant, new_name: str, db_session: AsyncSession) -> GardenPlant:
    plant.name = new_name
    await db_session.flush()
    await _add_history(plant.id, f"Переименовано в «{new_name}»", db_session)
    return plant


async def mark_plant_watered(plant: GardenPlant, db_session: AsyncSession) -> GardenPlant:
    now = datetime.now(UTC)
    plant.last_watered_at = now
    plant.next_watering_at = now + timedelta(days=plant.watering_interval_days)
    plant.last_notification_at = None
    await db_session.flush()
    await _add_history(plant.id, f"Полив ({now:%d.%m})", db_session)
    return plant


async def toggle_plant_notifications(plant: GardenPlant, db_session: AsyncSession) -> GardenPlant:
    plant.notifications_enabled = not plant.notifications_enabled
    plant.last_notification_at = None
    await db_session.flush()
    return plant


async def delete_plant(plant: GardenPlant, db_session: AsyncSession) -> None:
    await db_session.delete(plant)
    await db_session.flush()


async def get_recent_history(plant_id: int, db_session: AsyncSession, limit: int = 5) -> list[GardenPlantHistory]:
    result = await db_session.execute(
        select(GardenPlantHistory)
        .where(GardenPlantHistory.plant_id == plant_id)
        .order_by(GardenPlantHistory.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_due_plants(user_tg_id: int, db_session: AsyncSession, now: datetime) -> list[GardenPlant]:
    result = await db_session.execute(
        select(GardenPlant).where(
            GardenPlant.user_tg_id == user_tg_id,
            GardenPlant.notifications_enabled.is_(True),
            GardenPlant.next_watering_at.isnot(None),
            GardenPlant.next_watering_at <= now,
        )
    )
    return list(result.scalars().all())


def should_notify(plant: GardenPlant, now: datetime) -> bool:
    if plant.last_notification_at is None:
        return True
    last = plant.last_notification_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    return last.date() != now.date()


async def mark_notified(plant: GardenPlant, db_session: AsyncSession, now: datetime) -> None:
    plant.last_notification_at = now
    await db_session.flush()

async def add_history_entry(plant_id: int, description: str, db_session: AsyncSession) -> None:
    await _add_history(plant_id, description, db_session)



async def _add_history(plant_id: int, description: str, db_session: AsyncSession) -> None:
    entry = GardenPlantHistory(
        plant_id=plant_id,
        description=description,
    )
    db_session.add(entry)
    await db_session.flush()
