from enum import StrEnum, auto

from aiogram.fsm.state import State, StatesGroup


class Form(StatesGroup):
    space = State()
    geography = State()
    request = State()


class AIState(StatesGroup):
    IN_AI_DIALOG = State()
    WAITING_HOME_TIME = State()
    WAITING_CONFIRM_HOME = State()
    WAITING_PLANT_PHOTO = State()
    WAITING_CITY = State()

class GardenState(StatesGroup):
    WAITING_ADD_PLANT_CHOICE = State()
    WAITING_NEW_PLANT_PHOTO = State()
    WAITING_PLANT_NAME = State()
    WAITING_WATERING_INTERVAL_CONFIRM = State()
    WAITING_WATERING_INTERVAL_DAYS = State()
    WAITING_LAST_WATERED_DATE = State()
    WAITING_PLANT_RENAME = State()
    IN_GARDEN_STUB = State()


class PaidEntity(StrEnum):
    ONE_MONTH_SUBSCRIPTION = auto()
    ONE_YEAR_SUBSCRIPTION = auto()
    ONE_YEAR_GIFT_SUBSCRIPTION = auto()
    PICTURES_COUNTER_REFRESH = auto()


class PaymentType(StrEnum):
    RECURRENT = auto()
    ONE_TIME = auto()


class MenuButtons(StrEnum):
    YES = auto()
    NO = auto()


class SubscriptionAction(StrEnum):
    CANCEL_SUB_DIALOG = auto()
    CANCEL_SUB = auto()
    GIFT_SUB = auto()


class SubscriptionStatus(StrEnum):
    INACTIVE = auto()
    ACTIVE = auto()
    CREATED = auto()
    RENEWED = auto()
    PROLONGED = auto()


class Stage(StrEnum):
    DEV = auto()
    PROD = auto()

class GardenAction(StrEnum):
    OPEN = auto()
    ADD = auto()
    ADD_WITH_PHOTO = auto()
    ADD_WITHOUT_PHOTO = auto()
    CONFIRM_GUESS_YES = auto()
    CONFIRM_GUESS_NO = auto()
    CONFIRM_GUESS_RETAKE = auto()
    CONFIRM_WATERING_YES = auto()
    CONFIRM_WATERING_CHANGE = auto()
    VIEW = auto()
    WATERED = auto()
    SETTINGS = auto()
    TOGGLE_NOTIFICATIONS = auto()
    RENAME = auto()
    DELETE_CONFIRM = auto()
    DELETE = auto()
    BACK = auto()
    BACK_TO_LIST = auto()