import { useEffect } from "react";

import { API_BASE_URL } from "@/api/client";
import { queryClient } from "@/api/queryClient";

const RUN_RECONNECT_HINT_MS = 15_000;
const RUN_FALLBACK_POLL_MS = 10_000;

export function getRunFallbackPollMs(): number {
  return RUN_FALLBACK_POLL_MS;
}

export interface IntakeClarifyEventPayload {
  turn: number;
  question: string;
  field_targets: string[];
  suggested_options: string[];
  draft_complete: boolean;
}

export interface IntakeCompletePayload {
  turn: number;
  draft: Record<string, unknown>;
}

export interface PlanPublishedPayload {
  plan_id: string;
  version: number;
  task_count: number;
}

export interface PlanConfirmedPayload {
  plan_id: string;
  version: number;
  kept_task_count: number;
  disabled_task_ids: string[];
  confirmed_at: string | null;
}

export interface RunEventsOptions {
  // Phase 1b: surface intake event payloads to callers that drive the chat
  // page (NewRunChatPage). Generic runs that do not care about intake leave
  // these undefined and continue with cache invalidation only.
  onIntakeClarify?: (payload: IntakeClarifyEventPayload) => void;
  onIntakeComplete?: (payload: IntakeCompletePayload) => void;
  // Phase 2: PlanConfirmPage subscribes to plan.published to render the plan
  // the moment it appears (instead of polling Run.plan_tree). plan.confirmed
  // is forwarded so the page can navigate to the run view once the executor
  // takes over.
  onPlanPublished?: (payload: PlanPublishedPayload) => void;
  onPlanConfirmed?: (payload: PlanConfirmedPayload) => void;
}

interface RunEventEnvelope {
  payload?: unknown;
}

function parseEventPayload(rawData: string): unknown {
  try {
    const envelope = JSON.parse(rawData) as RunEventEnvelope;
    return envelope.payload ?? null;
  } catch {
    return null;
  }
}

function coerceIntakeClarifyPayload(value: unknown): IntakeClarifyEventPayload | null {
  if (value === null || typeof value !== "object") {
    return null;
  }
  const record = value as Record<string, unknown>;
  const question = record.question;
  if (typeof question !== "string" || question.length === 0) {
    return null;
  }
  const fieldTargetsRaw = record.field_targets;
  const fieldTargets = Array.isArray(fieldTargetsRaw)
    ? fieldTargetsRaw.filter((item): item is string => typeof item === "string")
    : [];
  const suggestedRaw = record.suggested_options;
  const suggestedOptions = Array.isArray(suggestedRaw)
    ? suggestedRaw.filter((item): item is string => typeof item === "string")
    : [];
  const turnRaw = record.turn;
  const turn = typeof turnRaw === "number" ? turnRaw : 0;
  const draftComplete = record.draft_complete === true;
  return {
    turn,
    question,
    field_targets: fieldTargets,
    suggested_options: suggestedOptions,
    draft_complete: draftComplete,
  };
}

function coerceIntakeCompletePayload(value: unknown): IntakeCompletePayload | null {
  if (value === null || typeof value !== "object") {
    return null;
  }
  const record = value as Record<string, unknown>;
  const turnRaw = record.turn;
  const turn = typeof turnRaw === "number" ? turnRaw : 0;
  const draftRaw = record.draft;
  const draft = draftRaw !== null && typeof draftRaw === "object" ? (draftRaw as Record<string, unknown>) : {};
  return { turn, draft };
}

function coercePlanPublishedPayload(value: unknown): PlanPublishedPayload | null {
  if (value === null || typeof value !== "object") {
    return null;
  }
  const record = value as Record<string, unknown>;
  const planIdRaw = record.plan_id;
  if (typeof planIdRaw !== "string" || planIdRaw.length === 0) {
    return null;
  }
  const versionRaw = record.version;
  const taskCountRaw = record.task_count;
  return {
    plan_id: planIdRaw,
    version: typeof versionRaw === "number" ? versionRaw : 1,
    task_count: typeof taskCountRaw === "number" ? taskCountRaw : 0,
  };
}

function coercePlanConfirmedPayload(value: unknown): PlanConfirmedPayload | null {
  if (value === null || typeof value !== "object") {
    return null;
  }
  const record = value as Record<string, unknown>;
  const planIdRaw = record.plan_id;
  if (typeof planIdRaw !== "string" || planIdRaw.length === 0) {
    return null;
  }
  const versionRaw = record.version;
  const keptRaw = record.kept_task_count;
  const disabledRaw = record.disabled_task_ids;
  const disabledTaskIds = Array.isArray(disabledRaw)
    ? disabledRaw.filter((item): item is string => typeof item === "string")
    : [];
  const confirmedAtRaw = record.confirmed_at;
  return {
    plan_id: planIdRaw,
    version: typeof versionRaw === "number" ? versionRaw : 2,
    kept_task_count: typeof keptRaw === "number" ? keptRaw : 0,
    disabled_task_ids: disabledTaskIds,
    confirmed_at: typeof confirmedAtRaw === "string" ? confirmedAtRaw : null,
  };
}

export function useRunEvents(runId: string, options: RunEventsOptions = {}): void {
  const { onIntakeClarify, onIntakeComplete, onPlanPublished, onPlanConfirmed } = options;
  useEffect(() => {
    if (!runId) {
      return;
    }
    const eventsUrl = `${API_BASE_URL}/api/runs/${runId}/events`;
    const eventSource = new EventSource(eventsUrl);
    const invalidateRunDetail = (): void => {
      void queryClient.invalidateQueries({ queryKey: ["run-detail", runId] });
    };
    const invalidateRunTrace = (): void => {
      void queryClient.invalidateQueries({ queryKey: ["run-trace", runId] });
    };
    const invalidateRunMetrics = (): void => {
      void queryClient.invalidateQueries({ queryKey: ["run-metrics", runId] });
    };
    const invalidateRunReport = (): void => {
      void queryClient.invalidateQueries({ queryKey: ["run-report", runId] });
      void queryClient.invalidateQueries({ queryKey: ["run-conclusions", runId] });
    };
    const onFallbackMessage = (): void => {
      invalidateRunDetail();
      invalidateRunTrace();
    };

    eventSource.onmessage = onFallbackMessage;
    eventSource.addEventListener("step.start", () => {
      invalidateRunDetail();
      invalidateRunTrace();
    });
    eventSource.addEventListener("step.finish", () => {
      invalidateRunDetail();
      invalidateRunTrace();
      invalidateRunMetrics();
    });
    eventSource.addEventListener("qa.outcome", () => {
      invalidateRunDetail();
      invalidateRunTrace();
      invalidateRunMetrics();
    });
    eventSource.addEventListener("supervisor.decision", () => {
      invalidateRunTrace();
    });
    eventSource.addEventListener("curator.finish", () => {
      void queryClient.invalidateQueries({ queryKey: ["skill-candidates"] });
    });
    eventSource.addEventListener("run.finish", () => {
      invalidateRunDetail();
      invalidateRunMetrics();
      invalidateRunReport();
    });
    eventSource.addEventListener("intake.clarify_request", (event: MessageEvent<string>) => {
      invalidateRunDetail();
      if (onIntakeClarify === undefined) {
        return;
      }
      const payload = coerceIntakeClarifyPayload(parseEventPayload(event.data));
      if (payload !== null) {
        onIntakeClarify(payload);
      }
    });
    eventSource.addEventListener("intake.complete", (event: MessageEvent<string>) => {
      invalidateRunDetail();
      if (onIntakeComplete === undefined) {
        return;
      }
      const payload = coerceIntakeCompletePayload(parseEventPayload(event.data));
      if (payload !== null) {
        onIntakeComplete(payload);
      }
    });
    eventSource.addEventListener("plan.published", (event: MessageEvent<string>) => {
      invalidateRunDetail();
      invalidateRunTrace();
      if (onPlanPublished === undefined) {
        return;
      }
      const payload = coercePlanPublishedPayload(parseEventPayload(event.data));
      if (payload !== null) {
        onPlanPublished(payload);
      }
    });
    eventSource.addEventListener("plan.confirmed", (event: MessageEvent<string>) => {
      invalidateRunDetail();
      invalidateRunTrace();
      if (onPlanConfirmed === undefined) {
        return;
      }
      const payload = coercePlanConfirmedPayload(parseEventPayload(event.data));
      if (payload !== null) {
        onPlanConfirmed(payload);
      }
    });
    eventSource.addEventListener("error", () => {
      // Browser-side EventSource handles retry; backend hints 15s.
      const _retryHintMs = RUN_RECONNECT_HINT_MS;
      void _retryHintMs;
    });
    return () => {
      eventSource.close();
    };
  }, [runId, onIntakeClarify, onIntakeComplete, onPlanPublished, onPlanConfirmed]);
}
