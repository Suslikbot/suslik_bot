import redis
import json

r = redis.Redis(
    host="redis-18396.c13.us-east-1-3.ec2.cloud.redislabs.com",
    port=18396,
    username="default",
    password="o0vbOITUgcYpHP7vSrictJvCjKnSuBS3",
    decode_responses=True
)

data = {}

for key in r.scan_iter("*"):
    try:
        data[key] = r.get(key)
    except:
        data[key] = "NON-STRING"

with open("dump2.json", "w") as f:
    json.dump(data, f, indent=2)

print("Export complete")