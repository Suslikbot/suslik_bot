from __future__ import annotations
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


STAT_PREFIX = "STAT|"
STAT_LOG_NAME = "suslik_robot"
STAT_LOG_PATTERNS = (
    "%d.%m.%Y %H:%M:%S.%f%z",
    "%d.%m.%Y %H:%M:%S%z",
)
LEGACY_PAYWALL_MARKER = "has exceeded the action limit."
LEGACY_PAYMENT_MARKERS = (
    "was successful",
    "has paid for",
)
LEGACY_DIAGNOSIS_MARKERS = (
    "calling ai_assistant_photo_handler",
    "calling handle_plant_photo",
)


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
    base_name = f"{STAT_LOG_NAME}.log"
    paths: list[Path] = []
    if log_dir.exists():
        paths.extend(sorted(log_dir.glob(f"{base_name}*")))
    root_log = Path(base_name)
    if root_log.exists():
        paths.append(root_log)
        paths.extend(sorted(Path(".").glob(f"{base_name}.*")))
    unique_paths = {path.resolve(): path for path in paths}
    return sorted(unique_paths.values())


def _parse_timestamp(line: str) -> tuple[datetime | None, str]:
    if " | " not in line:
        return None, line
    timestamp_str, message = line.split(" | ", 1)
    timestamp_str = timestamp_str.strip().replace("М", "")
    try:
        for pattern in STAT_LOG_PATTERNS:
            try:
                return datetime.strptime(timestamp_str, pattern), message.strip()
            except ValueError:
                continue
    except ValueError:
        return None, line
    return None, line

def _parse_stat_event(message: str) -> str | None:
    marker_index = message.find(STAT_PREFIX)
    if marker_index == -1:
        return None
    payload = message[marker_index + len(STAT_PREFIX):]
    for chunk in payload.split("|"):
        if chunk.startswith("event="):
            return chunk.split("=", 1)[1]
    return None


def _parse_update_payload(message: str) -> dict | None:
    stripped = message.strip()
    if not stripped.startswith("{"):
        return None
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if "update_id" not in payload:
        return None
    return payload


def _get_message_payload(update_payload: dict) -> dict | None:
    return update_payload.get("message") or update_payload.get("edited_message")


def _extract_event_from_update(
    update_payload: dict,
    seen_photo_users: set[int],
) -> str | None:
    message_payload = _get_message_payload(update_payload)
    if not message_payload:
        return None
    from_user = message_payload.get("from_user") or {}
    if from_user.get("is_bot"):
        return None
    text = message_payload.get("text")
    if isinstance(text, str) and text.startswith("/start"):
        return "Start_bot"
    if "photo" in message_payload:
        user_id = from_user.get("id")
        if isinstance(user_id, int) and user_id not in seen_photo_users:
            seen_photo_users.add(user_id)
            return "Photo_upload"
    return None


def _is_paywall_view(message: str) -> bool:
    return LEGACY_PAYWALL_MARKER in message


def _is_payment_success(message: str) -> bool:
    return any(marker in message for marker in LEGACY_PAYMENT_MARKERS)


def _is_diagnosis_result(message: str) -> bool:
    return any(marker in message for marker in LEGACY_DIAGNOSIS_MARKERS)

def iter_stat_events(paths: Iterable[Path]) -> list[tuple[datetime, str]]:
    events: list[tuple[datetime, str]] = []
    seen_photo_users: set[int] = set()
    for path in paths:
        try:
            with path.open("r", encoding="utf-8") as log_file:
                for line in log_file:
                    timestamp, message = _parse_timestamp(line)
                    if timestamp is None:
                        continue
                    stat_event = _parse_stat_event(message)
                    if stat_event:
                        events.append((timestamp, stat_event))
                        continue
                    if _is_paywall_view(message):
                        events.append((timestamp, "Paywall_view"))
                    if _is_payment_success(message):
                        events.append((timestamp, "Payment_success"))
                    if _is_diagnosis_result(message):
                        events.append((timestamp, "Diagnosis_result"))
                    update_payload = _parse_update_payload(message)
                    if update_payload:
                        update_event = _extract_event_from_update(update_payload, seen_photo_users)
                        if update_event:
                            events.append((timestamp, update_event))
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