from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.controllers.garden import resolve_next_watering_at, was_watered_today
from bot.handlers import garden as garden_module


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"

class FakeMessage:
    def __init__(self) -> None:
        self.answers: list[str] = []
        self.text = ""
        self.reply_markups: list[object | None] = []
        self.reply_markup_cleared = False

    async def answer(self, text: str, *_args, **_kwargs) -> None:
        self.answers.append(text)
        self.reply_markups.append(_kwargs.get("reply_markup"))

    async def edit_reply_markup(self, *_args, **_kwargs) -> None:
        self.reply_markup_cleared = True


class FakeState:
    def __init__(self, data: dict | None = None, current_state=None) -> None:
        self.data = data or {}
        self.cleared = False
        self.state = current_state

    async def get_data(self):
        return self.data

    async def clear(self) -> None:
        self.cleared = True

    async def set_state(self, state) -> None:
        self.state = state

    async def get_state(self):
        return self.state


class FakeCallback:
    def __init__(self, message: FakeMessage) -> None:
        self.message = message
        self.answered = False

    async def answer(self, *_args, **_kwargs) -> None:
        self.answered = True


@pytest.mark.anyio
async def test_ensure_garden_access_without_subscription_shows_paywall(monkeypatch) -> None:
    message = FakeMessage()
    user = SimpleNamespace()

    monkeypatch.setattr(garden_module, "has_active_subscription", lambda *_: False)

    allowed = await garden_module.ensure_garden_access(message=message, user=user)

    assert allowed is False
    assert message.answers == [garden_module.garden_text["paywall"]]


@pytest.mark.anyio
async def test_open_garden_by_command_for_active_subscription(monkeypatch) -> None:
    message = FakeMessage()
    show_garden_list = AsyncMock()

    monkeypatch.setattr(garden_module, "ensure_garden_access", AsyncMock(return_value=True))
    monkeypatch.setattr(garden_module, "show_garden_list", show_garden_list)
    monkeypatch.setattr(garden_module, "log_garden_action", AsyncMock())

    await garden_module.open_garden_by_command(
        message=message,
        user=SimpleNamespace(),
        db_session=SimpleNamespace(),
        settings=SimpleNamespace(bot=SimpleNamespace(CHAT_LOG_ID=1)),
    )

    show_garden_list.assert_awaited_once()


@pytest.mark.anyio
async def test_open_garden_by_command_without_subscription(monkeypatch) -> None:
    message = FakeMessage()
    show_garden_list = AsyncMock()

    monkeypatch.setattr(garden_module, "ensure_garden_access", AsyncMock(return_value=False))
    monkeypatch.setattr(garden_module, "show_garden_list", show_garden_list)
    monkeypatch.setattr(garden_module, "log_garden_action", AsyncMock())

    await garden_module.open_garden_by_command(
        message=message,
        user=SimpleNamespace(),
        db_session=SimpleNamespace(),
        settings=SimpleNamespace(bot=SimpleNamespace(CHAT_LOG_ID=1)),
    )

    show_garden_list.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize("raw_date", ["10.06.2026", "15.02.2026"])
async def test_add_garden_plant_last_watered_rejects_invalid_date_range(monkeypatch, raw_date: str) -> None:
    class _TestDatetime:
        @classmethod
        def now(cls, _tz=None):
            return datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC)

        @classmethod
        def strptime(cls, date_string: str, fmt: str):
            return datetime.strptime(date_string, fmt)

    message = FakeMessage()
    message.text = raw_date
    state = FakeState(
        {
            "garden_pending_plant_name": "Пацан",
            "garden_watering_interval_days": 7,
        }
    )
    add_plant = AsyncMock()

    monkeypatch.setattr(garden_module, "datetime", _TestDatetime)
    monkeypatch.setattr(garden_module, "ensure_garden_access", AsyncMock(return_value=True))
    monkeypatch.setattr(garden_module, "add_plant", add_plant)

    await garden_module.add_garden_plant_last_watered(
        message=message,
        state=state,
        user=SimpleNamespace(tg_id=1),
        db_session=SimpleNamespace(),
        settings=SimpleNamespace(bot=SimpleNamespace(CHAT_LOG_ID=1)),
    )

    add_plant.assert_not_awaited()
    assert message.answers == [
        "Дата последнего полива должна быть не позже сегодня и не старше 40 дней. "
        "Введите дату в формате ДД.ММ.ГГГГ."
    ]
    assert state.cleared is False


def test_resolve_next_watering_at_clamps_past_date_to_now() -> None:
    now = datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC)
    last_watered_at = datetime(2026, 4, 12, 0, 0, 0, tzinfo=UTC)

    resolved = resolve_next_watering_at(last_watered_at, 7, now=now)

    assert resolved == now


@pytest.mark.parametrize(
    ("raw_text", "expected"),
    [
        ("7", 7),
        ("10 дней", 10),
        ("Поливать раз в 15 дней", 15),
        ("0", None),
        ("61", None),
        ("не знаю", None),
    ],
)
def test_parse_watering_days(raw_text: str, expected: int | None) -> None:
    assert garden_module.parse_watering_days(raw_text) == expected


def test_parse_garden_ai_result_extracts_name_health_and_watering_days() -> None:
    parsed = garden_module.parse_garden_ai_result(
        "NAME: фикус\nHEALTH: ПОМОЩЬ\nWATER_DAYS: 10"
    )

    assert parsed == {
        "name": "фикус",
        "health_status": "нуждается в помощи",
        "watering_days": 10,
    }


def test_was_watered_today_detects_same_day() -> None:
    now = datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC)
    plant = SimpleNamespace(last_watered_at=datetime(2026, 4, 26, 8, 0, 0, tzinfo=UTC))

    assert was_watered_today(plant, now=now) is True


@pytest.mark.anyio
async def test_add_garden_plant_last_watered_shows_today_for_overdue_next_watering(monkeypatch) -> None:
    class _TestDatetime:
        @classmethod
        def now(cls, _tz=None):
            return datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC)

        @classmethod
        def strptime(cls, date_string: str, fmt: str):
            return datetime.strptime(date_string, fmt)

    plant = SimpleNamespace(
        id=1,
        watering_interval_days=7,
        status="нуждается в помощи",
        last_watered_at=None,
        next_watering_at=None,
    )
    message = FakeMessage()
    message.text = "12.04.2026"
    state = FakeState(
        {
            "garden_pending_plant_name": "кент",
            "garden_watering_interval_days": 7,
            "garden_photo_snapshot": {},
            "garden_photo_analysis": None,
            "garden_photo_file_path": None,
            "garden_health_status": "нуждается в помощи",
        }
    )
    show_garden_list = AsyncMock()

    monkeypatch.setattr(garden_module, "datetime", _TestDatetime)
    monkeypatch.setattr(garden_module, "ensure_garden_access", AsyncMock(return_value=True))
    monkeypatch.setattr(garden_module, "add_plant", AsyncMock(return_value=plant))
    monkeypatch.setattr(garden_module, "show_garden_list", show_garden_list)
    monkeypatch.setattr(garden_module, "log_garden_action", AsyncMock())

    await garden_module.add_garden_plant_last_watered(
        message=message,
        state=state,
        user=SimpleNamespace(tg_id=1),
        db_session=SimpleNamespace(flush=AsyncMock()),
        settings=SimpleNamespace(bot=SimpleNamespace(CHAT_LOG_ID=1)),
    )

    assert message.answers[0] == "Готово! «кент» теперь в саду."
    assert message.answers[1] == "Записал последний полив: 12.04.2026.\nСледующий полив: сегодня."


@pytest.mark.anyio
async def test_mark_watered_rejects_second_watering_same_day(monkeypatch) -> None:
    message = FakeMessage()
    callback = FakeCallback(message)
    plant = SimpleNamespace(
        id=1,
        name="кент",
        last_watered_at=datetime(2026, 4, 26, 8, 0, 0, tzinfo=UTC),
    )
    mark_plant_watered = AsyncMock()

    monkeypatch.setattr(garden_module, "get_plant", AsyncMock(return_value=plant))
    monkeypatch.setattr(garden_module, "mark_plant_watered", mark_plant_watered)
    monkeypatch.setattr(garden_module, "log_garden_action", AsyncMock())

    await garden_module.mark_watered(
        callback=callback,
        callback_data=SimpleNamespace(plant_id=1),
        user=SimpleNamespace(tg_id=1, fullname="Test", username="test"),
        db_session=SimpleNamespace(),
        settings=SimpleNamespace(bot=SimpleNamespace(CHAT_LOG_ID=1)),
    )

    mark_plant_watered.assert_not_awaited()
    assert message.answers == [
        "Сегодня «кент» уже был полит(а) 💧\nДважды за день поливать нельзя — это плохо для растения."
    ]


@pytest.mark.anyio
async def test_back_from_garden_list_returns_to_ai_dialog(monkeypatch) -> None:
    message = FakeMessage()
    callback = FakeCallback(message)
    state = FakeState(current_state=garden_module.GardenState.IN_GARDEN_STUB)

    monkeypatch.setattr(garden_module, "log_garden_action", AsyncMock())

    await garden_module.back_handler(
        callback=callback,
        callback_data=SimpleNamespace(plant_id=None),
        state=state,
        user=SimpleNamespace(tg_id=1, fullname="Test", username="test"),
        db_session=SimpleNamespace(),
        settings=SimpleNamespace(bot=SimpleNamespace(CHAT_LOG_ID=1)),
    )

    assert state.state == garden_module.AIState.IN_AI_DIALOG
    assert message.answers == ["Возвращаю в режим диалога 💬"]
