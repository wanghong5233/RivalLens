from __future__ import annotations

from core import defaults


def test_s4a_business_caps_remain_at_legacy_values() -> None:
    assert defaults.MAX_SUPERVISOR_ITERATIONS == 10
    assert defaults.MAX_REACT_TURNS == 6
    assert defaults.MAX_ADDITIONAL_PLAN_TASKS == 5
    assert defaults.MAX_FOCUS_DIMENSIONS == 5
    assert defaults.MAX_QA_RERESEARCH_ITERATIONS == 3

    assert defaults.MAX_DISCOVERY_SEARCH_QUERIES == 5
    assert defaults.DISCOVERY_SEARCH_MAX_RESULTS_CAP == 10
    assert defaults.DISCOVERY_SNIPPETS_TO_EXTRACT == 20
    assert defaults.DEFAULT_DISCOVER_MAX_RESULTS == 8

    assert defaults.PLAN_TASK_TITLE_MAX_LEN == 60
    assert defaults.PLAN_TASK_DESCRIPTION_MAX_LEN == 500
