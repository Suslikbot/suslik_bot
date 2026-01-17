import asyncio
from types import SimpleNamespace

import pytest

from bot.handlers import command as command_module
from bot.internal.enums import AIState


class FakeMessage:
    def __init__(self) -> None:
        self.answers: list[str] = []
        self.photos: list[str] = []

    async def answer(self, text: str, *args, **kwargs) -> None:
        self.answers.append(text)

    async def answer_photo(self, photo, *args, **kwargs) -> None:
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
    user = SimpleNamespace(source="default", fullname="Test User", is_context_added=True)
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
