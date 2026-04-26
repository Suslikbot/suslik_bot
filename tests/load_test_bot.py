import asyncio
import os
import time

import httpx

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]


API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"


async def send_message(client, text):
    resp = await client.post(
        API_URL,
        json={
            "chat_id": CHAT_ID,
            "text": text,
        },
        timeout=10,
    )
    resp.raise_for_status()


async def main(concurrency=10, total=100):
    start = time.time()

    async with httpx.AsyncClient() as client:
        sem = asyncio.Semaphore(concurrency)

        async def task(i):
            async with sem:
                await send_message(client, f"/start {i}")

        await asyncio.gather(*(task(i) for i in range(total)))

    elapsed = time.time() - start
    print(f"Sent {total} messages in {elapsed:.2f}s")  # noqa: T201


if __name__ == "__main__":
    asyncio.run(main(concurrency=10, total=100))
