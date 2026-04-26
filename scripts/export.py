import json
import os
from pathlib import Path

import redis

r = redis.Redis(
    host=os.environ["REDIS_HOST"],
    port=int(os.environ.get("REDIS_PORT", "6379")),
    username=os.environ.get("REDIS_USERNAME", "default"),
    password=os.environ["REDIS_PASSWORD"],
    decode_responses=True,
)

data = {}

for key in r.scan_iter("*"):
    try:
        data[key] = r.get(key)
    except redis.ResponseError:
        data[key] = "NON-STRING"

with Path("dump2.json").open("w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)

print("Export complete") # noqa: T201
