from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers import command as command_module
from bot.handlers import onboarding_callbacks as onboarding_module
from bot.internal.enums import AIState, Form

USER_ACTION_COUNT = 5
TEST_ACTION_COUNT = 2
@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeState:
    def __init__(self, current_state=None, data: dict | None = None) -> None:
        self.state = current_state
        self.data = data or {}

    async def get_state(self):
        return self.state

    async def set_state(self, state) -> None:
        self.state = state

    async def update_data(self, **kwargs) -> None:
        self.data.update(kwargs)

    async def get_data(self):
        return self.data


class FakeMessage:
    def __init__(self) -> None:
        self.answers: list[str] = []
        self.reply_markup_cleared = False
        self.bot = SimpleNamespace()
        self.chat = SimpleNamespace(id=1)

    async def answer(self, text: str, *_args, **_kwargs) -> None:
        self.answers.append(text)

    async def edit_reply_markup(self, *_args, **_kwargs) -> None:
        self.reply_markup_cleared = True


class FakeCallback:
    def __init__(self, data: str, message: FakeMessage) -> None:
        self.data = data
        self.message = message
        self.answered = False

    async def answer(self, *_args, **_kwargs) -> None:
        self.answered = True


class FakeDBSession:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("node", "handler", "callback_data", "initial_data", "expected_state", "expected_response"),
    [
        (
            "send_photo",
            onboarding_module.onb_send_photo,
            "onb:send_photo",
            {},
            AIState.WAITING_PLANT_PHOTO,
            "📎 Пришли фото растения 📸",
        ),
        (
            "home_time_now",
            onboarding_module.handle_home_time,
            "home_time:0",
            {},
            AIState.WAITING_PLANT_PHOTO,
            "Отлично! Тогда начинаем прямо сейчас 😊",
        ),
        (
            "home_time_later",
            onboarding_module.handle_home_time,
            "home_time:2",
            {},
            AIState.WAITING_CONFIRM_HOME,
            "Отлично! Напомню через 2 часа 😊",
        ),
        (
            "confirm_home",
            onboarding_module.confirm_home,
            "home:yes",
            {},
            AIState.WAITING_PLANT_PHOTO,
            "📎 Пришли фото растения 📸",
        ),
    ],
)
async def test_onboarding_fsm_transitions_table( # noqa: PLR0913
    monkeypatch,
    node,
    handler,
    callback_data,
    initial_data,
    expected_state,
    expected_response,
) -> None:
    monkeypatch.setattr(onboarding_module, "log_onboarding_step", AsyncMock())

    class _TestDatetime:
        @classmethod
        def now(cls, _tz=None):
            return datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

    class _FakeTask:
        def add_done_callback(self, _callback) -> None:
            return None

    def _consume_task(coro):
        coro.close()
        return _FakeTask()

    monkeypatch.setattr(onboarding_module, "datetime", _TestDatetime)
    monkeypatch.setattr(onboarding_module.asyncio, "create_task", _consume_task)

    message = FakeMessage()
    callback = FakeCallback(data=callback_data, message=message)
    state = FakeState(data=initial_data)

    user = SimpleNamespace(tg_id=1, username="u", ai_thread=None)
    settings = SimpleNamespace(bot=SimpleNamespace(ADMINS=[]))

    await handler(callback=callback, state=state, user=user, settings=settings)

    assert state.state == expected_state, node
    assert message.answers, node
    assert expected_response in message.answers[0], node


@pytest.mark.anyio
@pytest.mark.parametrize("scenario", ["rescue", "growth"])
async def test_onboarding_waiting_city_text_transition(monkeypatch, scenario: str) -> None:
    monkeypatch.setattr(onboarding_module, "log_onboarding_step", AsyncMock())

    async def rescue_screen(message, city):
        await message.answer(f"rescue:{city}")
        return f"rescue:{city}"

    async def growth_screen(message, city):
        await message.answer(f"growth:{city}")
        return f"growth:{city}"

    monkeypatch.setattr(onboarding_module, "show_rescue_screen", rescue_screen)
    monkeypatch.setattr(onboarding_module, "show_growth_screen", growth_screen)

    message = FakeMessage()
    message.text = "Москва"
    state = FakeState(data={"onboarding_scenario": scenario})
    user = SimpleNamespace(geography=None)
    db_session = FakeDBSession()

    await onboarding_module.handle_city(
        message=message,
        state=state,
        user=user,
        db_session=db_session,
        settings=SimpleNamespace(),
    )

    assert state.state == AIState.IN_AI_DIALOG
    assert user.geography == "Москва"
    assert message.answers == [f"{scenario}:Москва"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "handler_name",
    [
        "handle_city_photo_fallback",
        "handle_city_voice_fallback",
        "handle_city_sticker_fallback",
    ],
)
async def test_waiting_city_non_text_fallbacks(handler_name: str) -> None:
    message = FakeMessage()
    handler = getattr(onboarding_module, handler_name)

    await handler(message=message)

    assert message.answers == ["пришли город текстом"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "handler_name",
    [
        "waiting_home_time_text",
        "waiting_home_time_voice",
        "waiting_home_time_photo",
    ],
)
async def test_waiting_home_time_non_callback_fallbacks(handler_name: str) -> None:
    message = FakeMessage()
    handler = getattr(onboarding_module, handler_name)

    await handler(message=message)

    assert message.answers == ["нажми кнопку выбора времени"]


@pytest.mark.anyio
async def test_skip_callback_with_ai_thread_and_no_client(monkeypatch) -> None:
    monkeypatch.setattr(onboarding_module, "log_onboarding_step", AsyncMock())
    callback = FakeCallback(data="skip", message=FakeMessage())
    state = FakeState()
    user = SimpleNamespace(ai_thread="thread-1", action_count=0, tg_id=1)
    db_session = FakeDBSession()

    await onboarding_module.handle_skip_onboarding(
        callback=callback,
        state=state,
        user=user,
        db_session=db_session,
        settings=SimpleNamespace(),
        openai_client=None,
    )

    assert user.ai_thread == "thread-1"
    assert user.action_count == TEST_ACTION_COUNT
    assert state.state == AIState.IN_AI_DIALOG
    assert db_session.commits == 1


@pytest.mark.anyio
@pytest.mark.parametrize("callback_data", ["pay:rescue", "pay:growth"])
async def test_pay_callbacks_with_ai_thread_and_no_client(monkeypatch, callback_data: str) -> None:
    monkeypatch.setattr(onboarding_module, "log_onboarding_step", AsyncMock())
    monkeypatch.setattr(onboarding_module, "show_subscription_paywall", AsyncMock())

    callback = FakeCallback(data=callback_data, message=FakeMessage())
    user = SimpleNamespace(ai_thread="thread-1", action_count=0, tg_id=1)
    db_session = FakeDBSession()

    await onboarding_module.handle_paywall_from_onboarding(
        callback=callback,
        user=user,
        settings=SimpleNamespace(),
        db_session=db_session,
        openai_client=None,
    )

    assert user.ai_thread == "thread-1"
    assert user.action_count == USER_ACTION_COUNT
    assert db_session.commits == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    "intermediate_state",
    [
        AIState.WAITING_PLANT_PHOTO,
        AIState.WAITING_CITY,
        Form.space,
        Form.geography,
        Form.request,
    ],
)
async def test_start_smoke_in_intermediate_states(monkeypatch, intermediate_state) -> None:
    monkeypatch.setattr(
        command_module,
        "WELCOME_BY_SOURCE",
        {"default": {"photo": None, "text": None}},
    )

    message = FakeMessage()
    state = FakeState(current_state=intermediate_state)
    user = SimpleNamespace(source="default", fullname="Test", is_context_added=False, tg_id=1)

    await command_module.command_handler(
        message=message,
        command=SimpleNamespace(command="start"),
        user=user,
        settings=SimpleNamespace(),
        state=state,
        db_session=SimpleNamespace(),
    )

    assert message.answers == [
        "Мы уже начали знакомство! 👀\n"
        "Продолжай — я жду твой ответ или фото.",
    ]
