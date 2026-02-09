from aiogram.filters.callback_data import CallbackData

from bot.internal.enums import GardenAction, MenuButtons, PaidEntity, SubscriptionAction


class PaidEntityCallbackFactory(CallbackData, prefix="paid_functions"):
    entity: PaidEntity


class SubscriptionActionsCallbackFactory(CallbackData, prefix="subscription_actions"):
    action: SubscriptionAction


class NewDialogCallbackFactory(CallbackData, prefix="new_dialog"):
    choice: MenuButtons

class GardenCallbackFactory(CallbackData, prefix="garden"):
    action: GardenAction
    plant_id: int = 0