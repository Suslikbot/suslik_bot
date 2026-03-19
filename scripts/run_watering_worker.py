import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def main() -> None:
    runpy.run_module("bot.watering_worker", run_name="__main__")


if __name__ == "__main__":
    main()