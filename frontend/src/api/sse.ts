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
