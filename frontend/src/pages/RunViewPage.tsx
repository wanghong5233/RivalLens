import {
  Activity,
  Boxes,
  CircleSlash,
  Copy,
  FileText,
  GitBranch,
  Download,
  RotateCcw,
  Share2,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Link, useNavigate, useParams } from "react-router-dom";
import remarkGfm from "remark-gfm";

import { queryClient } from "@/api/queryClient";
import {
  useResetRun,
  useRunComparisons,
  useRunConclusions,
  useRunDetail,
  useRunKnowledge,
  useRunMetrics,
  useRunReport,
  useRunTrace,
} from "@/api/hooks";
import type {
  RunKnowledgeResponse,
  RunMetricsResponse,
  RunTraceResponse,
} from "@/api/types";
import { useRunEvents } from "@/api/sse";
import { BattlecardGrid } from "@/components/battlecard";
import { ComparisonMatrix } from "@/components/comparison/ComparisonMatrix";
import { EvidenceDrawer } from "@/components/EvidenceDrawer";
import { KnowledgePanel } from "@/components/knowledge/KnowledgePanel";
import { MetricsPanel } from "@/components/MetricsPanel";
import { RunBreadcrumb } from "@/components/RunBreadcrumb";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { pushToast } from "@/components/ui/toaster";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toCitationLinkMarkdown, transformEvidenceMarkdownUrl } from "@/lib/evidenceLinks";
import { formatDateTime, formatDuration, formatRunTitle } from "@/lib/format";
import { SHOW_DEBUG_PANELS } from "@/lib/debugFlags";
import { runPhaseRoute } from "@/lib/runRoute";
import { track } from "@/lib/analytics";
import { cn } from "@/lib/utils";

type RunViewTab = "battlecard" | "knowledge" | "report" | "trace";

const METHODOLOGY_HEADING = "数据来源与方法论";

function toHeadingId(value: string): string {
  return value.trim().toLowerCase().replace(/[^\w\u4e00-\u9fa5\s-]/g, "").replace(/\s+/g, "-");
}

function isRunViewTab(value: string): value is RunViewTab {
  return value === "battlecard" || value === "knowledge" || value === "report" || value === "trace";
}

function hasMethodologyHeading(markdown: string): boolean {
  return /^##\s+数据来源与方法论\s*$/m.test(markdown);
}

export function RunViewPage(): JSX.Element {
  const { runId: runIdFromParams } = useParams<{ runId: string }>();
  const navigate = useNavigate();
  const runId = runIdFromParams ?? "";
  const [isEvidenceDrawerOpen, setIsEvidenceDrawerOpen] = useState(false);
  const [activeEvidenceIds, setActiveEvidenceIds] = useState<string[]>([]);
  const [activeTab, setActiveTab] = useState<RunViewTab>("report");
  useRunEvents(runId);

  const detailQuery = useRunDetail(runId);
  const traceQuery = useRunTrace(runId);
  const resetRunMutation = useResetRun();

  const runStatus = detailQuery.data?.status ?? "running";
  const isRunActive = runStatus === "running";
  const isReportReady = runStatus === "completed" || runStatus === "degraded";
  // failed/cancelled are *terminal-without-output* — KPI cards and Tabs are
  // dead weight (they all collapse to "-" or "生成中" placeholders).
  // We collapse them into a single outcome card with the actions that matter.
  const isTerminalFailure = runStatus === "failed" || runStatus === "cancelled";
  const reportQuery = useRunReport(runId, { enabled: isReportReady });
  const conclusionsQuery = useRunConclusions(runId, {
    enabled: isReportReady,
    refetchInterval: isRunActive ? 2_000 : false,
  });
  const comparisonsQuery = useRunComparisons(runId, {
    enabled: isReportReady,
    refetchInterval: isRunActive ? 2_000 : false,
  });
  const knowledgeQuery = useRunKnowledge(runId, {
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
  const hasMethodologySection = useMemo(() => hasMethodologyHeading(reportMarkdown), [reportMarkdown]);
  const reportEvidenceIds = useMemo(
    () => Object.keys(reportQuery.data?.evidence_id_to_brief ?? {}),
    [reportQuery.data?.evidence_id_to_brief],
  );
  const conclusions = conclusionsQuery.data?.items ?? [];
  const comparisons = comparisonsQuery.data?.items ?? [];
  const activeRunRoute = detailQuery.data ? runPhaseRoute(detailQuery.data) : null;

  function openEvidenceDrawer(evidenceIds: string[]): void {
    if (evidenceIds.length === 0) return;
    setActiveEvidenceIds(evidenceIds);
    setIsEvidenceDrawerOpen(true);
  }

  function handleTabChange(value: string): void {
    if (isRunViewTab(value)) {
      setActiveTab(value);
    }
  }

  function handleOpenMethodology(): void {
    setActiveTab("report");
    window.requestAnimationFrame(() => {
      document.getElementById(toHeadingId(METHODOLOGY_HEADING))?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    });
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
        <RunBreadcrumb run={detailQuery.data} />
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <h1
              className="text-h1 text-foreground"
              title={detailQuery.data?.user_query ?? undefined}
            >
              {detailQuery.data ? formatRunTitle(detailQuery.data, { max: 60 }) : "加载中..."}
            </h1>
            <p className="mt-1 text-micro text-foreground-subtle">
              {detailQuery.data ? formatDateTime(detailQuery.data.started_at) : ""} · {runId}
            </p>
            {detailQuery.data?.user_query ? (
              <p
                className="mt-2 line-clamp-2 max-w-3xl text-caption text-foreground-subtle"
                title={detailQuery.data.user_query}
              >
                {detailQuery.data.user_query}
              </p>
            ) : null}
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

      {detailQuery.data && isTerminalFailure && (
        <RunOutcomeCard
          runId={runId}
          status={runStatus as "failed" | "cancelled"}
          startedAt={detailQuery.data.started_at}
          finishedAt={detailQuery.data.finished_at}
          onReanalyze={() => navigate(`/app/runs/new?from=${runId}`)}
        />
      )}

      {detailQuery.data && !isTerminalFailure && (
        <>
          {/* Running hint */}
          {isRunActive && activeRunRoute !== null && activeRunRoute !== `/app/runs/${runId}` ? (
            <div className="flex flex-col gap-3 rounded-lg border border-primary/25 bg-primary/[0.06] p-4 text-caption text-foreground-muted sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-center gap-2">
                <Activity className="h-4 w-4 text-primary" />
                <span>分析仍在进行中，建议查看实时进度，避免在报告生成前看到空结果。</span>
              </div>
              <Button asChild size="sm" variant="secondary">
                <Link to={activeRunRoute}>前往实时进度</Link>
              </Button>
            </div>
          ) : null}

          {/* KPI bar */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <KpiCard label="覆盖率" value={metricsQuery.data ? `${(metricsQuery.data.coverage_rate * 100).toFixed(0)}%` : "-"} />
            <KpiCard label="QA 通过" value={metricsQuery.data ? `${((1 - metricsQuery.data.qa_rejection_rate) * 100).toFixed(0)}%` : "-"} />
            <KpiCard label="证据数" value={metricsQuery.data?.evidence_count_total.toLocaleString() ?? "-"} />
            <KpiCard
              label="耗时"
              value={
                detailQuery.data.finished_at
                  ? formatDuration(detailQuery.data.started_at, detailQuery.data.finished_at)
                  : "进行中"
              }
            />
          </div>

          {isReportReady ? (
            <RunReadinessPanel
              hasMethodologySection={hasMethodologySection}
              knowledge={knowledgeQuery.data}
              metrics={metricsQuery.data}
              onOpenEvidence={() => openEvidenceDrawer(reportEvidenceIds)}
              onOpenMethodology={handleOpenMethodology}
              onSelectTab={setActiveTab}
              reportEvidenceCount={reportEvidenceIds.length}
              trace={traceQuery.data}
            />
          ) : null}

          {isReportReady ? <MetricsPanel isRunActive={isRunActive} runId={runId} /> : null}

          {/* Tabs */}
          <Tabs value={activeTab} onValueChange={handleTabChange}>
            <div className="flex items-center justify-between gap-3">
              <TabsList>
                <TabsTrigger value="battlecard">Battlecard</TabsTrigger>
                <TabsTrigger value="knowledge">竞品知识</TabsTrigger>
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
                {SHOW_DEBUG_PANELS && isReportReady ? (
                  <Button size="sm" variant="ghost" onClick={() => navigate(`/app/runs/${runId}/audit`)} aria-label="运行诊断">
                    <ShieldCheck className="h-3.5 w-3.5" />
                  </Button>
                ) : null}
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

            {/* Knowledge tab */}
            <TabsContent value="knowledge" className="space-y-4">
              {!isReportReady && (
                <div className="flex items-center gap-2 rounded-lg border border-white/[0.06] bg-surface p-4 text-caption text-foreground-muted">
                  <Activity className="h-4 w-4 text-primary" />
                  报告生成后将展示结构化功能树、定价模型和用户画像。
                </div>
              )}
              {isReportReady ? (
                <KnowledgePanel
                  errorMessage={knowledgeQuery.error?.message ?? null}
                  isLoading={knowledgeQuery.isLoading}
                  knowledge={knowledgeQuery.data ?? null}
                  onEvidenceClick={openEvidenceDrawer}
                />
              ) : null}
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
                <>
                  <ComparisonMatrix comparisons={comparisons} onEvidenceClick={openEvidenceDrawer} />
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
                      urlTransform={transformEvidenceMarkdownUrl}
                    >
                      {reportWithCitationLinks}
                    </ReactMarkdown>
                  </article>
                </>
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

interface RunReadinessPanelProps {
  hasMethodologySection: boolean;
  knowledge: RunKnowledgeResponse | undefined;
  metrics: RunMetricsResponse | undefined;
  reportEvidenceCount: number;
  trace: RunTraceResponse | undefined;
  onOpenEvidence: () => void;
  onOpenMethodology: () => void;
  onSelectTab: (tab: RunViewTab) => void;
}

function formatCompactPercent(value: number | undefined): string {
  return value === undefined ? "-" : `${(value * 100).toFixed(0)}%`;
}

function RunReadinessPanel({
  hasMethodologySection,
  knowledge,
  metrics,
  reportEvidenceCount,
  trace,
  onOpenEvidence,
  onOpenMethodology,
  onSelectTab,
}: RunReadinessPanelProps): JSX.Element {
  const featureCount = knowledge?.features.length ?? 0;
  const pricingCount = knowledge?.pricings.length ?? 0;
  const personaCount = knowledge?.personas.length ?? 0;
  const schemaCount = featureCount + pricingCount + personaCount;
  const agentCount = trace === undefined ? null : new Set(trace.steps.map((step) => step.agent_name)).size;
  const qaText =
    metrics === undefined
      ? "-"
      : metrics.qa_rejected_steps === 0
        ? "QA 已通过"
        : `QA ${metrics.qa_rejected_steps.toLocaleString()} 次打回`;
  const sourceAuthorityTotal =
    metrics === undefined
      ? 0
      : Object.values(metrics.source_authority_distribution).reduce((sum, count) => sum + count, 0);
  const officialSourceRate =
    metrics !== undefined && sourceAuthorityTotal > 0
      ? (metrics.source_authority_distribution.official ?? 0) / sourceAuthorityTotal
      : undefined;

  return (
    <section className="rounded-xl border border-primary/20 bg-primary/[0.04] p-4">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-foreground">交付速览</h2>
          <p className="mt-1 text-xs text-foreground-muted">
            把评分项入口前置：报告、溯源、Schema、Agent 可观测性都能从这里进入。
          </p>
        </div>
        <Button size="sm" variant="secondary" onClick={() => onSelectTab("report")}>
          查看完整报告
        </Button>
      </div>

      <div className="grid gap-3 lg:grid-cols-4">
        <ReadinessCard
          actionLabel="定位方法论"
          description={hasMethodologySection ? "报告包含确定性数据来源与方法论段" : "报告暂未检测到方法论段"}
          disabled={!hasMethodologySection}
          icon={FileText}
          onAction={onOpenMethodology}
          title="报告可用性"
          value={hasMethodologySection ? "含方法论" : "待检查"}
        />
        <ReadinessCard
          actionLabel="查看引用证据"
          description={`官方来源占比 ${formatCompactPercent(officialSourceRate)}`}
          disabled={reportEvidenceCount === 0}
          icon={ShieldCheck}
          onAction={onOpenEvidence}
          title="信息溯源"
          value={`${reportEvidenceCount.toLocaleString()} 条引用`}
        />
        <ReadinessCard
          actionLabel="打开 Schema"
          description={`功能 ${featureCount.toLocaleString()} / 定价 ${pricingCount.toLocaleString()} / 用户画像 ${personaCount.toLocaleString()}`}
          icon={Boxes}
          onAction={() => onSelectTab("knowledge")}
          title="知识 Schema"
          value={`${schemaCount.toLocaleString()} 条结构化记录`}
        />
        <ReadinessCard
          actionLabel="查看回放"
          description={`${qaText} · LLM ${metrics?.llm_call_count.toLocaleString() ?? "-"} 次调用`}
          icon={GitBranch}
          onAction={() => onSelectTab("trace")}
          title="Agent 可观测"
          value={agentCount === null ? "-" : `${agentCount.toLocaleString()} 类 Agent`}
        />
      </div>
    </section>
  );
}

interface ReadinessCardProps {
  actionLabel: string;
  description: string;
  icon: typeof FileText;
  title: string;
  value: string;
  disabled?: boolean;
  onAction: () => void;
}

function ReadinessCard({
  actionLabel,
  description,
  disabled = false,
  icon: Icon,
  title,
  value,
  onAction,
}: ReadinessCardProps): JSX.Element {
  return (
    <article className="flex min-h-36 flex-col justify-between rounded-lg border border-white/[0.06] bg-surface p-3">
      <div>
        <div className="flex items-center gap-2 text-xs font-medium text-foreground-muted">
          <Icon className="h-3.5 w-3.5 text-primary" />
          {title}
        </div>
        <p className="mt-2 text-lg font-semibold text-foreground">{value}</p>
        <p className="mt-1 text-xs leading-5 text-foreground-subtle">{description}</p>
      </div>
      <Button className="mt-3 w-fit" disabled={disabled} onClick={onAction} size="sm" type="button" variant="outline">
        {actionLabel}
      </Button>
    </article>
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

interface RunOutcomeCardProps {
  runId: string;
  status: "failed" | "cancelled";
  startedAt: string;
  finishedAt: string | null;
  onReanalyze: () => void;
}

/**
 * Replaces the KPI + Tabs region when the run ended without producing a
 * report. Pattern follows Vercel's "Deployment failed" page and GitHub
 * Actions failed-run summary: large icon + status headline + brief
 * timeline + the two actions that actually matter (re-run, see logs).
 *
 * We deliberately avoid showing KPI placeholders ("-") or "报告生成中" hints
 * here — they're noise once the run is terminal-without-output.
 */
function RunOutcomeCard({
  runId,
  status,
  startedAt,
  finishedAt,
  onReanalyze,
}: RunOutcomeCardProps): JSX.Element {
  const isFailed = status === "failed";
  const Icon = isFailed ? XCircle : CircleSlash;
  return (
    <div
      className={cn(
        "rounded-xl border p-6",
        isFailed
          ? "border-danger/25 bg-danger/[0.04]"
          : "border-white/[0.08] bg-white/[0.02]",
      )}
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
        <div
          className={cn(
            "flex h-12 w-12 shrink-0 items-center justify-center rounded-full",
            isFailed
              ? "bg-danger/10 text-danger"
              : "bg-white/[0.06] text-foreground-muted",
          )}
        >
          <Icon className="h-6 w-6" />
        </div>
        <div className="min-w-0 flex-1 space-y-3">
          <div>
            <h2 className="text-h3 font-semibold text-foreground">
              {isFailed ? "分析未能完成" : "分析已停止"}
            </h2>
            <p className="mt-1 text-caption text-foreground-muted">
              {isFailed
                ? "运行过程中发生错误，可在「决策回放」查看 Agent 最后操作以定位原因，或直接基于此重新发起一次。"
                : "你在分析进行中点击了停止；可以基于同一需求重新发起一次。"}
            </p>
          </div>
          <dl className="grid grid-cols-3 gap-x-4 gap-y-1.5 border-t border-white/[0.04] pt-3 text-caption">
            <div className="space-y-0.5">
              <dt className="text-micro text-foreground-subtle">开始时间</dt>
              <dd className="font-medium text-foreground">{formatDateTime(startedAt)}</dd>
            </div>
            <div className="space-y-0.5">
              <dt className="text-micro text-foreground-subtle">结束时间</dt>
              <dd className="font-medium text-foreground">
                {finishedAt ? formatDateTime(finishedAt) : "-"}
              </dd>
            </div>
            <div className="space-y-0.5">
              <dt className="text-micro text-foreground-subtle">耗时</dt>
              <dd className="font-medium text-foreground">
                {formatDuration(startedAt, finishedAt)}
              </dd>
            </div>
          </dl>
          <div className="flex flex-wrap gap-2 pt-1">
            <Button onClick={onReanalyze} size="sm">
              <RotateCcw className="h-3.5 w-3.5" />
              基于此重新分析
            </Button>
            <Button asChild size="sm" variant="outline">
              <Link to={`/app/runs/${runId}/trace`}>查看决策回放</Link>
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
