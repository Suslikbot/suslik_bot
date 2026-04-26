"""Purge user data for testing: Redis FSM + Postgres rows by Telegram ID.

This script removes:
- FSM state/data in Redis (aiogram storage)
- User row in Postgres (`users`) by tg_id
- One-time purchases by user_id (no FK cascade in model)

Because of FK ON DELETE CASCADE from `users.tg_id`, deleting user also removes:
- user_counters
- payments
- plant_analyses

Usage:
  python scripts/purge_user.py --tg-id 123456789 --yes
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis
from sqlalchemy import delete, select

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bot.config import get_settings  # noqa: E402
from database.database_connector import get_db  # noqa: E402
from database.models import OneTimePurchase, User  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Purge user from Redis FSM and Postgres")
    parser.add_argument("--tg-id", type=int, required=True, help="Telegram user id")
    parser.add_argument("--yes", action="store_true", help="Confirm destructive action")
    return parser.parse_args()


async def clear_fsm(tg_id: int, settings) -> None:
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
    await fsm.clear()

    await bot.session.close()
    await storage.close()


async def purge_postgres(tg_id: int, settings) -> dict[str, int]:
    db = get_db(settings)
    deleted_counts = {
        "one_time_purchases": 0,
        "users": 0,
    }

    async with db.session_factory() as session:
        deleted_counts["one_time_purchases"] = (
            await session.execute(delete(OneTimePurchase).where(OneTimePurchase.user_id == tg_id))
        ).rowcount or 0

        user = await session.scalar(select(User).where(User.tg_id == tg_id))
        if user is not None:
            await session.delete(user)
            deleted_counts["users"] = 1

        await session.commit()

    await db.dispose()
    return deleted_counts


async def main() -> None:
    args = parse_args()
    if not args.yes:
        raise SystemExit("Refusing to purge without --yes")

    settings = get_settings()

    await clear_fsm(args.tg_id, settings)
    deleted = await purge_postgres(args.tg_id, settings)

    print("Purge completed") # noqa: T201
    print(f"tg_id: {args.tg_id}") # noqa: T201
    print("deleted:") # noqa: T201
    print("- redis_fsm_state_and_data") # noqa: T201
    print(f"- one_time_purchases: {deleted['one_time_purchases']}") # noqa: T201
    print(f"- users: {deleted['users']} (cascade removes user_counters, payments, plant_analyses)") # noqa: T201


if __name__ == "__main__":
    asyncio.run(main())
