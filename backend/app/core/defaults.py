"""Single source of truth for default analysis dimensions and entity caps.

Pure business constants only: no env reads, no imports of app modules, so any
layer (schemas / agents / router) can import this without import cycles.
Env-driven runtime config lives in core/config.py instead.
"""
from __future__ import annotations

# Default focus dimensions used when intake / LLM does not specify any.
DEFAULT_FOCUS_DIMENSIONS: tuple[str, ...] = ("feature", "pricing", "user_feedback")

# Entity caps. Values are kept identical to the pre-S1 scattered literals so
# this consolidation is behavior-preserving.
MAX_RESEARCH_COMPETITORS: int = 8
MAX_DISCOVERY_COMPETITORS: int = 10
MAX_TOTAL_PLAN_TASKS: int = 12
MAX_WRITE_SECTIONS: int = 8
