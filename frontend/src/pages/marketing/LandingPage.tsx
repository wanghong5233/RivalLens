import { ArrowRight, FileSearch, Layers, Share2 } from "lucide-react";
import { useEffect } from "react";
import { Link } from "react-router-dom";

import { useRunsList } from "@/api/hooks";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDateTime, formatRunTitle } from "@/lib/format";

export function LandingPage(): JSX.Element {
  const completedRunsQuery = useRunsList({ status: "completed", limit: 3, offset: 0 });

  useEffect(() => {
    document.title = "RivalLens — AI 竞品雷达";
  }, []);

  return (
    <div className="space-y-20 pb-16">
      {/* Hero */}
      <section className="relative pt-16 text-center">
        <div className="absolute inset-0 -z-10 overflow-hidden">
          <div className="absolute left-1/2 top-0 h-[500px] w-[800px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary/[0.06] blur-[120px]" />
        </div>
        <p className="mb-4 inline-flex items-center gap-2 rounded-full bg-primary/10 px-3 py-1 text-micro font-medium text-primary ring-1 ring-inset ring-primary/20">
          AI-Powered Competitive Intelligence
        </p>
        <h1 className="mx-auto max-w-3xl font-display text-display text-foreground">
          3 分钟产出可溯源的
          <br />
          <span className="text-primary">Battlecard 报告</span>
        </h1>
        <p className="mx-auto mt-5 max-w-2xl text-body text-foreground-muted">
          输入竞品名称，RivalLens 通过多 Agent 协作自动采集公开信息，生成结构化竞品结论矩阵，帮助产品经理与创业者更快做出业务决策。
        </p>
        <div className="mt-8 flex items-center justify-center gap-3">
          <Button asChild size="lg">
            <Link to="/app/runs/new">
              开始分析
              <ArrowRight className="h-4 w-4" />
            </Link>
          </Button>
          <Button asChild size="lg" variant="secondary">
            <Link to="/app">进入工作区</Link>
          </Button>
        </div>
      </section>

      {/* Product preview mock — Battlecard style */}
      <section className="relative mx-auto max-w-4xl">
        <div className="rounded-xl border border-white/[0.06] bg-surface p-6 shadow-raised">
          <div className="mb-4 flex items-center gap-3">
            <div className="h-2 w-2 rounded-full bg-success" />
            <span className="text-caption text-foreground-muted">分析完成 · 3 个竞品 · 42 条结论</span>
          </div>
          <div className="grid gap-3 md:grid-cols-3">
            {["Competitor A", "Competitor B", "Competitor C"].map((name) => (
              <div key={name} className="rounded-lg border border-white/[0.06] bg-page p-4">
                <p className="mb-3 text-caption font-semibold text-foreground">{name}</p>
                <div className="space-y-2">
                  <div className="flex items-start gap-2">
                    <span className="mt-0.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                    <span className="text-micro text-foreground-muted">定价策略偏向企业级，年付折扣 20%</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="mt-0.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-warning" />
                    <span className="text-micro text-foreground-muted">用户反馈集中在上手门槛高</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="mt-0.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-success" />
                    <span className="text-micro text-foreground-muted">API 集成能力强，文档完善</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="absolute -inset-px -z-10 rounded-xl bg-gradient-to-b from-primary/20 to-transparent opacity-40 blur-xl" />
      </section>

      {/* Value props */}
      <section className="grid gap-6 md:grid-cols-3">
        <div className="space-y-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 ring-1 ring-inset ring-primary/20">
            <FileSearch className="h-5 w-5 text-primary" />
          </div>
          <h3 className="text-h3 text-foreground">自动调研</h3>
          <p className="text-caption text-foreground-muted">
            并行抓取竞品官网、定价页、用户反馈，形成可追踪证据链。每条结论都可溯源到原始信息。
          </p>
        </div>
        <div className="space-y-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent/10 ring-1 ring-inset ring-accent/20">
            <Layers className="h-5 w-5 text-accent" />
          </div>
          <h3 className="text-h3 text-foreground">结构化结论</h3>
          <p className="text-caption text-foreground-muted">
            把离散信息变成按竞品分组的 Battlecard 矩阵，输出置信度与风险标记，支持跨竞品对比。
          </p>
        </div>
        <div className="space-y-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-success/10 ring-1 ring-inset ring-success/20">
            <Share2 className="h-5 w-5 text-success" />
          </div>
          <h3 className="text-h3 text-foreground">一键分享</h3>
          <p className="text-caption text-foreground-muted">
            导出 PDF / Markdown 或生成公开链接，让团队快速对齐决策结论，无需重复沟通。
          </p>
        </div>
      </section>

      {/* Showcase wall */}
      <section className="space-y-4">
        <div className="flex items-end justify-between">
          <h2 className="text-h2 text-foreground">最近完成的分析</h2>
          <Link className="text-caption text-primary hover:underline" to="/examples">
            查看全部
          </Link>
        </div>

        {completedRunsQuery.isLoading && (
          <div className="grid gap-4 md:grid-cols-3">
            <Skeleton className="h-28 w-full" />
            <Skeleton className="h-28 w-full" />
            <Skeleton className="h-28 w-full" />
          </div>
        )}

        {completedRunsQuery.isError && (
          <Card>
            <CardContent className="py-6 text-caption text-danger">
              {completedRunsQuery.error.message}
            </CardContent>
          </Card>
        )}

        <div className="grid gap-4 md:grid-cols-3">
          {(completedRunsQuery.data?.items ?? []).map((run) => (
            <Link key={run.run_id} to={`/share/${run.run_id}`}>
              <Card className="h-full transition-colors hover:border-white/[0.12]">
                <CardContent className="space-y-2 p-5">
                  <p
                    className="line-clamp-2 text-caption font-medium text-foreground"
                    title={run.user_query}
                  >
                    {formatRunTitle(run)}
                  </p>
                  <div className="flex items-center gap-2">
                    <StatusBadge status={run.status} />
                  </div>
                  <p className="text-micro text-foreground-subtle">
                    {run.finished_at ? formatDateTime(run.finished_at) : "处理中"}
                  </p>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-white/[0.04] pt-6 text-micro text-foreground-subtle">
        <div className="flex items-center justify-between">
          <p>数据来源以公开信息为主，每条结论可追溯到证据原文。</p>
          <div className="flex gap-4">
            <Link className="hover:text-foreground" to="/examples">案例</Link>
            <Link className="hover:text-foreground" to="/pricing">定价</Link>
            <Link className="hover:text-foreground" to="/app">工作区</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
