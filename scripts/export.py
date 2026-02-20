import redis
import json

r = redis.Redis(
    host="redis-12487.c278.us-east-1-4.ec2.cloud.redislabs.com",
    port=12487,
    username="default",
    password="VfW7UIF9fCqWfgEB4BisP0qGBCYMx5QA",
    decode_responses=True
)

data = {}

for key in r.scan_iter("*"):
    try:
        data[key] = r.get(key)
    except:
        data[key] = "NON-STRING"

with open("dump.json", "w") as f:
    json.dump(data, f, indent=2)

print("Export complete")