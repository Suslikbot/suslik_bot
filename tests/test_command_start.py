import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from bot.handlers import command as command_module
from bot.internal.enums import AIState


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeMessage:
    def __init__(self) -> None:
        self.answers: list[str] = []
        self.photos: list[str] = []

    async def answer(self, text: str, *_args, **_kwargs) -> None:
        self.answers.append(text)

    async def answer_photo(self, photo, *_args, **_kwargs) -> None:
        self.photos.append(str(photo))


class FakeState:
    def __init__(self) -> None:
        self.state = None

    async def get_state(self):
        return self.state

    async def set_state(self, state) -> None:
        self.state = state


@pytest.mark.anyio
async def test_start_when_context_already_added_sets_state(monkeypatch) -> None:
    monkeypatch.setattr(
        command_module,
        "WELCOME_BY_SOURCE",
        {"default": {"photo": None, "text": None}},
    )

    message = FakeMessage()
    state = FakeState()
    user = SimpleNamespace(tg_id=1, source="default", fullname="Test User", is_context_added=True)
    command = SimpleNamespace(command="start")

    await command_module.command_handler(
        message=message,
        command=command,
        user=user,
        settings=SimpleNamespace(),
        state=state,
        db_session=SimpleNamespace(),
    )

    assert state.state == AIState.IN_AI_DIALOG
    assert message.answers == [
        "Мы уже знакомы 🌿\nПросто задай вопрос или пришли фото растения.",
    ]


@pytest.mark.anyio
async def test_start_for_multiple_users_sets_state(monkeypatch) -> None:
    monkeypatch.setattr(
        command_module,
        "WELCOME_BY_SOURCE",
        {"default": {"photo": None, "text": None}},
    )

    async def run_start(user_id: int):
        message = FakeMessage()
        state = FakeState()
        user = SimpleNamespace(
            tg_id=user_id,
            source="default",
            fullname=f"Test User {user_id}",
            is_context_added=True,
        )
        command = SimpleNamespace(command="start")

        await command_module.command_handler(
            message=message,
            command=command,
            user=user,
            settings=SimpleNamespace(),
            state=state,
            db_session=SimpleNamespace(),
        )

        return message, state

    results = await asyncio.gather(*(run_start(user_id) for user_id in range(10)))

    for message, state in results:
        assert state.state == AIState.IN_AI_DIALOG
        assert message.answers == [
            "Мы уже знакомы 🌿\nПросто задай вопрос или пришли фото растения.",
        ]


@pytest.mark.anyio
async def test_dialog_with_active_subscription_has_full_access_message() -> None:
    message = FakeMessage()
    state = FakeState()
    user = SimpleNamespace(
        tg_id=123,
        is_subscribed=True,
        expired_at=datetime.now(UTC) + timedelta(days=1),
        action_count=0,
    )
    command = SimpleNamespace(command="dialog")
    settings = SimpleNamespace(bot=SimpleNamespace(ADMINS=[], ACTIONS_THRESHOLD=5))

    await command_module.command_handler(
        message=message,
        command=command,
        user=user,
        settings=settings,
        state=state,
        db_session=SimpleNamespace(),
    )

    assert state.state == AIState.IN_AI_DIALOG
    assert message.answers == [
        "Режим AI-диалога активирован 💬\nПодписка активна — у вас полный доступ.",
    ]


@pytest.mark.anyio
async def test_dialog_without_subscription_keeps_freemium_message() -> None:
    message = FakeMessage()
    state = FakeState()
    user = SimpleNamespace(
        tg_id=321,
        is_subscribed=False,
        expired_at=None,
        action_count=3,
    )
    command = SimpleNamespace(command="dialog")
    settings = SimpleNamespace(bot=SimpleNamespace(ADMINS=[], ACTIONS_THRESHOLD=5))

    await command_module.command_handler(
        message=message,
        command=command,
        user=user,
        settings=settings,
        state=state,
        db_session=SimpleNamespace(),
    )

    assert state.state == AIState.IN_AI_DIALOG
    assert message.answers == [
        "Режим AI-диалога активирован 💬\nВы в бесплатном режиме: осталось 2 запросов.",
    ]
