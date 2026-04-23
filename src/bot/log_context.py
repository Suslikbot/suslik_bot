import logging
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any


@dataclass
class LogContext:
    correlation_id: str | None = None
    user_id: int | str | None = None
    state: str | None = None
    operation: str | None = None


_log_context: ContextVar[LogContext] = ContextVar("log_context", default=LogContext())


def get_log_context() -> LogContext:
    return _log_context.get()


def bind_log_context(
    *,
    correlation_id: str | None = None,
    user_id: int | str | None = None,
    state: str | None = None,
    operation: str | None = None,
) -> None:
    current = get_log_context()
    _log_context.set(
        LogContext(
            correlation_id=correlation_id if correlation_id is not None else current.correlation_id,
            user_id=user_id if user_id is not None else current.user_id,
            state=state if state is not None else current.state,
            operation=operation if operation is not None else current.operation,
        )
    )


def set_log_context(
    *,
    correlation_id: str | None = None,
    user_id: int | str | None = None,
    state: str | None = None,
    operation: str | None = None,
):
    return _log_context.set(
        LogContext(
            correlation_id=correlation_id,
            user_id=user_id,
            state=state,
            operation=operation,
        )
    )


def reset_log_context(token: Any) -> None:
    _log_context.reset(token)


class LogContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        context = get_log_context()
        record.correlation_id = context.correlation_id or "-"
        record.user_id = context.user_id or "-"
        record.state = context.state or "-"
        record.operation = context.operation or "-"
        return True
