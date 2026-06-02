import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  CircleSlash,
  Clock,
  Compass,
  Globe2,
  Hammer,
  Info,
  Loader2,
  Microscope,
  PenLine,
  Search,
  Sparkles,
  Wrench,
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { useRunDetail, useSubmitRunFollowUp } from "@/api/hooks";
import { useRunEvents } from "@/api/sse";
import type {
  EvidenceCollectedPayload,
  FollowUpReceivedPayload,
  RunFinishPayload,
  StepFinishEventPayload,
  SupervisorDecisionEventPayload,
  ToolEventPayload,
  ToolFinishEventPayload,
} from "@/api/sse";
import type { PlanTaskStage, PlanTree } from "@/api/types";
import { CancelRunButton } from "@/components/CancelRunButton";
import { EvidenceDrawer } from "@/components/EvidenceDrawer";
import { RunBreadcrumb } from "@/components/RunBreadcrumb";
import { StatusBadge } from "@/components/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { pushToast } from "@/components/ui/toaster";
import { formatRunTitle } from "@/lib/format";
import { cn } from "@/lib/utils";

type PlanTaskRuntimeStatus = "queued" | "running" | "completed";

type ToolRuntimeStatus = "running" | "done" | "error";

interface ToolActivityEntry {
  key: string;
  tool: string;
  competitorId: string | null;
  dimension: string | null;
  argsSummary: Record<string, unknown> | undefined;
  status: ToolRuntimeStatus;
  startedAt: number;
  latencyMs: number | null;
  snippetCount: number | null;
  error: string | null;
}

const STAGE_META: Record<
  PlanTaskStage,
  { label: string; icon: typeof Compass; tone: string }
> = {
  discover: { label: "发现", icon: Compass, tone: "text-primary" },
  research: { label: "调研", icon: Microscope, tone: "text-accent" },
  analyze: { label: "分析", icon: Sparkles, tone: "text-warning" },
  write: { label: "撰写", icon: PenLine, tone: "text-success" },
};

const STAGE_ORDER: PlanTaskStage[] = ["discover", "research", "analyze", "write"];

const AGENT_NAME_TO_STAGE: Record<string, PlanTaskStage> = {
  discovery: "discover",
  researcher: "research",
  analyst: "analyze",
  writer: "write",
};

const TOOL_ICONS: Record<string, typeof Wrench> = {
  search_web: Search,
  fetch_url: Globe2,
  parse_page: Globe2,
  extract_structured: Hammer,
  load_skill: Wrench,
  read_skill_file: Wrench,
};

const TERMINAL_STATUSES = new Set(["completed", "degraded", "failed", "cancelled"]);

const MAX_TOOL_ENTRIES = 12;
const MAX_EVIDENCE_ENTRIES = 30;
const TERMINAL_REDIRECT_MS = 2_500;

// Stuck detection: when the run is still "running" but no SSE traffic has been
// seen for this long, surface a "可能已中断" hint with a one-tap stop. Empirical
// upper bound: a single research iteration on Doubao + Tavily completes well
// under 90s; 4 min covers slow batches without false positives.
const STUCK_HINT_THRESHOLD_MS = 240_000;
const STUCK_HINT_TICK_MS = 15_000;

function buildToolKey(payload: ToolEventPayload): string {
  return `${payload.tool}|${payload.competitor_id ?? "-"}|${payload.dimension ?? "-"}|${payload.turn ?? 0}`;
}

export function LiveRunPage(): JSX.Element {
  const { runId: rawRunId } = useParams<{ runId: string }>();
  const runId = rawRunId ?? "";
  const navigate = useNavigate();
  const runDetail = useRunDetail(runId);

  const planTree = runDetail.data?.plan_tree ?? null;
  const runStatus = runDetail.data?.status ?? null;
  const intakeDraft = runDetail.data?.intake_draft ?? null;

  const [planTaskStatus, setPlanTaskStatus] = useState<Record<string, PlanTaskRuntimeStatus>>(
    {},
  );
  const [toolActivity, setToolActivity] = useState<ToolActivityEntry[]>([]);
  const [evidenceFeed, setEvidenceFeed] = useState<EvidenceCollectedPayload[]>([]);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerEvidenceIds, setDrawerEvidenceIds] = useState<string[]>([]);
  // Phase 4: pending follow-ups the supervisor has not yet consumed. Seeded
  // by local /follow-up submissions and remote followup.received events;
  // pruned by consumed_follow_up_ids on supervisor.decision.
  const [pendingFollowUps, setPendingFollowUps] = useState<FollowUpReceivedPayload[]>([]);
  // Terminal RUN_FINISH payload carries error_type / error_message which we
  // surface on the failed / cancelled Alert banner. Keep it in state instead
  // of synthesizing the banner from run.status alone — the reason text is
  // what makes the failure actionable.
  const [finishPayload, setFinishPayload] = useState<RunFinishPayload | null>(null);
  // Wall-clock of the most recent meaningful SSE traffic; drives stuck
  // detection. Bumped by every callback below (tool / step / decision /
  // evidence / follow-up). useRef avoids re-rendering on every event; the
  // tick timer reads it lazily.
  const lastActivityAtRef = useRef<number>(Date.now());
  const [now, setNow] = useState<number>(Date.now());

  // Reset the per-task runtime status whenever the plan changes (e.g. after a
  // version bump from a future edit). All tasks start as "queued".
  useEffect(() => {
    setPlanTaskStatus((prev) => {
      if (planTree === null) {
        return {};
      }
      // Preserve completed/running marks for tasks that still exist, default
      // everything else (and new tasks) to queued.
      const next: Record<string, PlanTaskRuntimeStatus> = {};
      for (const task of planTree.tasks) {
        next[task.task_id] = prev[task.task_id] ?? "queued";
      }
      return next;
    });
  }, [planTree]);

  const bumpActivity = useCallback(() => {
    lastActivityAtRef.current = Date.now();
  }, []);

  const handleSupervisorDecision = useCallback(
    (payload: SupervisorDecisionEventPayload) => {
      bumpActivity();
      if (payload.plan_task_ids.length > 0) {
        setPlanTaskStatus((prev) => {
          const next = { ...prev };
          for (const taskId of payload.plan_task_ids) {
            // Don't downgrade a completed tile back to "running" if a later
            // decision references the same task (defensive).
            if (next[taskId] !== "completed") {
              next[taskId] = "running";
            }
          }
          return next;
        });
      }
      const consumed = payload.consumed_follow_up_ids;
      if (consumed !== undefined && consumed.length > 0) {
        const consumedSet = new Set(consumed);
        setPendingFollowUps((prev) => prev.filter((entry) => !consumedSet.has(entry.follow_up_id)));
      }
    },
    [bumpActivity],
  );

  const handleStepFinish = useCallback(
    (payload: StepFinishEventPayload) => {
      bumpActivity();
      const targetStage = AGENT_NAME_TO_STAGE[payload.agent_name];
      if (!targetStage || planTree === null) {
        return;
      }
      setPlanTaskStatus((prev) => {
        const next = { ...prev };
        for (const task of planTree.tasks) {
          if (task.stage !== targetStage) continue;
          if (targetStage === "research") {
            // researcher.step.finish carries a single competitor_id; only flip
            // the matching task and skip the rest of the research bucket so we
            // don't mass-mark unfinished competitors as done.
            if (
              payload.competitor_id !== null &&
              task.competitor_id === payload.competitor_id
            ) {
              next[task.task_id] = "completed";
            }
          } else {
            next[task.task_id] = "completed";
          }
        }
        return next;
      });
    },
    [planTree, bumpActivity],
  );

  const handleToolStart = useCallback((payload: ToolEventPayload) => {
    bumpActivity();
    const key = buildToolKey(payload);
    setToolActivity((prev) => {
      const next: ToolActivityEntry = {
        key,
        tool: payload.tool,
        competitorId: payload.competitor_id,
        dimension: payload.dimension,
        argsSummary: payload.args_summary,
        status: "running",
        startedAt: Date.now(),
        latencyMs: null,
        snippetCount: null,
        error: null,
      };
      const without = prev.filter((entry) => entry.key !== key);
      return [next, ...without].slice(0, MAX_TOOL_ENTRIES);
    });
  }, [bumpActivity]);

  const handleToolFinish = useCallback((payload: ToolFinishEventPayload) => {
    bumpActivity();
    const key = buildToolKey(payload);
    setToolActivity((prev) => {
      const existingIndex = prev.findIndex((entry) => entry.key === key);
      const status: ToolRuntimeStatus = payload.success ? "done" : "error";
      if (existingIndex === -1) {
        // tool.finish without a paired start (out-of-order or page mounted
        // mid-call); synthesize a row so the user still sees the outcome.
        const synthesized: ToolActivityEntry = {
          key,
          tool: payload.tool,
          competitorId: payload.competitor_id,
          dimension: payload.dimension,
          argsSummary: payload.args_summary,
          status,
          startedAt: Date.now() - payload.latency_ms,
          latencyMs: payload.latency_ms,
          snippetCount: payload.snippet_count,
          error: payload.error,
        };
        return [synthesized, ...prev].slice(0, MAX_TOOL_ENTRIES);
      }
      const next = [...prev];
      next[existingIndex] = {
        ...next[existingIndex],
        status,
        latencyMs: payload.latency_ms,
        snippetCount: payload.snippet_count,
        error: payload.error,
      };
      return next;
    });
  }, [bumpActivity]);

  const handleEvidenceCollected = useCallback((payload: EvidenceCollectedPayload) => {
    bumpActivity();
    setEvidenceFeed((prev) => {
      if (prev.some((entry) => entry.evidence_id === payload.evidence_id)) {
        return prev;
      }
      return [payload, ...prev].slice(0, MAX_EVIDENCE_ENTRIES);
    });
  }, [bumpActivity]);

  const handleFollowUpReceived = useCallback((payload: FollowUpReceivedPayload) => {
    bumpActivity();
    setPendingFollowUps((prev) => {
      if (prev.some((entry) => entry.follow_up_id === payload.follow_up_id)) {
        return prev;
      }
      return [...prev, payload];
    });
  }, [bumpActivity]);

  const handleRunFinish = useCallback((payload: RunFinishPayload) => {
    setFinishPayload(payload);
  }, []);

  useRunEvents(runId, {
    onSupervisorDecision: handleSupervisorDecision,
    onStepFinish: handleStepFinish,
    onToolStart: handleToolStart,
    onToolFinish: handleToolFinish,
    onEvidenceCollected: handleEvidenceCollected,
    onFollowUpReceived: handleFollowUpReceived,
    onRunFinish: handleRunFinish,
  });

  // Stuck detection ticker: only runs while the page thinks the run is alive,
  // and only fires often enough to update the "X 分钟前" caption. The actual
  // threshold check is in the JSX so the badge appears immediately when the
  // bar crosses the line.
  useEffect(() => {
    if (runStatus === null || TERMINAL_STATUSES.has(runStatus)) {
      return;
    }
    const intervalId = window.setInterval(() => {
      setNow(Date.now());
    }, STUCK_HINT_TICK_MS);
    return () => window.clearInterval(intervalId);
  }, [runStatus]);

  // When the run reaches a terminal state, defer the navigation a moment so
  // the user can see the final flips (completed tiles + last evidence cards).
  useEffect(() => {
    if (!runId || !runStatus || !TERMINAL_STATUSES.has(runStatus)) {
      return;
    }
    const timeoutId = window.setTimeout(() => {
      navigate(`/app/runs/${runId}`, { replace: true });
    }, TERMINAL_REDIRECT_MS);
    return () => window.clearTimeout(timeoutId);
  }, [runId, runStatus, navigate]);

  const stageTasks = useMemo(() => {
    if (planTree === null) {
      return null;
    }
    const grouped: Record<PlanTaskStage, PlanTree["tasks"]> = {
      discover: [],
      research: [],
      analyze: [],
      write: [],
    };
    for (const task of planTree.tasks) {
      grouped[task.stage].push(task);
    }
    return grouped;
  }, [planTree]);

  const progress = useMemo(() => {
    if (planTree === null) {
      return { total: 0, completed: 0, running: 0 };
    }
    let completed = 0;
    let running = 0;
    for (const task of planTree.tasks) {
      const status = planTaskStatus[task.task_id] ?? "queued";
      if (status === "completed") completed += 1;
      else if (status === "running") running += 1;
    }
    return { total: planTree.tasks.length, completed, running };
  }, [planTree, planTaskStatus]);

  const handleOpenEvidence = (evidenceId: string): void => {
    setDrawerEvidenceIds([evidenceId]);
    setDrawerOpen(true);
  };

  if (!runId) {
    return (
      <div className="px-6 py-12">
        <Card>
          <CardContent className="space-y-3 py-8 text-center">
            <p className="text-foreground-muted">缺少 run id，无法打开实时进度页。</p>
            <Button asChild>
              <Link to="/app">回到我的分析</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (runDetail.isLoading) {
    return (
      <div className="px-6 py-8">
        <Skeleton className="mb-4 h-10 w-72" />
        <Skeleton className="h-[520px] w-full" />
      </div>
    );
  }

  const isTerminal = runStatus !== null && TERMINAL_STATUSES.has(runStatus);
  const userQuery = intakeDraft?.user_query ?? runDetail.data?.user_query ?? "";
  const headerTitle = runDetail.data
    ? formatRunTitle(runDetail.data, { max: 50 })
    : userQuery || "正在分析中…";
  const isFailureTerminal = runStatus === "failed" || runStatus === "cancelled";
  const idleMs = isTerminal ? 0 : now - lastActivityAtRef.current;
  const isStuck = !isTerminal && idleMs >= STUCK_HINT_THRESHOLD_MS;

  return (
    <div className="space-y-4 px-6 py-6">
      <div className="flex flex-col gap-3 rounded-2xl border border-white/[0.08] bg-white/[0.02] p-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 space-y-1.5">
          <RunBreadcrumb run={runDetail.data} current="实时监控" />
          <h1
            className="line-clamp-1 max-w-[640px] text-h3 font-semibold text-foreground"
            title={userQuery || undefined}
          >
            {headerTitle}
          </h1>
          <div className="font-mono text-xs uppercase tracking-wide text-foreground-subtle">
            {runId}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {runStatus ? <StatusBadge status={runStatus} /> : null}
          {planTree !== null ? (
            <Badge variant="secondary">
              已完成 {progress.completed}/{progress.total} · 进行中 {progress.running}
            </Badge>
          ) : null}
          {!isTerminal ? (
            <CancelRunButton runId={runId} redirectTo={null} />
          ) : null}
          {isTerminal ? (
            <Button asChild size="sm">
              <Link to={`/app/runs/${runId}`}>
                查看完整报告 <ChevronRight className="ml-1 h-3.5 w-3.5" />
              </Link>
            </Button>
          ) : null}
        </div>
      </div>

      {isFailureTerminal ? (
        <TerminalAlert
          tone={runStatus === "cancelled" ? "neutral" : "danger"}
          icon={runStatus === "cancelled" ? CircleSlash : XCircle}
          title={
            runStatus === "cancelled" ? "此次分析已停止" : "分析未能完成"
          }
          message={
            finishPayload?.error_message ??
            (runStatus === "cancelled"
              ? "已采集的证据保留在历史中，可重新发起新的分析。"
              : "后台任务异常退出，请查看日志或重新发起一次分析。")
          }
          errorType={finishPayload?.error_type ?? null}
          runId={runId}
        />
      ) : null}

      {isStuck ? (
        <StuckHintAlert
          idleMs={idleMs}
          runId={runId}
        />
      ) : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <PlanTreeColumn planTree={planTree} stageTasks={stageTasks} planTaskStatus={planTaskStatus} />
        <div className="space-y-4">
          <ToolActivityCard entries={toolActivity} />
          <EvidenceFeedCard entries={evidenceFeed} onOpen={handleOpenEvidence} />
        </div>
      </div>

      <FollowUpComposer
        runId={runId}
        isTerminal={isTerminal}
        pending={pendingFollowUps}
        onSubmitted={handleFollowUpReceived}
      />

      <EvidenceDrawer
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
        runId={runId}
        evidenceIds={drawerEvidenceIds}
      />
    </div>
  );
}

interface FollowUpComposerProps {
  runId: string;
  isTerminal: boolean;
  pending: FollowUpReceivedPayload[];
  // Mirror the SSE handler so locally-submitted follow-ups appear in the
  // chip row immediately; the upcoming followup.received broadcast will be
  // deduped by id.
  onSubmitted: (payload: FollowUpReceivedPayload) => void;
}

const FOLLOWUP_MAX_LEN = 1000;

function FollowUpComposer({
  runId,
  isTerminal,
  pending,
  onSubmitted,
}: FollowUpComposerProps): JSX.Element | null {
  const [text, setText] = useState("");
  const submit = useSubmitRunFollowUp();

  if (isTerminal) {
    return null;
  }

  const trimmed = text.trim();
  const tooLong = trimmed.length > FOLLOWUP_MAX_LEN;
  const canSubmit = trimmed.length > 0 && !tooLong && !submit.isPending;

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }
    try {
      const response = await submit.mutateAsync({
        runId,
        payload: { text: trimmed },
      });
      onSubmitted({
        follow_up_id: response.follow_up_id,
        text: trimmed,
        applies_to_stage: null,
        received_at: response.received_at,
      });
      setText("");
      pushToast({
        title: "追加指令已送达",
        description: "Agent 将在下一次决策中处理这条指令。",
        variant: "success",
      });
    } catch (error) {
      const status = (error as { response?: { status?: number } }).response?.status;
      const errorCode = (error as { response?: { data?: { error_code?: string } } }).response?.data
        ?.error_code;
      const description =
        errorCode === "FOLLOWUP_GRAPH_PAUSED"
          ? "当前需要先完成 intake / plan 确认。"
          : errorCode === "FOLLOWUP_NOT_EXECUTING"
            ? "计划尚未确认，无法追加指令。"
            : errorCode === "FOLLOWUP_RUN_NOT_RUNNING"
              ? "Run 已结束，无法追加指令。"
              : `提交失败（${status ?? "unknown"}）。`;
      pushToast({
        title: "追加指令未送达",
        description,
        variant: "danger",
      });
    }
  };

  return (
    <div className="space-y-2 rounded-2xl border border-white/[0.08] bg-white/[0.02] p-4">
      {pending.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {pending.map((entry) => (
            <Badge
              key={entry.follow_up_id}
              variant="outline"
              className="max-w-[320px] truncate"
              title={entry.text}
            >
              <Clock className="mr-1 h-3 w-3" /> 等待处理 · {entry.text}
            </Badge>
          ))}
        </div>
      ) : null}
      <form onSubmit={handleSubmit} className="flex items-end gap-2">
        <div className="flex-1">
          <label
            htmlFor="follow-up-text"
            className="block text-xs uppercase tracking-wide text-foreground-muted"
          >
            追加指令
          </label>
          <textarea
            id="follow-up-text"
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="想让 Agent 额外关注哪些竞品 / 维度？（≤ 1000 字符）"
            rows={2}
            className={cn(
              "mt-1 w-full resize-none rounded-md border border-white/[0.08] bg-transparent px-3 py-2 text-sm text-foreground placeholder:text-foreground-muted/60",
              "focus:border-primary/40 focus:outline-none",
              tooLong ? "border-danger/60" : "",
            )}
          />
          {tooLong ? (
            <div className="mt-1 text-xs text-danger">
              超过 {FOLLOWUP_MAX_LEN} 字符上限。
            </div>
          ) : null}
        </div>
        <Button type="submit" disabled={!canSubmit} size="sm">
          {submit.isPending ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : null}
          发送
        </Button>
      </form>
    </div>
  );
}

interface PlanTreeColumnProps {
  planTree: PlanTree | null;
  stageTasks: Record<PlanTaskStage, PlanTree["tasks"]> | null;
  planTaskStatus: Record<string, PlanTaskRuntimeStatus>;
}

function PlanTreeColumn({
  planTree,
  stageTasks,
  planTaskStatus,
}: PlanTreeColumnProps): JSX.Element {
  if (planTree === null || stageTasks === null) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Plan Tree</CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-72 w-full" />
        </CardContent>
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2 text-base">
          <Activity className="h-4 w-4 text-primary" />
          执行进度 · Plan Tree
        </CardTitle>
        <Badge variant="outline">v{planTree.version}</Badge>
      </CardHeader>
      <CardContent className="space-y-4">
        {STAGE_ORDER.map((stage) => {
          const tasks = stageTasks[stage];
          if (tasks.length === 0) return null;
          const meta = STAGE_META[stage];
          const Icon = meta.icon;
          return (
            <div key={stage} className="space-y-2">
              <div className="flex items-center gap-2">
                <Icon className={cn("h-4 w-4", meta.tone)} />
                <span className="text-sm font-medium text-foreground">{meta.label}</span>
                <span className="text-xs text-foreground-muted">· {tasks.length} 项</span>
              </div>
              <ul className="space-y-1.5">
                {tasks.map((task) => {
                  const status = planTaskStatus[task.task_id] ?? "queued";
                  return (
                    <li
                      key={task.task_id}
                      className={cn(
                        "flex items-start gap-2 rounded-lg border px-3 py-2 text-sm",
                        status === "running"
                          ? "border-warning/30 bg-warning/[0.04]"
                          : status === "completed"
                          ? "border-success/30 bg-success/[0.04]"
                          : "border-white/[0.06] bg-white/[0.02]",
                      )}
                    >
                      <PlanTaskStatusIcon status={status} />
                      <div className="min-w-0 flex-1">
                        <div className="line-clamp-1 text-foreground">{task.title}</div>
                        {(task.competitor_id || task.focus_dimensions.length > 0) && (
                          <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-foreground-muted">
                            {task.competitor_id ? <span>· {task.competitor_id}</span> : null}
                            {task.focus_dimensions.length > 0 ? (
                              <span>
                                · {task.focus_dimensions.slice(0, 3).join(" / ")}
                                {task.focus_dimensions.length > 3 ? " …" : ""}
                              </span>
                            ) : null}
                          </div>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

function PlanTaskStatusIcon({ status }: { status: PlanTaskRuntimeStatus }): JSX.Element {
  if (status === "running") {
    return <Loader2 className="mt-0.5 h-4 w-4 animate-spin text-warning" />;
  }
  if (status === "completed") {
    return <CheckCircle2 className="mt-0.5 h-4 w-4 text-success" />;
  }
  return <CircleDot className="mt-0.5 h-4 w-4 text-foreground-muted" />;
}

interface ToolActivityCardProps {
  entries: ToolActivityEntry[];
}

function ToolActivityCard({ entries }: ToolActivityCardProps): JSX.Element {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2 text-base">
          <Wrench className="h-4 w-4 text-accent" />
          工具调用
        </CardTitle>
        <Badge variant="secondary">{entries.length}</Badge>
      </CardHeader>
      <CardContent>
        {entries.length === 0 ? (
          <div className="flex items-center gap-2 rounded-lg border border-dashed border-white/[0.08] px-3 py-6 text-sm text-foreground-muted">
            <Clock className="h-4 w-4" />
            Agent 还未发起任何工具调用。
          </div>
        ) : (
          <ul className="space-y-2">
            {entries.map((entry) => {
              const Icon = TOOL_ICONS[entry.tool] ?? Wrench;
              return (
                <li
                  key={entry.key}
                  className={cn(
                    "flex items-start gap-2 rounded-lg border px-3 py-2 text-sm",
                    entry.status === "running"
                      ? "border-warning/30 bg-warning/[0.04]"
                      : entry.status === "error"
                      ? "border-danger/30 bg-danger/[0.04]"
                      : "border-success/30 bg-success/[0.04]",
                  )}
                >
                  <ToolActivityStatusIcon status={entry.status} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 text-xs text-foreground-muted">
                      <Icon className="h-3.5 w-3.5" />
                      <span className="font-mono text-foreground">{entry.tool}</span>
                      {entry.competitorId ? <span>· {entry.competitorId}</span> : null}
                      {entry.dimension ? <span>· {entry.dimension}</span> : null}
                    </div>
                    <div className="mt-1 line-clamp-1 text-sm text-foreground">
                      {formatToolArgs(entry.argsSummary)}
                    </div>
                    <div className="mt-0.5 flex items-center gap-2 text-xs text-foreground-muted">
                      {entry.status === "running" ? (
                        <span>进行中…</span>
                      ) : (
                        <>
                          {entry.latencyMs !== null ? <span>{entry.latencyMs}ms</span> : null}
                          {entry.snippetCount !== null ? (
                            <span>{entry.snippetCount} 条片段</span>
                          ) : null}
                          {entry.error ? <span className="text-danger">{entry.error}</span> : null}
                        </>
                      )}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function ToolActivityStatusIcon({ status }: { status: ToolRuntimeStatus }): JSX.Element {
  if (status === "running") {
    return <Loader2 className="mt-0.5 h-4 w-4 animate-spin text-warning" />;
  }
  if (status === "error") {
    return <AlertTriangle className="mt-0.5 h-4 w-4 text-danger" />;
  }
  return <CheckCircle2 className="mt-0.5 h-4 w-4 text-success" />;
}

function formatToolArgs(args: Record<string, unknown> | undefined): string {
  if (!args || Object.keys(args).length === 0) {
    return "—";
  }
  const parts: string[] = [];
  for (const key of ["query", "url", "skill_id", "path"]) {
    const value = args[key];
    if (typeof value === "string" && value.length > 0) {
      parts.push(value);
    }
  }
  if (parts.length === 0) {
    return JSON.stringify(args);
  }
  return parts.join(" · ");
}

interface TerminalAlertProps {
  tone: "danger" | "neutral";
  icon: typeof XCircle;
  title: string;
  message: string;
  errorType: string | null;
  runId: string;
}

function TerminalAlert({
  tone,
  icon: Icon,
  title,
  message,
  errorType,
  runId,
}: TerminalAlertProps): JSX.Element {
  const isDanger = tone === "danger";
  return (
    <div
      className={cn(
        "flex flex-col gap-3 rounded-2xl border p-4 lg:flex-row lg:items-center lg:justify-between",
        isDanger
          ? "border-danger/30 bg-danger/[0.06]"
          : "border-white/[0.08] bg-white/[0.04]",
      )}
    >
      <div className="flex items-start gap-3">
        <Icon
          className={cn("mt-0.5 h-5 w-5 shrink-0", isDanger ? "text-danger" : "text-foreground-muted")}
        />
        <div className="space-y-1">
          <div className={cn("text-sm font-medium", isDanger ? "text-danger" : "text-foreground")}>
            {title}
          </div>
          <p className="text-sm text-foreground-muted">{message}</p>
          {errorType !== null ? (
            <div className="text-xs text-foreground-muted/70">错误类型：{errorType}</div>
          ) : null}
        </div>
      </div>
      <div className="flex shrink-0 flex-wrap items-center gap-2">
        <Button asChild variant="ghost" size="sm">
          <Link to="/app">返回我的分析</Link>
        </Button>
        <Button asChild size="sm">
          <Link to={`/app/runs/${runId}`}>查看已有结果</Link>
        </Button>
      </div>
    </div>
  );
}

function formatIdleDuration(idleMs: number): string {
  if (idleMs < 60_000) {
    return `${Math.floor(idleMs / 1000)} 秒`;
  }
  if (idleMs < 3_600_000) {
    return `${Math.floor(idleMs / 60_000)} 分钟`;
  }
  return `${Math.floor(idleMs / 3_600_000)} 小时`;
}

interface StuckHintAlertProps {
  idleMs: number;
  runId: string;
}

function StuckHintAlert({ idleMs, runId }: StuckHintAlertProps): JSX.Element {
  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-warning/40 bg-warning/[0.08] p-4 lg:flex-row lg:items-center lg:justify-between">
      <div className="flex items-start gap-3">
        <Info className="mt-0.5 h-5 w-5 shrink-0 text-warning" />
        <div className="space-y-1">
          <div className="text-sm font-medium text-warning">分析似乎已停滞</div>
          <p className="text-sm text-foreground-muted">
            最近 {formatIdleDuration(idleMs)} 没有收到任何进度事件。Agent
            可能正在处理长耗时的子任务，也可能已经中断。
          </p>
        </div>
      </div>
      <div className="flex shrink-0">
        <CancelRunButton runId={runId} label="标记为失败并退出" redirectTo={null} size="sm" />
      </div>
    </div>
  );
}

interface EvidenceFeedCardProps {
  entries: EvidenceCollectedPayload[];
  onOpen: (evidenceId: string) => void;
}

function EvidenceFeedCard({ entries, onOpen }: EvidenceFeedCardProps): JSX.Element {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2 text-base">
          <Sparkles className="h-4 w-4 text-success" />
          证据流
        </CardTitle>
        <Badge variant="secondary">{entries.length}</Badge>
      </CardHeader>
      <CardContent>
        {entries.length === 0 ? (
          <div className="flex items-center gap-2 rounded-lg border border-dashed border-white/[0.08] px-3 py-6 text-sm text-foreground-muted">
            <Clock className="h-4 w-4" />
            等待第一条证据落库…
          </div>
        ) : (
          <ul className="space-y-2">
            {entries.map((entry) => (
              <li key={entry.evidence_id}>
                <button
                  type="button"
                  onClick={() => onOpen(entry.evidence_id)}
                  className="w-full rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2 text-left text-sm transition-colors hover:border-primary/30 hover:bg-primary/[0.04]"
                >
                  <div className="flex flex-wrap items-center gap-1.5 text-xs text-foreground-muted">
                    <span className="font-mono text-foreground">{entry.evidence_id}</span>
                    {entry.competitor_id ? <span>· {entry.competitor_id}</span> : null}
                    {entry.dimension ? <span>· {entry.dimension}</span> : null}
                    {entry.source_type ? <span>· {entry.source_type}</span> : null}
                  </div>
                  <div className="mt-1 line-clamp-1 text-foreground">
                    {entry.source_title ?? entry.source_url ?? "未提供来源标题"}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
