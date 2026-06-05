"""Single source of truth for default analysis dimensions and entity caps.

Pure business constants only: no env reads, no imports of app modules, so any
layer (schemas / agents / router) can import this without import cycles.
Env-driven runtime config lives in core/config.py instead.
"""
from __future__ import annotations

# Default focus dimensions used when intake / LLM does not specify any.
DEFAULT_FOCUS_DIMENSIONS: tuple[str, ...] = ("feature", "pricing", "user_feedback")
