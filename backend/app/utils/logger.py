from __future__ import annotations

from contextlib import contextmanager
import logging
import sys
from typing import Iterator

import structlog

from core.config import settings
from utils.request_id import request_id_ctx


def configure_logging() -> None:
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    class _SuppressHealthAccessLog(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            message = record.getMessage()
            return 'GET /health' not in message and 'HEAD /health' not in message

    logging.getLogger("uvicorn.access").addFilter(_SuppressHealthAccessLog())

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)


def bind_request_id() -> None:
    structlog.contextvars.bind_contextvars(request_id=request_id_ctx.get())


def clear_request_id() -> None:
    structlog.contextvars.clear_contextvars()


@contextmanager
def bind_run(run_id: str, *, node: str | None = None) -> Iterator[None]:
    values: dict[str, str] = {"run_id": run_id}
    if node is not None:
        values["node"] = node
    with structlog.contextvars.bound_contextvars(**values):
        yield


@contextmanager
def bind_step(step_id: str) -> Iterator[None]:
    with structlog.contextvars.bound_contextvars(step_id=step_id):
        yield
