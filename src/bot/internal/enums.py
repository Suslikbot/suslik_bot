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
