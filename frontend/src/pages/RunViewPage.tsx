import { Activity, Copy, Download, RotateCcw, Share2 } from "lucide-react";
import { useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Link, useNavigate, useParams } from "react-router-dom";
import remarkGfm from "remark-gfm";

import { queryClient } from "@/api/queryClient";
import { useResetRun, useRunConclusions, useRunDetail, useRunMetrics, useRunReport, useRunTrace } from "@/api/hooks";
import { useRunEvents } from "@/api/sse";
import { BattlecardGrid } from "@/components/battlecard";
import { EvidenceDrawer } from "@/components/EvidenceDrawer";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { pushToast } from "@/components/ui/toaster";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { formatDateTime, formatRelativeTime } from "@/lib/format";
import { track } from "@/lib/analytics";

const CITATION_REGEX = /\[(ev_[a-zA-Z0-9_]+)\]/g;

function toHeadingId(value: string): string {
  return value.trim().toLowerCase().replace(/[^\w\u4e00-\u9fa5\s-]/g, "").replace(/\s+/g, "-");
}

function toCitationLinkMarkdown(markdown: string): string {
  return markdown.replace(CITATION_REGEX, (_match, evidenceId: string) => `[${evidenceId}](evidence://${evidenceId})`);
}

export function RunViewPage(): JSX.Element {
  const { runId: runIdFromParams } = useParams<{ runId: string }>();
  const navigate = useNavigate();
  const runId = runIdFromParams ?? "";
  const [isEvidenceDrawerOpen, setIsEvidenceDrawerOpen] = useState(false);
  const [activeEvidenceIds, setActiveEvidenceIds] = useState<string[]>([]);
  useRunEvents(runId);

  const detailQuery = useRunDetail(runId);
  const traceQuery = useRunTrace(runId);
  const resetRunMutation = useResetRun();

  const runStatus = detailQuery.data?.status ?? "running";
  const isRunActive = runStatus === "running";
  const isReportReady = runStatus === "completed" || runStatus === "degraded";
  const reportQuery = useRunReport(runId, { enabled: isReportReady });
  const conclusionsQuery = useRunConclusions(runId, {
    enabled: isReportReady,
    refetchInterval: isRunActive ? 2_000 : false,
  });
  const metricsQuery = useRunMetrics(runId, {
    enabled: isReportReady,
    refetchInterval: isRunActive ? 2_000 : false,
  });

  const recentDecisions = useMemo(
    () => traceQuery.data?.supervisor_decisions.slice(-5).reverse() ?? [],
    [traceQuery.data?.supervisor_decisions],
  );

  const reportMarkdown = reportQuery.data?.content_markdown ?? "";
  const reportWithCitationLinks = useMemo(() => toCitationLinkMarkdown(reportMarkdown), [reportMarkdown]);
  const conclusions = conclusionsQuery.data?.items ?? [];

  function openEvidenceDrawer(evidenceIds: string[]): void {
    if (evidenceIds.length === 0) return;
    setActiveEvidenceIds(evidenceIds);
    setIsEvidenceDrawerOpen(true);
  }

  async function handleResetRun(resetTo: "analyst" | "writer"): Promise<void> {
    if (!runId) return;
    await resetRunMutation.mutateAsync({ runId, resetTo });
    await queryClient.invalidateQueries({ queryKey: ["run-detail", runId] });
    await queryClient.invalidateQueries({ queryKey: ["run-trace", runId] });
    await queryClient.invalidateQueries({ queryKey: ["run-report", runId] });
  }

  function handleExportMarkdown(): void {
    if (!reportMarkdown) {
      pushToast({ title: "暂无报告内容", variant: "warning" });
      return;
    }
    const blob = new Blob([reportMarkdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `rivallens_report_${runId}.md`;
    a.click();
    URL.revokeObjectURL(url);
    track("run_view.export_markdown", { run_id: runId });
  }

  async function handleCopyShareLink(): Promise<void> {
    const sharedUrl = `${window.location.origin}/share/${runId}`;
    try {
      await navigator.clipboard.writeText(sharedUrl);
      pushToast({ title: "分享链接已复制", description: sharedUrl, variant: "success" });
      track("run_view.copy_share_link", { run_id: runId });
    } catch {
      pushToast({ title: "复制失败", variant: "danger" });
    }
  }

  return (
    <section className="space-y-6">
      {/* Header */}
      <header className="space-y-2">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <h1 className="text-h1 text-foreground">{detailQuery.data?.user_query ?? "加载中..."}</h1>
            <p className="mt-1 text-micro text-foreground-subtle">
              {detailQuery.data ? formatDateTime(detailQuery.data.started_at) : ""} · {runId}
            </p>
          </div>
          <StatusBadge status={runStatus} />
        </div>
      </header>

      {detailQuery.isLoading && (
        <div className="space-y-3">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      )}

      {detailQuery.isError && (
        <div className="rounded-lg border border-danger/30 bg-danger/5 p-4 text-caption text-danger">
          {detailQuery.error.message}
        </div>
      )}

      {detailQuery.data && (
        <>
          {/* KPI bar */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <KpiCard label="覆盖率" value={metricsQuery.data ? `${(metricsQuery.data.coverage_rate * 100).toFixed(0)}%` : "-"} />
            <KpiCard label="QA 通过" value={metricsQuery.data ? `${((1 - metricsQuery.data.qa_rejection_rate) * 100).toFixed(0)}%` : "-"} />
            <KpiCard label="证据数" value={metricsQuery.data?.evidence_count_total.toLocaleString() ?? "-"} />
            <KpiCard label="耗时" value={detailQuery.data.finished_at ? formatRelativeTime(detailQuery.data.finished_at) : "进行中"} />
          </div>

          {/* Tabs */}
          <Tabs defaultValue="battlecard">
            <div className="flex items-center justify-between gap-3">
              <TabsList>
                <TabsTrigger value="battlecard">Battlecard</TabsTrigger>
                <TabsTrigger value="report">完整报告</TabsTrigger>
                <TabsTrigger value="trace">决策回放</TabsTrigger>
              </TabsList>
              {/* Toolbar */}
              <div className="flex items-center gap-1.5">
                <Button size="sm" variant="ghost" onClick={() => void handleCopyShareLink()} aria-label="复制分享链接">
                  <Share2 className="h-3.5 w-3.5" />
                </Button>
                <Button size="sm" variant="ghost" onClick={handleExportMarkdown} aria-label="导出 Markdown">
                  <Download className="h-3.5 w-3.5" />
                </Button>
                <Button size="sm" variant="ghost" onClick={() => navigate(`/app/runs/new?from=${runId}`)} aria-label="再分析一版">
                  <RotateCcw className="h-3.5 w-3.5" />
                </Button>
                <Button size="sm" variant="ghost" onClick={() => navigate(`/app/compare?run_ids=${runId}`)} aria-label="对比矩阵">
                  <Copy className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>

            {/* Battlecard tab */}
            <TabsContent value="battlecard" className="space-y-4">
              {!isReportReady && (
                <div className="flex items-center gap-2 rounded-lg border border-white/[0.06] bg-surface p-4 text-caption text-foreground-muted">
                  <Activity className="h-4 w-4 text-primary" />
                  报告生成中，完成后将展示 Battlecard 网格。
                </div>
              )}
              {isReportReady && conclusionsQuery.isLoading && <Skeleton className="h-60 w-full" />}
              {isReportReady && !conclusionsQuery.isLoading && (
                <BattlecardGrid runId={runId} conclusions={conclusions} />
              )}
            </TabsContent>

            {/* Full report tab */}
            <TabsContent value="report" className="space-y-4">
              {!isReportReady && (
                <div className="flex items-center gap-2 rounded-lg border border-white/[0.06] bg-surface p-4 text-caption text-foreground-muted">
                  <Activity className="h-4 w-4 text-primary" />
                  报告仍在生成中。
                </div>
              )}
              {reportQuery.isLoading && <Skeleton className="h-60 w-full" />}
              {reportQuery.isError && (
                <p className="text-caption text-danger">报告读取失败：{reportQuery.error.message}</p>
              )}
              {isReportReady && !reportQuery.isLoading && !reportQuery.isError && (
                <article className="prose prose-invert max-w-none rounded-lg border border-white/[0.06] bg-surface p-6 text-caption leading-7 prose-headings:text-foreground prose-p:text-foreground-muted prose-strong:text-foreground prose-a:text-primary">
                  <ReactMarkdown
                    components={{
                      a: ({ href, children }) => {
                        if (href?.startsWith("evidence://")) {
                          const evidenceId = href.replace("evidence://", "");
                          return (
                            <button
                              className="cursor-pointer rounded bg-primary/10 px-1.5 py-0.5 text-micro text-primary ring-1 ring-inset ring-primary/20 hover:bg-primary/20"
                              onClick={() => openEvidenceDrawer([evidenceId])}
                              type="button"
                            >
                              {children}
                            </button>
                          );
                        }
                        return <a href={href} rel="noreferrer" target="_blank">{children}</a>;
                      },
                      h2: ({ children }) => {
                        const text = Array.isArray(children)
                          ? children.map((c) => (typeof c === "string" ? c : "")).join(" ").trim()
                          : typeof children === "string" ? children.trim() : "";
                        return <h2 id={toHeadingId(text)}>{children}</h2>;
                      },
                    }}
                    remarkPlugins={[remarkGfm]}
                  >
                    {reportWithCitationLinks}
                  </ReactMarkdown>
                </article>
              )}
            </TabsContent>

            {/* Trace tab */}
            <TabsContent value="trace" className="space-y-4">
              {isReportReady && (
                <div className="flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={resetRunMutation.isPending}
                    onClick={() => void handleResetRun("writer")}
                  >
                    重写报告
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={resetRunMutation.isPending}
                    onClick={() => void handleResetRun("analyst")}
                  >
                    重做分析
                  </Button>
                </div>
              )}
              <div className="space-y-2">
                {recentDecisions.length === 0 && (
                  <p className="text-caption text-foreground-muted">暂无决策记录。</p>
                )}
                {recentDecisions.map((d) => (
                  <div key={d.id} className="rounded-lg border border-white/[0.06] bg-surface p-3">
                    <p className="text-caption font-medium text-foreground">
                      iter {d.iteration} · {d.chosen_tool}
                    </p>
                    <p className="mt-1 text-micro text-foreground-muted">{d.reasoning_summary}</p>
                  </div>
                ))}
              </div>
              <Button asChild size="sm" variant="outline">
                <Link to={`/app/runs/${runId}/trace`}>打开完整回放</Link>
              </Button>
            </TabsContent>
          </Tabs>
        </>
      )}

      <EvidenceDrawer
        evidenceIds={activeEvidenceIds}
        onOpenChange={setIsEvidenceDrawerOpen}
        open={isEvidenceDrawerOpen}
        runId={runId}
      />
    </section>
  );
}

function KpiCard({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div className="rounded-lg border border-white/[0.06] bg-surface px-4 py-3">
      <p className="text-micro text-foreground-subtle">{label}</p>
      <p className="mt-0.5 text-h3 font-semibold text-foreground">{value}</p>
    </div>
  );
}
