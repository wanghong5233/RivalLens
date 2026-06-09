import { useMemo, useSyncExternalStore } from "react";

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

type PlanTaskRuntimeStatus = "queued" | "running" | "completed";
type ToolRuntimeStatus = "running" | "done" | "error";

export interface ToolActivityEntry {
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

export interface LiveRunProgressState {
  planTaskStatus: Record<string, PlanTaskRuntimeStatus>;
  toolActivity: ToolActivityEntry[];
  evidenceFeed: EvidenceCollectedPayload[];
  pendingFollowUps: FollowUpReceivedPayload[];
  finishPayload: RunFinishPayload | null;
  lastActivityAt: number;
}

const AGENT_NAME_TO_STAGE: Record<string, PlanTaskStage> = {
  discovery: "discover",
  researcher: "research",
  analyst: "analyze",
  writer: "write",
};

const MAX_TOOL_ENTRIES = 12;
const MAX_EVIDENCE_ENTRIES = 30;

const storeByRunId = new Map<string, LiveRunProgressState>();
const listenersByRunId = new Map<string, Set<() => void>>();

function createInitialState(): LiveRunProgressState {
  return {
    planTaskStatus: {},
    toolActivity: [],
    evidenceFeed: [],
    pendingFollowUps: [],
    finishPayload: null,
    lastActivityAt: Date.now(),
  };
}

function ensureState(runId: string): LiveRunProgressState {
  const existing = storeByRunId.get(runId);
  if (existing !== undefined) {
    return existing;
  }
  const initial = createInitialState();
  storeByRunId.set(runId, initial);
  return initial;
}

function emit(runId: string): void {
  const listeners = listenersByRunId.get(runId);
  if (listeners === undefined) {
    return;
  }
  for (const listener of listeners) {
    listener();
  }
}

function update(runId: string, updater: (prev: LiveRunProgressState) => LiveRunProgressState): void {
  const prev = ensureState(runId);
  const next = updater(prev);
  storeByRunId.set(runId, next);
  emit(runId);
}

function touchActivity(state: LiveRunProgressState): LiveRunProgressState {
  return {
    ...state,
    lastActivityAt: Date.now(),
  };
}

function buildToolKey(payload: ToolEventPayload): string {
  return `${payload.tool}|${payload.competitor_id ?? "-"}|${payload.dimension ?? "-"}|${payload.turn ?? 0}`;
}

function cloneTaskStatusMap(
  prev: Record<string, PlanTaskRuntimeStatus>,
): Record<string, PlanTaskRuntimeStatus> {
  return { ...prev };
}

export function ensureRunTaskStatuses(runId: string, planTree: PlanTree | null): void {
  update(runId, (prev) => {
    if (planTree === null) {
      return prev;
    }
    const nextTaskStatus: Record<string, PlanTaskRuntimeStatus> = {};
    for (const task of planTree.tasks) {
      nextTaskStatus[task.task_id] = prev.planTaskStatus[task.task_id] ?? "queued";
    }
    return {
      ...prev,
      planTaskStatus: nextTaskStatus,
    };
  });
}

export function recordSupervisorDecision(
  runId: string,
  payload: SupervisorDecisionEventPayload,
): void {
  update(runId, (prev) => {
    const next = touchActivity(prev);
    if (payload.plan_task_ids.length > 0) {
      const planTaskStatus = cloneTaskStatusMap(next.planTaskStatus);
      for (const taskId of payload.plan_task_ids) {
        if (planTaskStatus[taskId] !== "completed") {
          planTaskStatus[taskId] = "running";
        }
      }
      next.planTaskStatus = planTaskStatus;
    }
    const consumed = payload.consumed_follow_up_ids;
    if (consumed !== undefined && consumed.length > 0) {
      const consumedSet = new Set(consumed);
      next.pendingFollowUps = next.pendingFollowUps.filter(
        (entry) => !consumedSet.has(entry.follow_up_id),
      );
    }
    return next;
  });
}

export function recordStepFinish(
  runId: string,
  payload: StepFinishEventPayload,
  planTree: PlanTree | null,
): void {
  if (planTree === null) {
    return;
  }
  const targetStage = AGENT_NAME_TO_STAGE[payload.agent_name];
  if (targetStage === undefined) {
    return;
  }
  update(runId, (prev) => {
    const next = touchActivity(prev);
    const planTaskStatus = cloneTaskStatusMap(next.planTaskStatus);
    for (const task of planTree.tasks) {
      if (task.stage !== targetStage) {
        continue;
      }
      if (targetStage === "research") {
        if (payload.competitor_id !== null && task.competitor_id === payload.competitor_id) {
          planTaskStatus[task.task_id] = "completed";
        }
      } else {
        planTaskStatus[task.task_id] = "completed";
      }
    }
    next.planTaskStatus = planTaskStatus;
    return next;
  });
}

export function recordToolStart(runId: string, payload: ToolEventPayload): void {
  update(runId, (prev) => {
    const next = touchActivity(prev);
    const key = buildToolKey(payload);
    const entry: ToolActivityEntry = {
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
    const without = next.toolActivity.filter((item) => item.key !== key);
    next.toolActivity = [entry, ...without].slice(0, MAX_TOOL_ENTRIES);
    return next;
  });
}

export function recordToolFinish(runId: string, payload: ToolFinishEventPayload): void {
  update(runId, (prev) => {
    const next = touchActivity(prev);
    const key = buildToolKey(payload);
    const status: ToolRuntimeStatus = payload.success ? "done" : "error";
    const existingIndex = next.toolActivity.findIndex((entry) => entry.key === key);
    if (existingIndex === -1) {
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
      next.toolActivity = [synthesized, ...next.toolActivity].slice(0, MAX_TOOL_ENTRIES);
      return next;
    }
    const entries = [...next.toolActivity];
    entries[existingIndex] = {
      ...entries[existingIndex],
      status,
      latencyMs: payload.latency_ms,
      snippetCount: payload.snippet_count,
      error: payload.error,
    };
    next.toolActivity = entries;
    return next;
  });
}

export function recordEvidenceCollected(runId: string, payload: EvidenceCollectedPayload): void {
  update(runId, (prev) => {
    const next = touchActivity(prev);
    if (next.evidenceFeed.some((entry) => entry.evidence_id === payload.evidence_id)) {
      return next;
    }
    next.evidenceFeed = [payload, ...next.evidenceFeed].slice(0, MAX_EVIDENCE_ENTRIES);
    return next;
  });
}

export function recordFollowUpReceived(runId: string, payload: FollowUpReceivedPayload): void {
  update(runId, (prev) => {
    const next = touchActivity(prev);
    if (next.pendingFollowUps.some((entry) => entry.follow_up_id === payload.follow_up_id)) {
      return next;
    }
    next.pendingFollowUps = [...next.pendingFollowUps, payload];
    return next;
  });
}

export function recordRunFinish(runId: string, payload: RunFinishPayload): void {
  update(runId, (prev) => ({
    ...prev,
    finishPayload: payload,
  }));
}

export function useLiveRunProgress(runId: string): LiveRunProgressState {
  const subscribe = useMemo(
    () => (listener: () => void): (() => void) => {
      const listeners = listenersByRunId.get(runId) ?? new Set<() => void>();
      listeners.add(listener);
      listenersByRunId.set(runId, listeners);
      return () => {
        const current = listenersByRunId.get(runId);
        if (current === undefined) {
          return;
        }
        current.delete(listener);
        if (current.size === 0) {
          listenersByRunId.delete(runId);
        }
      };
    },
    [runId],
  );
  const getSnapshot = useMemo(
    () => (): LiveRunProgressState => ensureState(runId),
    [runId],
  );
  const getServerSnapshot = useMemo(() => createInitialState, []);
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

