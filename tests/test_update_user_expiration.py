from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from dateutil.relativedelta import relativedelta

from bot.controllers.user import update_user_expiration


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeSession:
    def __init__(self) -> None:
        self.added = []

    def add(self, obj) -> None:
        self.added.append(obj)


@pytest.mark.anyio
async def test_update_user_expiration_extends_from_current_expired_at_when_active() -> None:
    session = FakeSession()
    current_expired_at = datetime.now(UTC) + timedelta(days=10)
    user = SimpleNamespace(tg_id=1, expired_at=current_expired_at, is_subscribed=False)

    new_expired_at = await update_user_expiration(user, relativedelta(months=1), session)

    assert new_expired_at == current_expired_at + relativedelta(months=1)
    assert user.expired_at == current_expired_at + relativedelta(months=1)
    assert user.is_subscribed is True
    assert session.added == [user]


@pytest.mark.anyio
async def test_update_user_expiration_extends_from_now_when_expired() -> None:
    session = FakeSession()
    user = SimpleNamespace(
        tg_id=1,
        expired_at=datetime.now(UTC) - timedelta(days=2),
        is_subscribed=False,
    )
    before_call = datetime.now(UTC)

    new_expired_at = await update_user_expiration(user, relativedelta(days=30), session)

    assert new_expired_at >= before_call + relativedelta(days=30)
    assert user.expired_at == new_expired_at
    assert user.is_subscribed is True
    assert session.added == [user]
