import logging.config
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from pydantic_settings import SettingsConfigDict
from bot.log_context import LogContextFilter


class CustomFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        ct = datetime.fromtimestamp(record.created).astimezone()
        if datefmt:
            base_time = ct.strftime("%d.%m.%Y %H:%M:%S")
            msecs = f"{int(record.msecs):03d}М"
            tz = ct.strftime("%z")
            return f"{base_time}.{msecs}{tz}"
        return super().formatTime(record, datefmt)


main_template = {
    "format": "%(asctime)s | corr=%(correlation_id)s user=%(user_id)s state=%(state)s op=%(operation)s | %(message)s",
    "datefmt": "%d.%m.%Y %H:%M:%S%z",
}
error_template = {
    "format": "%(asctime)s [%(levelname)8s] [%(module)s:%(funcName)s:%(lineno)d] corr=%(correlation_id)s user=%(user_id)s state=%(state)s op=%(operation)s | %(message)s",
    "datefmt": "%d.%m.%Y %H:%M:%S%z",
}


def setup_logs(app_name: str):
    Path("logs").mkdir(parents=True, exist_ok=True)
    logging_config = get_logging_config(app_name)
    logging.config.dictConfig(logging_config)


def get_logging_config(app_name: str):
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "main": {
                "()": CustomFormatter,
                "format": main_template["format"],
                "datefmt": main_template["datefmt"],
            },
            "errors": {
                "()": CustomFormatter,
                "format": error_template["format"],
                "datefmt": error_template["datefmt"],
            },
        },
        "filters": {
            "log_context": {
                "()": LogContextFilter,
            },
        },
        "handlers": {
            "stdout": {
                "class": "logging.StreamHandler",
                "level": "INFO",
                "formatter": "main",
                "stream": sys.stdout,
                "filters": ["log_context"],
            },
            "stderr": {
                "class": "logging.StreamHandler",
                "level": "WARNING",
                "formatter": "errors",
                "stream": sys.stderr,
                "filters": ["log_context"],
            },
            "file": {
                "()": RotatingFileHandler,
                "level": "INFO",
                "formatter": "main",
                "filename": f"logs/{app_name}.log",
                "maxBytes": 50000000,
                "backupCount": 3,
                "encoding": "utf-8",
                "filters": ["log_context"],
            },
        },
        "loggers": {
            "root": {
                "level": "DEBUG",
                "handlers": ["stdout", "stderr", "file"],
            },
        },
    }


def assign_config_dict(prefix: str = "") -> SettingsConfigDict:
    return SettingsConfigDict(
        env_prefix=prefix,
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )
