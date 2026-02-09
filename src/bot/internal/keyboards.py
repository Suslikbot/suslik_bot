from aiogram.types import (
    InlineKeyboardMarkup,
    KeyboardButton,
    KeyboardButtonRequestUsers,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.internal.callbacks import (
    GardenCallbackFactory,
    PaidEntityCallbackFactory,
    SubscriptionActionsCallbackFactory,
)
from bot.internal.enums import GardenAction, PaidEntity, SubscriptionAction


def subscription_kb(prolong: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    month_text = "Продлить на месяц" if prolong else "Месяц"
    year_text = "Продлить на год" if prolong else "Годовая подписка"
    for text, callback in [
        (
            month_text,
            PaidEntityCallbackFactory(entity=PaidEntity.ONE_MONTH_SUBSCRIPTION).pack(),
        ),
        (
            year_text,
            PaidEntityCallbackFactory(entity=PaidEntity.ONE_YEAR_SUBSCRIPTION).pack(),
        ),
    ]:
        kb.button(text=text, callback_data=callback)
    kb.button(
        text="Подарить годовую подписку",
        callback_data=SubscriptionActionsCallbackFactory(action=SubscriptionAction.GIFT_SUB).pack(),
    )
    kb.adjust(1)
    return kb.as_markup()


def payment_link_kb(value: int, url: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=f"Оплатить {value}₽", url=url)
    return kb.as_markup()


def cancel_autopayment_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="Отмена подписки",
        callback_data=SubscriptionActionsCallbackFactory(action=SubscriptionAction.CANCEL_SUB_DIALOG).pack(),
    )
    kb.button(
        text="Подарить годовую подписку",
        callback_data=SubscriptionActionsCallbackFactory(action=SubscriptionAction.GIFT_SUB).pack(),
    )
    kb.adjust(1)
    return kb.as_markup()


def autopayment_cancelled_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="Отменить автопродление",
        callback_data=SubscriptionActionsCallbackFactory(action=SubscriptionAction.CANCEL_SUB).pack(),
    )
    return kb.as_markup()


def refresh_pictures_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="Купить доп. пакет",
        callback_data=PaidEntityCallbackFactory(entity=PaidEntity.PICTURES_COUNTER_REFRESH).pack(),
    )
    return kb.as_markup()

def garden_entry_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="➕ Добавить еще растение",
        callback_data=GardenCallbackFactory(action=GardenAction.ADD).pack(),
    )
    kb.button(
        text="🏡 Перейти в Мой сад",
        callback_data=GardenCallbackFactory(action=GardenAction.OPEN).pack(),
    )
    kb.adjust(1)
    return kb.as_markup()


def garden_list_kb(plant_buttons: list[tuple[str, int]]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for title, plant_id in plant_buttons:
        kb.button(
            text=title,
            callback_data=GardenCallbackFactory(action=GardenAction.VIEW, plant_id=plant_id).pack(),
        )
    kb.button(
        text="➕ Добавить новое",
        callback_data=GardenCallbackFactory(action=GardenAction.ADD).pack(),
    )
    kb.button(
        text="⬅️ Назад",
        callback_data=GardenCallbackFactory(action=GardenAction.BACK).pack(),
    )
    kb.adjust(1)
    return kb.as_markup()


def garden_plant_kb(plant_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ Я полил(а) его сегодня",
        callback_data=GardenCallbackFactory(action=GardenAction.WATERED, plant_id=plant_id).pack(),
    )
    kb.button(
        text="⚙️ Настройки",
        callback_data=GardenCallbackFactory(action=GardenAction.SETTINGS, plant_id=plant_id).pack(),
    )
    kb.button(
        text="⬅️ Назад к списку",
        callback_data=GardenCallbackFactory(action=GardenAction.BACK_TO_LIST).pack(),
    )
    kb.adjust(1)
    return kb.as_markup()


def garden_settings_kb(plant_id: int, notifications_enabled: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✏️ Дать имя",
        callback_data=GardenCallbackFactory(action=GardenAction.RENAME, plant_id=plant_id).pack(),
    )
    toggle_text = "🔕 Выключить уведомления" if notifications_enabled else "🔔 Включить уведомления"
    kb.button(
        text=toggle_text,
        callback_data=GardenCallbackFactory(action=GardenAction.TOGGLE_NOTIFICATIONS, plant_id=plant_id).pack(),
    )
    kb.button(
        text="🗑 Удалить из сада",
        callback_data=GardenCallbackFactory(action=GardenAction.DELETE_CONFIRM, plant_id=plant_id).pack(),
    )
    kb.button(
        text="⬅️ Назад",
        callback_data=GardenCallbackFactory(action=GardenAction.BACK, plant_id=plant_id).pack(),
    )
    kb.adjust(1)
    return kb.as_markup()


def garden_delete_confirm_kb(plant_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="Да, удалить",
        callback_data=GardenCallbackFactory(action=GardenAction.DELETE, plant_id=plant_id).pack(),
    )
    kb.button(
        text="Ой, нет, отмена",
        callback_data=GardenCallbackFactory(action=GardenAction.BACK, plant_id=plant_id).pack(),
    )
    kb.adjust(2)
    return kb.as_markup()

share_contact_kb = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(
                text="Выберите контакт",
                request_users=KeyboardButtonRequestUsers(request_id=1),
            )
        ]
    ],
    resize_keyboard=True,
    one_time_keyboard=True,
)
