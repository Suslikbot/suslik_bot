from datetime import UTC, datetime, timedelta
import re
from logging import getLogger
from pathlib import Path
from uuid import uuid4
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message
from sqlalchemy.ext.asyncio import AsyncSession
from bot.ai_client import AIClient
from bot.controllers.gpt import get_or_create_ai_thread
from bot.controllers.garden import (
    add_plant,
    delete_plant,
    add_history_entry,
    add_plant_photo,
    get_plant,
    get_recent_history,
    list_user_plants,
    mark_plant_watered,
    rename_plant,
    toggle_plant_notifications,
    GARDEN_STATUS_CRITICAL,
    GARDEN_STATUS_NEEDS_HELP,
    GARDEN_STATUS_HEALTHY,
)
from bot.controllers.user import has_active_subscription
from bot.internal.callbacks import GardenCallbackFactory
from bot.internal.enums import AIState, GardenAction, GardenState
from bot.internal.keyboards import (
    dialog_menu_kb,
    garden_delete_confirm_kb,
    garden_add_choice_kb,
    garden_species_confirm_kb,
    garden_watering_confirm_kb,
    garden_list_kb,
    garden_welcome_kb,
    garden_plant_kb,
    garden_settings_kb,
    subscription_kb,
)
from bot.controllers.statistics import build_stat_message
from bot.config import Settings
from bot.internal.lexicon import garden_text
from database.models import GardenPlant, User

router = Router()
logger = getLogger(__name__)
DEFAULT_GARDEN_AVATAR_PATH = "src/bot/data/pitomnik.png"
GARDEN_PHOTO_STORAGE_DIR = Path("storage/garden_photos")


def normalize_garden_health_status(raw_status: str | None) -> str:
    if not raw_status:
        return GARDEN_STATUS_HEALTHY

    normalized = raw_status.strip().lower()
    if "крит" in normalized or "red" in normalized:
        return GARDEN_STATUS_CRITICAL
    if "помощ" in normalized or "yellow" in normalized or "желт" in normalized:
        return GARDEN_STATUS_NEEDS_HELP
    if "здоров" in normalized or "green" in normalized or "зелен" in normalized:
        return GARDEN_STATUS_HEALTHY
    return GARDEN_STATUS_HEALTHY

def parse_plant_snapshot(snapshot_text: str) -> dict[str, str | int | None]:
    status_match = re.search(r"STATUS:\s*(.+)", snapshot_text)
    water_match = re.search(r"WATER_DAYS:\s*(\d+)", snapshot_text)
    spray_match = re.search(r"SPRAY_DAYS:\s*(.+)", snapshot_text)
    light_match = re.search(r"LIGHT:\s*(.+)", snapshot_text)

    status = status_match.group(1).strip() if status_match else "Активный рост"
    water_days = int(water_match.group(1)) if water_match else 7
    spray_days = spray_match.group(1).strip() if spray_match else "2"
    light = light_match.group(1).strip() if light_match else "Рассеянный свет"

    return {
        "status": status,
        "water_days": max(1, water_days),
        "spray_days": spray_days,
        "light": light,
    }


def build_snapshot_history_text(snapshot: dict[str, str | int | None], next_water_at: datetime) -> str:
    return (
        "Сводка по фото:\n"
        f"💧 Полив: каждые {snapshot['water_days']} дн. (след. {next_water_at:%d.%m})\n"
        f"💦 Опрыскивание: раз в {snapshot['spray_days']} дн.\n"
        f"☀️ Свет: {snapshot['light']}"
    )

@router.callback_query(F.data == "postpay:stay_dialog")
async def post_payment_stay_dialog(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    settings: Settings,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    await state.set_state(AIState.IN_AI_DIALOG)
    user.action_count += 1
    await db_session.flush()
    decision_text = "Остаться в IN_AI_DIALOG"
    logger.info(build_stat_message("Postpay_choice", user.tg_id) + f" | decision={decision_text}")
    await callback.message.bot.send_message(
        settings.bot.CHAT_LOG_ID,
        f"[postpay_choice] user={user.tg_id} @{user.username} decision={decision_text} action_count={user.action_count}",
    )
    await callback.message.answer(
        "Отлично, остаёмся в режиме диалога 💬",
        reply_markup=dialog_menu_kb(),
    )


@router.callback_query(F.data == "postpay:open_garden")
async def post_payment_open_garden_stub(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    settings: Settings,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    await state.set_state(GardenState.IN_GARDEN_STUB)
    user.action_count += 1
    await db_session.flush()
    decision_text = "Перейти в сад"
    logger.info(build_stat_message("Postpay_choice", user.tg_id) + f" | decision={decision_text}")
    await callback.message.bot.send_message(
        settings.bot.CHAT_LOG_ID,
        f"[postpay_choice] user={user.tg_id} @{user.username} decision={decision_text} action_count={user.action_count}",
    )
    caption = (
        "Я автоматически создал раздел 🏡 Мой сад и бережно перенес твое растение туда. "
        "Теперь я помню его историю болезней и график полива.\n\n"
        "Хочешь добавить сюда остальных зеленых жильцов, или пока займемся этим?"
    )
    await callback.message.answer_photo(
        photo=FSInputFile(path="src/bot/data/pitomnik.png"),
        caption=caption,
        reply_markup=garden_welcome_kb(),
    )




def status_emoji(status: str) -> str:
    normalized = normalize_garden_health_status(status)
    if normalized == GARDEN_STATUS_CRITICAL:
        return "🔴"
    if normalized == GARDEN_STATUS_NEEDS_HELP:
        return "🟡"
    return "🟢"


def format_watering_recommendation_days(days: int) -> str:
    if days % 10 == 1 and days % 100 != 11:
        return f"{days} день"
    if days % 10 in {2, 3, 4} and not 12 <= days % 100 <= 14:
        return f"{days} дня"
    return f"{days} дней"


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
    if not has_active_subscription(user, datetime.now(UTC)):
        await callback.message.answer(garden_text["paywall"], reply_markup=subscription_kb())
        return
    await show_garden_list(callback.message, user, db_session)

@router.message(AIState.IN_AI_DIALOG, F.text == "🏡 Мой сад")
async def open_garden_from_dialog_menu(
    message: Message,
    user: User,
    db_session: AsyncSession,
) -> None:
    if not has_active_subscription(user, datetime.now(UTC)):
        await message.answer(garden_text["paywall"], reply_markup=subscription_kb())
        return
    await show_garden_list(message, user, db_session)



@router.callback_query(GardenCallbackFactory.filter(F.action == GardenAction.ADD))
async def add_garden_plant_prompt(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
) -> None:
    await callback.answer()
    if not has_active_subscription(user, datetime.now(UTC)):
        await callback.message.answer(garden_text["paywall"], reply_markup=subscription_kb())
        return
    await state.set_state(GardenState.WAITING_ADD_PLANT_CHOICE)
    await callback.message.answer(
        "Хочешь добавить растение с фото?",
        reply_markup=garden_add_choice_kb(),
    )

@router.callback_query(GardenCallbackFactory.filter(F.action == GardenAction.ADD_WITH_PHOTO))
async def add_garden_plant_with_photo(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
) -> None:
    await callback.answer()
    if not has_active_subscription(user, datetime.now(UTC)):
        await callback.message.answer(garden_text["paywall"], reply_markup=subscription_kb())
        return
    await state.update_data(
        garden_photo_file_path=DEFAULT_GARDEN_AVATAR_PATH,
        garden_photo_analysis="Фото не предоставлено пользователем.",
        garden_health_status=GARDEN_STATUS_HEALTHY,
    )
    await state.set_state(GardenState.WAITING_NEW_PLANT_PHOTO)
    await callback.message.answer("Отлично! Пришли фото растения 📸")


@router.callback_query(GardenCallbackFactory.filter(F.action == GardenAction.ADD_WITHOUT_PHOTO))
async def add_garden_plant_without_photo(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
) -> None:
    await callback.answer()
    if not has_active_subscription(user, datetime.now(UTC)):
        await callback.message.answer(garden_text["paywall"], reply_markup=subscription_kb())
        return
    await state.set_state(GardenState.WAITING_PLANT_NAME)
    await callback.message.answer(garden_text["add_prompt"])



@router.message(GardenState.WAITING_NEW_PLANT_PHOTO, F.photo)
async def garden_add_photo_received(
    message: Message,
    state: FSMContext,
    user: User,
    settings: Settings,
    db_session: AsyncSession,
    openai_client: AIClient,
) -> None:
    if not has_active_subscription(user, datetime.now(UTC)):
        await message.answer(garden_text["paywall"], reply_markup=subscription_kb())
        await state.clear()
        return

    photo = message.photo[-1]
    file_info = await message.bot.get_file(photo.file_id)
    file_bytes = await message.bot.download_file(file_info.file_path)
    image_bytes = file_bytes.read()
    extension = Path(file_info.file_path or "").suffix or ".jpg"
    GARDEN_PHOTO_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    photo_path = GARDEN_PHOTO_STORAGE_DIR / f"{user.tg_id}_{uuid4().hex}{extension}"
    photo_path.write_bytes(image_bytes)
    thread_id = await get_or_create_ai_thread(user, openai_client, db_session)
    prompt = (
        "Определи вид растения по фото. Ответь ТОЛЬКО коротким названием растения на русском, "
        "без пояснений, без пунктуации и без дополнительных слов."
    )
    guess, thread_id = await openai_client.get_response_with_image(
        thread_id=thread_id,
        text=prompt,
        image_bytes=image_bytes,
        message=message,
        fullname=user.fullname,
    )
    health_prompt = (
        "Оцени здоровье растения на фото. "
        "Ответь ТОЛЬКО одним словом: КРИТИЧЕСКОЕ или ПОМОЩЬ или ЗДОРОВ."
    )
    health_raw, thread_id = await openai_client.get_response_with_image(
        thread_id=thread_id,
        text=health_prompt,
        image_bytes=image_bytes,
        message=message,
        fullname=user.fullname,
    )
    health_status = normalize_garden_health_status(health_raw)
    user.ai_thread = thread_id
    db_session.add(user)
    await state.update_data(
        garden_photo_file_path=str(photo_path),
        garden_photo_analysis=(
            f"AI-определение по фото: {guess.strip() if guess else 'не получено'}\n"
            f"AI-оценка здоровья: {health_status}"
        ),
        garden_health_status=health_status,
    )
    if not guess or guess.startswith("Превышены лимиты") or guess.startswith("Ошибка при обработке изображения"):
        await message.answer("Не удалось распознать растение по фото 😔\nНапиши название растения вручную.")
        await state.set_state(GardenState.WAITING_PLANT_NAME)
        return

    guessed_plant = guess.strip().splitlines()[0].strip(" .,!?:;\"'")
    await state.update_data(garden_guessed_plant=guessed_plant)
    await message.answer(
        f"Похоже, это: {guessed_plant}. Так ли это?",
        reply_markup=garden_species_confirm_kb(),
    )

@router.callback_query(GardenCallbackFactory.filter(F.action == GardenAction.CONFIRM_GUESS_YES))
async def garden_confirm_guess_yes(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await callback.answer()
    data = await state.get_data()
    guessed = data.get("garden_guessed_plant", "растение")
    await state.set_state(GardenState.WAITING_PLANT_NAME)
    await callback.message.answer(f"Отлично! Тогда напиши кличку для «{guessed}».")


@router.callback_query(GardenCallbackFactory.filter(F.action == GardenAction.CONFIRM_GUESS_NO))
async def garden_confirm_guess_no(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await callback.answer()
    await state.set_state(GardenState.WAITING_PLANT_NAME)
    await callback.message.answer("Хорошо, тогда напиши название растения вручную.")

@router.callback_query(GardenCallbackFactory.filter(F.action == GardenAction.CONFIRM_GUESS_RETAKE))
async def garden_confirm_guess_retake(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await callback.answer()
    await state.set_state(GardenState.WAITING_NEW_PLANT_PHOTO)
    await callback.message.answer("Окей, сделай новое фото растения 📸")

@router.message(GardenState.WAITING_NEW_PLANT_PHOTO)
async def garden_add_photo_retry(
    message: Message,
) -> None:
    await message.answer("Нужна именно фотография растения 📸 или нажми «Оставить без фото».")

@router.message(GardenState.WAITING_PLANT_NAME)
async def add_garden_plant(
    message: Message,
    state: FSMContext,
    user: User,
) -> None:
    if not has_active_subscription(user, datetime.now(UTC)):
        await message.answer(garden_text["paywall"], reply_markup=subscription_kb())
        await state.clear()
        return
    plant_name = (message.text or "").strip()
    if not plant_name:
        await message.answer(garden_text["add_retry"])
        return
    data = await state.get_data()
    water_days = int(data.get("garden_watering_interval_days", 7))

    await state.update_data(
        garden_pending_plant_name=plant_name,
        garden_watering_interval_days=max(1, water_days),
    )
    recommendation = format_watering_recommendation_days(max(1, water_days))
    await state.set_state(GardenState.WAITING_WATERING_INTERVAL_CONFIRM)
    await message.answer(
        f"Рекомендую поливать это растение каждые {recommendation}. Подходит такая частота?",
        reply_markup=garden_watering_confirm_kb(),
    )

    @router.callback_query(GardenCallbackFactory.filter(F.action == GardenAction.CONFIRM_WATERING_YES))
    async def garden_confirm_watering_yes(
            callback: CallbackQuery,
            state: FSMContext,
    ) -> None:
        await callback.answer()
        await state.set_state(GardenState.WAITING_LAST_WATERED_DATE)
        await callback.message.answer(
            "Когда вы поливали растение в последний раз?\nВведите дату в формате ДД.ММ.ГГГГ (например: 09.02.2026)."
        )

    @router.callback_query(GardenCallbackFactory.filter(F.action == GardenAction.CONFIRM_WATERING_CHANGE))
    async def garden_confirm_watering_change(
            callback: CallbackQuery,
            state: FSMContext,
    ) -> None:
        await callback.answer()
        await state.set_state(GardenState.WAITING_WATERING_INTERVAL_DAYS)
        await callback.message.answer("Окей, укажи частоту полива в днях (например: 5).")



@router.message(GardenState.WAITING_WATERING_INTERVAL_DAYS)
async def garden_set_watering_interval_days(
    message: Message,
    state: FSMContext,
) -> None:
    raw_value = (message.text or "").strip()
    if not raw_value.isdigit():
        await message.answer("Нужно ввести число дней, например: 5.")
        return

    days = int(raw_value)
    if days < 1 or days > 60:
        await message.answer("Выберите значение от 1 до 60 дней.")
        return

    await state.update_data(garden_watering_interval_days=days)
    await state.set_state(GardenState.WAITING_LAST_WATERED_DATE)
    await message.answer(
        f"Отлично, зафиксировал: каждые {format_watering_recommendation_days(days)}.\n"
        "Когда вы поливали растение в последний раз?\n"
        "Введите дату в формате ДД.ММ.ГГГГ (например: 09.02.2026)."
    )


@router.message(GardenState.WAITING_LAST_WATERED_DATE)
async def add_garden_plant_last_watered(
    message: Message,
    state: FSMContext,
    user: User,
    db_session: AsyncSession,
) -> None:
    if not has_active_subscription(user, datetime.now(UTC)):
        await message.answer(garden_text["paywall"], reply_markup=subscription_kb())
        await state.clear()
        return

    raw_date = (message.text or "").strip()
    try:
        parsed_date = datetime.strptime(raw_date, "%d.%m.%Y").replace(tzinfo=UTC)
    except ValueError:
        await message.answer("Не понял дату 🙏 Используйте формат ДД.ММ.ГГГГ, например 09.02.2026.")
        return

    data = await state.get_data()
    plant_name = (data.get("garden_pending_plant_name") or "").strip()
    if not plant_name:
        await state.clear()
        await message.answer("Не нашёл название растения. Давайте начнём заново через «Добавить растение». ")
        return

    snapshot = data.get("garden_photo_snapshot") or {}
    water_days = int(data.get("garden_watering_interval_days", 7))
    photo_analysis = data.get("garden_photo_analysis")
    photo_file_path = data.get("garden_photo_file_path")
    health_status = normalize_garden_health_status(data.get("garden_health_status"))
    plant = await add_plant(
        user.tg_id,
        plant_name,
        db_session,
        watering_interval_days=water_days,
    )
    if photo_file_path:
        await add_plant_photo(
            plant_id=plant.id,
            file_path=str(photo_file_path),
            db_session=db_session,
            analysis=photo_analysis,
            is_primary=True,
        )
    plant.status = health_status
    if isinstance(snapshot, dict) and snapshot.get("status"):
        plant.status = normalize_garden_health_status(str(snapshot["status"]))

    plant.last_watered_at = parsed_date
    plant.next_watering_at = parsed_date + timedelta(days=plant.watering_interval_days)

    if isinstance(snapshot, dict) and snapshot:
        history_text = build_snapshot_history_text(snapshot, plant.next_watering_at)
        await add_history_entry(plant.id, history_text, db_session)

    await db_session.flush()

    await state.clear()
    await message.answer(garden_text["add_success"].format(name=plant_name))
    await message.answer(
        f"Записал последний полив: {parsed_date.strftime('%d.%m.%Y')}.\n"
        f"Следующий полив: {plant.next_watering_at.strftime('%d.%m.%Y')}."
    )
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
    if not has_active_subscription(user, datetime.now(UTC)):
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