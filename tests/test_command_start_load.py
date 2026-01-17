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


@pytest.mark.asyncio
async def test_command_start_under_load(monkeypatch):
    """
    🔥 Нагрузочный тест command_handler:
    - 100 последовательных запусков
    - 50 параллельных пользователей
    """

    monkeypatch.setattr(
        command_module,
        "WELCOME_BY_SOURCE",
        {"default": {"photo": None, "text": None}},
    )

    async def run_once():
        message = FakeMessage()
        state = FakeState()
        user = SimpleNamespace(
            source="default",
            fullname="Test User",
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

        return state.state, message.answers

    # --- 100 последовательных запусков ---
    for _ in range(100):
        state, answers = await run_once()
        assert state == AIState.IN_AI_DIALOG
        assert answers
        assert "Мы уже знакомы" in answers[0]

    # --- 50 параллельных запусков ---
    results = await asyncio.gather(
        *[run_once() for _ in range(50)]
    )

    for state, answers in results:
        assert state == AIState.IN_AI_DIALOG
        assert answers
        assert "Мы уже знакомы" in answers[0]
