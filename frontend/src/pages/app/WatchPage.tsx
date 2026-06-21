import { ArrowUpRight, CalendarClock, Plus, RefreshCw, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import {
  useCreateWatchlistItem,
  useDeleteWatchlistItem,
  useManualRefreshWatchlist,
  useWatchlistDigest,
} from "@/api/hooks";
import type { CompetitorDiffResponse } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { pushToast } from "@/components/ui/toaster";
import { RefreshScheduleDialog } from "@/components/watchlist/RefreshScheduleDialog";
import { formatDateTime, formatRelativeTime } from "@/lib/format";

function toConfidenceVariant(confidence: string): "success" | "warning" | "danger" | "secondary" {
  const normalized = confidence.trim().toLowerCase();
  if (normalized === "high") return "success";
  if (normalized === "medium") return "warning";
  if (normalized === "low") return "danger";
  return "secondary";
}

function focusRunLink(latestRunId: string | null, competitorId: string): string {
  const params = new URLSearchParams();
  if (latestRunId) {
    params.set("from", latestRunId);
  }
  params.set("seed", competitorId);
  return `/app/runs/new?${params.toString()}`;
}

const CHANGE_TYPE_LABEL: Record<string, string> = {
  stance_changed: "阵营变化",
  new_dimension: "新增维度",
  lost_dimension: "丢失维度",
  summary_changed: "描述更新",
};

const SIGNIFICANCE_VARIANT: Record<string, "danger" | "warning" | "secondary"> = {
  high: "danger",
  medium: "warning",
  low: "secondary",
};

function RecentChangeItem({ diff }: { diff: CompetitorDiffResponse }): JSX.Element {
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-micro text-foreground-muted">
      <span className="font-mono text-foreground-subtle">{diff.dimension}</span>
      <Badge variant="outline">{CHANGE_TYPE_LABEL[diff.change_type] ?? diff.change_type}</Badge>
      {diff.change_type === "stance_changed" && diff.old_value?.stance && diff.new_value?.stance ? (
        <span>
          {diff.old_value.stance} → {diff.new_value.stance}
        </span>
      ) : null}
      <Badge variant={SIGNIFICANCE_VARIANT[diff.significance] ?? "secondary"}>
        {diff.significance}
      </Badge>
    </div>
  );
}

export function WatchPage(): JSX.Element {
  const [newCompetitor, setNewCompetitor] = useState("");
  const [refreshingIds, setRefreshingIds] = useState<Set<string>>(new Set());
  const navigate = useNavigate();
  const watchlistDigestQuery = useWatchlistDigest();
  const createMutation = useCreateWatchlistItem();
  const deleteMutation = useDeleteWatchlistItem();
  const refreshMutation = useManualRefreshWatchlist();

  async function handleAdd(): Promise<void> {
    const id = newCompetitor.trim();
    if (!id) return;
    try {
      await createMutation.mutateAsync({ competitor_id: id });
      setNewCompetitor("");
      pushToast({ title: `已添加 ${id}`, variant: "success" });
    } catch (error) {
      if (error instanceof Error)
        pushToast({ title: "添加失败", description: error.message, variant: "danger" });
    }
  }

  async function handleDelete(watchId: string): Promise<void> {
    try {
      await deleteMutation.mutateAsync(watchId);
      pushToast({ title: "已移除", variant: "success" });
    } catch (error) {
      if (error instanceof Error)
        pushToast({ title: "移除失败", description: error.message, variant: "danger" });
    }
  }

  async function handleRefresh(watchId: string): Promise<void> {
    setRefreshingIds((prev) => new Set(prev).add(watchId));
    try {
      const result = await refreshMutation.mutateAsync(watchId);
      pushToast({ title: "刷新任务已启动", variant: "success" });
      navigate(`/app/runs/${result.run_id}/live`);
    } catch (error) {
      if (error instanceof Error)
        pushToast({ title: "触发刷新失败", description: error.message, variant: "danger" });
    } finally {
      setRefreshingIds((prev) => {
        const next = new Set(prev);
        next.delete(watchId);
        return next;
      });
    }
  }

  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-h1 text-foreground">竞品追踪</h1>
        <p className="mt-1 text-caption text-foreground-muted">
          添加竞品到追踪列表，自动汇总历史分析里的最新结论动态。
        </p>
      </header>

      <div className="flex gap-2">
        <Input
          placeholder="输入竞品名称..."
          value={newCompetitor}
          onChange={(e) => setNewCompetitor(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void handleAdd();
          }}
        />
        <Button onClick={() => void handleAdd()} disabled={createMutation.isPending}>
          <Plus className="h-4 w-4" />
          添加
        </Button>
      </div>

      {watchlistDigestQuery.isLoading && (
        <div className="space-y-3">
          <Skeleton className="h-36 w-full" />
          <Skeleton className="h-36 w-full" />
        </div>
      )}

      {watchlistDigestQuery.data && watchlistDigestQuery.data.length === 0 && (
        <div className="rounded-lg border border-white/[0.06] bg-surface p-8 text-center text-caption text-foreground-muted">
          追踪列表为空，添加竞品开始持续监控。
        </div>
      )}

      <div className="space-y-4">
        {(watchlistDigestQuery.data ?? []).map((item) => (
          <article
            key={item.watch_id}
            className="overflow-hidden rounded-lg border border-white/[0.06] bg-surface"
          >
            <div className="flex items-start justify-between gap-3 px-4 py-3">
              <div>
                <h2 className="text-caption font-semibold text-foreground">{item.competitor_id}</h2>
                {item.note ? (
                  <p className="mt-0.5 text-micro text-foreground-subtle">{item.note}</p>
                ) : null}
                {item.source_role ? (
                  <p className="mt-0.5 text-micro text-foreground-subtle">来源角色：{item.source_role}</p>
                ) : null}
                {item.added_from_run_id ? (
                  <p className="mt-0.5 text-micro text-foreground-subtle">来源 run：{item.added_from_run_id}</p>
                ) : null}
                <p className="mt-1 text-micro text-foreground-subtle">
                  追踪自 {formatDateTime(item.created_at)}
                </p>
                {item.last_refreshed_at || item.next_refresh_at ? (
                  <p className="mt-0.5 text-micro text-foreground-subtle">
                    {item.last_refreshed_at
                      ? `上次刷新 ${formatRelativeTime(item.last_refreshed_at)}`
                      : "尚未刷新"}
                    {item.next_refresh_at
                      ? ` · 下次 ${formatRelativeTime(item.next_refresh_at)}`
                      : null}
                  </p>
                ) : null}
              </div>
              <div className="flex items-start gap-2">
                <div className="flex flex-wrap justify-end gap-1.5">
                  <Badge variant="secondary">{item.insight_count} 条洞察</Badge>
                  <Badge variant="secondary">{item.run_count} 次分析</Badge>
                  <Badge variant="outline">
                    最近 {item.last_updated_at ? formatRelativeTime(item.last_updated_at) : "-"}
                  </Badge>
                </div>
                <Button
                  size="icon"
                  variant="ghost"
                  onClick={() => void handleRefresh(item.watch_id)}
                  disabled={refreshingIds.has(item.watch_id)}
                  aria-label="立即刷新"
                  title="立即刷新"
                >
                  <RefreshCw
                    className={`h-3.5 w-3.5 text-foreground-muted ${refreshingIds.has(item.watch_id) ? "animate-spin" : ""}`}
                  />
                </Button>
                <RefreshScheduleDialog item={item}>
                  <Button
                    size="icon"
                    variant="ghost"
                    aria-label="刷新计划"
                    title="刷新计划"
                  >
                    <CalendarClock className="h-3.5 w-3.5 text-foreground-muted" />
                  </Button>
                </RefreshScheduleDialog>
                <Button
                  size="icon"
                  variant="ghost"
                  onClick={() => void handleDelete(item.watch_id)}
                  aria-label="移除"
                >
                  <Trash2 className="h-3.5 w-3.5 text-foreground-muted" />
                </Button>
              </div>
            </div>

            {item.recent_changes && item.recent_changes.length > 0 ? (
              <div className="border-t border-white/[0.04] px-4 py-3">
                <p className="mb-2 text-micro font-medium text-foreground-subtle">最近变更</p>
                <ul className="space-y-1.5">
                  {item.recent_changes.slice(0, 3).map((diff) => (
                    <li key={diff.diff_id}>
                      <RecentChangeItem diff={diff} />
                    </li>
                  ))}
                </ul>
                {item.last_run_id ? (
                  <Link
                    className="mt-2 inline-flex items-center gap-1 text-micro text-primary hover:underline"
                    to={`/app/runs/${item.last_run_id}`}
                  >
                    查看完整报告
                    <ArrowUpRight className="h-3 w-3" />
                  </Link>
                ) : null}
              </div>
            ) : null}

            <div className="border-t border-white/[0.04] px-4 py-3">
              {item.delta && (item.delta.added_claims.length > 0 || item.delta.removed_claims.length > 0) ? (
                <div className="mb-2 rounded-md border border-primary/20 bg-primary/5 p-2 text-micro text-foreground-subtle">
                  <p className="font-medium text-foreground">最近两次变化</p>
                  {item.delta.added_claims.length > 0 ? (
                    <p className="mt-1">新增：{item.delta.added_claims.join("；")}</p>
                  ) : null}
                  {item.delta.removed_claims.length > 0 ? (
                    <p className="mt-1">减少：{item.delta.removed_claims.join("；")}</p>
                  ) : null}
                </div>
              ) : null}
              {item.items.length === 0 ? (
                <div className="rounded-md border border-dashed border-white/[0.1] bg-black/10 px-3 py-4 text-micro text-foreground-subtle">
                  暂无分析洞察，先做一次分析后这里会自动出现最新动态。
                </div>
              ) : (
                <ul className="space-y-2.5">
                  {item.items.map((insight) => (
                    <li
                      key={insight.conclusion_id}
                      className="rounded-md border border-white/[0.05] bg-black/10 p-3"
                    >
                      <div className="flex flex-wrap items-center gap-1.5 text-micro">
                        <Badge variant="outline" className="capitalize">
                          {insight.section}
                        </Badge>
                        <Badge variant={toConfidenceVariant(insight.confidence)}>
                          {insight.confidence}
                        </Badge>
                        <span className="text-foreground-subtle">
                          {formatRelativeTime(insight.created_at)}
                        </span>
                      </div>
                      <p className="mt-1.5 line-clamp-2 text-caption text-foreground-muted">
                        {insight.claim}
                      </p>
                      <Link
                        className="mt-1.5 inline-flex items-center gap-1 text-micro text-primary hover:underline"
                        to={`/app/runs/${insight.run_id}`}
                      >
                        来源：{insight.run_title}
                        <ArrowUpRight className="h-3.5 w-3.5" />
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="flex items-center gap-2 border-t border-white/[0.04] px-4 py-3">
              {item.latest_run_id ? (
                <Button asChild size="sm" variant="outline">
                  <Link to={`/app/runs/${item.latest_run_id}`}>查看最近分析</Link>
                </Button>
              ) : null}
              <Button asChild size="sm" variant="outline">
                <Link to={focusRunLink(item.latest_run_id, item.competitor_id)}>
                  <RefreshCw className="h-3.5 w-3.5" />
                  手动重跑
                </Link>
              </Button>
              <Button asChild size="sm" variant="ghost">
                <Link to="/app/runs/new">去分析</Link>
              </Button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
