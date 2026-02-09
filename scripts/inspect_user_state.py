#!/usr/bin/env python3
"""Inspect user's current FSM state (Redis) and profile data (Postgres) by Telegram ID.

Usage:
  python scripts/inspect_user_state.py --tg-id 123456789
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis
from sqlalchemy import desc, select

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bot.config import get_settings  # noqa: E402
from database.database_connector import get_db  # noqa: E402
from database.models import OneTimePurchase, Payment, PlantAnalysis, User, UserCounters  # noqa: E402


@dataclass
class UserSnapshot:
    tg_id: int
    fsm_state: str | None
    fsm_data: dict
    user: dict | None
    counters: dict | None
    latest_analysis: dict | None
    purchases: list[dict]
    recent_payments: list[dict]


def model_to_dict(model, fields: list[str]) -> dict:
    return {field: getattr(model, field) for field in fields}


async def build_snapshot(tg_id: int) -> UserSnapshot:
    settings = get_settings()
    redis_client = Redis(
        host=settings.redis.HOST,
        port=settings.redis.PORT,
        username=settings.redis.USERNAME,
        password=settings.redis.PASSWORD.get_secret_value(),
        decode_responses=True,
    )
    storage = RedisStorage(redis=redis_client)

    bot = Bot(token=settings.bot.TOKEN.get_secret_value())
    me = await bot.get_me()

    fsm = FSMContext(
        storage=storage,
        key=StorageKey(bot_id=me.id, chat_id=tg_id, user_id=tg_id),
    )

    db = get_db(settings)
    async with db.session_factory() as session:
        user = await session.scalar(select(User).where(User.tg_id == tg_id))
        counters = await session.scalar(select(UserCounters).where(UserCounters.tg_id == tg_id))
        latest_analysis = await session.scalar(
            select(PlantAnalysis)
            .where(PlantAnalysis.user_tg_id == tg_id)
            .order_by(desc(PlantAnalysis.created_at))
            .limit(1)
        )
        purchases = (
            await session.scalars(
                select(OneTimePurchase)
                .where(OneTimePurchase.user_id == tg_id)
                .order_by(desc(OneTimePurchase.created_at))
                .limit(20)
            )
        ).all()
        payments = (
            await session.scalars(
                select(Payment)
                .where(Payment.user_tg_id == tg_id)
                .order_by(desc(Payment.created_at))
                .limit(20)
            )
        ).all()

    snapshot = UserSnapshot(
        tg_id=tg_id,
        fsm_state=await fsm.get_state(),
        fsm_data=await fsm.get_data(),
        user=model_to_dict(
            user,
            [
                "id",
                "tg_id",
                "fullname",
                "username",
                "ai_thread",
                "action_count",
                "is_subscribed",
                "subscription_duration",
                "is_autopayment_enabled",
                "is_context_added",
                "expired_at",
                "space",
                "geography",
                "request",
                "payment_method_id",
                "source",
                "created_at",
            ],
        )
        if user
        else None,
        counters=model_to_dict(counters, ["id", "tg_id", "period_started_at", "image_count", "created_at"])
        if counters
        else None,
        latest_analysis=model_to_dict(
            latest_analysis,
            ["id", "user_tg_id", "thread_id", "tg_file_id", "tg_file_unique_id", "health_score", "created_at"],
        )
        if latest_analysis
        else None,
        purchases=[
            model_to_dict(p, ["id", "user_id", "product_code", "is_consumed", "created_at"]) for p in purchases
        ],
        recent_payments=[
            model_to_dict(
                p,
                [
                    "id",
                    "payment_id",
                    "user_tg_id",
                    "payment_type",
                    "price",
                    "description",
                    "is_paid",
                    "created_at",
                ],
            )
            for p in payments
        ],
    )

    await bot.session.close()
    await storage.close()
    await db.dispose()

    return snapshot


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect user FSM state (Redis) and DB records by tg_id")
    parser.add_argument("--tg-id", type=int, required=True, help="Telegram user id")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    snapshot = await build_snapshot(args.tg_id)
    print(json.dumps(asdict(snapshot), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())