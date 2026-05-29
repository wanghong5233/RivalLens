import { useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Link, useParams } from "react-router-dom";
import remarkGfm from "remark-gfm";

import { queryClient } from "@/api/queryClient";
import { useResetRun, useRunDetail, useRunReport, useRunTrace } from "@/api/hooks";
import { useRunEvents } from "@/api/sse";
import { EvidenceDrawer } from "@/components/EvidenceDrawer";
import { MetricsPanel } from "@/components/MetricsPanel";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDateTime, formatRelativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const CITATION_REGEX = /\[(ev_[a-zA-Z0-9_]+)\]/g;

function toCitationLinkMarkdown(markdown: string): string {
  return markdown.replace(CITATION_REGEX, (_match, evidenceId: string) => {
    return `[${evidenceId}](evidence://${evidenceId})`;
  });
}

export function RunViewPage(): JSX.Element {
  const { runId: runIdFromParams } = useParams<{ runId: string }>();
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

  const traceSteps = traceQuery.data?.steps ?? [];
  const researcherSteps = traceSteps.filter((item) => item.agent_name === "researcher");
  const hasAnalystStep = traceSteps.some((item) => item.agent_name === "analyst");
  const hasWriterStep = traceSteps.some((item) => item.agent_name === "writer");

  const competitorProgress = useMemo(() => {
    const map = new Map<string, { done: boolean; evidenceCount: number }>();
    for (const competitorId of detailQuery.data?.competitors ?? []) {
      map.set(competitorId, { done: false, evidenceCount: 0 });
    }
    for (const step of researcherSteps) {
      const competitorId = step.payload.competitor_id;
      const evidenceIds = step.payload.evidence_ids;
      if (typeof competitorId !== "string") {
        continue;
      }
      const evidenceCount = Array.isArray(evidenceIds) ? evidenceIds.length : 0;
      const current = map.get(competitorId) ?? { done: false, evidenceCount: 0 };
      map.set(competitorId, {
        done: true,
        evidenceCount: current.evidenceCount + evidenceCount,
      });
    }
    return map;
  }, [detailQuery.data?.competitors, researcherSteps]);

  const progressStages = useMemo(() => {
    const isFinalized = runStatus === "completed" || runStatus === "degraded";
    const hasResearch = researcherSteps.length > 0;
    const stages: Array<{ key: string; label: string; state: "done" | "active" | "pending" }> = [
      { key: "research", label: "调研竞品", state: "pending" },
      { key: "analysis", label: "跨竞品分析", state: "pending" },
      { key: "writer", label: "撰写报告", state: "pending" },
    ];

    if (isFinalized) {
      return stages.map((item) => ({ ...item, state: "done" as const }));
    }
    if (!hasResearch) {
      stages[0].state = "active";
      return stages;
    }
    stages[0].state = "done";
    if (!hasAnalystStep) {
      stages[1].state = "active";
      return stages;
    }
    stages[1].state = "done";
    stages[2].state = hasWriterStep ? "done" : "active";
    return stages;
  }, [hasAnalystStep, hasWriterStep, researcherSteps.length, runStatus]);

  const latestEvents = useMemo(() => {
    const latest = traceSteps.slice(-6).reverse();
    return latest.map((step) => {
      const baseTime = formatDateTime(step.created_at);
      if (step.agent_name === "researcher") {
        const competitorId = typeof step.payload.competitor_id === "string" ? step.payload.competitor_id : "unknown";
        const evidenceCount = Array.isArray(step.payload.evidence_ids) ? step.payload.evidence_ids.length : 0;
        return `${baseTime}  Researcher(${competitorId}) 完成，输出 ${evidenceCount} 条 evidence`;
      }
      if (step.agent_name === "analyst") {
        return `${baseTime}  Analyst 完成跨竞品分析`;
      }
      if (step.agent_name === "writer") {
        return `${baseTime}  Writer 生成报告草稿`;
      }
      if (step.agent_name === "qa") {
        return `${baseTime}  QA 校验状态：${step.status}`;
      }
      return `${baseTime}  ${step.agent_name} 状态：${step.status}`;
    });
  }, [traceSteps]);
  const hasCuratorStep = traceSteps.some((item) => item.agent_name === "skill_curator");
  const showCuratorPending =
    (runStatus === "completed" || runStatus === "degraded") && !hasCuratorStep;
  const isResetPending = resetRunMutation.isPending;

  function openEvidenceDrawer(evidenceIds: string[]): void {
    if (evidenceIds.length === 0) {
      return;
    }
    setActiveEvidenceIds(evidenceIds);
    setIsEvidenceDrawerOpen(true);
  }

  async function handleResetRun(resetTo: "analyst" | "writer"): Promise<void> {
    if (!runId) {
      return;
    }
    await resetRunMutation.mutateAsync({ runId, resetTo });
    await queryClient.invalidateQueries({ queryKey: ["run-detail", runId] });
    await queryClient.invalidateQueries({ queryKey: ["run-trace", runId] });
    await queryClient.invalidateQueries({ queryKey: ["run-report", runId] });
  }

  const reportMarkdown = reportQuery.data?.content_markdown ?? "";
  const reportWithCitationLinks = useMemo(
    () => toCitationLinkMarkdown(reportMarkdown),
    [reportMarkdown],
  );

  return (
    <section className="space-y-4">
      <header className="space-y-2">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold">Run 详情</h1>
            <p className="font-mono text-xs text-muted-foreground">{runId}</p>
          </div>
          <div className="flex items-center gap-2">
            <StatusBadge status={runStatus} />
            <Link
              className="rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground hover:border-primary hover:text-foreground"
              to={`/runs/${runId}/trace`}
            >
              开发者视图
            </Link>
          </div>
        </div>
      </header>

      {detailQuery.isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      ) : null}

      {detailQuery.isError ? (
        <Card className="border-red-400/40">
          <CardContent className="pt-6 text-sm text-red-200">{detailQuery.error.message}</CardContent>
        </Card>
      ) : null}

      {detailQuery.data ? (
        <>
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">任务概览</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm text-muted-foreground">
              <p>query: {detailQuery.data.user_query}</p>
              <p>
                pack: {detailQuery.data.industry_pack} · competitors: {detailQuery.data.competitors.length}
              </p>
              <p>
                started: {formatDateTime(detailQuery.data.started_at)} ({formatRelativeTime(detailQuery.data.started_at)})
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">业务进度</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-2 sm:grid-cols-3">
                {progressStages.map((stage) => (
                  <div
                    className={cn(
                      "rounded-md border px-3 py-2 text-sm",
                      stage.state === "done" && "border-emerald-500/40 bg-emerald-500/10 text-emerald-200",
                      stage.state === "active" && "border-primary/50 bg-primary/10 text-foreground",
                      stage.state === "pending" && "border-border text-muted-foreground",
                    )}
                    key={stage.key}
                  >
                    {stage.state === "done" ? "✓" : stage.state === "active" ? "●" : "○"} {stage.label}
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          <MetricsPanel isRunActive={isRunActive} runId={runId} />

          {isReportReady ? (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">阶段重放（B2）</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-sm text-muted-foreground">
                  当结果不满意时，可从指定阶段回放。重放会清理该阶段及后续轨迹，然后从 checkpoint 继续执行。
                </p>
                <div className="flex flex-wrap gap-2">
                  <Button
                    disabled={isResetPending}
                    onClick={() => {
                      void handleResetRun("writer");
                    }}
                    type="button"
                    variant="outline"
                  >
                    {isResetPending ? "重放中..." : "重写报告（writer）"}
                  </Button>
                  <Button
                    disabled={isResetPending}
                    onClick={() => {
                      void handleResetRun("analyst");
                    }}
                    type="button"
                    variant="outline"
                  >
                    {isResetPending ? "重放中..." : "重做分析（analyst）"}
                  </Button>
                </div>
                {resetRunMutation.isError ? (
                  <p className="text-sm text-red-200">阶段重放失败：{resetRunMutation.error.message}</p>
                ) : null}
              </CardContent>
            </Card>
          ) : null}

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">竞品进度</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-2 sm:grid-cols-2">
                {detailQuery.data.competitors.map((competitorId) => {
                  const item = competitorProgress.get(competitorId) ?? { done: false, evidenceCount: 0 };
                  return (
                    <div className="rounded-md border border-border p-3 text-sm" key={competitorId}>
                      <p className="font-medium">{competitorId}</p>
                      <p className="mt-1 text-muted-foreground">
                        {item.done ? "✓ 已完成调研" : "⏳ 调研中"} · {item.evidenceCount} evidence
                      </p>
                      <Link
                        className="mt-2 inline-flex rounded-md border border-border px-2 py-1 text-xs text-muted-foreground hover:border-primary hover:text-foreground"
                        to={`/runs/${runId}/evidence?competitor_id=${encodeURIComponent(competitorId)}`}
                      >
                        查看证据
                      </Link>
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">最新事件</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 text-sm text-muted-foreground">
              {latestEvents.length > 0 ? latestEvents.map((event, index) => <p key={`${event}-${index}`}>• {event}</p>) : <p>暂无事件</p>}
            </CardContent>
          </Card>
          {showCuratorPending ? (
            <Card className="border-primary/40">
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Skill Curator 沉淀中...</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm text-muted-foreground">
                <p>主流程已完成，候选规则正在后台生成并写入 Skill Staging Console。</p>
                <Link className="text-primary hover:underline" to="/skills/staging">
                  前往 Skill Staging Console
                </Link>
              </CardContent>
            </Card>
          ) : null}
        </>
      ) : null}

      {isReportReady ? (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Battlecard 报告</CardTitle>
          </CardHeader>
          <CardContent>
            {reportQuery.isLoading ? <Skeleton className="h-60 w-full" /> : null}
            {reportQuery.isError ? (
              <p className="text-sm text-red-200">报告读取失败：{reportQuery.error.message}</p>
            ) : null}
            {!reportQuery.isLoading && !reportQuery.isError ? (
              <article className="prose prose-invert max-w-none text-sm leading-7">
                <ReactMarkdown
                  components={{
                    a: ({ href, children }) => {
                      if (href?.startsWith("evidence://")) {
                        const evidenceId = href.replace("evidence://", "");
                        return (
                          <button
                            className="cursor-pointer rounded bg-primary/15 px-1.5 py-0.5 text-xs text-primary hover:bg-primary/25"
                            onClick={() => openEvidenceDrawer([evidenceId])}
                            type="button"
                          >
                            {children}
                          </button>
                        );
                      }
                      return (
                        <a href={href} rel="noreferrer" target="_blank">
                          {children}
                        </a>
                      );
                    },
                  }}
                  remarkPlugins={[remarkGfm]}
                >
                  {reportWithCitationLinks}
                </ReactMarkdown>
              </article>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      <EvidenceDrawer
        evidenceIds={activeEvidenceIds}
        onOpenChange={setIsEvidenceDrawerOpen}
        open={isEvidenceDrawerOpen}
        runId={runId}
      />
    </section>
  );
}
