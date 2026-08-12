import json
import logging
from datetime import UTC, datetime
from typing import Any


class StructuredJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", record.getMessage()),
        }
        context = getattr(record, "context", None)
        if context:
            payload.update(context)
        return json.dumps(payload, separators=(",", ":"), sort_keys=True, default=str)


class StructuredStreamHandler(logging.StreamHandler):
    cmm_structured = True


def configure_logging(level: str = "INFO") -> None:
    logger = logging.getLogger("cmm")
    logger.setLevel(level.upper())
    logger.propagate = False
    if not any(getattr(handler, "cmm_structured", False) for handler in logger.handlers):
        handler = StructuredStreamHandler()
        handler.setFormatter(StructuredJsonFormatter())
        logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"cmm.{name}")


def log_event(logger: logging.Logger, level: int, event: str, **context: Any) -> None:
    safe_context = {key: value for key, value in context.items() if value is not None}
    logger.log(level, event, extra={"event": event, "context": safe_context})


def log_failure(
    logger: logging.Logger, event: str, exc: Exception, *, correlation_id: str | None,
    node: str, source: str | None = None, degraded: str | None = None,
) -> None:
    log_event(
        logger, logging.WARNING, event,
        correlation_id=correlation_id,
        node=node,
        source=source,
        exception_type=type(exc).__name__,
        degraded=degraded,
    )