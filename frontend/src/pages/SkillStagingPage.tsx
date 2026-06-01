import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, XCircle, Filter, AlertCircle, Sparkles, Zap, Eye } from "lucide-react";

import { useApproveCandidate, useRejectCandidate, useSkillCandidates } from "@/api/hooks";
import type { PromotedArtifactResponse } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDateTime } from "@/lib/format";

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
      speedX: (Math.random() - 0.5) * 0.15,
      speedY: (Math.random() - 0.5) * 0.15,
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
          className="absolute rounded-full bg-gradient-to-br from-blue-500/40 to-purple-500/40 animate-breathe"
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

export function SkillStagingPage(): JSX.Element {
  const [isVisible, setIsVisible] = useState(false);
  const [statusFilter, setStatusFilter] = useState("staging");
  const [appliesToFilter, setAppliesToFilter] = useState("");
  const [tagFilter, setTagFilter] = useState("");
  const [reviewedBy, setReviewedBy] = useState("owner_wh");
  const [pendingCandidateId, setPendingCandidateId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [promotionHints, setPromotionHints] = useState<PromotedArtifactResponse[]>([]);

  const candidatesQuery = useSkillCandidates({
    status: statusFilter === "all" ? undefined : statusFilter,
    applies_to: appliesToFilter.trim() || undefined,
    tag: tagFilter.trim() || undefined,
    limit: 50,
    offset: 0,
  });
  const approveMutation = useApproveCandidate();
  const rejectMutation = useRejectCandidate();

  useEffect(() => {
    setIsVisible(true);
  }, []);

  const stats = {
    total: candidatesQuery.data?.items.length || 0,
    staging: candidatesQuery.data?.items.filter((c) => c.status === "staging").length || 0,
    approved: candidatesQuery.data?.items.filter((c) => c.status === "approved").length || 0,
    rejected: candidatesQuery.data?.items.filter((c) => c.status === "rejected").length || 0,
  };

  async function reviewCandidate(
    candidateId: string,
    action: "approve" | "reject",
  ): Promise<void> {
    const reviewer = reviewedBy.trim();
    if (!reviewer) {
      setActionError("reviewed_by 不能为空。");
      return;
    }

    setPendingCandidateId(candidateId);
    try {
      if (action === "approve") {
        const result = await approveMutation.mutateAsync({ candidateId, reviewedBy: reviewer });
        setPromotionHints(result.promoted_artifacts);
      } else {
        await rejectMutation.mutateAsync({ candidateId, reviewedBy: reviewer });
        setPromotionHints([]);
      }
      setActionError(null);
      await candidatesQuery.refetch();
    } catch (error) {
      if (error instanceof Error) {
        setActionError(error.message);
      } else {
        setActionError("审核操作失败，请稍后重试。");
      }
    } finally {
      setPendingCandidateId(null);
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-blue-50 relative">
      <ParticleBackground />
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(99,102,241,0.05),transparent_70%)]" />

      {/* Header */}
      <header
        className={`sticky top-0 z-50 bg-white/80 backdrop-blur-lg border-b border-slate-100/50 transition-all duration-500 ${
          isVisible ? "opacity-100 translate-y-0" : "opacity-0 -translate-y-4"
        }`}
      >
        <div className="max-w-6xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <Link to="/" className="flex items-center gap-2 group">
              <div className="relative">
                <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg flex items-center justify-center transition-transform group-hover:scale-110 group-hover:rotate-12">
                  <Sparkles className="h-4 w-4 text-white" />
                </div>
                <div className="absolute inset-0 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg blur-md opacity-50 group-hover:opacity-75" />
              </div>
              <span className="font-semibold text-slate-900">RivalLens</span>
            </Link>

            <nav className="flex items-center gap-1">
              <Link
                to="/"
                className="px-4 py-2 rounded-lg text-sm font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition-all"
              >
                首页
              </Link>
              <Link
                to="/features"
                className="px-4 py-2 rounded-lg text-sm font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition-all"
              >
                功能介绍
              </Link>
              <Link
                to="/runs"
                className="px-4 py-2 rounded-lg text-sm font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition-all"
              >
                任务列表
              </Link>
              <Link
                to="/dashboard"
                className="px-4 py-2 rounded-lg text-sm font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition-all"
              >
                监控仪表盘
              </Link>
              <Link
                to="/feedback"
                className="px-4 py-2 rounded-lg text-sm font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition-all"
              >
                反馈闭环
              </Link>
              <Link
                to="/skills/staging"
                className="px-4 py-2 rounded-lg text-sm font-medium bg-gradient-to-r from-blue-500/20 to-purple-500/20 text-blue-600 relative"
              >
                Skill 审核台
                <span className="absolute inset-0 bg-gradient-to-r from-blue-500/30 to-purple-500/30 rounded-lg animate-pulse-glow" />
              </Link>
            </nav>

            <div className="flex items-center gap-2">
              <Button
                size="sm"
                onClick={() => window.location.reload()}
                className="group relative overflow-hidden bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 text-white"
              >
                <span className="relative z-10 flex items-center">
                  <Zap className="h-4 w-4 mr-1" />
                  刷新列表
                </span>
                <div className="absolute inset-0 bg-gradient-to-r from-blue-400 to-purple-500 opacity-0 group-hover:opacity-100 transition-opacity" />
              </Button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-6xl mx-auto px-4 py-8 relative z-10">
        {/* Page Header */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center">
              <Filter className="h-6 w-6 text-white" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-slate-900">Skill 审核台</h1>
              <p className="text-slate-500 text-sm">查看 Curator 生成的候选项，进行通过/拒绝审核。</p>
            </div>
          </div>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-4 gap-4 mb-6">
          <Card className="bg-white/80 backdrop-blur-sm border-slate-100 hover:shadow-lg transition-all duration-300 hover:-translate-y-1">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-slate-400 text-sm">总候选项</p>
                  <p className="text-2xl font-bold text-slate-900 mt-1">{stats.total}</p>
                </div>
                <div className="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center">
                  <Filter className="h-5 w-5 text-blue-500" />
                </div>
              </div>
            </CardContent>
          </Card>
          <Card className="bg-white/80 backdrop-blur-sm border-slate-100 hover:shadow-lg transition-all duration-300 hover:-translate-y-1">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-slate-400 text-sm">待审核</p>
                  <p className="text-2xl font-bold text-blue-600 mt-1">{stats.staging}</p>
                </div>
                <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center">
                  <Eye className="h-5 w-5 text-blue-500" />
                </div>
              </div>
            </CardContent>
          </Card>
          <Card className="bg-white/80 backdrop-blur-sm border-slate-100 hover:shadow-lg transition-all duration-300 hover:-translate-y-1">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-slate-400 text-sm">已通过</p>
                  <p className="text-2xl font-bold text-green-600 mt-1">{stats.approved}</p>
                </div>
                <div className="w-10 h-10 rounded-lg bg-green-100 flex items-center justify-center">
                  <CheckCircle2 className="h-5 w-5 text-green-500" />
                </div>
              </div>
            </CardContent>
          </Card>
          <Card className="bg-white/80 backdrop-blur-sm border-slate-100 hover:shadow-lg transition-all duration-300 hover:-translate-y-1">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-slate-400 text-sm">已拒绝</p>
                  <p className="text-2xl font-bold text-red-600 mt-1">{stats.rejected}</p>
                </div>
                <div className="w-10 h-10 rounded-lg bg-red-100 flex items-center justify-center">
                  <XCircle className="h-5 w-5 text-red-500" />
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Filter Card */}
        <Card className="bg-white/80 backdrop-blur-sm border-slate-100 shadow-lg shadow-slate-100/50 mb-6 hover:shadow-xl transition-all">
          <CardContent className="grid gap-4 pt-6 md:grid-cols-4">
            <div className="space-y-2">
              <label className="text-sm font-medium text-slate-700">状态筛选</label>
              <select
                className="h-11 w-full rounded-xl border border-slate-200 bg-white px-4 text-slate-800 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition-all"
                onChange={(event) => setStatusFilter(event.target.value)}
                value={statusFilter}
              >
                <option value="all">全部</option>
                <option value="staging">待审核</option>
                <option value="approved">已通过</option>
                <option value="rejected">已拒绝</option>
              </select>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-slate-700">applies_to</label>
              <Input
                onChange={(event) => setAppliesToFilter(event.target.value)}
                placeholder="qa_rule / prompt_template / source_routing"
                value={appliesToFilter}
                className="h-11 rounded-xl border-slate-200 focus:border-blue-500"
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-slate-700">tag</label>
              <Input
                onChange={(event) => setTagFilter(event.target.value)}
                placeholder="generic"
                value={tagFilter}
                className="h-11 rounded-xl border-slate-200 focus:border-blue-500"
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-slate-700">reviewed_by</label>
              <Input
                onChange={(event) => setReviewedBy(event.target.value)}
                placeholder="owner_wh"
                value={reviewedBy}
                className="h-11 rounded-xl border-slate-200 focus:border-blue-500"
              />
            </div>
          </CardContent>
        </Card>

        {/* Action Error */}
        {actionError ? (
          <Card className="bg-red-50/80 backdrop-blur-sm border-red-200 mb-6 animate-slide-in">
            <CardContent className="p-4">
              <div className="flex items-start gap-3">
                <AlertCircle className="h-5 w-5 text-red-500 flex-shrink-0 mt-0.5" />
                <p className="text-sm text-red-700">{actionError}</p>
              </div>
            </CardContent>
          </Card>
        ) : null}

        {/* Promotion Hints */}
        {promotionHints.length > 0 ? (
          <Card className="bg-green-50/80 backdrop-blur-sm border-green-200 mb-6 animate-slide-in">
            <CardHeader className="pb-2 bg-green-50/50">
              <CardTitle className="text-base text-green-800 flex items-center gap-2">
                <CheckCircle2 className="h-5 w-5" />
                已写回 backend/skills
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <p className="text-green-700">
                以下文件已更新，请手动执行 git commit 以完成版本入库：
              </p>
              {promotionHints.map((item) => (
                <div
                  className="rounded-xl border border-green-200 bg-white/80 px-4 py-3 font-mono text-xs hover:shadow-md transition-all"
                  key={`${item.path}-${item.entry_id}`}
                >
                  <p className="text-green-800">{item.path}</p>
                  <p className="text-green-600 mt-1">
                    action={item.action} · entry_id={item.entry_id}
                  </p>
                </div>
              ))}
            </CardContent>
          </Card>
        ) : null}

        {/* Loading State */}
        {candidatesQuery.isLoading ? (
          <div className="space-y-4">
            {Array.from({ length: 2 }).map((_, i) => (
              <Card key={i} className="bg-white/50 border-slate-100">
                <CardContent className="p-6">
                  <Skeleton className="h-6 w-1/3 mb-4 rounded" />
                  <Skeleton className="h-48 w-full rounded-xl" />
                </CardContent>
              </Card>
            ))}
          </div>
        ) : null}

        {/* Error State */}
        {candidatesQuery.isError ? (
          <Card className="bg-amber-50/80 backdrop-blur-sm border-amber-200">
            <CardContent className="p-6">
              <div className="flex items-start gap-3">
                <AlertCircle className="h-6 w-6 text-amber-600 flex-shrink-0" />
                <div>
                  <p className="text-sm font-medium text-amber-800">无法获取候选项</p>
                  <p className="text-xs text-amber-600 mt-1">
                    {candidatesQuery.error.message}
                  </p>
                  <Button
                    size="sm"
                    variant="outline"
                    className="mt-3 border-amber-300 text-amber-700 hover:bg-amber-100"
                    onClick={() => candidatesQuery.refetch()}
                  >
                    重新加载
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        ) : null}

        {/* Empty State */}
        {!candidatesQuery.isLoading && !candidatesQuery.isError && candidatesQuery.data?.items.length === 0 ? (
          <Card className="bg-slate-50/50 border-slate-100">
            <CardContent className="pt-16 pb-16 text-center">
              <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-gradient-to-br from-blue-100 to-purple-100 flex items-center justify-center">
                <Filter className="h-8 w-8 text-slate-400" />
              </div>
              <h3 className="text-lg font-semibold text-slate-900 mb-2">暂无候选项</h3>
              <p className="text-slate-500 text-sm">当前筛选条件下没有找到候选 Skill 项。</p>
            </CardContent>
          </Card>
        ) : null}

        {/* Candidates List */}
        {!candidatesQuery.isLoading && !candidatesQuery.isError && candidatesQuery.data && candidatesQuery.data.items.length > 0 ? (
          <div className="space-y-4">
            {candidatesQuery.data?.items.map((candidate, index) => {
              const isPending = pendingCandidateId === candidate.id;
              return (
                <Card
                  key={candidate.id}
                  className={`bg-white/80 backdrop-blur-sm border-slate-100 shadow-md hover:shadow-xl transition-all duration-300 hover:-translate-y-1 animate-slide-up ${
                    isPending ? "ring-2 ring-blue-500" : ""
                  }`}
                  style={{ animationDelay: `${index * 100}ms` }}
                >
                  <CardHeader className="pb-3">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <CardTitle className="font-mono text-base text-slate-900 flex items-center gap-2">
                        <Sparkles className="h-4 w-4 text-blue-500" />
                        {candidate.id}
                      </CardTitle>
                      <div className="flex items-center gap-2">
                        <Badge variant="outline" className="border-slate-300 text-slate-700 hover:bg-slate-50">
                          {candidate.candidate_type}
                        </Badge>
                        <Badge variant="secondary" className="bg-slate-100 text-slate-700">
                          {candidate.confidence}
                        </Badge>
                        <Badge className={
                          candidate.status === "approved" 
                            ? "bg-green-100 text-green-700" 
                            : candidate.status === "rejected"
                            ? "bg-red-100 text-red-700"
                            : "bg-blue-100 text-blue-700"
                        }>
                          {candidate.status === "approved" ? "已通过" : candidate.status === "rejected" ? "已拒绝" : "待审核"}
                        </Badge>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4 text-sm">
                    <div className="p-4 bg-gradient-to-r from-blue-50 to-purple-50 rounded-xl border border-blue-100">
                      <p className="text-slate-700 font-medium">设计依据</p>
                      <p className="text-slate-600 mt-1">{candidate.rationale}</p>
                    </div>
                    <div className="flex flex-wrap items-center gap-4 text-slate-500">
                      <span className="flex items-center gap-1">
                        <span className="w-2 h-2 rounded-full bg-blue-400" />
                        applies_to: {candidate.applies_to}
                      </span>
                      <span className="flex items-center gap-1">
                        <span className="w-2 h-2 rounded-full bg-purple-400" />
                        创建于: {formatDateTime(candidate.created_at)}
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {candidate.tags.length > 0 ? (
                        candidate.tags.map((tag) => (
                          <Badge key={tag} variant="outline" className="border-slate-200 text-slate-600">
                            {tag}
                          </Badge>
                        ))
                      ) : (
                        <span className="text-slate-400 text-xs">no tags</span>
                      )}
                    </div>
                    {candidate.supporting_run_ids.length > 0 && (
                      <div className="flex flex-wrap gap-2">
                        <span className="text-slate-500 text-xs">关联任务:</span>
                        {candidate.supporting_run_ids.map((runId) => (
                          <Link
                            className="rounded-md border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:border-blue-300 hover:text-blue-700 hover:bg-blue-50 transition-all"
                            key={runId}
                            to={`/runs/${runId}`}
                          >
                            <Eye className="h-3 w-3 inline mr-1" />
                            {runId}
                          </Link>
                        ))}
                      </div>
                    )}
                    <div className="p-4 bg-slate-900/90 rounded-xl overflow-x-auto border border-slate-700">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs text-slate-400">Payload</span>
                        <span className="text-xs text-slate-500">JSON</span>
                      </div>
                      <pre className="text-xs text-slate-300 leading-5">
                        {JSON.stringify(candidate.payload, null, 2)}
                      </pre>
                    </div>
                    {candidate.error ? (
                      <div className="p-3 bg-red-50/80 border border-red-200 rounded-lg">
                        <p className="text-xs text-red-700 font-medium">错误信息</p>
                        <p className="text-xs text-red-600 mt-1">{candidate.error}</p>
                      </div>
                    ) : null}
                    {candidate.status === "staging" ? (
                      <div className="flex items-center gap-3 pt-4 border-t border-slate-100">
                        <Button
                          disabled={isPending}
                          onClick={() => reviewCandidate(candidate.id, "approve")}
                          size="sm"
                          className="group relative overflow-hidden bg-gradient-to-r from-green-600 to-emerald-600 hover:from-green-700 hover:to-emerald-700 text-white"
                        >
                          {isPending ? (
                            <>处理中...</>
                          ) : (
                            <>
                              <CheckCircle2 className="h-4 w-4 mr-2" />
                              通过并生效
                            </>
                          )}
                        </Button>
                        <Button
                          disabled={isPending}
                          onClick={() => reviewCandidate(candidate.id, "reject")}
                          size="sm"
                          variant="outline"
                          className="border-slate-300 text-slate-700 hover:bg-red-50 hover:border-red-300 hover:text-red-700 transition-all"
                        >
                          {isPending ? (
                            <>处理中...</>
                          ) : (
                            <>
                              <XCircle className="h-4 w-4 mr-2" />
                              拒绝
                            </>
                          )}
                        </Button>
                      </div>
                    ) : null}
                  </CardContent>
                </Card>
              );
            })}
          </div>
        ) : null}
      </main>

      {/* Footer */}
      <footer className="py-8 px-4 bg-white/50 backdrop-blur-sm border-t border-slate-100 mt-auto">
        <div className="max-w-6xl mx-auto text-center">
          <p className="text-sm text-slate-500">
            RivalLens - AI 驱动的竞品分析平台
          </p>
        </div>
      </footer>
    </div>
  );
}
