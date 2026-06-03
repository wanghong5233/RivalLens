from __future__ import annotations

from agents.nodes.planner import reconcile_plan_tree_after_discovery
from schemas.plan import PlanTask, PlanTree


def test_reconcile_plan_tree_inserts_research_tasks_after_discover() -> None:
    plan = PlanTree(
        plan_id="plan_test",
        tasks=[
            PlanTask(stage="discover", title="发现竞品", description="discover"),
            PlanTask(stage="analyze", title="分析", description="analyze"),
            PlanTask(stage="write", title="撰写", description="write"),
        ],
        version=1,
    )
    reconciled = reconcile_plan_tree_after_discovery(
        plan_tree=plan,
        discovered_competitors=["Notion", "Cursor"],
        focus_dimensions=["feature", "pricing"],
    )
    stages = [task.stage for task in reconciled.tasks]
    assert stages == ["discover", "research", "research", "analyze", "write"]
    research_tasks = [task for task in reconciled.tasks if task.stage == "research"]
    assert [task.competitor_id for task in research_tasks] == ["Notion", "Cursor"]
    assert reconciled.version == 2


def test_reconcile_plan_tree_skips_duplicate_competitors() -> None:
    plan = PlanTree(
        tasks=[
            PlanTask(stage="discover", title="发现竞品", description="discover"),
            PlanTask(
                stage="research",
                title="调研 Notion",
                description="research",
                competitor_id="Notion",
            ),
            PlanTask(stage="analyze", title="分析", description="analyze"),
        ],
        version=3,
    )
    reconciled = reconcile_plan_tree_after_discovery(
        plan_tree=plan,
        discovered_competitors=["Notion", "Cursor"],
    )
    research_competitors = [
        task.competitor_id for task in reconciled.tasks if task.stage == "research"
    ]
    assert research_competitors == ["Notion", "Cursor"]
    assert reconciled.version == 4

