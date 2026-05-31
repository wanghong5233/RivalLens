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

export interface RunEventsOptions {
  // Phase 1b: surface intake event payloads to callers that drive the chat
  // page (NewRunChatPage). Generic runs that do not care about intake leave
  // these undefined and continue with cache invalidation only.
  onIntakeClarify?: (payload: IntakeClarifyEventPayload) => void;
  onIntakeComplete?: (payload: IntakeCompletePayload) => void;
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

export function useRunEvents(runId: string, options: RunEventsOptions = {}): void {
  const { onIntakeClarify, onIntakeComplete } = options;
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
    eventSource.addEventListener("error", () => {
      // Browser-side EventSource handles retry; backend hints 15s.
      const _retryHintMs = RUN_RECONNECT_HINT_MS;
      void _retryHintMs;
    });
    return () => {
      eventSource.close();
    };
  }, [runId, onIntakeClarify, onIntakeComplete]);
}
