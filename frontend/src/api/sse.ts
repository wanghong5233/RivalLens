import { useEffect } from "react";

import { API_BASE_URL } from "@/api/client";
import { queryClient } from "@/api/queryClient";

const RUN_RECONNECT_HINT_MS = 15_000;
const RUN_FALLBACK_POLL_MS = 10_000;

export function getRunFallbackPollMs(): number {
  return RUN_FALLBACK_POLL_MS;
}

export function useRunEvents(runId: string): void {
  useEffect(() => {
    if (!runId) {
      return;
    }
    const eventsUrl = `${API_BASE_URL}/api/runs/${runId}/events`;
    const eventSource = new EventSource(eventsUrl);
    const onMessage = (): void => {
      void queryClient.invalidateQueries({ queryKey: ["run-detail", runId] });
      void queryClient.invalidateQueries({ queryKey: ["run-trace", runId] });
    };
    eventSource.onmessage = onMessage;
    const eventTypes = [
      "step.start",
      "step.finish",
      "supervisor.decision",
      "qa.outcome",
      "curator.start",
      "curator.finish",
      "run.finish",
    ];
    for (const eventType of eventTypes) {
      eventSource.addEventListener(eventType, onMessage);
    }
    eventSource.addEventListener("error", () => {
      // Browser-side EventSource handles retry; backend hints 15s.
      const _retryHintMs = RUN_RECONNECT_HINT_MS;
      void _retryHintMs;
    });
    return () => {
      eventSource.close();
    };
  }, [runId]);
}
