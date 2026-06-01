import { Clock3, FileText, PlusCircle, Sparkles } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useResumeRun, useRunsList } from "@/api/hooks";
import { StatusBadge } from "@/components/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDateTime, formatRelativeTime, formatRunTitle } from "@/lib/format";

export function HomePage(): JSX.Element {
  const navigate = useNavigate();
  const runsQuery = useRunsList({ limit: 20, offset: 0 });
  const resumeMutation = useResumeRun();
  const [resumingRunId, setResumingRunId] = useState<string | null>(null);
  const [resumeError, setResumeError] = useState<string | null>(null);
  const runs = runsQuery.data?.items ?? [];

  const summary = useMemo(() => {
    const completedCount = runs.filter((item) => item.status === "completed").length;
    const activeCount = runs.filter((item) => item.status === "running").length;
    return {
      totalCount: runs.length,
      completedCount,
      activeCount,
    };
  }, [runs]);

  async function handleResumeRun(runId: string): Promise<void> {
    setResumingRunId(runId);
    try {
      await resumeMutation.mutateAsync(runId);
      setResumeError(null);
      await runsQuery.refetch();
      navigate(`/app/runs/${runId}`);
    } catch (error) {
      if (error instanceof Error) {
        setResumeError(error.message);
      } else {
        setResumeError("恢复运行失败，请稍后重试。");
      }
    } finally {
      setResumingRunId(null);
    }
  }

  return (
    <section className="space-y-5">
      <Card className="border-primary/25 bg-gradient-to-r from-primary/12 via-primary/5 to-transparent">
        <CardContent className="flex flex-col gap-4 pt-6 md:flex-row md:items-center md:justify-between">
          <div className="space-y-2">
            <p className="inline-flex items-center gap-2 text-xs text-primary">
              <Sparkles className="h-3.5 w-3.5" />
              面向产品经理与创业者
            </p>
            <h1 className="text-3xl font-semibold tracking-tight">我的竞品分析</h1>
            <p className="max-w-2xl text-sm text-muted-foreground">
              选择竞品并提出问题，RivalLens 会自动完成调研、分析与报告生成。每条关键结论都能追溯到证据来源。
            </p>
          </div>
          <Button className="self-start md:self-auto" onClick={() => navigate("/app/runs/new")} size="lg">
            <PlusCircle className="mr-2 h-4 w-4" />
            开始新分析
          </Button>
        </CardContent>
      </Card>

      <div className="grid gap-3 sm:grid-cols-3">
        <Card>
          <CardContent className="pt-6">
            <p className="text-xs text-muted-foreground">累计分析任务</p>
            <p className="mt-1 text-2xl font-semibold tabular-nums">{summary.totalCount}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-xs text-muted-foreground">正在进行</p>
            <p className="mt-1 text-2xl font-semibold text-amber-300 tabular-nums">{summary.activeCount}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-xs text-muted-foreground">已完成报告</p>
            <p className="mt-1 text-2xl font-semibold text-emerald-300 tabular-nums">{summary.completedCount}</p>
          </CardContent>
        </Card>
      </div>

      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">最近分析</h2>
          <p className="text-sm text-muted-foreground">点击任意卡片进入详情，查看报告、进度与证据。</p>
        </div>
      </div>

      {runsQuery.isLoading ? (
        <div className="space-y-4">
          <Skeleton className="h-36 w-full" />
          <Skeleton className="h-36 w-full" />
        </div>
      ) : null}

      {runsQuery.isError ? (
        <Card className="border-red-400/40">
          <CardContent className="pt-6 text-sm text-red-200">{runsQuery.error.message}</CardContent>
        </Card>
      ) : null}

      {resumeError ? (
        <Card className="border-red-400/40">
          <CardContent className="pt-6 text-sm text-red-200">{resumeError}</CardContent>
        </Card>
      ) : null}

      {!runsQuery.isLoading && !runsQuery.isError && runs.length === 0 ? (
        <Card>
          <CardContent className="space-y-3 pt-8 text-center">
            <p className="text-base font-medium">还没有分析任务</p>
            <p className="text-sm text-muted-foreground">先从一个清晰问题开始，例如“Cursor 与 Windsurf 的功能与定价差异”。</p>
            <div>
              <Button onClick={() => navigate("/app/runs/new")}>开始第一次分析</Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {!runsQuery.isLoading && !runsQuery.isError ? (
        <div className="space-y-4">
          {runs.map((run) => (
            <Card
              className="cursor-pointer border-border/80 transition hover:border-primary/45 focus-within:ring-1 focus-within:ring-ring"
              key={run.run_id}
              onClick={() => navigate(`/app/runs/${run.run_id}`)}
              onKeyDown={(event) => {
                if (event.key !== "Enter" && event.key !== " ") {
                  return;
                }
                event.preventDefault();
                navigate(`/app/runs/${run.run_id}`);
              }}
              role="button"
              tabIndex={0}
            >
              <CardHeader className="space-y-3 pb-3">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <CardTitle className="max-w-4xl text-xl leading-7" title={run.user_query}>
                    {formatRunTitle(run)}
                  </CardTitle>
                  <div className="flex items-center gap-2 whitespace-nowrap">
                    <StatusBadge status={run.status} />
                    {run.status === "running" ? (
                      <Button
                        disabled={resumingRunId === run.run_id}
                        onClick={(event) => {
                          event.stopPropagation();
                          void handleResumeRun(run.run_id);
                        }}
                        size="sm"
                        variant="outline"
                      >
                        恢复运行
                      </Button>
                    ) : null}
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-4 text-sm">
                <div className="flex flex-wrap items-center gap-2 text-muted-foreground">
                  {run.domain_hint ? (
                    <Badge variant="outline" className="border-primary/40 bg-primary/10 text-foreground">
                      领域：{run.domain_hint}
                    </Badge>
                  ) : null}
                  <Badge variant="secondary" className="bg-muted/70">
                    <Clock3 className="mr-1 h-3.5 w-3.5" />
                    {formatRelativeTime(run.started_at)}
                  </Badge>
                  <Badge variant={run.has_report ? "default" : "secondary"}>
                    <FileText className="mr-1 h-3.5 w-3.5" />
                    {run.has_report ? "报告已生成" : "报告生成中"}
                  </Badge>
                </div>

                <div className="grid gap-2 text-muted-foreground sm:grid-cols-2">
                  <p>创建时间：{formatDateTime(run.started_at)}</p>
                  <p>完成时间：{run.finished_at ? formatDateTime(run.finished_at) : "正在处理中"}</p>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : null}
    </section>
  );
}
