from datetime import UTC, datetime
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.controllers.garden import (
    add_plant,
    delete_plant,
    get_plant,
    get_recent_history,
    list_user_plants,
    mark_plant_watered,
    rename_plant,
    toggle_plant_notifications,
)
from bot.internal.callbacks import GardenCallbackFactory
from bot.internal.enums import GardenAction, GardenState
from bot.internal.keyboards import (
    garden_delete_confirm_kb,
    garden_list_kb,
    garden_plant_kb,
    garden_settings_kb,
    subscription_kb,
)
from bot.internal.lexicon import garden_text
from database.models import GardenPlant, User

router = Router()


def is_subscription_active(user: User) -> bool:
    if not user.is_subscribed or not user.expired_at:
        return False
    now = datetime.now(UTC)
    expired_at = user.expired_at
    if expired_at.tzinfo is None:
        expired_at = expired_at.replace(tzinfo=UTC)
    return expired_at > now


def status_emoji(status: str) -> str:
    normalized = status.lower()
    if "леч" in normalized:
        return "🩺"
    if "рост" in normalized:
        return "🌿"
    return "🟢"


def format_next_watering(plant: GardenPlant) -> str:
    if not plant.next_watering_at:
        return "не задан"
    next_at = plant.next_watering_at
    if next_at.tzinfo is None:
        next_at = next_at.replace(tzinfo=UTC)
    today = datetime.now(UTC).date()
    if next_at.date() <= today:
        return "сегодня"
    return next_at.strftime("%d.%m")


async def show_garden_list(message: Message, user: User, db_session: AsyncSession) -> None:
    plants = await list_user_plants(user.tg_id, db_session)
    if not plants:
        await message.answer(garden_text["empty"], reply_markup=garden_list_kb([]))
        return
    lines = [garden_text["list_intro"], f"Всего растений: {len(plants)}"]
    plant_buttons: list[tuple[str, int]] = []
    for idx, plant in enumerate(plants, start=1):
        emoji = status_emoji(plant.status)
        next_watering = format_next_watering(plant)
        lines.append(f"{idx}. {plant.name} — {emoji} {plant.status}")
        lines.append(f"Следующий полив: {next_watering}")
        plant_buttons.append((f"{emoji} {plant.name}", plant.id))
    await message.answer("\n".join(lines), reply_markup=garden_list_kb(plant_buttons))


async def show_plant_detail(message: Message, plant: GardenPlant, db_session: AsyncSession) -> None:
    history_entries = await get_recent_history(plant.id, db_session)
    history_text = "\n".join(f"• {entry.description}" for entry in history_entries) or "• Пока пусто"
    next_watering = format_next_watering(plant)
    lines = [
        f"Заголовок: {plant.name}",
        f"Статус: {status_emoji(plant.status)} {plant.status}",
        "",
        "Сводка:",
        f"💧 Полив: каждые {plant.watering_interval_days} дн.",
        f"Следующий полив: {next_watering}",
        "",
        "История:",
        history_text,
    ]
    await message.answer("\n".join(lines), reply_markup=garden_plant_kb(plant.id))


@router.callback_query(GardenCallbackFactory.filter(F.action == GardenAction.OPEN))
async def open_garden(
    callback: CallbackQuery,
    user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    if not is_subscription_active(user):
        await callback.message.answer(garden_text["paywall"], reply_markup=subscription_kb())
        return
    await show_garden_list(callback.message, user, db_session)


@router.callback_query(GardenCallbackFactory.filter(F.action == GardenAction.ADD))
async def add_garden_plant_prompt(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
) -> None:
    await callback.answer()
    if not is_subscription_active(user):
        await callback.message.answer(garden_text["paywall"], reply_markup=subscription_kb())
        return
    await state.set_state(GardenState.WAITING_PLANT_NAME)
    await callback.message.answer(garden_text["add_prompt"])


@router.message(GardenState.WAITING_PLANT_NAME)
async def add_garden_plant(
    message: Message,
    state: FSMContext,
    user: User,
    db_session: AsyncSession,
) -> None:
    if not is_subscription_active(user):
        await message.answer(garden_text["paywall"], reply_markup=subscription_kb())
        await state.clear()
        return
    plant_name = (message.text or "").strip()
    if not plant_name:
        await message.answer(garden_text["add_retry"])
        return
    await add_plant(user.tg_id, plant_name, db_session)
    await state.clear()
    await message.answer(garden_text["add_success"].format(name=plant_name))
    await show_garden_list(message, user, db_session)


@router.callback_query(GardenCallbackFactory.filter(F.action == GardenAction.VIEW))
async def view_garden_plant(
    callback: CallbackQuery,
    callback_data: GardenCallbackFactory,
    user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    plant = await get_plant(callback_data.plant_id, user.tg_id, db_session)
    if not plant:
        await callback.message.answer(garden_text["not_found"])
        return
    await show_plant_detail(callback.message, plant, db_session)


@router.callback_query(GardenCallbackFactory.filter(F.action == GardenAction.WATERED))
async def mark_watered(
    callback: CallbackQuery,
    callback_data: GardenCallbackFactory,
    user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    plant = await get_plant(callback_data.plant_id, user.tg_id, db_session)
    if not plant:
        await callback.message.answer(garden_text["not_found"])
        return
    await mark_plant_watered(plant, db_session)
    await callback.message.answer(garden_text["watered_success"].format(name=plant.name))
    await show_plant_detail(callback.message, plant, db_session)


@router.callback_query(GardenCallbackFactory.filter(F.action == GardenAction.SETTINGS))
async def plant_settings(
    callback: CallbackQuery,
    callback_data: GardenCallbackFactory,
    user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    plant = await get_plant(callback_data.plant_id, user.tg_id, db_session)
    if not plant:
        await callback.message.answer(garden_text["not_found"])
        return
    await callback.message.answer(
        garden_text["settings"].format(name=plant.name),
        reply_markup=garden_settings_kb(plant.id, plant.notifications_enabled),
    )


@router.callback_query(GardenCallbackFactory.filter(F.action == GardenAction.RENAME))
async def rename_prompt(
    callback: CallbackQuery,
    callback_data: GardenCallbackFactory,
    state: FSMContext,
    user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    plant = await get_plant(callback_data.plant_id, user.tg_id, db_session)
    if not plant:
        await callback.message.answer(garden_text["not_found"])
        return
    await state.update_data(rename_plant_id=plant.id)
    await state.set_state(GardenState.WAITING_PLANT_RENAME)
    await callback.message.answer(garden_text["rename_prompt"].format(name=plant.name))


@router.message(GardenState.WAITING_PLANT_RENAME)
async def rename_plant_handler(
    message: Message,
    state: FSMContext,
    user: User,
    db_session: AsyncSession,
) -> None:
    if not is_subscription_active(user):
        await message.answer(garden_text["paywall"], reply_markup=subscription_kb())
        await state.clear()
        return
    data = await state.get_data()
    plant_id = data.get("rename_plant_id")
    plant = await get_plant(plant_id, user.tg_id, db_session)
    if not plant:
        await message.answer(garden_text["not_found"])
        await state.clear()
        return
    new_name = (message.text or "").strip()
    if not new_name:
        await message.answer(garden_text["rename_retry"])
        return
    await rename_plant(plant, new_name, db_session)
    await state.clear()
    await message.answer(garden_text["rename_success"].format(name=new_name))
    await show_plant_detail(message, plant, db_session)


@router.callback_query(GardenCallbackFactory.filter(F.action == GardenAction.TOGGLE_NOTIFICATIONS))
async def toggle_notifications(
    callback: CallbackQuery,
    callback_data: GardenCallbackFactory,
    user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    plant = await get_plant(callback_data.plant_id, user.tg_id, db_session)
    if not plant:
        await callback.message.answer(garden_text["not_found"])
        return
    await toggle_plant_notifications(plant, db_session)
    status_text = garden_text["notifications_on"] if plant.notifications_enabled else garden_text["notifications_off"]
    await callback.message.answer(status_text.format(name=plant.name))
    await callback.message.answer(
        garden_text["settings"].format(name=plant.name),
        reply_markup=garden_settings_kb(plant.id, plant.notifications_enabled),
    )


@router.callback_query(GardenCallbackFactory.filter(F.action == GardenAction.DELETE_CONFIRM))
async def delete_confirm(
    callback: CallbackQuery,
    callback_data: GardenCallbackFactory,
    user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    plant = await get_plant(callback_data.plant_id, user.tg_id, db_session)
    if not plant:
        await callback.message.answer(garden_text["not_found"])
        return
    await callback.message.answer(
        garden_text["delete_confirm"].format(name=plant.name),
        reply_markup=garden_delete_confirm_kb(plant.id),
    )


@router.callback_query(GardenCallbackFactory.filter(F.action == GardenAction.DELETE))
async def delete_plant_handler(
    callback: CallbackQuery,
    callback_data: GardenCallbackFactory,
    user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    plant = await get_plant(callback_data.plant_id, user.tg_id, db_session)
    if not plant:
        await callback.message.answer(garden_text["not_found"])
        return
    await delete_plant(plant, db_session)
    await callback.message.answer(garden_text["delete_success"].format(name=plant.name))
    await show_garden_list(callback.message, user, db_session)


@router.callback_query(GardenCallbackFactory.filter(F.action == GardenAction.BACK_TO_LIST))
async def back_to_list(
    callback: CallbackQuery,
    user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    await show_garden_list(callback.message, user, db_session)


@router.callback_query(GardenCallbackFactory.filter(F.action == GardenAction.BACK))
async def back_handler(
    callback: CallbackQuery,
    callback_data: GardenCallbackFactory,
    user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    if callback_data.plant_id:
        plant = await get_plant(callback_data.plant_id, user.tg_id, db_session)
        if plant:
            await show_plant_detail(callback.message, plant, db_session)
            return
    await show_garden_list(callback.message, user, db_session)