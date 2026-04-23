from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers import garden as garden_module


class FakeMessage:
    def __init__(self) -> None:
        self.answers: list[str] = []

    async def answer(self, text: str, *args, **kwargs) -> None:
        self.answers.append(text)


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

    await garden_module.open_garden_by_command(
        message=message,
        user=SimpleNamespace(),
        db_session=SimpleNamespace(),
    )

    show_garden_list.assert_awaited_once()


@pytest.mark.anyio
async def test_open_garden_by_command_without_subscription(monkeypatch) -> None:
    message = FakeMessage()
    show_garden_list = AsyncMock()

    monkeypatch.setattr(garden_module, "ensure_garden_access", AsyncMock(return_value=False))
    monkeypatch.setattr(garden_module, "show_garden_list", show_garden_list)

    await garden_module.open_garden_by_command(
        message=message,
        user=SimpleNamespace(),
        db_session=SimpleNamespace(),
    )

    show_garden_list.assert_not_awaited()
