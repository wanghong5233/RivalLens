from __future__ import annotations

from functools import wraps
from typing import Any, Awaitable, Callable, TypeVar, cast

from utils.logger import bind_run, get_logger

F = TypeVar("F", bound=Callable[..., Awaitable[dict[str, Any]]])


def log_node(name: str) -> Callable[[F], F]:
    """Add consistent start/finish/error logs around a graph node."""

    def decorator(fn: F) -> F:
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
            if not args:
                return await fn(*args, **kwargs)
            state = args[0]
            if not isinstance(state, dict):
                return await fn(*args, **kwargs)

            run_id = state.get("run_id")
            normalized_run_id = run_id if isinstance(run_id, str) else "unknown"
            logger = get_logger(f"agents.{name}")

            with bind_run(normalized_run_id, node=name):
                logger.info("node.start", iteration=state.get("current_iteration"))
                try:
                    result = await fn(*args, **kwargs)
                except Exception as exc:
                    logger.exception("node.error", exc_type=type(exc).__name__)
                    raise
                logger.info(
                    "node.finish",
                    status=result.get("status") if isinstance(result, dict) else None,
                )
                return result

        return cast(F, wrapper)

    return decorator
