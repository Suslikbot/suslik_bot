from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from bot.controllers.user import has_active_subscription


@pytest.mark.parametrize(
    ("user", "expected"),
    [
        (SimpleNamespace(is_subscribed=False, expired_at=datetime.now(UTC) + timedelta(days=1)), False),
        (SimpleNamespace(is_subscribed=True, expired_at=None), False),
        (SimpleNamespace(is_subscribed=True, expired_at=datetime.now(UTC)), False),
        (SimpleNamespace(is_subscribed=True, expired_at=datetime.now(UTC) - timedelta(seconds=1)), False),
        (SimpleNamespace(is_subscribed=True, expired_at=datetime.now(UTC) + timedelta(seconds=1)), True),
    ],
)
def test_has_active_subscription_cases(user, expected) -> None:
    assert has_active_subscription(user, datetime.now(UTC)) is expected
