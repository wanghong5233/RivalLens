import { useMemo, useState, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import { Link, useParams } from "react-router-dom";
import remarkGfm from "remark-gfm";
import { ArrowLeft, Clock, FileText, Users, ChevronRight, RefreshCw, Activity, CheckCircle2, Sparkles } from "lucide-react";

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

interface Particle {
  id: number;
  x: number;
  y: number;
  size: number;
  speedX: number;
  speedY: number;
  opacity: number;
}

function ParticleBackground(): JSX.Element {
  const [particles, setParticles] = useState<Particle[]>([]);

  useEffect(() => {
    const initialParticles: Particle[] = Array.from({ length: 20 }, (_, i) => ({
      id: i,
      x: Math.random() * 100,
      y: Math.random() * 100,
      size: Math.random() * 2 + 1,
      speedX: (Math.random() - 0.5) * 0.2,
      speedY: (Math.random() - 0.5) * 0.2,
      opacity: Math.random() * 0.3 + 0.1,
    }));
    setParticles(initialParticles);

    const interval = setInterval(() => {
      setParticles((prev) =>
        prev.map((p) => ({
          ...p,
          x: (p.x + p.speedX + 100) % 100,
          y: (p.y + p.speedY + 100) % 100,
        }))
      );
    }, 80);

    return () => clearInterval(interval);
  }, []);

  return (
    <div className="fixed inset-0 pointer-events-none overflow-hidden z-0">
      {particles.map((particle) => (
        <div
          key={particle.id}
          className="absolute rounded-full bg-gradient-to-br from-blue-500/40 to-purple-600/40 animate-breathe"
          style={{
            left: `${particle.x}%`,
            top: `${particle.y}%`,
            width: `${particle.size}px`,
            height: `${particle.size}px`,
            opacity: particle.opacity,
            animationDelay: `${particle.id * 0.15}s`,
          }}
        />
      ))}
    </div>
  );
}

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
  const [isVisible, setIsVisible] = useState(false);
  const [animatedCards, setAnimatedCards] = useState<boolean[]>([]);
  useRunEvents(runId);

  useEffect(() => {
    setIsVisible(true);
    setAnimatedCards(new Array(6).fill(false));

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            const index = parseInt(entry.target.getAttribute("data-card-index") || "0");
            setAnimatedCards((prev) => {
              const newArr = [...prev];
              newArr[index] = true;
              return newArr;
            });
          }
        });
      },
      { threshold: 0.1 }
    );

    setTimeout(() => {
      document.querySelectorAll("[data-card-index]").forEach((el) => {
        observer.observe(el);
      });
    }, 300);

    return () => observer.disconnect();
  }, []);

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
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-blue-50 relative">
      <ParticleBackground />

      {/* Header */}
      <header className={`sticky top-0 z-50 glass border-b border-slate-100/50 transition-all duration-500 ${isVisible ? "opacity-100 translate-y-0" : "opacity-0 -translate-y-4"}`}>
        <div className="max-w-5xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Link to="/" className="flex items-center gap-2 text-slate-600 hover:text-slate-900 group transition-all hover:-translate-y-0.5">
                <ArrowLeft className="h-5 w-5" />
                <span className="text-sm font-medium">返回首页</span>
              </Link>
              <div className="h-4 w-px bg-slate-200" />
              <div>
                <h1 className="text-lg font-semibold text-slate-900 gradient-text">分析详情</h1>
                <p className="text-xs text-slate-500 font-mono bg-slate-100/80 px-2 py-1 rounded">{runId}</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <StatusBadge status={runStatus} />
              <Link
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-blue-50 text-blue-600 hover:bg-blue-100 hover:text-blue-700 transition-all hover-lift"
                to={`/runs/${runId}/trace`}
              >
                <Activity className="h-4 w-4" />
                开发者视图
              </Link>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-5xl mx-auto px-4 py-8">
        {/* Loading State */}
        {detailQuery.isLoading ? (
          <div className="space-y-4">
            <Skeleton className="h-32 w-full rounded-xl" />
            <Skeleton className="h-48 w-full rounded-xl" />
          </div>
        ) : null}

        {/* Error State */}
        {detailQuery.isError ? (
          <Card className="border-0 shadow-md bg-amber-50">
            <CardContent className="p-6">
              <div className="flex items-start gap-3">
                <Activity className="h-6 w-6 text-amber-600 flex-shrink-0" />
                <div>
                  <p className="text-sm font-medium text-amber-800">无法获取分析详情</p>
                  <p className="text-xs text-amber-600 mt-1">
                    {detailQuery.error.message}
                  </p>
                  <Button
                    size="sm"
                    variant="outline"
                    className="mt-3 border-amber-300 text-amber-700 hover:bg-amber-100"
                    onClick={() => detailQuery.refetch()}
                  >
                    <RefreshCw className="h-4 w-4 mr-2" />
                    重新加载
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        ) : null}

        {/* Detail Content */}
        {detailQuery.data ? (
          <>
            {/* Task Overview */}
            <Card 
              data-card-index={0}
              className={`border-0 shadow-lg shadow-slate-100/50 mb-6 overflow-hidden transition-all duration-500 ${animatedCards[0] ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`}
            >
              <CardHeader className="pb-3 bg-gradient-to-r from-blue-50 to-purple-50/30 -mx-4 -mt-4 px-6 py-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg flex items-center justify-center">
                      <Sparkles className="h-4 w-4 text-white" />
                    </div>
                    <CardTitle className="text-base font-semibold text-slate-900">任务概览</CardTitle>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-slate-500 bg-white/60 backdrop-blur-sm px-3 py-1.5 rounded-full">
                    <Clock className="h-3 w-3" />
                    {formatRelativeTime(detailQuery.data.started_at)}
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-4 text-sm pt-4">
                <div className="p-4 bg-gradient-to-r from-blue-500/5 to-purple-500/5 rounded-xl border border-blue-100/50 hover-lift">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="w-6 h-6 rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white text-xs">?</span>
                    <p className="text-slate-800 font-medium">分析问题</p>
                  </div>
                  <p className="text-slate-600 mt-1 pl-8">{detailQuery.data.user_query}</p>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  {[
                    { label: "领域", value: detailQuery.data.domain_hint ?? "未指定", icon: "🌐" },
                    { label: "竞品数量", value: detailQuery.data.competitors.length, icon: "🎯" },
                    { label: "参考链接", value: detailQuery.data.reference_urls.length, icon: "🔗" },
                    { label: "开始时间", value: formatDateTime(detailQuery.data.started_at), icon: "⏰" },
                  ].map((stat, index) => (
                    <div 
                      key={stat.label}
                      className="p-3 bg-gradient-to-br from-white to-slate-50/50 rounded-xl border border-slate-100 hover-lift group"
                      style={{ transitionDelay: `${index * 50}ms` }}
                    >
                      <p className="text-xs text-slate-500 mb-1">{stat.label}</p>
                      <p className="text-sm font-semibold text-slate-900 group-hover:text-blue-600 transition-colors">{stat.value}</p>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* Progress Stages */}
            <Card 
              data-card-index={1}
              className={`border-0 shadow-lg shadow-slate-100/50 mb-6 overflow-hidden transition-all duration-500 ${animatedCards[1] ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`}
            >
              <CardHeader className="pb-3 bg-gradient-to-r from-cyan-50 to-blue-50/30 -mx-4 -mt-4 px-6 py-4">
                <CardTitle className="text-base font-semibold text-slate-900">业务进度</CardTitle>
              </CardHeader>
              <CardContent className="pt-4">
                <div className="flex items-center gap-2">
                  {progressStages.map((stage, index) => (
                    <div key={stage.key} className="flex-1">
                      <div className={cn(
                        "relative rounded-xl border px-4 py-4 text-center transition-all duration-300",
                        stage.state === "done" && "border-emerald-500/50 bg-gradient-to-br from-emerald-500/10 to-emerald-500/5 shadow-sm",
                        stage.state === "active" && "border-blue-500/50 bg-gradient-to-br from-blue-500/15 to-blue-500/5 shadow-lg shadow-blue-500/20",
                        stage.state === "pending" && "border-slate-200 bg-gradient-to-br from-slate-50 to-white",
                      )}>
                        {/* Animated ring */}
                        <div className={cn(
                          "absolute inset-0 rounded-xl opacity-0 transition-opacity",
                          stage.state === "active" && "opacity-100",
                        )}>
                          <div className="absolute inset-0 rounded-xl border-2 border-blue-400/30 animate-ping" />
                        </div>
                        
                        <div className="relative flex flex-col items-center gap-2">
                          <div className={cn(
                            "w-10 h-10 rounded-full flex items-center justify-center transition-all duration-300",
                            stage.state === "done" && "bg-gradient-to-br from-emerald-500 to-emerald-600 shadow-lg shadow-emerald-500/30",
                            stage.state === "active" && "bg-gradient-to-br from-blue-500 to-blue-600 shadow-lg shadow-blue-500/30",
                            stage.state === "pending" && "bg-slate-100",
                          )}>
                            {stage.state === "done" && <CheckCircle2 className="h-5 w-5 text-white" />}
                            {stage.state === "active" && <Activity className="h-5 w-5 text-white animate-pulse" />}
                            {stage.state === "pending" && (
                              <div className="w-4 h-4 rounded-full border-2 border-slate-300 border-t-slate-500" />
                            )}
                          </div>
                          <span className={cn(
                            "text-sm font-medium",
                            stage.state === "done" && "text-emerald-700",
                            stage.state === "active" && "text-blue-700",
                            stage.state === "pending" && "text-slate-500",
                          )}>
                            {stage.label}
                          </span>
                        </div>
                      </div>
                      {index < progressStages.length - 1 && (
                        <div className="relative h-8 flex items-center justify-center">
                          <div className={cn(
                            "h-1 w-8 rounded-full transition-all duration-500",
                            stage.state === "done" && "bg-gradient-to-r from-emerald-400 to-emerald-500",
                            stage.state === "active" && "bg-gradient-to-r from-blue-300 to-blue-400",
                            stage.state === "pending" && "bg-slate-200",
                          )} />
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* Metrics Panel */}
            <MetricsPanel isRunActive={isRunActive} runId={runId} />

            {/* Navigation Links */}
            <Card 
              className="border-0 shadow-lg shadow-slate-100/50 mb-6 overflow-hidden"
            >
              <CardHeader className="pb-3 bg-gradient-to-r from-violet-50 to-purple-50/30 -mx-4 -mt-4 px-6 py-4">
                <CardTitle className="text-base font-semibold text-slate-900">分析工具</CardTitle>
              </CardHeader>
              <CardContent className="pt-4">
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                  <Link
                    to={`/runs/${runId}/schema`}
                    className="flex flex-col items-center p-4 bg-gradient-to-br from-white to-slate-50/50 rounded-xl border border-slate-100 hover:border-blue-300 hover:shadow-lg hover:shadow-blue-100/50 transition-all hover-lift group"
                  >
                    <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center mb-3 group-hover:scale-110 transition-transform">
                      <Users className="h-5 w-5 text-white" />
                    </div>
                    <span className="text-sm font-medium text-slate-700 group-hover:text-blue-600 transition-colors">知识 Schema</span>
                  </Link>
                  <Link
                    to={`/runs/${runId}/agents`}
                    className="flex flex-col items-center p-4 bg-gradient-to-br from-white to-slate-50/50 rounded-xl border border-slate-100 hover:border-green-300 hover:shadow-lg hover:shadow-green-100/50 transition-all hover-lift group"
                  >
                    <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-green-500 to-emerald-600 flex items-center justify-center mb-3 group-hover:scale-110 transition-transform">
                      <Users className="h-5 w-5 text-white" />
                    </div>
                    <span className="text-sm font-medium text-slate-700 group-hover:text-green-600 transition-colors">Agent 角色</span>
                  </Link>
                  <Link
                    to={`/runs/${runId}/compare`}
                    className="flex flex-col items-center p-4 bg-gradient-to-br from-white to-slate-50/50 rounded-xl border border-slate-100 hover:border-orange-300 hover:shadow-lg hover:shadow-orange-100/50 transition-all hover-lift group"
                  >
                    <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-orange-500 to-amber-600 flex items-center justify-center mb-3 group-hover:scale-110 transition-transform">
                      <Users className="h-5 w-5 text-white" />
                    </div>
                    <span className="text-sm font-medium text-slate-700 group-hover:text-orange-600 transition-colors">竞品对比</span>
                  </Link>
                  <Link
                    to={`/runs/${runId}/evidence`}
                    className="flex flex-col items-center p-4 bg-gradient-to-br from-white to-slate-50/50 rounded-xl border border-slate-100 hover:border-cyan-300 hover:shadow-lg hover:shadow-cyan-100/50 transition-all hover-lift group"
                  >
                    <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center mb-3 group-hover:scale-110 transition-transform">
                      <FileText className="h-5 w-5 text-white" />
                    </div>
                    <span className="text-sm font-medium text-slate-700 group-hover:text-cyan-600 transition-colors">证据管理</span>
                  </Link>
                  <Link
                    to={`/runs/${runId}/survey`}
                    className="flex flex-col items-center p-4 bg-gradient-to-br from-white to-slate-50/50 rounded-xl border border-slate-100 hover:border-purple-300 hover:shadow-lg hover:shadow-purple-100/50 transition-all hover-lift group"
                  >
                    <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-purple-500 to-pink-600 flex items-center justify-center mb-3 group-hover:scale-110 transition-transform">
                      <Users className="h-5 w-5 text-white" />
                    </div>
                    <span className="text-sm font-medium text-slate-700 group-hover:text-purple-600 transition-colors">用户研究</span>
                  </Link>
                  <Link
                    to={`/runs/${runId}/export`}
                    className="flex flex-col items-center p-4 bg-gradient-to-br from-white to-slate-50/50 rounded-xl border border-slate-100 hover:border-rose-300 hover:shadow-lg hover:shadow-rose-100/50 transition-all hover-lift group"
                  >
                    <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-rose-500 to-red-600 flex items-center justify-center mb-3 group-hover:scale-110 transition-transform">
                      <FileText className="h-5 w-5 text-white" />
                    </div>
                    <span className="text-sm font-medium text-slate-700 group-hover:text-rose-600 transition-colors">导出分享</span>
                  </Link>
                </div>
              </CardContent>
            </Card>

            {/* Stage Replay */}
            {isReportReady ? (
              <Card 
                data-card-index={2}
                className={`border-0 shadow-lg shadow-slate-100/50 mb-6 overflow-hidden transition-all duration-500 ${animatedCards[2] ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`}
              >
                <CardHeader className="pb-3 bg-gradient-to-r from-green-50 to-cyan-50/30 -mx-4 -mt-4 px-6 py-4">
                  <CardTitle className="text-base font-semibold text-slate-900">阶段重放</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4 pt-4">
                  <div className="p-4 bg-gradient-to-r from-green-500/5 to-cyan-500/5 rounded-xl border border-green-100/50">
                    <p className="text-sm text-slate-600">
                      当结果不满意时，可从指定阶段回放。重放会清理该阶段及后续轨迹，然后从 checkpoint 继续执行。
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-3">
                    <Button
                      disabled={isResetPending}
                      onClick={() => {
                        void handleResetRun("writer");
                      }}
                      type="button"
                      className="group relative overflow-hidden bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-700 hover:to-purple-700 text-white px-6 py-2.5"
                    >
                      <span className="relative z-10 flex items-center">
                        <RefreshCw className="h-4 w-4 mr-2" />
                        重写报告（writer）
                      </span>
                      <div className="absolute inset-0 bg-gradient-to-r from-indigo-400 to-purple-500 opacity-0 group-hover:opacity-100 transition-opacity" />
                    </Button>
                    <Button
                      disabled={isResetPending}
                      onClick={() => {
                        void handleResetRun("analyst");
                      }}
                      type="button"
                      className="group relative overflow-hidden bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-700 hover:to-blue-700 text-white px-6 py-2.5"
                    >
                      <span className="relative z-10 flex items-center">
                        <RefreshCw className="h-4 w-4 mr-2" />
                        重做分析（analyst）
                      </span>
                      <div className="absolute inset-0 bg-gradient-to-r from-cyan-400 to-blue-500 opacity-0 group-hover:opacity-100 transition-opacity" />
                    </Button>
                  </div>
                  {resetRunMutation.isError ? (
                    <div className="p-4 bg-red-50/80 border border-red-200 rounded-xl">
                      <p className="text-sm text-red-700">阶段重放失败：{resetRunMutation.error.message}</p>
                    </div>
                  ) : null}
                </CardContent>
              </Card>
            ) : null}

            {/* Competitor Progress */}
            <Card 
              data-card-index={3}
              className={`border-0 shadow-lg shadow-slate-100/50 mb-6 overflow-hidden transition-all duration-500 ${animatedCards[3] ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`}
            >
              <CardHeader className="pb-3 bg-gradient-to-r from-purple-50 to-pink-50/30 -mx-4 -mt-4 px-6 py-4">
                <CardTitle className="text-base font-semibold text-slate-900">竞品进度</CardTitle>
              </CardHeader>
              <CardContent className="pt-4">
                <div className="grid gap-4 sm:grid-cols-2">
                  {detailQuery.data.competitors.map((competitorId, index) => {
                    const item = competitorProgress.get(competitorId) ?? { done: false, evidenceCount: 0 };
                    return (
                      <div 
                        key={competitorId} 
                        className={cn(
                          "relative rounded-xl border p-5 transition-all duration-300 hover-lift",
                          item.done ? "border-emerald-200 bg-gradient-to-br from-emerald-50/80 to-white" : "border-slate-200 bg-gradient-to-br from-slate-50/80 to-white",
                        )}
                        style={{ transitionDelay: `${index * 100}ms` }}
                      >
                        {/* Decorative corner */}
                        <div className={cn(
                          "absolute top-0 right-0 w-16 h-16 rounded-bl-full transition-opacity",
                          item.done ? "bg-gradient-to-br from-emerald-400/20 to-transparent" : "bg-gradient-to-br from-amber-400/10 to-transparent",
                        )} />
                        
                        <div className="relative">
                          <div className="flex items-center justify-between mb-3">
                            <p className="font-semibold text-slate-900">{competitorId}</p>
                            {item.done ? (
                              <span className="flex items-center gap-1 text-xs text-emerald-600 bg-emerald-100 px-3 py-1 rounded-full">
                                <CheckCircle2 className="h-3 w-3" />
                                已完成
                              </span>
                            ) : (
                              <span className="flex items-center gap-1 text-xs text-amber-600 bg-amber-100 px-3 py-1 rounded-full">
                                <Activity className="h-3 w-3 animate-pulse" />
                                调研中
                              </span>
                            )}
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-2xl font-bold gradient-text">{item.evidenceCount}</span>
                            <span className="text-sm text-slate-500">条证据</span>
                          </div>
                          <Link
                            className="mt-4 inline-flex items-center gap-1.5 text-sm text-blue-600 hover:text-blue-700 transition-all group"
                            to={`/runs/${runId}/evidence?competitor_id=${encodeURIComponent(competitorId)}`}
                          >
                            <FileText className="h-4 w-4" />
                            查看证据
                            <ChevronRight className="h-4 w-4 group-hover:translate-x-1 transition-transform" />
                          </Link>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>

            {/* Latest Events */}
            <Card 
              data-card-index={4}
              className={`border-0 shadow-lg shadow-slate-100/50 mb-6 overflow-hidden transition-all duration-500 ${animatedCards[4] ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`}
            >
              <CardHeader className="pb-3 bg-gradient-to-r from-orange-50 to-amber-50/30 -mx-4 -mt-4 px-6 py-4">
                <CardTitle className="text-base font-semibold text-slate-900">最新事件</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 pt-4">
                {latestEvents.length > 0 ? (
                  latestEvents.map((event, index) => (
                    <div 
                      key={`${event}-${index}`} 
                      className="group flex items-start gap-3 p-4 bg-gradient-to-r from-slate-50/50 to-white rounded-xl border border-transparent hover:border-slate-100 transition-all hover-lift"
                      style={{ animationDelay: `${index * 80}ms` }}
                    >
                      <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center flex-shrink-0 group-hover:scale-110 transition-transform">
                        <Activity className="h-4 w-4 text-white" />
                      </div>
                      <p className="text-sm text-slate-600 flex-1">{event}</p>
                    </div>
                  ))
                ) : (
                  <div className="text-center py-10">
                    <div className="w-16 h-16 bg-gradient-to-br from-slate-100 to-slate-50 rounded-full flex items-center justify-center mx-auto mb-4">
                      <Users className="h-8 w-8 text-slate-300" />
                    </div>
                    <p className="text-sm text-slate-500">暂无事件</p>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Curator Pending */}
            {showCuratorPending ? (
              <Card 
                data-card-index={5}
                className="border-0 shadow-lg shadow-blue-100/30 bg-gradient-to-br from-blue-50/80 to-indigo-50/50 mb-6 overflow-hidden"
              >
                <CardHeader className="pb-3 -mx-4 -mt-4 px-6 py-4">
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-lg flex items-center justify-center">
                      <Sparkles className="h-4 w-4 text-white animate-pulse" />
                    </div>
                    <CardTitle className="text-base font-semibold text-blue-800">Skill Curator 沉淀中...</CardTitle>
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="p-3 bg-blue-50/60 rounded-xl">
                    <p className="text-sm text-blue-700">
                      主流程已完成，候选规则正在后台生成并写入 Skill Staging Console。
                    </p>
                  </div>
                  <Link 
                    className="inline-flex items-center gap-2 text-blue-600 hover:text-blue-700 font-medium group" 
                    to="/skills/staging"
                  >
                    前往 Skill Staging Console
                    <ChevronRight className="h-4 w-4 group-hover:translate-x-1 transition-transform" />
                  </Link>
                </CardContent>
              </Card>
            ) : null}
          </>
        ) : null}

        {/* Report */}
        {isReportReady ? (
          <Card 
            data-card-index={5}
            className={`border-0 shadow-lg shadow-slate-100/50 mb-6 overflow-hidden transition-all duration-500 ${animatedCards[5] ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"}`}
          >
            <CardHeader className="pb-3 bg-gradient-to-r from-indigo-50 to-violet-50/30 -mx-4 -mt-4 px-6 py-4">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 bg-gradient-to-br from-indigo-500 to-violet-600 rounded-lg flex items-center justify-center">
                  <FileText className="h-4 w-4 text-white" />
                </div>
                <CardTitle className="text-base font-semibold text-slate-900">Battlecard 报告</CardTitle>
              </div>
            </CardHeader>
            <CardContent className="pt-4">
              {reportQuery.isLoading ? (
                <div className="space-y-4 animate-pulse">
                  <Skeleton className="h-6 w-32 rounded-lg" />
                  <Skeleton className="h-4 w-full rounded-lg" />
                  <Skeleton className="h-4 w-3/4 rounded-lg" />
                  <Skeleton className="h-4 w-5/6 rounded-lg" />
                  <Skeleton className="h-6 w-24 rounded-lg mt-4" />
                  <Skeleton className="h-4 w-full rounded-lg" />
                  <Skeleton className="h-4 w-2/3 rounded-lg" />
                </div>
              ) : null}
              {reportQuery.isError ? (
                <div className="p-6 bg-red-50/80 border border-red-200 rounded-xl">
                  <p className="text-sm text-red-700">报告读取失败：{reportQuery.error.message}</p>
                  <Button
                    size="sm"
                    variant="outline"
                    className="mt-3 border-red-300 text-red-700 hover:bg-red-100"
                    onClick={() => reportQuery.refetch()}
                  >
                    <RefreshCw className="h-4 w-4 mr-2" />
                    重新加载
                  </Button>
                </div>
              ) : null}
              {!reportQuery.isLoading && !reportQuery.isError ? (
                <article className="prose prose-slate max-w-none text-sm leading-relaxed">
                  <ReactMarkdown
                    components={{
                      h1: ({ children }) => <h1 className="text-xl font-bold text-slate-900 mb-4 mt-6">{children}</h1>,
                      h2: ({ children }) => <h2 className="text-lg font-semibold text-slate-800 mb-3 mt-5">{children}</h2>,
                      h3: ({ children }) => <h3 className="text-base font-semibold text-slate-700 mb-2 mt-4">{children}</h3>,
                      p: ({ children }) => <p className="text-slate-600 mb-3">{children}</p>,
                      ul: ({ children }) => <ul className="list-disc list-inside mb-3 text-slate-600">{children}</ul>,
                      ol: ({ children }) => <ol className="list-decimal list-inside mb-3 text-slate-600">{children}</ol>,
                      li: ({ children }) => <li className="mb-1">{children}</li>,
                      a: ({ href, children }) => {
                        if (href?.startsWith("evidence://")) {
                          const evidenceId = href.replace("evidence://", "");
                          return (
                            <button
                              className="cursor-pointer rounded bg-gradient-to-r from-blue-500/20 to-purple-500/20 px-2 py-0.5 text-xs text-blue-700 hover:from-blue-500/30 hover:to-purple-500/30 transition-all"
                              onClick={() => openEvidenceDrawer([evidenceId])}
                              type="button"
                            >
                              {children}
                            </button>
                          );
                        }
                        return (
                          <a href={href} rel="noreferrer" target="_blank" className="text-blue-600 hover:text-blue-700 hover:underline">
                            {children}
                          </a>
                        );
                      },
                      table: ({ children }) => (
                        <div className="overflow-x-auto mb-4">
                          <table className="w-full border-collapse">
                            {children}
                          </table>
                        </div>
                      ),
                      th: ({ children }) => (
                        <th className="border border-slate-200 bg-slate-50 px-4 py-2 text-left text-sm font-semibold text-slate-700">
                          {children}
                        </th>
                      ),
                      td: ({ children }) => (
                        <td className="border border-slate-200 px-4 py-2 text-sm text-slate-600">
                          {children}
                        </td>
                      ),
                      code: ({ className, children }) => {
                        const isBlock = className?.includes("language-");
                        if (isBlock) {
                          return (
                            <pre className="bg-slate-900 text-slate-100 p-4 rounded-xl overflow-x-auto text-sm">
                              <code>{children}</code>
                            </pre>
                          );
                        }
                        return (
                          <code className="bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded text-xs font-mono">
                            {children}
                          </code>
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

        {/* Evidence Drawer */}
        <EvidenceDrawer
          evidenceIds={activeEvidenceIds}
          onOpenChange={setIsEvidenceDrawerOpen}
          open={isEvidenceDrawerOpen}
          runId={runId}
        />
      </main>

      {/* Footer */}
      <footer className="py-8 px-4 bg-white/80 backdrop-blur-sm border-t border-slate-100/50 mt-auto relative z-10">
        <div className="max-w-5xl mx-auto text-center">
          <div className="flex items-center justify-center gap-2 mb-3">
            <div className="w-6 h-6 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg flex items-center justify-center">
              <Sparkles className="h-3 w-3 text-white" />
            </div>
            <span className="font-semibold text-slate-900 gradient-text">RivalLens</span>
          </div>
          <p className="text-sm text-slate-500">
            AI 驱动的竞品分析平台
          </p>
        </div>
      </footer>
    </div>
  );
}
