from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from db.engine import get_session_factory
from models.evidence import EvidenceRecord
from models.llm_call import LLMCall
from models.report import Report
from models.run import Run
from models.step import Step
from models.supervisor_decision import SupervisorDecisionRecord


router = APIRouter()


class AgentStatusResponse(BaseModel):
    agent_name: str
    role: str
    status: str = Field(description="active or idle")
    task_count: int
    success_rate: float
    avg_latency_ms: int


class DashboardMetricsResponse(BaseModel):
    total_runs: int
    running_runs: int
    completed_runs: int
    failed_runs: int
    total_evidence: int
    total_llm_calls: int
    total_tokens: int
    avg_run_duration_seconds: float | None
    overall_success_rate: float


class DataSourceDistribution(BaseModel):
    source_type: str
    count: int
    percentage: float


class DailyRunStats(BaseModel):
    date: str
    count: int
    avg_duration_seconds: float | None


class DashboardResponse(BaseModel):
    metrics: DashboardMetricsResponse
    agent_status: list[AgentStatusResponse]
    source_distribution: list[DataSourceDistribution]
    daily_stats: list[DailyRunStats]


AGENT_ROLES = {
    "supervisor": "任务调度",
    "researcher": "信息采集",
    "analyst": "竞品分析",
    "writer": "报告撰写",
    "qa": "质量校验",
    "skill_curator": "技能沉淀",
}


@dataclass
class DashboardMetrics:
    total_runs: int = 0
    running_runs: int = 0
    completed_runs: int = 0
    failed_runs: int = 0
    total_evidence: int = 0
    total_llm_calls: int = 0
    total_tokens: int = 0
    total_duration_seconds: float = 0.0
    completed_duration_count: int = 0


@router.get("/api/dashboard", response_model=DashboardResponse)
async def get_dashboard() -> DashboardResponse:
    session_factory = get_session_factory()
    async with session_factory() as session:
        # 统计总任务数
        total_runs = (await session.execute(select(func.count()).select_from(Run))).scalar_one()
        
        # 统计运行中任务数
        running_runs = (
            await session.execute(select(func.count()).select_from(Run).where(Run.status == "running"))
        ).scalar_one()
        
        # 统计已完成任务数
        completed_runs = (
            await session.execute(select(func.count()).select_from(Run).where(Run.status == "completed"))
        ).scalar_one()
        
        # 统计失败任务数
        failed_runs = (
            await session.execute(select(func.count()).select_from(Run).where(Run.status == "failed"))
        ).scalar_one()
        
        # 统计总证据数
        total_evidence = (await session.execute(select(func.count()).select_from(EvidenceRecord))).scalar_one()
        
        # 统计总 LLM 调用数和 Token 消耗
        llm_stats = (
            await session.execute(
                select(
                    func.count(),
                    func.coalesce(func.sum(LLMCall.prompt_tokens), 0) + func.coalesce(func.sum(LLMCall.completion_tokens), 0)
                )
                .select_from(LLMCall)
            )
        ).first()
        total_llm_calls = llm_stats[0]
        total_tokens = int(llm_stats[1] or 0)
        
        # 计算平均运行时长
        avg_duration_result = (
            await session.execute(
                select(
                    func.avg(
                        func.extract("epoch", Run.finished_at) - func.extract("epoch", Run.started_at)
                    )
                )
                .select_from(Run)
                .where(Run.status.in_(["completed", "degraded"]))
                .where(Run.finished_at.is_not(None))
            )
        ).scalar_one()
        avg_duration_seconds = float(avg_duration_result) if avg_duration_result else None
        
        # 计算总体成功率
        overall_success_rate = (completed_runs / max(total_runs, 1)) * 100
        
        # 统计各 Agent 的任务数和成功率
        agent_stats = {}
        for agent_name in AGENT_ROLES.keys():
            agent_stats[agent_name] = {
                "task_count": 0,
                "success_count": 0,
                "total_latency_ms": 0,
                "latency_count": 0,
            }
        
        step_rows = (await session.execute(select(Step).order_by(Step.created_at.asc()))).scalars().all()
        for step in step_rows:
            if step.agent_name in agent_stats:
                agent_stats[step.agent_name]["task_count"] += 1
                if step.status == "completed":
                    agent_stats[step.agent_name]["success_count"] += 1
                if step.started_at and step.finished_at:
                    latency_ms = int((step.finished_at - step.started_at).total_seconds() * 1000)
                    agent_stats[step.agent_name]["total_latency_ms"] += latency_ms
                    agent_stats[step.agent_name]["latency_count"] += 1
        
        # 构建 Agent 状态响应
        agent_status = []
        for agent_name, role in AGENT_ROLES.items():
            stats = agent_stats[agent_name]
            success_rate = (stats["success_count"] / max(stats["task_count"], 1)) * 100
            avg_latency_ms = int(stats["total_latency_ms"] / max(stats["latency_count"], 1))
            agent_status.append(
                AgentStatusResponse(
                    agent_name=agent_name,
                    role=role,
                    status="active" if stats["task_count"] > 0 else "idle",
                    task_count=stats["task_count"],
                    success_rate=round(success_rate, 1),
                    avg_latency_ms=avg_latency_ms,
                )
            )
        
        # 统计数据源分布
        source_distribution_raw = (
            await session.execute(
                select(EvidenceRecord.source_type, func.count())
                .group_by(EvidenceRecord.source_type)
                .order_by(func.count().desc())
            )
        ).all()
        
        source_distribution = []
        for source_type, count in source_distribution_raw:
            percentage = (count / max(total_evidence, 1)) * 100
            source_distribution.append(
                DataSourceDistribution(
                    source_type=source_type,
                    count=count,
                    percentage=round(percentage, 1),
                )
            )
        
        # 统计最近7天的每日任务数
        daily_stats = []
        today = datetime.now(timezone.utc).date()
        for i in range(6, -1, -1):
            date = today - timedelta(days=i)
            date_start = datetime(date.year, date.month, date.day, 0, 0, 0, tzinfo=timezone.utc)
            date_end = date_start + timedelta(days=1)
            
            day_runs = (
                await session.execute(
                    select(Run)
                    .where(Run.started_at >= date_start)
                    .where(Run.started_at < date_end)
                )
            ).scalars().all()
            
            count = len(day_runs)
            completed_day_runs = [
                r for r in day_runs if r.status in ["completed", "degraded"] and r.finished_at
            ]
            if completed_day_runs:
                avg_duration = sum(
                    (r.finished_at - r.started_at).total_seconds() for r in completed_day_runs
                ) / len(completed_day_runs)
            else:
                avg_duration = None
            
            daily_stats.append(
                DailyRunStats(
                    date=date.strftime("%Y-%m-%d"),
                    count=count,
                    avg_duration_seconds=round(avg_duration, 1) if avg_duration else None,
                )
            )
    
    metrics = DashboardMetricsResponse(
        total_runs=total_runs,
        running_runs=running_runs,
        completed_runs=completed_runs,
        failed_runs=failed_runs,
        total_evidence=total_evidence,
        total_llm_calls=total_llm_calls,
        total_tokens=total_tokens,
        avg_run_duration_seconds=round(avg_duration_seconds, 1) if avg_duration_seconds else None,
        overall_success_rate=round(overall_success_rate, 1),
    )
    
    return DashboardResponse(
        metrics=metrics,
        agent_status=agent_status,
        source_distribution=source_distribution,
        daily_stats=daily_stats,
    )
