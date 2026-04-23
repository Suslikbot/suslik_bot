from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from bot.internal.enums import PaidEntity
from webapp import webhook as webhook_module


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeRequest:
    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.headers = {"x-request-id": "test-request"}
        self.app = SimpleNamespace(state=SimpleNamespace(bot_id=42))

    async def json(self) -> dict:
        return self._payload


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.flush_calls = 0
        self.commit_calls = 0

    def add(self, obj) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        self.flush_calls += 1

    async def commit(self) -> None:
        self.commit_calls += 1


class FakeFSMContext:
    async def set_data(self, _data: dict) -> None:
        return


class FakeBot:
    def __init__(self) -> None:
        self.sent_messages: list[tuple] = []
        self.sent_photos: list[tuple] = []

    async def send_message(self, *args, **kwargs) -> None:
        self.sent_messages.append((args, kwargs))

    async def send_photo(self, *args, **kwargs) -> None:
        self.sent_photos.append((args, kwargs))


@pytest.mark.anyio
async def test_successful_payment_opens_access_and_duplicate_is_idempotent(monkeypatch) -> None:
    payment = SimpleNamespace(
        payment_id="pay_1",
        user_tg_id=101,
        payment_type="one_time",
        is_paid=False,
    )
    user = SimpleNamespace(
        tg_id=101,
        username="@u",
        expired_at=None,
        is_subscribed=False,
        payment_method_id=None,
        is_autopayment_enabled=False,
        subscription_duration=None,
    )
    bot = FakeBot()
    db_session = FakeSession()
    settings = SimpleNamespace(
        redis=SimpleNamespace(HOST="localhost", PORT=6379, DB=0, USERNAME=None, PASSWORD=SimpleNamespace(get_secret_value=lambda: "")),
        bot=SimpleNamespace(CHAT_LOG_ID=999),
    )
    payload = {
        "type": "notification",
        "event": "payment.succeeded",
        "object": {
            "id": "pay_1",
            "status": "succeeded",
            "paid": True,
            "metadata": {"entity": PaidEntity.ONE_MONTH_SUBSCRIPTION},
        },
    }

    monkeypatch.setattr(webhook_module, "Redis", lambda *args, **kwargs: object())
    monkeypatch.setattr(webhook_module, "RedisStorage", lambda *_: object())
    monkeypatch.setattr(webhook_module, "FSMContext", lambda *args, **kwargs: FakeFSMContext())
    monkeypatch.setattr(webhook_module, "FSInputFile", lambda path: path)
    async def fake_get_payment_from_db(*_args, **_kwargs):
        return payment

    async def fake_get_user_from_db_by_tg_id(*_args, **_kwargs):
        return user

    monkeypatch.setattr(webhook_module, "get_payment_from_db", fake_get_payment_from_db)
    monkeypatch.setattr(webhook_module, "get_user_from_db_by_tg_id", fake_get_user_from_db_by_tg_id)

    request = FakeRequest(payload)

    first_response = await webhook_module.yookassa_webhook(request=request, bot=bot, settings=settings, db_session=db_session)
    first_expired_at = user.expired_at

    second_response = await webhook_module.yookassa_webhook(request=request, bot=bot, settings=settings, db_session=db_session)

    assert first_response.status_code == 200
    assert second_response.status_code == 200

    assert user.is_subscribed is True
    assert user.expired_at is not None
    assert user.expired_at > datetime.now(UTC) + timedelta(days=29)
    assert payment.is_paid is True

    assert len(bot.sent_photos) == 1
    assert user.expired_at == first_expired_at
