#!/usr/bin/env python3
"""Ping configured OpenAI Assistant using project env vars.

Usage:
  python scripts/ping_ai_agent.py --prompt "Привет! Ответь одним словом: pong"
"""

from __future__ import annotations

import argparse
import asyncio
import os

from dotenv import load_dotenv
from openai import AsyncOpenAI


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send a test message to configured OpenAI assistant")
    parser.add_argument(
        "--prompt",
        default="Привет! Ответь коротко: pong",
        help="Prompt sent to assistant",
    )
    parser.add_argument("--timeout", type=int, default=120, help="Seconds to wait for run completion")
    return parser.parse_args()


async def wait_for_completion(client: AsyncOpenAI, thread_id: str, run_id: str, timeout: int) -> str:
    loop = asyncio.get_running_loop()
    started = loop.time()

    while True:
        run = await client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run_id)
        if run.status in {"completed", "failed", "cancelled", "expired"}:
            return run.status

        if loop.time() - started > timeout:
            raise TimeoutError(f"Run {run_id} did not complete within {timeout} seconds")

        await asyncio.sleep(2)


async def main() -> None:
    args = parse_args()
    load_dotenv()

    api_key = os.getenv("GPT_OPENAI_API_KEY", "")
    assistant_id = os.getenv("GPT_ASSISTANT_ID", "")

    if not api_key:
        raise SystemExit("GPT_OPENAI_API_KEY is empty or not set")
    if not assistant_id:
        raise SystemExit("GPT_ASSISTANT_ID is empty or not set")

    client = AsyncOpenAI(api_key=api_key)

    thread = await client.beta.threads.create()
    await client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=args.prompt,
    )

    run = await client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=assistant_id,
    )

    status = await wait_for_completion(client, thread.id, run.id, args.timeout)
    if status != "completed":
        raise SystemExit(f"Assistant run finished with status: {status}")

    messages = await client.beta.threads.messages.list(thread_id=thread.id, limit=1)
    answer = messages.data[0].content[0].text.value
    print("Assistant reply:\n")
    print(answer)


if __name__ == "__main__":
    asyncio.run(main())