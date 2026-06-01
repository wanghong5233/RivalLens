import type { RunStatus } from "@/api/types";

export function formatDateTime(value: string | null): string {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN", { hour12: false });
}

export function formatRelativeTime(value: string | null): string {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  const now = Date.now();
  const diffMs = date.getTime() - now;
  const diffMinutes = Math.round(diffMs / 60_000);
  const rtf = new Intl.RelativeTimeFormat("zh-CN", { numeric: "auto" });
  if (Math.abs(diffMinutes) < 60) {
    return rtf.format(diffMinutes, "minute");
  }
  const diffHours = Math.round(diffMinutes / 60);
  if (Math.abs(diffHours) < 24) {
    return rtf.format(diffHours, "hour");
  }
  const diffDays = Math.round(diffHours / 24);
  return rtf.format(diffDays, "day");
}

export function statusToLabel(status: RunStatus): string {
  if (status === "running") {
    return "进行中";
  }
  if (status === "completed") {
    return "已完成";
  }
  if (status === "degraded") {
    return "降级完成";
  }
  if (status === "failed") {
    return "失败";
  }
  return status;
}

const TITLE_FALLBACK_MAX = 40;

/**
 * Resolve the short label shown on run cards / page headers.
 *
 * The LLM-derived `title` is the source of truth once intake completes; before
 * that (and for legacy runs migrated from before column existed) we fall back
 * to the first non-empty line of `user_query`, truncated to a sensible length.
 *
 * Centralizing this prevents the FE from diverging between Dashboard / Live /
 * RunView / Home and avoids each page reinventing its own truncation rules.
 */
export function formatRunTitle(
  run: { title?: string | null; user_query: string },
  options: { max?: number } = {},
): string {
  const max = options.max ?? TITLE_FALLBACK_MAX;
  if (typeof run.title === "string" && run.title.trim()) {
    return run.title.trim();
  }
  const firstLine = run.user_query
    .split(/\r?\n/)
    .map((line) => line.trim())
    .find((line) => line.length > 0);
  if (!firstLine) {
    return "未命名分析";
  }
  if (firstLine.length <= max) {
    return firstLine;
  }
  return `${firstLine.slice(0, max - 1)}…`;
}
