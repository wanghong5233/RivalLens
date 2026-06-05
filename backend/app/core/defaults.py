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

# Agent loop and planning caps.
MAX_SUPERVISOR_ITERATIONS: int = 10
MAX_REACT_TURNS: int = 6
MAX_ADDITIONAL_PLAN_TASKS: int = 5
MAX_FOCUS_DIMENSIONS: int = 5
MAX_QA_RERESEARCH_ITERATIONS: int = 3

# Discovery capacity defaults and hard caps.
MAX_DISCOVERY_SEARCH_QUERIES: int = 5
DISCOVERY_SEARCH_MAX_RESULTS_CAP: int = 10
DISCOVERY_SNIPPETS_TO_EXTRACT: int = 20
DEFAULT_DISCOVER_MAX_RESULTS: int = 8

# Plan text caps shared by LLM parsing and user-added plan task normalization.
PLAN_TASK_TITLE_MAX_LEN: int = 60
PLAN_TASK_DESCRIPTION_MAX_LEN: int = 500
