import { ArrowRight, Plus, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useResumeRun, useRunsList, useWatchlist } from "@/api/hooks";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { pushToast } from "@/components/ui/toaster";
import { formatDateTime, formatRelativeTime } from "@/lib/format";
import { track } from "@/lib/analytics";

const PAGE_SIZE = 10;
type StatusFilter = "all" | "running" | "completed" | "degraded" | "failed";

export function DashboardPage(): JSX.Element {
  const navigate = useNavigate();
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [offset, setOffset] = useState(0);
  const [searchKeyword, setSearchKeyword] = useState("");

  const runsQuery = useRunsList({
    status: statusFilter === "all" ? undefined : statusFilter,
    limit: PAGE_SIZE,
    offset,
  });
  const latestCompletedQuery = useRunsList({ status: "completed", limit: 4, offset: 0 });
  const latestRunsQuery = useRunsList({ limit: 20, offset: 0 });
  const watchlistQuery = useWatchlist();
  const resumeMutation = useResumeRun();

  const currentItems = runsQuery.data?.items ?? [];
  const filteredItems = useMemo(() => {
    const kw = searchKeyword.trim().toLowerCase();
    return kw ? currentItems.filter((i) => i.user_query.toLowerCase().includes(kw)) : currentItems;
  }, [currentItems, searchKeyword]);

  const latestRuns = latestRunsQuery.data?.items ?? [];
  const continueRun = latestRuns.find((i) => i.status === "running" || i.status === "failed");
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;
  const totalPages = Math.max(1, Math.ceil((runsQuery.data?.total ?? 0) / PAGE_SIZE));

  async function handleResumeRun(runId: string): Promise<void> {
    try {
      await resumeMutation.mutateAsync(runId);
      track("dashboard.resume_run", { run_id: runId });
      pushToast({ title: "任务已恢复", variant: "success" });
      navigate(`/app/runs/${runId}`);
    } catch (error) {
      if (error instanceof Error) {
        pushToast({ title: "恢复失败", description: error.message, variant: "danger" });
      }
    }
  }

  return (
    <section className="space-y-8">
      {/* Header */}
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-h1 text-foreground">仪表盘</h1>
          <p className="mt-1 text-caption text-foreground-muted">继续上次任务、复盘历史报告、快速启动新分析。</p>
        </div>
        <Button asChild>
          <Link to="/app/runs/new">
            <Plus className="h-4 w-4" />
            新建分析
          </Link>
        </Button>
      </div>

      {/* Top cards */}
      <div className="grid gap-4 md:grid-cols-2">
        {/* Continue card */}
        <div className="rounded-lg border border-white/[0.06] bg-surface p-5">
          <p className="text-micro font-medium uppercase tracking-wider text-foreground-subtle">继续上次</p>
          {continueRun ? (
            <div className="mt-3 space-y-2">
              <p className="text-caption font-medium text-foreground">{continueRun.user_query}</p>
              <div className="flex items-center gap-2">
                <StatusBadge status={continueRun.status} />
                <span className="text-micro text-foreground-subtle">{formatRelativeTime(continueRun.started_at)}</span>
              </div>
              <Button
                size="sm"
                onClick={() => {
                  if (continueRun.status === "running") {
                    navigate(`/app/runs/${continueRun.run_id}`);
                    return;
                  }
                  void handleResumeRun(continueRun.run_id);
                }}
              >
                继续处理
              </Button>
            </div>
          ) : (
            <p className="mt-3 text-caption text-foreground-muted">暂无进行中任务</p>
          )}
        </div>

        {/* Watchlist card */}
        <div className="rounded-lg border border-white/[0.06] bg-surface p-5">
          <p className="text-micro font-medium uppercase tracking-wider text-foreground-subtle">Watchlist</p>
          <p className="mt-3 text-h2 font-semibold text-foreground">{watchlistQuery.data?.length ?? 0}</p>
          <p className="text-micro text-foreground-muted">个竞品正在追踪</p>
          <Button asChild size="sm" variant="secondary" className="mt-3">
            <Link to="/app/watch">管理 Watchlist</Link>
          </Button>
        </div>
      </div>

      {/* Latest reports */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-h3 text-foreground">最新报告</h2>
          <Link className="text-micro text-primary hover:underline" to="/examples">
            查看全部 <ArrowRight className="inline h-3 w-3" />
          </Link>
        </div>
        {latestCompletedQuery.isLoading ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24 w-full" />)}
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {(latestCompletedQuery.data?.items ?? []).map((run) => (
              <Link
                key={run.run_id}
                to={`/app/runs/${run.run_id}`}
                className="rounded-lg border border-white/[0.06] bg-surface p-4 transition-colors hover:border-white/[0.12]"
              >
                <p className="line-clamp-2 text-caption font-medium text-foreground">{run.user_query}</p>
                <p className="mt-2 text-micro text-foreground-subtle">
                  {run.finished_at ? formatDateTime(run.finished_at) : "处理中"}
                </p>
              </Link>
            ))}
          </div>
        )}
      </div>

      {/* History */}
      <div className="space-y-3">
        <h2 className="text-h3 text-foreground">历史任务</h2>
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-foreground-subtle" />
            <Input className="pl-9" onChange={(e) => setSearchKeyword(e.target.value)} placeholder="搜索..." value={searchKeyword} />
          </div>
          <select
            className="h-9 rounded-md border border-white/[0.08] bg-white/[0.03] px-3 text-caption text-foreground"
            onChange={(e) => { setStatusFilter(e.target.value as StatusFilter); setOffset(0); }}
            value={statusFilter}
          >
            <option value="all">全部</option>
            <option value="running">进行中</option>
            <option value="completed">已完成</option>
            <option value="degraded">降级</option>
            <option value="failed">失败</option>
          </select>
        </div>

        {runsQuery.isLoading && <Skeleton className="h-32 w-full" />}
        {runsQuery.isError && (
          <div className="rounded-lg border border-danger/30 bg-danger/5 p-3 text-caption text-danger">{runsQuery.error.message}</div>
        )}

        <div className="space-y-1">
          {filteredItems.map((run) => (
            <button
              key={run.run_id}
              type="button"
              onClick={() => navigate(`/app/runs/${run.run_id}`)}
              className="flex w-full items-center justify-between gap-3 rounded-md px-3 py-2.5 text-left transition-colors hover:bg-white/[0.03] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-caption font-medium text-foreground">{run.user_query}</p>
                <p className="text-micro text-foreground-subtle">
                  {run.domain_hint ?? "通用"} · {run.evidence_count} 证据 · {run.step_count} 步骤
                </p>
              </div>
              <StatusBadge status={run.status} />
            </button>
          ))}
        </div>

        {/* Pagination */}
        <div className="flex items-center justify-between text-micro text-foreground-subtle">
          <span>{currentPage} / {totalPages}</span>
          <div className="flex gap-1">
            <Button size="sm" variant="ghost" disabled={offset === 0} onClick={() => setOffset((p) => Math.max(0, p - PAGE_SIZE))}>上一页</Button>
            <Button size="sm" variant="ghost" disabled={offset + PAGE_SIZE >= (runsQuery.data?.total ?? 0)} onClick={() => setOffset((p) => p + PAGE_SIZE)}>下一页</Button>
          </div>
        </div>
      </div>
    </section>
  );
}
