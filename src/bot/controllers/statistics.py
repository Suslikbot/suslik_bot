from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


STAT_PREFIX = "STAT|"
STAT_LOG_NAME = "suslik_robot"
STAT_LOG_PATTERN = "%d.%m.%Y %H:%M:%S%z"


@dataclass(frozen=True)
class StatsSnapshot:
    start_bot: int = 0
    photo_upload: int = 0
    paywall_view: int = 0
    payment_success: int = 0
    diagnosis_result: int = 0


def build_stat_message(event: str, user_tg_id: int | None = None, extra: dict[str, str] | None = None) -> str:
    parts = [f"{STAT_PREFIX}event={event}"]
    if user_tg_id is not None:
        parts.append(f"user={user_tg_id}")
    if extra:
        parts.extend([f"{key}={value}" for key, value in extra.items()])
    return "|".join(parts)


def list_stat_log_paths() -> list[Path]:
    log_dir = Path("logs")
    base = log_dir / f"{STAT_LOG_NAME}.log"
    if not log_dir.exists():
        return []
    return sorted(log_dir.glob(f"{base.name}*"))


def _parse_timestamp(line: str) -> tuple[datetime | None, str]:
    if " | " not in line:
        return None, line
    timestamp_str, message = line.split(" | ", 1)
    try:
        return datetime.strptime(timestamp_str.strip(), STAT_LOG_PATTERN), message.strip()
    except ValueError:
        return None, line


def iter_stat_events(paths: Iterable[Path]) -> list[tuple[datetime, str]]:
    events: list[tuple[datetime, str]] = []
    for path in paths:
        try:
            with path.open("r", encoding="utf-8") as log_file:
                for line in log_file:
                    if STAT_PREFIX not in line:
                        continue
                    timestamp, message = _parse_timestamp(line)
                    if timestamp is None:
                        continue
                    marker_index = message.find(STAT_PREFIX)
                    if marker_index == -1:
                        continue
                    payload = message[marker_index + len(STAT_PREFIX):]
                    event = None
                    for chunk in payload.split("|"):
                        if chunk.startswith("event="):
                            event = chunk.split("=", 1)[1]
                            break
                    if event:
                        events.append((timestamp, event))
        except FileNotFoundError:
            continue
    return events


def build_stats_snapshot(
    events: list[tuple[datetime, str]],
    start_at: datetime | None,
    end_at: datetime | None,
) -> StatsSnapshot:
    snapshot = StatsSnapshot()
    counts = {
        "Start_bot": 0,
        "Photo_upload": 0,
        "Paywall_view": 0,
        "Payment_success": 0,
        "Diagnosis_result": 0,
    }
    for timestamp, event in events:
        if start_at is not None and timestamp < start_at:
            continue
        if end_at is not None and timestamp >= end_at:
            continue
        if event in counts:
            counts[event] += 1
    return StatsSnapshot(
        start_bot=counts["Start_bot"],
        photo_upload=counts["Photo_upload"],
        paywall_view=counts["Paywall_view"],
        payment_success=counts["Payment_success"],
        diagnosis_result=counts["Diagnosis_result"],
    )